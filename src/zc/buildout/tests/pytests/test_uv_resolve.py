"""Unit tests for the uv pylock.toml resolver in zc.buildout.uv_resolve."""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pkg_resources
import pytest

import zc.buildout
from zc.buildout import easy_install, uv_resolve
from zc.buildout.uv_resolve import ResolutionError, resolve

UV = shutil.which('uv')
requires_uv = pytest.mark.skipif(UV is None, reason='uv executable not found')

LOCK_DEMO = """\
lock-version = "1.0"
created-by = "uv"

[[packages]]
name = "demo"
version = "1.0"

[[packages.wheels]]
url = "https://files.example.com/demo-1.0-py3-none-any.whl"
hashes = { sha256 = "aaaa" }
"""

LOCK_TWO_PACKAGES = """\
lock-version = "1.0"
created-by = "uv"

[[packages]]
name = "demo-pkg"
version = "1.0"

[packages.sdist]
url = "https://files.example.com/demo_pkg-1.0.tar.gz"
hashes = { sha256 = "sdist-hash" }

[[packages.wheels]]
url = "https://files.example.com/demo_pkg-1.0-py3-none-any.whl"
hashes = { sha256 = "wheel-one" }

[[packages.wheels]]
url = "https://files.example.com/demo_pkg-1.0-py39-none-any.whl"
hashes = { sha256 = "wheel-two" }

[[packages]]
name = "other"
version = "2.0"

[packages.sdist]
url = "https://files.example.com/other-2.0.tar.gz"
hashes = { sha256 = "other-sdist" }
"""

LOCK_DIRECTORY = """\
lock-version = "1.0"
created-by = "uv"

[[packages]]
name = "devpkg"
directory = { path = "/dev/pkg" }

[[packages]]
name = "demo"
version = "1.0"

[[packages.wheels]]
url = "https://files.example.com/demo-1.0-py3-none-any.whl"
hashes = { sha256 = "aaaa" }
"""

LOCK_DIRECTORY_NO_PATH = """\
lock-version = "1.0"
created-by = "uv"

[[packages]]
name = "devpkg"
directory = { editable = false }
"""


def _record_run(monkeypatch, lock_text=LOCK_DEMO, returncode=0, stderr=''):
    """Stub ``_run``: record argv and input files, write a canned lock."""
    calls = []

    def fake_run(args):
        texts = {'requirements': Path(args[3]).read_text()}
        if '-c' in args:
            constraint_path = args[args.index('-c') + 1]
            texts['constraints'] = Path(constraint_path).read_text()
        if '--overrides' in args:
            overrides_path = args[args.index('--overrides') + 1]
            texts['overrides'] = Path(overrides_path).read_text()
        out_path = args[args.index('-o') + 1]
        Path(out_path).write_text(lock_text)
        calls.append((list(args), texts))
        return subprocess.CompletedProcess(args, returncode, '', stderr)

    monkeypatch.setattr(uv_resolve, '_run', fake_run)
    return calls


def _resolve_with_lock(monkeypatch, lock_text):
    """Resolve one requirement against the stubbed ``_run`` lock output."""
    _record_run(monkeypatch, lock_text)
    return resolve(requirements=['demo'], constraints={}, links=[],
                   index_url=None, uv='/uv', python='/python')


def _make_wheel(directory, name='demo', version='1.0'):
    """Write a minimal pure-python wheel for ``name`` into ``directory``."""
    dist_info = f'{name}-{version}.dist-info'
    wheel_path = directory / f'{name}-{version}-py3-none-any.whl'
    with zipfile.ZipFile(wheel_path, 'w') as zf:
        zf.writestr(
            f'{dist_info}/METADATA',
            f'Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n')
        zf.writestr(
            f'{dist_info}/WHEEL',
            'Wheel-Version: 1.0\nGenerator: test\n'
            'Root-Is-Purelib: true\nTag: py3-none-any\n')
        zf.writestr(f'{dist_info}/RECORD', '')
    return wheel_path


