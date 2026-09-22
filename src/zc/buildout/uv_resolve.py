"""Resolve requirements to pinned artifacts with ``uv pip compile``."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name

logger = logging.getLogger(__name__)

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11: tomli, a setup.py conditional
    import tomli as tomllib  # ty: ignore[unresolved-import]  # runtime: setup.py conditional for Python < 3.11


@dataclass(frozen=True)
class PinnedDist:
    """One project pinned to a version and its artifact URLs.

    ``url`` is the first wheel URL when the lock offers wheels, the
    sdist URL otherwise (so ``url == sdist_url`` for an sdist-only
    lock); ``sha256`` is that URL's hash. ``sdist_url`` and
    ``sdist_sha256`` are None when the lock carries no sdist.

    ``directory`` carries the project path when the lock entry is a
    directory pin, which is how a develop project handed to the compile
    as an override comes back.  Such a pin has no artifact: ``url`` is
    empty and ``version`` may be empty too, since uv omits it when the
    compile never built the project's metadata.  Directory pins are
    never installed; the caller grafts the matching develop
    distribution instead.
    """

    name: str
    version: str
    url: str
    sha256: str | None
    sdist_url: str | None
    sdist_sha256: str | None
    directory: str | None = None


@dataclass(frozen=True)
class PinnedSet:
    """The pinned distributions of one lock, in lock order."""

    dists: tuple[PinnedDist, ...]

    def for_project(self, name: str) -> PinnedDist | None:
        """Return the pin for project ``name``, canonicalized, or None."""
        wanted = canonicalize_name(name)
        for dist in self.dists:
            if canonicalize_name(dist.name) == wanted:
                return dist
        return None


class ResolutionError(Exception):
    """``uv pip compile`` failed; ``stderr`` carries its captured stderr."""

    def __init__(self, message: str, stderr: str = '') -> None:
        super().__init__(message)
        self.stderr: str = stderr


def resolve(*, requirements: Sequence[str], constraints: Mapping[str, str],
            links: Sequence[str], index_url: str | None,
            prefer_final: bool = True, offline: bool = False, uv: str,
            python: str, fallback_index_url: str | None = None,
            overrides: Sequence[str] = (),
            ) -> PinnedSet:
    """Compile ``requirements`` to a ``PinnedSet`` with ``uv pip compile``.

    ``constraints`` maps project names to pinned versions, ``links`` are
    extra find-links locations, and ``index_url`` is the configured
    package index, normalized like ``easy_install._extra_index_url``: a
    directory goes to uv as find-links, a plain URL as its
    ``--default-index``. ``prefer_final`` maps to ``--prerelease``
    explicitly: ``if-necessary`` when true, ``allow`` when false, so
    uv may select pre-releases only then; ``offline`` forbids network
    access, so uv serves the configured sources from its own cache or
    not at all. ``uv`` and ``python`` name the uv binary and the
    interpreter to resolve for.

    ``fallback_index_url`` goes on the argv as ``--default-index``
    only when the configured index produced none (unset, dropped, or
    routed to find-links as a directory): without any index uv falls
    back to PyPI.  It is how the test harness injects its dead index
    now that the scrubbed child environment no longer leaks
    ``UV_INDEX_URL``; production callers leave it unset.

    ``overrides`` carries override lines in pip's ``name @ url`` form,
    written to an ``overrides.txt`` that uv applies through
    ``--overrides``.  The install loop hands develop projects to the
    compile this way: an override wins over configured sources wherever
    the resolved closure references the project, and stays inert when
    nothing does, so an unreferenced develop project can neither fail
    nor skew an unrelated resolution (probes B2 a/b/c).

    The compile resolves the full dependency closure: one compile
    carries every requirement the caller passes plus their transitive
    dependencies, so a set of requirements resolved together stays
    mutually consistent.
    """
    with tempfile.TemporaryDirectory(prefix='zc-buildout-uv-') as tmp:
        workdir = Path(tmp)
        requirements_in = workdir / 'requirements.in'
        requirements_in.write_text(
            ''.join(f'{requirement}\n' for requirement in requirements),
            encoding='utf-8')
        lock_file = workdir / 'pylock.toml'
        args = [uv, 'pip', 'compile', str(requirements_in), '-o',
                str(lock_file), '--python', python]
        for link in links:
            args.extend(['-f', link])
        args.extend(_constraints_args(workdir, requirements, constraints))
        args.extend(_overrides_args(workdir, overrides))
        args.extend(_index_args(index_url, fallback_index_url))
        # Explicit both ways (probes p3, p6, p7): if-necessary is the
        # uv default today, but naming it pins the mapping against uv
        # default drift.
        args.extend(['--prerelease',
                     'allow' if not prefer_final else 'if-necessary'])
        if offline:
            # --offline alone: the index and find-links stay in the
            # source set and a warm uv cache serves them with zero
            # network access; --no-index would blind the registry
            # cache (probes p8, p11, p12).
            args.append('--offline')
        completed = _run(args)
        if completed.returncode != 0:
            raise ResolutionError(
                f'uv pip compile exited with status {completed.returncode}',
                completed.stderr)
        try:
            lock = tomllib.loads(lock_file.read_text(encoding='utf-8'))
        except tomllib.TOMLDecodeError as err:
            raise ResolutionError(
                f'uv produced an unparsable pylock.toml: {err}',
                completed.stderr) from err
        return _parse_lock(lock)


# Ambient uv configuration must not leak into a resolve: the buildout
# configuration alone decides sources, prerelease policy, offline mode,
# and cache use.  UV_CACHE_DIR stays: the cache is the store that
# offline resolves serve from, and the test harness redirects it.
_SCRUBBED_ENV_VARS = frozenset([
    'UV_INDEX_URL', 'UV_DEFAULT_INDEX', 'UV_EXTRA_INDEX_URL',
    'UV_FIND_LINKS', 'UV_PRERELEASE', 'UV_OFFLINE', 'UV_NO_CACHE',
    'UV_INSECURE_HOST',
])


def _child_env() -> dict[str, str]:
    """``os.environ`` minus the ambient uv configuration variables."""
    return {name: value for name, value in os.environ.items()
            if name not in _SCRUBBED_ENV_VARS}


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ``args`` with captured output; the seam monkeypatched by tests."""
    return subprocess.run(
        args, capture_output=True, text=True, check=False,
        env=_child_env())


