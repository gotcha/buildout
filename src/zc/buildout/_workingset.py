"""Working-set facade: the uv-mode stand-in for pkg_resources' global set.

With ``installer = uv`` the buildout must run without importing
pkg_resources.  The legacy (pip) code paths still use the real
pkg_resources working set, so every public helper here is called only
from uv-mode branches, with one exception: the dist adapters
(:func:`dist_name`, :func:`dist_location`, :func:`is_develop`,
:func:`sort_key`) are mode-agnostic duck-typing helpers used by shared
code such as ``_dists_sig``.

Until the easy_install unit lands, the distributions flowing through
here are still pkg_resources objects in both modes, so the adapters
read their attributes directly; the importlib.metadata fallbacks keep
the same call sites working once the dist model changes.

Two load-bearing contracts:

- ``AmbientWorkingSet.add`` must put the dist's location on
  ``sys.path`` exactly like ``pkg_resources.WorkingSet.add`` does on
  the global working set (whose ``entries`` *is* ``sys.path``): after
  ``easy_install.install`` grafts dists into the ambient set, the
  recipe entry points load and iterate through plain import
  machinery.  The insertion itself is delegated to the dist's own
  ``insert_on`` (duck-typed) so the semantics stay bit-identical while
  dists are pkg_resources-shaped.
- The class must stay truthy like a pkg_resources WorkingSet (which
  defines neither ``__len__`` nor ``__bool__``):
  ``easy_install.Installer.install`` reads ``bool(working_set)`` as
  "this install serves the running buildout".

Bridging: where pkg_resources semantics are load-bearing for exact
transcripts (environment lookups in ``find``, version-conflict
reporting in ``resolve``), the facade delegates to the real
pkg_resources working set *when it is already loaded* — which it is
in uv mode until the easy_install unit removes its import.  The
bridge never imports pkg_resources; once the easy_install unit lands
and pkg_resources is never loaded, the importlib.metadata paths below
take over and the test suites re-verify them.
"""
from __future__ import annotations

import email
import errno
import logging
import operator
import os
import re
import sys
import warnings
import zipfile
from collections.abc import Iterable, Iterator
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, cast

from packaging.markers import InvalidMarker, Marker
from packaging.requirements import Requirement as PackagingRequirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version
from packaging.version import parse as parse_version

from zc.buildout.utils import normalize_name

if TYPE_CHECKING:
    import pkg_resources

    _Dist = pkg_resources.Distribution | metadata.Distribution


# pkg_resources precedence constants.  Defined here so the uv path
# never has to import pkg_resources to name them.
DEVELOP_DIST = -1  # pkg_resources.DEVELOP_DIST
CHECKOUT_DIST = 0  # pkg_resources.CHECKOUT_DIST
SOURCE_DIST = 1  # pkg_resources.SOURCE_DIST
BINARY_DIST = 2  # pkg_resources.BINARY_DIST
EGG_DIST = 3  # pkg_resources.EGG_DIST


def dist_name(dist: pkg_resources.Distribution | metadata.Distribution) -> str:
    """The project name as the dist's metadata spells it."""
    name = getattr(dist, 'project_name', None)
    if name is not None:
        return name
    return dist.metadata['Name']


def dist_key(dist: pkg_resources.Distribution | metadata.Distribution) -> str:
    """The pkg_resources key: the project name lowercased (not canonicalized)."""
    key = getattr(dist, 'key', None)
    if key is not None:
        return key
    return dist.metadata['Name'].lower()


def dist_version(dist: pkg_resources.Distribution | metadata.Distribution) -> str:
    return dist.version


def dist_location(
        dist: pkg_resources.Distribution | metadata.Distribution) -> str:
    """Where the dist lives: the egg directory or the site directory."""
    location = getattr(dist, 'location', None)
    if location is not None:
        return location
    return str(dist.locate_file(''))


def is_develop(
        dist: pkg_resources.Distribution | metadata.Distribution) -> bool:
    """Whether the dist counts as a develop dist for signatures.

    pkg_resources marks a dist DEVELOP_DIST when its metadata sits
    directly on a path entry — a checkout's ``foo.egg-info``, but also
    any installed ``site-packages/foo.dist-info``; only metadata
    nested inside a ``.egg`` bundle gets EGG_DIST.  The importlib
    fallback mirrors exactly that, since ``_dists_sig`` output must
    stay byte-identical to the pkg_resources-based signatures already
    persisted in users' ``.installed.cfg`` files.
    """
    precedence = getattr(dist, 'precedence', None)
    if precedence is not None:
        return precedence == DEVELOP_DIST
    return not dist_location(dist).endswith('.egg')


def _precedence(
        dist: pkg_resources.Distribution | metadata.Distribution) -> int:
    precedence = getattr(dist, 'precedence', None)
    if precedence is not None:
        return precedence
    return DEVELOP_DIST if is_develop(dist) else EGG_DIST


def _parsed_version(dist: pkg_resources.Distribution | metadata.Distribution):
    parsed = getattr(dist, 'parsed_version', None)
    if parsed is not None:
        return parsed
    return parse_version(dist.version)


def sort_key(
        dist: pkg_resources.Distribution | metadata.Distribution,
        ) -> tuple:
    """pkg_resources' ``Distribution.hashcmp``, duck-typed.

    ``_dists_sig`` sorts with this key so its output stays
    byte-identical to the pkg_resources-based implementation: the
    signatures persist in ``.installed.cfg`` and a silent reorder
    would reinstall every part on the first run after upgrade.
    """
    return (
        _parsed_version(dist),
        _precedence(dist),
        dist_key(dist),
        dist_location(dist),
        getattr(dist, 'py_version', None) or '',
        getattr(dist, 'platform', None) or '',
    )


def _is_pkg_requirement(req) -> bool:
    """Whether ``req`` is a pkg_resources Requirement.

    pkg_resources' Requirement carries ``key`` (and ``project_name``);
    packaging's does not.  Attribute detection, not isinstance: since
    setuptools 75 pkg_resources.Requirement *subclasses*
    packaging.Requirement, so isinstance cannot tell them apart.  The
    facade's own Requirement reproduces ``key``, so it is excluded by
    class: bridging facade requirements into the pkg working set would
    hand pkg-shaped dists to a containment check that only accepts
    facade dists, raising VersionConflict on a matching install.
    """
    return hasattr(req, 'key') and not isinstance(req, Requirement)