def test_base_argv_shape(monkeypatch):
    calls = _record_run(monkeypatch)
    pinned = resolve(requirements=['demo'], constraints={}, links=[],
                     index_url=None, uv='/uv', python='/python')
    args, texts = calls[0]
    assert args[:3] == ['/uv', 'pip', 'compile']
    assert args[3].endswith('requirements.in')
    assert args[4] == '-o'
    assert args[5].endswith('pylock.toml')
    assert Path(args[3]).parent == Path(args[5]).parent
    assert args[6:] == ['--python', '/python', '--no-deps',
                        '--prerelease', 'if-necessary']
    assert texts == {'requirements': 'demo\n'}
    dist = pinned.for_project('demo')
    assert dist is not None
    assert dist.version == '1.0'


def test_one_find_links_per_link(monkeypatch):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=['/a', '/b'],
            index_url=None, uv='/uv', python='/python')
    args, _texts = calls[0]
    assert args[6:] == [
        '--python', '/python', '--no-deps', '-f', '/a', '-f', '/b',
        '--prerelease', 'if-necessary']


def test_constraints_add_dash_c_and_file(monkeypatch):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={'demo': '1.0'}, links=[],
            index_url=None, uv='/uv', python='/python')
    args, texts = calls[0]
    assert args[args.index('-c') + 1].endswith('constraints.txt')
    assert texts['constraints'] == 'demo==1.0\n'


def test_no_constraints_no_dash_c(monkeypatch):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[],
            index_url=None, uv='/uv', python='/python')
    args, texts = calls[0]
    assert '-c' not in args
    assert 'constraints' not in texts


def test_constraint_values_keep_operator_led_specifiers(monkeypatch):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'],
            constraints={'demo': '1.0', 'other': '>=2.0', 'third': '<4'},
            links=[], index_url=None, uv='/uv', python='/python')
    _args, texts = calls[0]
    assert texts['constraints'] == 'demo==1.0\nother>=2.0\nthird<4\n'


def test_overrides_add_dash_dash_overrides_and_file(monkeypatch):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[],
            index_url=None, uv='/uv', python='/python',
            overrides=['devpkg @ file:///dev/pkg',
                       'other @ file:///dev/other'])
    args, texts = calls[0]
    assert args[args.index('--overrides') + 1].endswith('overrides.txt')
    assert texts['overrides'] == (
        'devpkg @ file:///dev/pkg\nother @ file:///dev/other\n')


def test_no_overrides_no_dash_dash_overrides(monkeypatch):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[],
            index_url=None, uv='/uv', python='/python')
    args, texts = calls[0]
    assert '--overrides' not in args
    assert 'overrides' not in texts


def test_prefer_final_false_allows_prereleases(monkeypatch):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[], index_url=None,
            prefer_final=False, uv='/uv', python='/python')
    args, _texts = calls[0]
    assert args[-2:] == ['--prerelease', 'allow']


def test_prefer_final_true_emits_if_necessary(monkeypatch):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[], index_url=None,
            uv='/uv', python='/python')
    args, _texts = calls[0]
    assert args[-2:] == ['--prerelease', 'if-necessary']


def test_offline_adds_offline_without_no_index(monkeypatch):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[], index_url=None,
            offline=True, uv='/uv', python='/python')
    args, _texts = calls[0]
    assert args[-1] == '--offline'
    assert '--no-index' not in args


def test_offline_keeps_index_and_find_links_in_the_source_set(
        monkeypatch, tmp_path):
    # Probes p8, p11, and p12: --no-index blinds a warm registry cache,
    # while --offline alone lets it serve the configured sources.
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={},
            links=['https://example.com/links'],
            index_url='https://example.com/simple',
            offline=True, uv='/uv', python='/python')
    args, _texts = calls[0]
    assert args[args.index('-f') + 1] == 'https://example.com/links'
    assert args[args.index('--default-index') + 1] == 'https://example.com/simple'
    assert args[-1] == '--offline'


def test_online_default_adds_no_offline_flags(monkeypatch):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[], index_url=None,
            uv='/uv', python='/python')
    args, _texts = calls[0]
    assert '--offline' not in args
    assert '--no-index' not in args


def test_directory_index_routes_to_find_links(monkeypatch, tmp_path):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[],
            index_url=str(tmp_path), uv='/uv', python='/python')
    args, _texts = calls[0]
    expected = tmp_path.expanduser().resolve().as_uri()
    assert args[args.index('-f') + 1] == expected
    assert '--default-index' not in args