def _constraints_args(
        workdir: Path,
        requirements: Sequence[str],
        constraints: Mapping[str, str],
        ) -> list[str]:
    """The ``-c constraints.txt`` arguments, empty when nothing valid pins."""
    if not constraints:
        return []
    lines = _validated_constraint_lines(requirements, constraints)
    if not lines:
        return []
    constraints_txt = workdir / 'constraints.txt'
    constraints_txt.write_text(''.join(lines), encoding='utf-8')
    return ['-c', str(constraints_txt)]


def _overrides_args(workdir: Path, overrides: Sequence[str]) -> list[str]:
    """The ``--overrides overrides.txt`` arguments, empty without overrides."""
    if not overrides:
        return []
    overrides_txt = workdir / 'overrides.txt'
    overrides_txt.write_text(
        ''.join(f'{override}\n' for override in overrides),
        encoding='utf-8')
    return ['--overrides', str(overrides_txt)]


def _validated_constraint_lines(
        requirements: Sequence[str],
        constraints: Mapping[str, str],
        ) -> list[str]:
    """Constraints-file lines for a [versions] mapping, junk filtered out.

    The whole mapping is handed to every compile, so one entry that is
    no valid specifier would abort unrelated resolutions with uv's
    constraints-file parse error.  pip mode only ever applies the entry
    for the project being installed, so an invalid entry for another
    project is skipped with a warning here, while an invalid entry for
    a project being resolved raises the same IncompatibleConstraintError
    pip mode raises for a disallowed pin.
    """
    resolved: dict[str, str] = {}
    for requirement in requirements:
        try:
            name = Requirement(requirement).name
        except InvalidRequirement:
            continue
        resolved[canonicalize_name(name)] = requirement
    lines = []
    for name, constraint in constraints.items():
        if not constraint:
            # pip parity: Installer._constrain skips a falsy [versions]
            # value, so an empty pin is no pin at all, for any project.
            continue
        if _is_valid_constraint(constraint):
            lines.append(_constraint_line(name, constraint))
            continue
        _reject_junk_constraint(resolved, name, constraint)
    return lines


def _reject_junk_constraint(
        resolved: Mapping[str, str],
        name: str,
        constraint: str,
        ) -> None:
    """Report a [versions] entry that is no valid specifier.

    An invalid pin for a project being resolved raises the same
    IncompatibleConstraintError pip mode raises for a disallowed pin;
    for any other project the entry is skipped with a warning, since
    pip mode never applies it.
    """
    requirement = resolved.get(canonicalize_name(name))
    if requirement is not None:
        from zc.buildout.easy_install import IncompatibleConstraintError
        raise IncompatibleConstraintError(
            f"The requirement ({requirement!r}) is not allowed "
            f"by your [versions] constraint ({constraint})")
    logger.warning(
        'Ignoring [versions] entry %s = %s:'
        ' not a valid version specifier.', name, constraint)


def _is_valid_constraint(constraint: str) -> bool:
    """True when ``constraint`` parses as the specifier uv is handed."""
    text = constraint if constraint[:1] in '<>=' else f'=={constraint}'
    try:
        SpecifierSet(text)
    except InvalidSpecifier:
        return False
    return True


def _constraint_line(name: str, constraint: str) -> str:
    """One constraints-file line for ``name`` with a [versions] value.

    The value syntax is the one ``easy_install._constrained_requirement``
    accepts: an operator-led specifier (``<``, ``>``, ``==``) passes
    through, a bare version means an exact pin.
    """
    if constraint[0] in '<>=':
        return f'{name}{constraint}\n'
    return f'{name}=={constraint}\n'


