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

import sys
from importlib import metadata
from typing import TYPE_CHECKING, cast

from packaging.requirements import Requirement as PackagingRequirement
from packaging.utils import canonicalize_name
from packaging.version import parse as parse_version

if TYPE_CHECKING:
    import pkg_resources

    _Dist = pkg_resources.Distribution | metadata.Distribution


# pkg_resources precedence constants.  Defined here so the uv path
# never has to import pkg_resources to name them.
DEVELOP_DIST = -1  # pkg_resources.DEVELOP_DIST
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
    packaging.Requirement, so isinstance cannot tell them apart.
    """
    return hasattr(req, 'key')


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
    """The pkg_resources VersionConflict for ``dist`` not matching ``req``.

    Raised through the bridge while pkg_resources is loaded; once the
    easy_install unit lands without pkg_resources this becomes a plain
    PackageNotFoundError-style failure and easy_install's ``except``
    clause is rewired in the same unit.
    """
    pkg_resources = sys.modules.get('pkg_resources')
    if pkg_resources is not None:
        return pkg_resources.VersionConflict(dist, req)
    return metadata.PackageNotFoundError(
        f'{dist_name(dist)} {dist_version(dist)} does not match {req}')


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

    def __init__(self) -> None:
        self.entries = sys.path
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
        if pkg_resources is not None and hasattr(dist, 'insert_on'):
            # Keep the real working set in the loop while it is
            # loaded: pkg_resources EntryPoint.load() resolves the
            # dist's requirements against the global set, which used
            # to receive these dists directly when easy_install got it
            # passed in.  insert_on is idempotent, so the doubled
            # sys.path handling is a no-op.  Once the easy_install
            # unit lands, pkg_resources is never loaded in uv mode and
            # this forwarding simply stops happening.
            pkg_resources.working_set.add(dist, entry, insert, replace)

    def __contains__(self, dist) -> bool:
        """True if ``dist`` is the active distribution for its project."""
        return self.by_key.get(dist_key(dist)) == dist

    def __iter__(self):
        # The dists grafted into this set, in registration order.
        # Environment dists that were never added are covered by the
        # ``find`` bridge while pkg_resources is loaded; iteration
        # feeds "required by" bookkeeping, where only grafted dists
        # carry relevant edges.
        return iter(self.by_key.values())

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