def test_file_uri_directory_index_routes_to_find_links(
        monkeypatch, tmp_path):
    calls = _record_run(monkeypatch)
    uri = tmp_path.expanduser().resolve().as_uri()
    resolve(requirements=['demo'], constraints={}, links=[],
            index_url=uri, uv='/uv', python='/python')
    args, _texts = calls[0]
    assert args[args.index('-f') + 1] == uri
    assert '--default-index' not in args


def test_directory_index_expands_project_subdirs(monkeypatch, tmp_path):
    (tmp_path / 'demo').mkdir()
    (tmp_path / 'other').mkdir()
    (tmp_path / 'a-file.txt').write_text('x')
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[],
            index_url=str(tmp_path), uv='/uv', python='/python')
    args, _texts = calls[0]
    root = tmp_path.expanduser().resolve()
    assert args[args.index('--python') + 2:] == [
        '--no-deps',
        '-f', root.as_uri(),
        '-f', (root / 'demo').as_uri(),
        '-f', (root / 'other').as_uri(),
        '--prerelease', 'if-necessary',
    ]


def test_remote_index_routes_to_index_url(monkeypatch):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[],
            index_url='https://example.com/simple',
            uv='/uv', python='/python')
    args, _texts = calls[0]
    assert args[args.index('--default-index') + 1] == 'https://example.com/simple'
    assert '-f' not in args


def test_missing_index_path_is_dropped(monkeypatch):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[],
            index_url='/no/such/index-dir', uv='/uv', python='/python')
    args, _texts = calls[0]
    assert '--default-index' not in args
    assert '-f' not in args
    assert args[6:] == ['--python', '/python', '--no-deps',
                        '--prerelease', 'if-necessary']


def test_fallback_index_fills_an_unset_index(monkeypatch):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[],
            index_url=None, uv='/uv', python='/python',
            fallback_index_url='file:///nonexistent-hermetic-index')
    args, _texts = calls[0]
    assert args[args.index('--default-index') + 1] == (
        'file:///nonexistent-hermetic-index')


def test_fallback_index_plugs_the_hole_behind_a_directory_index(
        monkeypatch, tmp_path):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[],
            index_url=str(tmp_path), uv='/uv', python='/python',
            fallback_index_url='file:///nonexistent-hermetic-index')
    args, _texts = calls[0]
    # The directory still routes to find-links; the fallback only
    # keeps uv from defaulting to PyPI.
    assert '-f' in args
    assert args[args.index('--default-index') + 1] == (
        'file:///nonexistent-hermetic-index')


def test_fallback_index_fills_a_dropped_index_path(monkeypatch):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[],
            index_url='/no/such/index-dir', uv='/uv', python='/python',
            fallback_index_url='file:///nonexistent-hermetic-index')
    args, _texts = calls[0]
    assert args[args.index('--default-index') + 1] == (
        'file:///nonexistent-hermetic-index')


def test_fallback_index_never_shadows_a_remote_index(monkeypatch):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[],
            index_url='https://example.com/simple',
            uv='/uv', python='/python',
            fallback_index_url='file:///nonexistent-hermetic-index')
    args, _texts = calls[0]
    assert args[args.index('--default-index') + 1] == 'https://example.com/simple'
    assert 'file:///nonexistent-hermetic-index' not in args


def test_native_spelled_file_url_index_routes_to_find_links(
        monkeypatch, tmp_path):
    # The shape zc.buildout.testing exports in buildout_testing_index_url:
    # 'file://' + a native tempfile.mkdtemp() path, 'file://C:\...' on
    # Windows, where the drive letter lands in the URL netloc.
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[],
            index_url='file://' + str(tmp_path), uv='/uv', python='/python')
    args, _texts = calls[0]
    assert args[args.index('-f') + 1] == Path(str(tmp_path)).as_uri()
    assert '--default-index' not in args


