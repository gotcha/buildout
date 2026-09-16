"""Resolve requirements to pinned artifacts with ``uv pip compile``."""

from __future__ import annotations

import subprocess
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.utils import canonicalize_name

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
    """

    name: str
    version: str
    url: str
    sha256: str | None
    sdist_url: str | None
    sdist_sha256: str | None


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

    def __init__(self, message: str, stderr: str) -> None:
        super().__init__(message)
        self.stderr: str = stderr


def resolve(*, requirements: Sequence[str], constraints: Mapping[str, str],
            links: Sequence[str], index_url: str | None,
            prefer_final: bool = True, offline: bool = False, uv: str,
            python: str) -> PinnedSet:
    """Compile ``requirements`` to a ``PinnedSet`` with ``uv pip compile``.

    ``constraints`` maps project names to pinned versions, ``links`` are
    extra find-links locations, and ``index_url`` is the configured
    package index, normalized like ``easy_install._extra_index_url``: a
    directory goes to uv as find-links, a plain URL as its
    ``--index-url``. With ``prefer_final`` false uv may select
    pre-releases; ``offline`` forbids network and index access. ``uv``
    and ``python`` name the uv binary and the interpreter to resolve for.

    Dependencies are not compiled (``--no-deps``): the caller resolves
    one requirement at a time and walks dependency metadata itself, so
    a transitive requirement that configured sources cannot reach must
    not fail the pin of the requirement being obtained.
    """
    with tempfile.TemporaryDirectory(prefix='zc-buildout-uv-') as tmp:
        workdir = Path(tmp)
        requirements_in = workdir / 'requirements.in'
        requirements_in.write_text(
            ''.join(f'{requirement}\n' for requirement in requirements),
            encoding='utf-8')
        lock_file = workdir / 'pylock.toml'
        args = [uv, 'pip', 'compile', str(requirements_in), '-o',
                str(lock_file), '--python', python, '--no-deps']
        for link in links:
            args.extend(['-f', link])
        if constraints:
            constraints_txt = workdir / 'constraints.txt'
            constraints_txt.write_text(
                ''.join(_constraint_line(name, constraint)
                        for name, constraint in constraints.items()),
                encoding='utf-8')
            args.extend(['-c', str(constraints_txt)])
        args.extend(_index_args(index_url))
        if not prefer_final:
            args.extend(['--prerelease', 'allow'])
        if offline:
            args.extend(['--offline', '--no-index'])
        completed = _run(args)
        if completed.returncode != 0:
            raise ResolutionError(
                f'uv pip compile exited with status {completed.returncode}',
                completed.stderr)
        lock = tomllib.loads(lock_file.read_text(encoding='utf-8'))
        return _parse_lock(lock)


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ``args`` with captured output; the seam monkeypatched by tests."""
    return subprocess.run(args, capture_output=True, text=True, check=False)


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
    dists: list[PinnedDist] = []
    for package in data.get('packages', []):
        wheels = package.get('wheels') or []
        sdist = package.get('sdist') or {}
        if wheels:
            url = wheels[0]['url']
            sha256 = _sha256(wheels[0])
        else:
            url = sdist['url']
            sha256 = _sha256(sdist)
        dists.append(PinnedDist(
            name=package['name'], version=package['version'], url=url,
            sha256=sha256, sdist_url=sdist.get('url'),
            sdist_sha256=_sha256(sdist)))
    return PinnedSet(tuple(dists))


def _sha256(artifact: Any) -> str | None:
    """The sha256 hash of a lock artifact entry, when it has hashes."""
    return (artifact.get('hashes') or {}).get('sha256')


def _index_args(index_url: str | None) -> list[str]:
    """Route a configured package index to uv arguments.

    Normalized like ``easy_install._extra_index_url``: a scheme-less
    value naming an existing directory becomes its ``file://`` URI, a
    scheme-less nonexistent path is dropped. uv refuses a plain
    directory tree as ``--index-url`` but accepts it as ``--find-links``,
    so directories go on the argv as ``-f``; real PEP 503 simple indexes
    keep ``--index-url``.
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
    return ['--index-url', index_url]


def _local_directory(url: str) -> Path | None:
    """The path of a ``file://`` URL naming a directory, else None."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'file':
        return None
    path = Path(urllib.request.url2pathname(parts.path))
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