def _req_key(req: pkg_resources.Requirement | PackagingRequirement) -> str:
    key = getattr(req, 'key', None)
    if key is not None:
        return key
    return req.name.lower()


def _req_name(req: pkg_resources.Requirement | PackagingRequirement) -> str:
    return getattr(req, 'project_name', None) or req.name


def _req_contains(
        req: pkg_resources.Requirement | PackagingRequirement,
        version: str,
        ) -> bool:
    """Whether ``version`` satisfies ``req``, prereleases included.

    Mirrors ``pkg_resources.Requirement.__contains__`` with a version
    string, which always allows prereleases.
    """
    if _is_pkg_requirement(req):
        pkg_req = cast('pkg_resources.Requirement', req)
        return version in pkg_req
    return req.specifier.contains(version, prereleases=True)


def _as_packaging_req(
        req: pkg_resources.Requirement | PackagingRequirement,
        ) -> PackagingRequirement:
    if _is_pkg_requirement(req):
        # str() of a pkg_resources requirement is the PEP 508 spelling.
        return PackagingRequirement(str(req))
    return req


def _version_conflict(dist, req):
    """The VersionConflict for ``dist`` not matching ``req``.

    The facade's own dists always raise the facade class, so uv-mode
    code can catch it whether or not pkg_resources happens to be
    loaded (the pytest process has it; production uv runs do not).
    Foreign dists still raise through the bridge while pkg_resources
    is loaded; without it the facade's own VersionConflict carries the
    same ``(dist, req)`` args ``errors.VersionConflict`` formats.
    """
    if isinstance(dist, Distribution):
        return VersionConflict(dist, req)
    pkg_resources = sys.modules.get('pkg_resources')
    if pkg_resources is not None:
        return pkg_resources.VersionConflict(dist, req)
    return VersionConflict(dist, req)


def not_found_errors() -> tuple[type[BaseException], ...]:
    """The "distribution not found" exception classes to catch.

    uv mode raises importlib.metadata's PackageNotFoundError; pip mode
    still raises pkg_resources' DistributionNotFound from its
    internals.  Bridged, not imported: by the time an uninstall error
    propagates in pip mode, pkg_resources is long since loaded; once
    the easy_install unit removes it from uv mode it is simply absent
    from the tuple.
    """
    errors: list[type[BaseException]] = [metadata.PackageNotFoundError]
    pkg_resources = sys.modules.get('pkg_resources')
    if pkg_resources is not None:
        errors.append(pkg_resources.DistributionNotFound)
    return tuple(errors)


class AmbientWorkingSet:
    """uv-mode replacement for the global pkg_resources working set.

    Holds the dists grafted by ``easy_install.install`` and mirrors
    the pkg_resources WorkingSet protocol the installer relies on:
    ``add`` (with ``replace``), membership, ``find``, ``by_key`` and
    iteration.  ``entries`` is the real ``sys.path`` list, so ``add``
    puts egg directories on ``sys.path`` exactly like the global
    pkg_resources working set — the side effect that makes recipe
    entry points importable after install.
    """

    def __init__(self, entries: list[str] | None = None) -> None:
        # None gives the ambient set whose entries *is* sys.path, the
        # pkg_resources global-set behavior; an explicit list gives a
        # plain working set like pkg_resources.WorkingSet(entries).
        self.entries = sys.path if entries is None else entries
        self.entry_keys: dict[str, list[str]] = {}
        self.by_key: dict[str, _Dist] = {}

    def add(self, dist, entry: str | None = None, insert: bool = True,
            replace: bool = False) -> None:
        """Register ``dist``; mirror pkg_resources WorkingSet.add.

        The dist's own ``insert_on`` performs the sys.path insertion
        so precedence and replace semantics stay bit-identical while
        dists are pkg_resources-shaped; the dist model's own objects
        must provide an equivalent once the easy_install unit lands.
        """
        if insert:
            dist.insert_on(self.entries, entry, replace=replace)
        if entry is None:
            entry = dist_location(dist)
        keys = self.entry_keys.setdefault(entry, [])
        keys2 = self.entry_keys.setdefault(dist_location(dist), [])
        if not replace and dist_key(dist) in self.by_key:
            # ignore hidden distros
            return
        self.by_key[dist_key(dist)] = dist
        if dist_key(dist) not in keys:
            keys.append(dist_key(dist))
        if dist_key(dist) not in keys2:
            keys2.append(dist_key(dist))
        pkg_resources = sys.modules.get('pkg_resources')
        if (pkg_resources is not None
                and not isinstance(dist, Distribution)
                and hasattr(dist, 'insert_on')):
            # Keep the real working set in the loop while it is
            # loaded: pkg_resources EntryPoint.load() resolves the
            # dist's requirements against the global set, which used
            # to receive these dists directly when easy_install got it
            # passed in.  insert_on is idempotent, so the doubled
            # sys.path handling is a no-op.  The facade's own dist
            # model is excluded: pkg_resources' working set cannot
            # track foreign objects (its add() calls pkg-only methods
            # like activate()).  Once the easy_install unit lands,
            # pkg_resources is never loaded in uv mode and this
            # forwarding simply stops happening.
            pkg_resources.working_set.add(dist, entry, insert, replace)

    def __contains__(self, dist) -> bool:
        """True if ``dist`` is the active distribution for its project."""
        return self.by_key.get(dist_key(dist)) == dist

    def __iter__(self):
        # pkg_resources.WorkingSet.__iter__: entries order, first dist
        # per project key.  insert_on's precedence semantics (eggs
        # ahead of their parent directory, replace front-inserts) make
        # this differ from add order — the easy_install graft relies
        # on replace front-insertion listing a set dependency-first.
        seen: dict[str, bool] = {}
        for item in self.entries:
            if item not in self.entry_keys:
                continue
            for key in self.entry_keys[item]:
                if key not in seen:
                    seen[key] = True
                    yield self.by_key[key]

    def find(
            self,
            req: pkg_resources.Requirement | PackagingRequirement,
            ) -> _Dist | None:
        """The active dist matching ``req``, or None.

        Dists grafted into this set answer first, with pkg_resources
        semantics: a held project at a non-matching version is a
        VersionConflict, not a miss.  While pkg_resources is loaded
        (every uv run until the easy_install unit), the global working
        set answers environment lookups bit-identically to today.
        """
        dist = self.by_key.get(_req_key(req))
        if dist is not None:
            if not _req_contains(req, dist_version(dist)):
                raise _version_conflict(dist, req)
            return dist
        pkg_resources = sys.modules.get('pkg_resources')
        if pkg_resources is not None and _is_pkg_requirement(req):
            return pkg_resources.working_set.find(req)
        return None