def test_windows_drive_file_url_without_local_dir_falls_back(monkeypatch):
    # A drive-spelled file URL whose directory does not exist must not
    # crash the resolver; it falls back to --default-index like any file
    # URL that names no local directory.
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[],
            index_url='file://C:\\no\\such\\buildout-index',
            uv='/uv', python='/python')
    args, _texts = calls[0]
    assert args[args.index('--default-index') + 1] == (
        'file://C:\\no\\such\\buildout-index')
    assert '-f' not in args


def test_empty_file_url_falls_back_to_default_index(monkeypatch):
    calls = _record_run(monkeypatch)
    resolve(requirements=['demo'], constraints={}, links=[],
            index_url='file://', uv='/uv', python='/python')
    args, _texts = calls[0]
    assert args[args.index('--default-index') + 1] == 'file://'
    assert '-f' not in args


def test_first_wheel_is_url_when_wheels_exist(monkeypatch):
    pinned = _resolve_with_lock(monkeypatch, LOCK_TWO_PACKAGES)
    dist = pinned.dists[0]
    assert dist.name == 'demo-pkg'
    assert dist.version == '1.0'
    assert dist.url == (
        'https://files.example.com/demo_pkg-1.0-py3-none-any.whl')
    assert dist.sha256 == 'wheel-one'
    assert dist.sdist_url == 'https://files.example.com/demo_pkg-1.0.tar.gz'
    assert dist.sdist_sha256 == 'sdist-hash'


def test_sdist_only_package_uses_sdist_url(monkeypatch):
    pinned = _resolve_with_lock(monkeypatch, LOCK_TWO_PACKAGES)
    dist = pinned.dists[1]
    assert dist.url == dist.sdist_url == (
        'https://files.example.com/other-2.0.tar.gz')
    assert dist.sha256 == dist.sdist_sha256 == 'other-sdist'


def test_package_order_is_preserved(monkeypatch):
    pinned = _resolve_with_lock(monkeypatch, LOCK_TWO_PACKAGES)
    assert [dist.name for dist in pinned.dists] == ['demo-pkg', 'other']


def test_for_project_matches_canonicalized_name(monkeypatch):
    pinned = _resolve_with_lock(monkeypatch, LOCK_TWO_PACKAGES)
    for query in ('demo-pkg', 'Demo_Pkg', 'DEMO.PKG'):
        dist = pinned.for_project(query)
        assert dist is not None
        assert dist.version == '1.0'


def test_for_project_absent_returns_none(monkeypatch):
    pinned = _resolve_with_lock(monkeypatch, LOCK_TWO_PACKAGES)
    assert pinned.for_project('absent') is None


def test_directory_entry_parses_as_directory_pin(monkeypatch):
    pinned = _resolve_with_lock(monkeypatch, LOCK_DIRECTORY)
    dist = pinned.for_project('devpkg')
    assert dist is not None
    assert dist.directory == '/dev/pkg'
    assert dist.version == ''
    assert dist.url == ''
    assert dist.sha256 is None
    assert dist.sdist_url is None
    demo = pinned.for_project('demo')
    assert demo is not None
    assert demo.directory is None
    assert demo.url.endswith('.whl')


def test_directory_entry_without_path_raises(monkeypatch):
    with pytest.raises(ResolutionError) as excinfo:
        _resolve_with_lock(monkeypatch, LOCK_DIRECTORY_NO_PATH)
    assert 'directory entry' in str(excinfo.value)


def test_nonzero_returncode_raises_resolution_error(monkeypatch):
    _record_run(monkeypatch, returncode=1, stderr='boom')
    with pytest.raises(ResolutionError) as excinfo:
        resolve(requirements=['demo'], constraints={}, links=[],
                index_url=None, uv='/uv', python='/python')
    assert excinfo.value.stderr == 'boom'


def test_child_env_drops_ambient_uv_configuration(monkeypatch):
    for name in sorted(uv_resolve._SCRUBBED_ENV_VARS):
        monkeypatch.setenv(name, 'injected')
    monkeypatch.setenv('UV_CACHE_DIR', '/cache')
    env = uv_resolve._child_env()
    assert all(name not in env for name in uv_resolve._SCRUBBED_ENV_VARS)
    # UV_CACHE_DIR stays: it names the store offline resolves serve
    # from, not a source.
    assert env['UV_CACHE_DIR'] == '/cache'
    # The parent environment itself is untouched.
    assert os.environ['UV_INDEX_URL'] == 'injected'