def _parse_lock(data: dict[str, Any]) -> PinnedSet:
    """Build the ``PinnedSet`` from parsed ``pylock.toml`` data."""
    return PinnedSet(tuple(
        _parse_package(package) for package in data.get('packages', [])))


def _parse_package(package: Any) -> PinnedDist:
    """One lock package entry as a ``PinnedDist``.

    A directory override comes back as ``directory = { path = ... }``
    with ``version`` optional; anything artifact-shaped keeps the
    wheel/sdist reading.  A lock whose shape differs from what uv 0.12
    writes raises a ResolutionError with context, never a raw KeyError
    or IndexError.
    """
    try:
        directory = package.get('directory')
        if directory is not None:
            return _parse_directory_package(package, directory)
        wheels = package.get('wheels') or []
        sdist = package.get('sdist') or {}
        if wheels:
            url = wheels[0]['url']
            sha256 = _sha256(wheels[0])
        else:
            url = sdist['url']
            sha256 = _sha256(sdist)
        return PinnedDist(
            name=package['name'], version=package['version'], url=url,
            sha256=sha256, sdist_url=sdist.get('url'),
            sdist_sha256=_sha256(sdist))
    except (KeyError, IndexError) as err:
        raise ResolutionError(
            'uv produced a pylock.toml with an unexpected shape:'
            f' {err!r} in the entry for {package.get("name")!r}') from err


def _parse_directory_package(package: Any, directory: Any) -> PinnedDist:
    """One lock directory entry as a ``PinnedDist`` marked by ``directory``.

    uv writes ``directory = { path = ... }`` for a directory override
    and may omit ``version`` when the compile never built the project's
    metadata.
    """
    path = directory.get('path')
    if not isinstance(path, str):
        raise ResolutionError(
            'uv produced a pylock.toml with an unexpected shape:'
            ' no path in the directory entry for'
            f' {package.get("name")!r}')
    return PinnedDist(
        name=package['name'], version=package.get('version', ''),
        url='', sha256=None, sdist_url=None, sdist_sha256=None,
        directory=path)


def _sha256(artifact: Any) -> str | None:
    """The sha256 hash of a lock artifact entry, when it has hashes."""
    return (artifact.get('hashes') or {}).get('sha256')


def _index_args(index_url: str | None,
                fallback_index_url: str | None = None) -> list[str]:
    """Route a configured package index to uv arguments.

    ``fallback_index_url`` becomes ``--default-index`` when the
    configured index routed to none: an argv with find-links but no
    index lets uv default to PyPI, which the harness's dead index must
    plug.
    """
    args = _configured_index_args(index_url)
    if fallback_index_url is not None and '--default-index' not in args:
        args.extend(['--default-index', fallback_index_url])
    return args


def _configured_index_args(index_url: str | None) -> list[str]:
    """Route a configured package index to uv arguments.

    Normalized like ``easy_install._extra_index_url``: a scheme-less
    value naming an existing directory becomes its ``file://`` URI, a
    scheme-less nonexistent path is dropped. uv refuses a plain
    directory tree as ``--default-index`` but accepts it as
    ``--find-links``, so directories go on the argv as ``-f``; real
    PEP 503 simple indexes keep ``--default-index`` (``--index-url``
    is deprecated at the uv 0.12 floor; ``--default-index`` is its
    replacement).
    """
    if not index_url:
        return []
    if not _is_url(index_url):
        index_path = Path(index_url)
        if not index_path.exists():
            return []
        index_url = index_path.expanduser().resolve().as_uri()
    directory = _local_directory(index_url)
    if directory is not None:
        return _find_links_args(directory)
    return ['--default-index', index_url]


_WINDOWS_DRIVE = re.compile(r'[A-Za-z]:($|[\\/])')


def _local_directory(url: str) -> Path | None:
    """The path of a ``file://`` URL naming a directory, else None.

    ``file://`` glued to a native Windows path (``file://C:\\index``)
    lands the drive in the URL netloc; reassemble the native spelling.
    Only absolute paths are returned: callers render the result with
    ``Path.as_uri``, which refuses relative paths.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'file':
        return None
    if _WINDOWS_DRIVE.match(parts.netloc):
        path = Path(urllib.parse.unquote(parts.netloc + parts.path))
    else:
        path = Path(urllib.request.url2pathname(parts.path))
    if not path.is_absolute():
        return None
    return path if path.is_dir() else None


def _find_links_args(directory: Path) -> list[str]:
    """Find-links args for a directory index tree.

    buildout treats such a tree as one project per subdirectory and uv
    does not recurse find-links directories, so each subdirectory
    becomes its own ``-f`` entry; the directory itself stays for flat
    layouts.
    """
    args = ['-f', directory.as_uri()]
    for child in sorted(directory.iterdir()):
        if child.is_dir():
            args.extend(['-f', child.as_uri()])
    return args


def _is_url(value: str) -> bool:
    """True when ``value`` carries a real URL scheme.

    A Windows drive path such as ``C:\\index`` parses with the
    one-letter scheme ``c``. Real index schemes (http, https, file)
    are longer than one character.
    """
    return len(urllib.parse.urlsplit(value).scheme) > 1