_AMBIENT: AmbientWorkingSet | None = None


def ambient() -> AmbientWorkingSet:
    """The process-global ambient working set for uv mode."""
    global _AMBIENT
    if _AMBIENT is None:
        _AMBIENT = AmbientWorkingSet()
    return _AMBIENT


def find_available(
        req: pkg_resources.Requirement | PackagingRequirement,
        ) -> _Dist | None:
    """Whether a dist satisfying ``req`` is reachable without installing.

    Unlike :meth:`AmbientWorkingSet.find`, which serves the
    installer's in-run bookkeeping, this also scans ``sys.path``
    through importlib.metadata; used for "is it already there?"
    pre-checks whose result is only tested for None.
    """
    found = ambient().find(req)
    if found is not None:
        return found
    name = canonicalize_name(_req_name(req))
    for dist in metadata.distributions():
        dist_name_ = dist.metadata['Name']
        if dist_name_ is None:
            continue
        if canonicalize_name(dist_name_) != name:
            continue
        if _req_contains(req, dist.version):
            return dist
    return None


def find_on_sys_path(req: Requirement) -> Distribution | None:
    """The first dist on ``sys.path`` matching ``req``.

    Mirrors ``pkg_resources.working_set.find(Requirement.parse(...))``
    for the testing harness: the global working set is the sys.path
    scan with first-found-wins per project, and a held project at a
    non-matching version is a VersionConflict, not a miss.
    """
    key = _req_key(req)
    for entry in sys.path:
        for dist in _scan_path_item(entry):
            if dist.key != key:
                continue
            if dist in req:
                return dist
            raise _version_conflict(dist, req)
    return None


def iter_entry_points(group: str, name: str | None = None):
    """Yield the entry points of ``group`` (optionally just ``name``).

    Replaces ``pkg_resources.iter_entry_points`` on the ambient set:
    importlib.metadata scans ``sys.path``, which the ambient set's
    ``add`` keeps current.  Like pkg_resources, each project yields
    once — the first occurrence on ``sys.path`` wins, whether or not
    that copy provides the entry point.  Iterating distributions keeps
    this 3.9-safe: ``EntryPoint.dist`` only exists on 3.10+.
    """
    seen: set[str] = set()
    for dist in metadata.distributions():
        dist_name = dist.metadata['Name']
        if dist_name is None:
            continue
        key = canonicalize_name(dist_name)
        if key in seen:
            continue
        seen.add(key)
        for ep in dist.entry_points:
            if ep.group == group and (name is None or ep.name == name):
                yield ep


def load_entry_point(project: str, group: str, name: str):
    """Load ``group``/``name`` from the dist for ``project``.

    pkg_resources raises DistributionNotFound for an unknown project
    and ImportError for an unknown entry point; here the project miss
    is PackageNotFoundError (caught via :func:`not_found_errors`),
    the entry-point miss stays ImportError.
    """
    dist = find_available(PackagingRequirement(project))
    if dist is None:
        raise metadata.PackageNotFoundError(project)
    get_entry_info = getattr(dist, 'get_entry_info', None)
    if get_entry_info is not None:
        # pkg_resources-shaped dist (both modes until the easy_install
        # unit lands).
        entry_point = get_entry_info(group, name)
    else:
        entry_point = None
        for ep in dist.entry_points:
            if ep.group == group and ep.name == name:
                entry_point = ep
                break
    if entry_point is None:
        raise ImportError(
            f'Entry point {name!r} not found in group {group!r} '
            f'for project {project!r}')
    return entry_point.load()


def _dist_requirements(dist) -> list[PackagingRequirement]:
    """The dist's dependency requirements, as packaging requirements."""
    requires = getattr(dist, 'requires', None)
    if callable(requires):
        # pkg_resources-shaped: requires() returns pkg_resources
        # Requirement objects.
        return [_as_packaging_req(req) for req in requires()]
    return [PackagingRequirement(req) for req in (requires or ())]


def resolve(requirements) -> list:
    """The dists for ``requirements`` and their dependency closure.

    uv-mode replacement for ``WorkingSet.resolve`` feeding
    ``_dists_sig``: while pkg_resources is loaded this delegates to
    the real resolve (bit-identical signatures); otherwise it walks
    ``requires`` metadata breadth-first over the ambient set and
    ``sys.path``.  The result is sorted by the caller, so only the
    set matters.  A project the environment holds at a non-matching
    version is a conflict, mirroring pkg_resources.
    """
    pkg_resources = sys.modules.get('pkg_resources')
    if pkg_resources is not None and all(
            _is_pkg_requirement(req) for req in requirements):
        return pkg_resources.working_set.resolve(requirements)
    result: list[_Dist] = []
    active: dict[str, _Dist] = {}
    queue = [_as_packaging_req(req) for req in requirements]
    while queue:
        req = queue.pop(0)
        name = canonicalize_name(req.name)
        if name in active:
            continue
        dist = ambient().find(req)
        if dist is None:
            dist = find_available(req)
        if dist is None:
            raise metadata.PackageNotFoundError(req.name)
        active[name] = dist
        result.append(dist)
        for dep in _dist_requirements(dist):
            if dep.marker is None:
                queue.append(dep)
                continue
            if dep.marker.evaluate():
                queue.append(dep)
                continue
            # The dependency may ride on an extra the requirement
            # asked for.
            for extra in req.extras:
                if dep.marker.evaluate({'extra': extra}):
                    queue.append(dep)
                    break
    return result