def test_run_spawns_uv_with_the_scrubbed_environment(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args, 0, '', '')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    monkeypatch.setenv('UV_FIND_LINKS', '/nonexistent-ambient-links')
    uv_resolve._run(['/uv', 'pip', 'compile'])
    assert 'UV_FIND_LINKS' not in captured['env']
    assert captured['env'].get('PATH') == os.environ.get('PATH')


@requires_uv
def test_ambient_uv_find_links_do_not_leak_into_a_resolve(
        tmp_path, monkeypatch):
    # Before the scrub, an exported UV_FIND_LINKS silently added
    # sources to every resolve (probe p4b).
    assert UV is not None
    links_dir = tmp_path / 'links'
    links_dir.mkdir()
    _make_wheel(links_dir)
    monkeypatch.setenv('UV_FIND_LINKS', str(links_dir))
    monkeypatch.setenv('UV_CACHE_DIR', str(tmp_path / 'uv-cache'))
    with pytest.raises(ResolutionError):
        resolve(requirements=['demo'], constraints={}, links=[],
                index_url='file:///nonexistent-hermetic-index',
                uv=UV, python=sys.executable)


@requires_uv
def test_explicit_find_links_serve_after_the_scrub(tmp_path, monkeypatch):
    # A bogus ambient UV_INDEX_URL/UV_FIND_LINKS pair must not break a
    # resolve whose sources are all explicit.
    assert UV is not None
    links_dir = tmp_path / 'links'
    links_dir.mkdir()
    _make_wheel(links_dir)
    monkeypatch.setenv('UV_FIND_LINKS', '/nonexistent-ambient-links')
    monkeypatch.setenv('UV_INDEX_URL', 'https://index.example.invalid/')
    monkeypatch.setenv('UV_CACHE_DIR', str(tmp_path / 'uv-cache'))
    pinned = resolve(
        requirements=['demo'], constraints={}, links=[str(links_dir)],
        index_url='file:///nonexistent-hermetic-index',
        uv=UV, python=sys.executable)
    dist = pinned.for_project('demo')
    assert dist is not None
    assert dist.version == '1.0'


@requires_uv
def test_prefer_final_true_picks_the_stable_release(tmp_path, monkeypatch):
    # Probes p3/p7 parity: the links dir holds a stable and a
    # prerelease; prefer-final picks the stable one.
    assert UV is not None
    links_dir = tmp_path / 'links'
    links_dir.mkdir()
    _make_wheel(links_dir, version='1.0')
    _make_wheel(links_dir, version='2.0a1')
    monkeypatch.setenv('UV_CACHE_DIR', str(tmp_path / 'uv-cache'))
    pinned = resolve(
        requirements=['demo'], constraints={}, links=[str(links_dir)],
        index_url=None, offline=True, prefer_final=True,
        uv=UV, python=sys.executable)
    dist = pinned.for_project('demo')
    assert dist is not None
    assert dist.version == '1.0'


@requires_uv
def test_prefer_final_false_picks_the_prerelease(tmp_path, monkeypatch):
    # Probe p6 parity: prefer-final off lets uv select the prerelease.
    assert UV is not None
    links_dir = tmp_path / 'links'
    links_dir.mkdir()
    _make_wheel(links_dir, version='1.0')
    _make_wheel(links_dir, version='2.0a1')
    monkeypatch.setenv('UV_CACHE_DIR', str(tmp_path / 'uv-cache'))
    pinned = resolve(
        requirements=['demo'], constraints={}, links=[str(links_dir)],
        index_url=None, offline=True, prefer_final=False,
        uv=UV, python=sys.executable)
    dist = pinned.for_project('demo')
    assert dist is not None
    assert dist.version == '2.0a1'


@requires_uv
def test_real_uv_resolves_wheel_from_find_links(tmp_path, monkeypatch):
    assert UV is not None
    links_dir = tmp_path / 'links'
    links_dir.mkdir()
    _make_wheel(links_dir)
    monkeypatch.setenv('UV_CACHE_DIR', str(tmp_path / 'uv-cache'))
    pinned = resolve(
        requirements=['demo'], constraints={}, links=[str(links_dir)],
        index_url=None, offline=True, uv=UV, python=sys.executable)
    dist = pinned.for_project('demo')
    assert dist is not None
    assert dist.version == '1.0'
    assert dist.url.startswith('file:')


@requires_uv
def test_real_uv_unknown_package_raises_resolution_error(
        tmp_path, monkeypatch):
    assert UV is not None
    monkeypatch.setenv('UV_CACHE_DIR', str(tmp_path / 'uv-cache'))
    with pytest.raises(ResolutionError):
        resolve(
            requirements=['no-such-package-for-uv-resolve-tests'],
            constraints={}, links=[], index_url=None, offline=True,
            uv=UV, python=sys.executable)


def _fake_pinned(name='demo', version='1.0',
                 url='file:///wheels/demo-1.0-py3-none-any.whl',
                 sdist_url='file:///sdists/demo-1.0.tar.gz'):
    """A one-entry ``PinnedSet`` as ``resolve`` returns it."""
    return uv_resolve.PinnedSet((uv_resolve.PinnedDist(
        name=name, version=version, url=url, sha256=None,
        sdist_url=sdist_url, sdist_sha256=None),))


def _stub_resolve(monkeypatch, pinned=None, error=None):
    """Stub ``resolve`` and ``_uv_executable`` on the easy_install side."""
    calls = []

    def fake_resolve(**kwargs):
        calls.append(kwargs)
        if error is not None:
            raise error
        return pinned

    monkeypatch.setattr(uv_resolve, 'resolve', fake_resolve)
    monkeypatch.setattr(easy_install, '_uv_executable', lambda: '/uv')
    return calls


def test_uv_available_dists_returns_dist_with_url_location(monkeypatch):
    calls = _stub_resolve(monkeypatch, pinned=_fake_pinned())
    req = pkg_resources.Requirement.parse('demo')
    dists = easy_install._uv_available_dists(
        req, None, {'demo': '1.0'}, ['/links'], None, True)
    assert dists is not None
    [dist] = dists
    assert dist.location == 'file:///wheels/demo-1.0-py3-none-any.whl'
    assert dist.project_name == 'demo'
    assert dist.version == '1.0'
    assert dist in req
    kwargs = calls[0]
    assert kwargs['requirements'] == ['demo']
    assert kwargs['constraints'] == {'demo': '1.0'}
    assert kwargs['links'] == ['/links']
    assert kwargs['prefer_final'] is True
    assert kwargs['uv'] == '/uv'
    assert kwargs['python'] is sys.executable


def test_uv_available_dists_resolution_error_means_none(monkeypatch):
    _stub_resolve(monkeypatch,
                  error=ResolutionError('uv failed', 'boom'))
    req = pkg_resources.Requirement.parse('demo')
    assert easy_install._uv_available_dists(
        req, None, {}, [], None, True) is None


def test_uv_available_dists_missing_project_means_none(monkeypatch):
    _stub_resolve(monkeypatch, pinned=_fake_pinned(name='other'))
    req = pkg_resources.Requirement.parse('demo')
    assert easy_install._uv_available_dists(
        req, None, {}, [], None, True) is None


def test_uv_available_dists_source_uses_sdist_url(monkeypatch):
    _stub_resolve(monkeypatch, pinned=_fake_pinned())
    req = pkg_resources.Requirement.parse('demo')
    dists = easy_install._uv_available_dists(req, 1, {}, [], None, True)
    assert dists is not None
    [dist] = dists
    assert dist.location == 'file:///sdists/demo-1.0.tar.gz'


def test_uv_available_dists_source_without_sdist_means_none(monkeypatch):
    _stub_resolve(monkeypatch, pinned=_fake_pinned(sdist_url=None))
    req = pkg_resources.Requirement.parse('demo')
    assert easy_install._uv_available_dists(
        req, 1, {}, [], None, True) is None


# Eggs are invisible to uv; when they are all a local directory offers,
# the user deserves a better error than Couldn't-find-a-distribution.

def _lay_eggs(directory, *names):
    for name in names:
        (directory / name).write_text('not really an egg')