# ---------------------------------------------------------------------
# The uv-mode dist model.
#
# The classes below reproduce the observable pkg_resources surface the
# easy_install internals consume, over stdlib metadata only, so the uv
# path runs with pkg_resources never loaded.  pip mode keeps the real
# pkg_resources objects; the shared helpers stay duck-typed over both.
#
# Every behavior here was pinned against setuptools 75.8.2's
# pkg_resources (the version the test suites seed) and is locked in by
# the byte-identity tables in
# zc/buildout/tests/pytests/test_workingset_adapters.py.  Notable
# pinned quirks:
# * ``safe_name`` normalizes name runs to dashes (setuptools 75;
#   setuptools 58 used underscores), so ``project_name`` spells
#   "Foo_Bar" as "Foo-Bar" while ``key`` is just ``project_name``
#   lowercased.
# * A ``.dist-info`` dist takes its version from the directory name;
#   an ``.egg-info`` dist re-reads ``Version:`` from the metadata.
# * Requirement containment always allows prereleases.
# * ``repr(requirement)`` is ``Requirement.parse('<str>')``; the
#   doctest transcripts show it.

_PY_MAJOR = f'{sys.version_info[0]}.{sys.version_info[1]}'


class _UnsetType:
    """Sentinel for "argument not given" where None is a real value."""
    __slots__ = ()


_UNSET = _UnsetType()

# pkg_resources.safe_name (setuptools 75.8.2): runs of characters that
# are not alphanumerics or dots collapse into one dash.  Not to be
# confused with install_backend._safe_name (underscores), which feeds
# egg *file* names where to_filename performs the dash translation.
def _safe_name(name: str) -> str:
    return re.sub('[^A-Za-z0-9.]+', '-', name)


def _to_filename(name: str) -> str:
    # pkg_resources.to_filename.
    return name.replace('-', '_')


def _safe_version(version: str) -> str:
    try:
        return str(parse_version(version))
    except InvalidVersion:
        return re.sub('[^A-Za-z0-9.]+', '-', version.replace(' ', '.'))


def _safe_extra(extra: str) -> str:
    # pkg_resources.safe_extra.
    return re.sub('[^A-Za-z0-9.-]+', '_', extra).lower()


@lru_cache
def _normalize_path(path: str) -> str:
    # pkg_resources.normalize_path, cached like _normalize_cached.
    return os.path.normcase(os.path.realpath(os.path.normpath(path)))


def _yield_lines(text: str) -> Iterator[str]:
    # pkg_resources.yield_lines for a plain string: stripped, no blank
    # lines, no comment-only lines; trailing comments stay.
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            yield line


def _drop_comment(line: str) -> str:
    # pkg_resources.drop_comment: 'foo # bar' -> 'foo', but a hash
    # without a space may be part of a URL.
    return line.partition(' #')[0]


def _join_continuation(lines: Iterable[str]) -> Iterator[str]:
    # pkg_resources.join_continuation, including its quirks: the
    # character preceding the backslash is elided, and a trailing
    # continuation with no next line suppresses the line.
    lines = iter(lines)
    for item in lines:
        while item.endswith('\\'):
            try:
                item = item[:-2].strip() + next(lines)
            except StopIteration:
                return
        yield item


def _parse_requirement_lines(text: str) -> Iterator[Requirement]:
    # pkg_resources.parse_requirements.
    return map(Requirement, _join_continuation(
        map(_drop_comment, _yield_lines(text))))


# pkg_resources' EGG_NAME: name and version have no dashes left by the
# time they land in a file name, so the regex may stop at dashes.
_EGG_NAME = re.compile(
    r"""
    (?P<name>[^-]+) (
        -(?P<ver>[^-]+) (
            -py(?P<pyver>[^-]+) (
                -(?P<plat>.+)
            )?
        )?
    )?
    """,
    re.VERBOSE,
).match

_macos_version_string = re.compile(r"macosx-(\d+)\.(\d+)-(.*)").match
_darwin_version_string = re.compile(r"darwin-(\d+)\.(\d+)\.(\d+)-(.*)").match


class UnknownExtra(Exception):
    """The distribution has no such extra feature (pkg_resources)."""


class VersionConflict(Exception):
    """A held dist does not satisfy the requirement.

    Mirrors pkg_resources.VersionConflict for the uv path: ``args``
    holds ``(dist, req)``, which is all ``errors.VersionConflict``
    reads when it formats the conflict report.
    """

    def __init__(self, dist, req) -> None:
        self.dist = dist
        self.req = req
        super().__init__(dist, req)

    def __str__(self) -> str:
        return f'{self.dist} is installed but {self.req} is required'


class Requirement(PackagingRequirement):
    """pkg_resources.Requirement's observable surface, packaging-based.

    pkg_resources' own Requirement has been a packaging.Requirement
    subclass since setuptools 75, so subclassing reproduces parsing,
    ``str()`` and marker handling exactly; this class re-adds the
    pkg-only attributes and semantics the easy_install internals use:
    ``key``, ``project_name``, ``specs``, tuple ``extras``,
    ``__contains__`` with unconditional prereleases, the
    ``hashCmp``-based equality and the ``Requirement.parse(...)``
    repr.
    """

    def __init__(self, requirement_string: str) -> None:
        super().__init__(requirement_string)
        self.unsafe_name = self.name
        project_name = _safe_name(self.name)
        self.project_name = project_name
        self.key = project_name.lower()
        self.specs = [
            (spec.operator, spec.version) for spec in self.specifier]
        # pkg_resources re-types extras to a safe_extra'd tuple.
        self.extras = tuple(map(  # ty: ignore[invalid-assignment]
            _safe_extra, self.extras))
        self._hashcmp = (
            self.key,
            self.url,
            self.specifier,
            frozenset(self.extras),
            str(self.marker) if self.marker else None,
        )

    @classmethod
    def parse(cls, requirement_string: str) -> Requirement:
        """Parse a requirement string, mirroring pkg_resources.parse."""
        return cls(requirement_string)

    def __eq__(self, other) -> bool:
        return (isinstance(other, Requirement)
                and self._hashcmp == other._hashcmp)

    def __ne__(self, other) -> bool:
        return not self == other

    def __hash__(self) -> int:
        return hash(self._hashcmp)

    def __contains__(self, item) -> bool:
        # pkg_resources.Requirement.__contains__: a dist matches when
        # its key matches and its version satisfies the specifier;
        # prereleases always allowed.  Dist detection duck-types on
        # key+version rather than isinstance so pkg-shaped dists from
        # a pkg_resources-built Environment (test seams instantiate it
        # while pkg_resources is loaded) match the same way facade
        # dists do; in production uv mode only facade dists exist.
        if hasattr(item, 'key') and hasattr(item, 'version'):
            if item.key != self.key:
                return False
            version = item.version
        else:
            version = item
        try:
            return self.specifier.contains(version, prereleases=True)
        except Exception:  # noqa: BLE001 - mirrors the patch in
            # patches.patch_pkg_resources_requirement_contains: the
            # InvalidVersion class may come from either packaging copy.
            return False

    def __repr__(self) -> str:
        return f'Requirement.parse({str(self)!r})'