def test_egg_only_find_links_raise_user_error(monkeypatch, tmp_path):
    _stub_resolve(monkeypatch, error=ResolutionError('uv failed', 'boom'))
    _lay_eggs(tmp_path, 'spam-2-py3.12.egg')
    req = pkg_resources.Requirement.parse('spam')
    with pytest.raises(zc.buildout.UserError) as excinfo:
        easy_install._uv_available_dists(
            req, None, {}, [str(tmp_path)], None, True)
    message = str(excinfo.value)
    assert 'installer = uv' in message
    assert 'legacy .egg' in message
    assert str(tmp_path) in message
    assert 'installer = pip' in message


def test_egg_only_on_missing_project_too(monkeypatch, tmp_path):
    _stub_resolve(monkeypatch, pinned=_fake_pinned(name='other'))
    _lay_eggs(tmp_path, 'spam-1.0-py3.12.egg')
    req = pkg_resources.Requirement.parse('spam')
    with pytest.raises(zc.buildout.UserError):
        easy_install._uv_available_dists(
            req, None, {}, [str(tmp_path)], None, True)


def test_wheel_or_sdist_alongside_egg_keeps_plain_none(monkeypatch, tmp_path):
    _stub_resolve(monkeypatch, error=ResolutionError('uv failed', 'boom'))
    _lay_eggs(tmp_path, 'spam-2-py3.12.egg', 'spam-1.0-py3-none-any.whl')
    req = pkg_resources.Requirement.parse('spam')
    assert easy_install._uv_available_dists(
        req, None, {}, [str(tmp_path)], None, True) is None


def test_other_project_eggs_stay_plain_none(monkeypatch, tmp_path):
    _stub_resolve(monkeypatch, error=ResolutionError('uv failed', 'boom'))
    _lay_eggs(tmp_path, 'spam-extra-2-py3.12.egg', 'ham-1-py3.12.egg')
    req = pkg_resources.Requirement.parse('spam')
    assert easy_install._uv_available_dists(
        req, None, {}, [str(tmp_path)], None, True) is None


def test_remote_links_are_not_scanned_for_eggs(monkeypatch):
    _stub_resolve(monkeypatch, error=ResolutionError('uv failed', 'boom'))
    req = pkg_resources.Requirement.parse('spam')
    assert easy_install._uv_available_dists(
        req, None, {}, ['http://localhost:1/links'], None, True) is None


def test_egg_error_mentions_file_url_locations(monkeypatch, tmp_path):
    _stub_resolve(monkeypatch, error=ResolutionError('uv failed', 'boom'))
    _lay_eggs(tmp_path, 'spam-2-py3.12.egg')
    req = pkg_resources.Requirement.parse('spam')
    with pytest.raises(zc.buildout.UserError) as excinfo:
        easy_install._uv_available_dists(
            req, None, {}, [tmp_path.as_uri()], None, True)
    assert 'legacy .egg' in str(excinfo.value)


# pkg_resources adds `extra == "..."` markers to requirements pulled
# via extras; under --no-deps the marker has no context and uv would
# silently drop the requirement.

def test_extra_only_marker_is_stripped(monkeypatch):
    calls = _stub_resolve(monkeypatch, pinned=_fake_pinned())
    req = pkg_resources.Requirement.parse('demo; extra == "foo"')
    dists = easy_install._uv_available_dists(req, None, {}, [], None, True)
    assert dists is not None
    assert calls[0]['requirements'] == ['demo']


def test_trailing_extra_marker_is_stripped(monkeypatch):
    calls = _stub_resolve(monkeypatch, pinned=_fake_pinned())
    req = pkg_resources.Requirement.parse(
        'demo; python_version > "3" and extra == "foo"')
    dists = easy_install._uv_available_dists(req, None, {}, [], None, True)
    assert dists is not None
    assert calls[0]['requirements'] == ['demo; python_version > "3"']


def test_unrelated_markers_are_kept(monkeypatch):
    calls = _stub_resolve(monkeypatch, pinned=_fake_pinned())
    req = pkg_resources.Requirement.parse('demo; python_version < "3.10"')
    dists = easy_install._uv_available_dists(req, None, {}, [], None, True)
    assert dists is not None
    assert calls[0]['requirements'] == ['demo; python_version < "3.10"']