def _metadata_fn(base: str, name: str) -> str:
    # pkg_resources.NullProvider._fn: '/'-joined resource paths.
    return os.path.join(base, *name.split('/')) if name else base


class _DirMetadata:
    """Metadata provider for an EGG-INFO or .dist-info directory."""

    def __init__(self, path: str) -> None:
        self.path = path

    def has_metadata(self, name: str) -> bool:
        return os.path.isfile(os.path.join(self.path, name))

    def get_metadata(self, name: str) -> str:
        if not self.has_metadata(name):
            raise KeyError(f'No metadata named {name!r}')
        with open(os.path.join(self.path, name), encoding='utf-8') as f:
            return f.read()

    def metadata_isdir(self, name: str) -> bool:
        return os.path.isdir(_metadata_fn(self.path, name))

    def metadata_listdir(self, name: str) -> list[str]:
        # os.listdir, like pkg_resources' filesystem provider: raises
        # FileNotFoundError when the directory does not exist.
        return os.listdir(_metadata_fn(self.path, name))


class _FileMetadata:
    """Metadata provider for a single-file .egg-info (PKG-INFO only)."""

    def __init__(self, path: str) -> None:
        self.path = path

    def has_metadata(self, name: str) -> bool:
        return name == 'PKG-INFO'

    def get_metadata(self, name: str) -> str:
        if name != 'PKG-INFO':
            raise KeyError(f'No metadata named {name!r}')
        with open(self.path, encoding='utf-8') as f:
            return f.read()

    def metadata_isdir(self, name: str) -> bool:
        # pkg_resources' egg_info is the file path itself; joining a
        # name under it is never a directory.
        return os.path.isdir(_metadata_fn(self.path, name))

    def metadata_listdir(self, name: str) -> list[str]:
        return os.listdir(_metadata_fn(self.path, name))


class _ZipMetadata:
    """Metadata provider for a zipped .egg (EGG-INFO/ inside)."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._names: list[str] | None = None

    def _zip_names(self) -> list[str]:
        if self._names is None:
            with zipfile.ZipFile(self.path) as zf:
                self._names = zf.namelist()
        return self._names

    def has_metadata(self, name: str) -> bool:
        return f'EGG-INFO/{name}' in self._zip_names()

    def get_metadata(self, name: str) -> str:
        if not self.has_metadata(name):
            raise KeyError(f'No metadata named {name!r}')
        with zipfile.ZipFile(self.path) as zf:
            return zf.read(f'EGG-INFO/{name}').decode('utf-8')

    def metadata_isdir(self, name: str) -> bool:
        # pkg_resources.ZipProvider._isdir over its parent->children
        # index: a directory exists iff some entry lies under it.
        return any(n.startswith(self._dir_prefix(name))
                   for n in self._zip_names())

    def metadata_listdir(self, name: str) -> list[str]:
        # ZipProvider._listdir: the direct children under the prefix.
        prefix = self._dir_prefix(name)
        children = []
        for n in self._zip_names():
            if n.startswith(prefix):
                child = n[len(prefix):].split('/')[0]
                if child and child not in children:
                    children.append(child)
        return children

    def _dir_prefix(self, name: str) -> str:
        return f'EGG-INFO/{name}/' if name else 'EGG-INFO/'


class _EmptyMetadata:
    path = ''

    def has_metadata(self, name: str) -> bool:
        return False

    def get_metadata(self, name: str) -> str:
        raise KeyError(f'No metadata named {name!r}')

    def metadata_isdir(self, name: str) -> bool:
        return False

    def metadata_listdir(self, name: str) -> list[str]:
        return []


class Distribution:
    """pkg_resources.Distribution's observable surface over plain files.

    Built by the :class:`Environment` scanner from an egg directory, a
    zipped egg, a metadata directory or a single-file egg-info; never
    wraps importlib.metadata's own Distribution because pkg_resources'
    name/version rules (directory name parsing, the egg-info metadata
    re-read) differ from importlib's and the differences are visible
    in transcripts and ``.installed.cfg`` signatures.
    """

    # 'PKG-INFO' for egg flavors, 'METADATA' for .dist-info, matching
    # pkg_resources' PKG_INFO class attribute.
    PKG_INFO = 'PKG-INFO'

    def __init__(self, location=None, provider=None, project_name=None,
                 version=None, py_version=None, platform=None,
                 precedence=EGG_DIST) -> None:
        self.project_name = _safe_name(project_name or 'Unknown')
        if version is not None:
            self._version = _safe_version(version)
        self.py_version = py_version
        self.platform = platform
        self.location = location
        self.precedence = precedence
        self._provider = provider or _EmptyMetadata()

    @classmethod
    def _from_egg_name(cls, location, provider, basename, precedence):
        # pkg_resources.Distribution.from_location: the name parts
        # come from the file name, never from the metadata.
        project_name = version = py_version = platform = None
        match = _EGG_NAME(os.path.splitext(basename)[0])
        if match:
            project_name, version, py_version, platform = match.group(
                'name', 'ver', 'pyver', 'plat')
        return cls(location, provider, project_name, version,
                   py_version, platform, precedence)

    @classmethod
    def from_egg(cls, path: str) -> Distribution:
        """A .egg bundle (directory or zip) as a dist: EGG_DIST."""
        location = _normalize_path(path)
        if os.path.isdir(path):
            provider = _DirMetadata(os.path.join(path, 'EGG-INFO'))
        else:
            provider = _ZipMetadata(path)
        return cls._from_egg_name(
            location, provider, os.path.basename(location), EGG_DIST)

    @classmethod
    def from_metadata_entry(cls, root: str, entry: str) -> Distribution | None:
        """A .egg-info/.dist-info entry as a dist: DEVELOP_DIST.

        Returns None for an empty metadata directory, which
        pkg_resources' distributions_from_metadata skips.
        """
        path = os.path.join(root, entry)
        if os.path.isdir(path):
            if not os.listdir(path):
                return None
            provider = _DirMetadata(path)
        else:
            provider = _FileMetadata(path)
        dist = cls._from_egg_name(root, provider, entry, DEVELOP_DIST)
        if entry.lower().endswith('.dist-info'):
            dist.PKG_INFO = 'METADATA'
        else:
            # pkg_resources.EggInfoDistribution._reload_version: the
            # metadata's Version: beats the file name's.
            md_version = dist._version_from_metadata()
            if md_version:
                dist._version = md_version
        return dist

    @property
    def key(self) -> str:
        key = getattr(self, '_key', None)
        if key is None:
            self._key = key = self.project_name.lower()
        return key

    @property
    def egg_info(self) -> str | None:
        """Path of the metadata directory (pkg_resources' egg_info).

        pkg_resources sets it eagerly at scan time: the EGG-INFO dir
        for an unpacked egg, ``<zip>/EGG-INFO`` for a zipped one, the
        .dist-info dir itself for a DistInfoDistribution.  The metadata
        provider's path is exactly that for the directory and file
        providers.
        """
        if isinstance(self._provider, _ZipMetadata):
            return os.path.join(self._provider.path, 'EGG-INFO')
        return getattr(self._provider, 'path', None)

    @property
    def version(self) -> str:
        version = getattr(self, '_version', None)
        if version is None:
            version = self._version_from_metadata()
            if version is None:
                raise ValueError(
                    f"Missing 'Version:' header and/or {self.PKG_INFO} "
                    f"file at path: {self.location}", self)
        return version

    @property
    def parsed_version(self):
        return parse_version(self.version)

    @property
    def hashcmp(self) -> tuple:
        return (
            self.parsed_version,
            self.precedence,
            self.key,
            self.location,
            self.py_version or '',
            self.platform or '',
        )

    def __eq__(self, other) -> bool:
        return (isinstance(other, self.__class__)
                and self.hashcmp == other.hashcmp)

    def __ne__(self, other) -> bool:
        return not self == other

    def __hash__(self) -> int:
        return hash(self.hashcmp)

    def __lt__(self, other) -> bool:
        return self.hashcmp < other.hashcmp

    def __str__(self) -> str:
        return f'{self.project_name} {self.version}'

    def __repr__(self) -> str:
        return f'{self} ({self.location})'

    def _version_from_metadata(self) -> str | None:
        # pkg_resources._get_version: the Version: header of PKG-INFO
        # (or METADATA for .dist-info), parsed as an email message.
        try:
            text = self._provider.get_metadata(self.PKG_INFO)
        except KeyError:
            return None
        return email.message_from_string(text).get('Version')

    def has_version(self) -> bool:
        try:
            _ = self.version
        except ValueError:
            return False
        return True

    def as_requirement(self) -> Requirement:
        """A requirement matching this distribution exactly."""
        parsed = self.parsed_version
        if isinstance(parsed, Version):
            spec = f'{self.project_name}=={parsed}'
        else:
            spec = f'{self.project_name}==={parsed}'
        return Requirement.parse(spec)

    def egg_name(self) -> str:
        """The standard .egg file name (pkg_resources.egg_name)."""
        filename = (f'{_to_filename(self.project_name)}'
                    f'-{_to_filename(self.version)}'
                    f'-py{self.py_version or _PY_MAJOR}')
        if self.platform:
            filename += '-' + self.platform
        return filename

    # -- metadata provider delegation -----------------------------

    def has_metadata(self, name: str) -> bool:
        return self._provider.has_metadata(name)

    def get_metadata(self, name: str) -> str:
        return self._provider.get_metadata(name)

    def get_metadata_lines(self, name: str) -> Iterator[str]:
        if not self._provider.has_metadata(name):
            return iter(())
        return _yield_lines(self._provider.get_metadata(name))

    def metadata_isdir(self, name: str) -> bool:
        # pkg_resources.Distribution reaches these through __getattr__
        # delegation to the provider; the facade declares them.
        return self._provider.metadata_isdir(name)

    def metadata_listdir(self, name: str) -> list[str]:
        return self._provider.metadata_listdir(name)

    def clone(self, **kw):
        """Copy this distribution, substituting changed keyword args.

        pkg_resources.Distribution.clone: name and version pass
        through ``__init__``'s normalizers again (idempotent); the
        metadata provider carries over unchanged.  A dist-info dist's
        instance-level ``PKG_INFO`` override is preserved the way
        pkg's DistInfoDistribution subclass keeps its class value.
        """
        for attr in ('project_name', 'version', 'py_version',
                     'platform', 'location', 'precedence'):
            kw.setdefault(attr, getattr(self, attr, None))
        kw.setdefault('provider', self._provider)
        clone = self.__class__(**kw)
        if 'PKG_INFO' in self.__dict__:
            clone.PKG_INFO = self.PKG_INFO
        return clone

    # -- entry points ----------------------------------------------

    @property
    def entry_points(self):
        # importlib parses entry_points.txt for both METADATA and
        # EGG-INFO directory layouts.  PathDistribution needs a real
        # pathlib.Path (its read_text calls joinpath).
        path = getattr(self._provider, 'path', None)
        if path and os.path.isdir(path):
            return metadata.PathDistribution(Path(path)).entry_points
        return ()

    # -- dependencies ------------------------------------------------

    @property
    def extras(self) -> list[str]:
        return [extra for extra in self._dep_map() if extra]

    def requires(self, extras: Iterable[str] = ()) -> list[Requirement]:
        """The requirements needed when the given extras are used."""
        dm = self._dep_map()
        deps = list(dm.get(None, ()))
        for extra in extras:
            try:
                deps.extend(dm[_safe_extra(extra)])
            except KeyError:
                raise UnknownExtra(f'{self} has no such extra feature '
                                   f'{extra!r}') from None
        return deps

    def _dep_map(self) -> dict[str | None, list[Requirement]]:
        dep_map = getattr(self, '_cached_dep_map', None)
        if dep_map is None:
            if self.PKG_INFO == 'METADATA':
                dep_map = self._dist_info_dep_map()
            else:
                dep_map = self._filter_extras(self._build_dep_map())
            self._cached_dep_map = dep_map
        return dep_map

    def _dist_info_dep_map(self) -> dict[str | None, list[Requirement]]:
        # pkg_resources.DistInfoDistribution._compute_dependencies.
        try:
            text = self._provider.get_metadata('METADATA')
        except KeyError:
            text = ''
        msg = email.message_from_string(text)
        reqs: list[Requirement] = []
        for req in msg.get_all('Requires-Dist') or []:
            reqs.extend(_parse_requirement_lines(req))

        def reqs_for_extra(extra):
            for req in reqs:
                if not req.marker or req.marker.evaluate(
                        {'extra': extra}):
                    yield req

        common = dict.fromkeys(reqs_for_extra(None))
        dep_map: dict[str | None, list[Requirement]] = {
            None: list(common)}
        for extra in msg.get_all('Provides-Extra') or []:
            s_extra = _safe_extra(extra.strip())
            dep_map[s_extra] = [
                r for r in reqs_for_extra(extra) if r not in common]
        return dep_map

    def _build_dep_map(self) -> dict[str | None, list[Requirement]]:
        # pkg_resources.Distribution._build_dep_map.
        dm: dict[str | None, list[Requirement]] = {}
        for name in 'requires.txt', 'depends.txt':
            if not self._provider.has_metadata(name):
                continue
            for extra, reqs in _split_sections(
                    self._provider.get_metadata(name)):
                dm.setdefault(extra, []).extend(
                    _parse_requirement_lines('\n'.join(reqs)))
        return dm

    @staticmethod
    def _filter_extras(
            dm: dict[str | None, list[Requirement]],
            ) -> dict[str | None, list[Requirement]]:
        # pkg_resources.Distribution._filter_extras: section markers
        # decide whether an extra's requirements apply at all.
        for extra in list(filter(None, dm)):
            reqs = dm.pop(extra)
            assert extra is not None
            new_extra, _, marker = extra.partition(':')
            fails_marker = False
            if marker:
                try:
                    fails_marker = not Marker(marker).evaluate()
                except InvalidMarker:
                    fails_marker = True
            if fails_marker:
                reqs = []
            dm.setdefault(_safe_extra(new_extra) or None, []).extend(
                reqs)
        return dm

    # -- sys.path insertion -------------------------------------------

    def insert_on(self, path: list[str], loc=None,
                  replace: bool = False) -> None:
        """Ensure ``self.location`` is on ``path`` (pkg_resources port).

        Reproduces pkg_resources.Distribution.insert_on: eggs insert
        ahead of their parent directory, ``replace`` front-inserts,
        duplicates collapse, and insertions into ``sys.path`` trigger
        the version-conflict check.
        """
        loc = loc or self.location
        if not loc:
            return

        nloc = _normalize_path(loc)
        bdir = os.path.dirname(nloc)
        npath = [(p and _normalize_path(p) or p) for p in path]

        p = 0
        found = False
        for p, item in enumerate(npath):
            if item == nloc:
                if not replace:
                    # Found and not replacing: leave path untouched.
                    return
                found = True
                break
            elif item == bdir and self.precedence == EGG_DIST:
                # An egg takes precedence over its directory, unless
                # it is already on the path and replace is off.
                if (not replace) and nloc in npath[p:]:
                    return
                if path is sys.path:
                    self.check_version_conflict()
                path.insert(p, loc)
                npath.insert(p, nloc)
                found = True
                break
        if not found:
            if path is sys.path:
                self.check_version_conflict()
            if replace:
                path.insert(0, loc)
            else:
                path.append(loc)
            return

        # Remove duplicates below the spot where we found/inserted.
        while True:
            try:
                np = npath.index(nloc, p + 1)
            except ValueError:
                break
            else:
                del npath[np], path[np]
                p = np

    def check_version_conflict(self) -> None:
        # pkg_resources.Distribution.check_version_conflict: warn when
        # a different version of an already-imported module lands on
        # sys.path.  pkg_resources' declared-namespace registry is
        # empty here by construction: pkg_resources never loads in uv
        # mode, so no namespace was ever declared through it.
        if self.key == 'setuptools':
            return
        nsp = dict.fromkeys(self.get_metadata_lines(
            'namespace_packages.txt'))
        loc = _normalize_path(self.location)
        for modname in self.get_metadata_lines('top_level.txt'):
            if modname not in sys.modules or modname in nsp:
                continue
            if modname in ('pkg_resources', 'setuptools', 'site'):
                continue
            fn = getattr(sys.modules[modname], '__file__', None)
            if fn and (_normalize_path(fn).startswith(loc)
                       or fn.startswith(self.location)):
                continue
            warnings.warn(
                f'Module {modname} was already imported from {fn}, '
                f'but {self.location} is being added to sys.path',
                UserWarning, stacklevel=2)


def _split_sections(text: str) -> Iterator[tuple[str | None, list[str]]]:
    # pkg_resources.split_sections: (section, content) pairs where
    # content excludes blank and comment-only lines.
    section: str | None = None
    content: list[str] = []
    for line in _yield_lines(text):
        if line.startswith('['):
            if line.endswith(']'):
                if section or content:
                    yield section, content
                section = line[1:-1].strip()
                content = []
            else:
                raise ValueError('Invalid section heading', line)
        else:
            content.append(line)
    yield section, content


def _compatible_platforms(provided: str | None, required: str | None) -> bool:
    """pkg_resources.compatible_platforms, verbatim semantics."""
    if provided is None or required is None or provided == required:
        return True

    reqMac = _macos_version_string(required)
    if reqMac:
        provMac = _macos_version_string(provided)
        if not provMac:
            # Backwards compatibility for packages built before
            # setuptools 0.6.
            provDarwin = _darwin_version_string(provided)
            if provDarwin:
                dversion = int(provDarwin.group(1))
                macosversion = f'{reqMac.group(1)}.{reqMac.group(2)}'
                if (dversion == 7
                        and macosversion >= '10.3'
                        or dversion == 8
                        and macosversion >= '10.4'):
                    return True
            return False

        if (provMac.group(1) != reqMac.group(1)
                or provMac.group(3) != reqMac.group(3)):
            return False

        if int(provMac.group(2)) > int(reqMac.group(2)):
            return False

        return True

    return False


def _is_unpacked_egg(path: str) -> bool:
    return path.lower().endswith('.egg') and os.path.isfile(
        os.path.join(path, 'EGG-INFO', 'PKG-INFO'))


def _is_zip_egg(path: str) -> bool:
    return path.lower().endswith('.egg') and zipfile.is_zipfile(path)


def _safe_listdir(path: str):
    # pkg_resources.safe_listdir: missing or unreadable dirs are
    # simply empty.
    try:
        return os.listdir(path)
    except (PermissionError, NotADirectoryError):
        pass
    except OSError as e:
        if e.errno not in (errno.ENOTDIR, errno.EACCES, errno.ENOENT):
            raise
    return ()


def _egg_dist_or_none(path: str) -> Distribution | None:
    """The dist for an egg path, or None for a metadata-less zip.

    pkg_resources.find_eggs_in_zip yields a zipped egg only when its
    EGG-INFO holds a PKG-INFO.
    """
    if _is_unpacked_egg(path):
        return Distribution.from_egg(path)
    if _is_zip_egg(path):
        dist = Distribution.from_egg(path)
        if dist.has_metadata('PKG-INFO'):
            return dist
    return None


def _scan_path_item(path_item: str) -> Iterator[Distribution]:
    """pkg_resources.find_on_path/find_distributions for one entry."""
    path_item = _normalize_path(path_item)

    if _is_unpacked_egg(path_item) or _is_zip_egg(path_item):
        # The path entry itself is an egg.  Nested eggs inside a zip
        # are a pkg_resources-era artifact this scanner deliberately
        # does not reproduce.
        dist = _egg_dist_or_none(path_item)
        if dist is not None:
            yield dist
        return

    if not os.path.isdir(path_item):
        return

    for entry in sorted(_safe_listdir(path_item)):
        lower = entry.lower()
        fullpath = os.path.join(path_item, entry)
        if (lower.endswith('.egg-info')
                or lower.endswith('.dist-info')
                and os.path.isdir(fullpath)):
            dist = Distribution.from_metadata_entry(path_item, entry)
            if dist is not None:
                yield dist
            continue
        dist = _egg_dist_or_none(fullpath)
        if dist is not None:
            yield dist
            continue
        if lower.endswith('.egg-link'):
            # pkg_resources.resolve_egg_link: only the *first*
            # referenced path's dists count, even when that path
            # yields nothing (the classic second line, '.', is
            # unreachable).
            with open(fullpath, encoding='utf-8') as f:
                for ref in _yield_lines(f.read()):
                    resolved = os.path.join(path_item, ref)
                    yield from _scan_path_item(resolved)
                    break


# Public alias for callers porting off pkg_resources.find_distributions
# (install_backend's pin lookup), the same scanner under its
# single-path-item contract.
scan_path_item = _scan_path_item


class Environment:
    """pkg_resources.Environment + buildout's EnvironmentMixin fixes.

    Scans path entries for distributions and keeps them newest-first
    per project, keyed by the canonicalized name
    (``EnvironmentMixin``'s fix for setuptools 69.3+ name changes,
    buildout issue #647).  ``can_add`` reproduces buildout's macOS
    machine-type override (buildout PR #707): platform strings from a
    different macOS major/minor are accepted as long as the
    architecture matches.
    """

    def __init__(self, search_path: Iterable[str] | None = None,
                 platform: str | _UnsetType | None = _UNSET,
                 python: str | _UnsetType | None = _UNSET,
                 logger: logging.Logger | None = None) -> None:
        self._distmap: dict[str, list[Distribution]] = {}
        if platform is _UNSET:
            # Lazy: install_backend imports _workingset at module
            # level, so a top-level import of its platform helper
            # would cycle.
            from zc.buildout.install_backend import _supported_platform
            platform = _supported_platform()
        # None means "match all platforms"; the default is the
        # running one (pkg_resources.Environment semantics).
        self.platform = cast('str | None', platform)
        if python is _UNSET:
            python = _PY_MAJOR
        # None means "match all Python versions".
        self.python = cast('str | None', python)
        self._logger = (logger if logger is not None
                        else logging.getLogger('zc.buildout._workingset'))
        self.scan(search_path)

    @property
    def _mac_machine_type(self) -> str:
        # easy_install.Environment._mac_machine_type.
        platform = self.platform
        assert platform is not None
        match = _macos_version_string(platform)
        if match is None:
            return ''
        return match.group(3)

    def can_add(self, dist: Distribution) -> bool:
        """Whether ``dist`` is acceptable for this environment.

        pkg_resources.Environment.can_add plus buildout's macOS
        machine-type fallback (easy_install.Environment.can_add).
        """
        py_compat = (
            self.python is None
            or dist.py_version is None
            or dist.py_version == self.python
        )
        if py_compat and _compatible_platforms(dist.platform,
                                               self.platform):
            return True
        if sys.platform != 'darwin':
            return False
        if not py_compat:
            return False
        # compatible_platforms() accepts a None provided platform, so
        # the first branch would not have failed on that account.
        dist_platform = dist.platform
        assert dist_platform is not None
        provMac = _macos_version_string(dist_platform)
        if not provMac:
            return False
        provided_machine_type = provMac.group(3)
        if provided_machine_type != self._mac_machine_type:
            return False
        self._logger.debug(
            'Accepted dist %s although its provided platform %s does not '
            'match our supported platform %s.',
            dist,
            dist.platform,
            self.platform,
        )
        return True

    def add(self, dist: Distribution) -> None:
        """Add ``dist`` if we ``can_add()`` it and it has a version."""
        if self.can_add(dist) and dist.has_version():
            # EnvironmentMixin: the canonicalized key, not dist.key.
            distribution_key = normalize_name(dist.key)
            dists = self._distmap.setdefault(distribution_key, [])
            if dist not in dists:
                dists.append(dist)
                dists.sort(key=operator.attrgetter('hashcmp'),
                           reverse=True)

    def remove(self, dist: Distribution) -> None:
        self._distmap[normalize_name(dist.key)].remove(dist)

    def scan(self, search_path: Iterable[str] | None = None) -> None:
        """Scan ``search_path`` for usable distributions."""
        if search_path is None:
            search_path = sys.path
        for item in search_path:
            for dist in _scan_path_item(item):
                self.add(dist)

    def __getitem__(self, project_name: str) -> list[Distribution]:
        """Newest-to-oldest list of distributions for the project."""
        distribution_key = normalize_name(project_name)
        return self._distmap.get(distribution_key, [])

    def __iter__(self) -> Iterator[str]:
        for key in self._distmap:
            if self[key]:
                yield key
