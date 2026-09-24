"""Unit tests for the uv installer fork in zc.buildout.easy_install."""
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit
from urllib.request import url2pathname

import pkg_resources
import pytest

import zc.buildout
from zc.buildout import easy_install, uv_resolve
from zc.buildout.easy_install import (
    _extra_index_url,
    _pip_install_env,
    _uv_executable,
    _uv_install_args,
    _uv_sibling_executable,
)

UV_BASE_ARGS = [
    '/uv', 'pip', 'install', '--no-deps', '-t', '/dest',
    '--python', sys.executable,
]


def _record_install(monkeypatch):
    """Stub ``_run_pip``: record (args, env), leave a .dist-info in dest."""
    calls = []

    def fake_run_pip(args, env, dest, level):
        distinfo = os.path.join(dest, 'demo-1.0.dist-info')
        os.makedirs(distinfo, exist_ok=True)
        with open(os.path.join(distinfo, 'METADATA'), 'w') as f:
            f.write('Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n')
        calls.append((args, env))
        return ''

    monkeypatch.setattr(easy_install, '_run_pip', fake_run_pip)
    return calls


def test_uv_base_args_shape():
    args = _uv_install_args('/uv', 'demo', '/dest', False, None, logging.INFO)
    assert args == UV_BASE_ARGS + ['-q', 'demo']


def test_uv_debug_log_level_selects_verbose():
    args = _uv_install_args('/uv', 'demo', '/dest', False, None, logging.DEBUG)
    assert args == UV_BASE_ARGS + ['-v', 'demo']


def test_uv_editable_flag_goes_before_spec():
    args = _uv_install_args('/uv', 'demo', '/dest', True, None, logging.INFO)
    assert args[-2:] == ['-e', 'demo']


def test_uv_remote_index_becomes_extra_index_url():
    args = _uv_install_args(
        '/uv', 'demo', '/dest', False, 'https://example.com/simple',
        logging.INFO)
    assert args == UV_BASE_ARGS + [
        '-q', '--extra-index-url', 'https://example.com/simple', 'demo']


def test_uv_existing_directory_index_becomes_file_uri(tmp_path):
    args = _uv_install_args(
        '/uv', 'demo', '/dest', False, str(tmp_path), logging.INFO)
    expected = tmp_path.expanduser().resolve().as_uri()
    assert args == UV_BASE_ARGS + ['-q', '--extra-index-url', expected, 'demo']


def test_uv_missing_directory_index_is_dropped():
    args = _uv_install_args(
        '/uv', 'demo', '/dest', False, '/no/such/index-dir', logging.INFO)
    assert args == UV_BASE_ARGS + ['-q', 'demo']


def test_uv_args_never_carry_no_python_version_warning():
    for editable in (False, True):
        for level in (logging.DEBUG, logging.INFO):
            args = _uv_install_args(
                '/uv', 'demo', '/dest', editable,
                'https://example.com/simple', level)
            assert '--no-python-version-warning' not in args


def test_extra_index_url_is_shared_with_pip(tmp_path):
    # The directory-to-file:// conversion lives in one helper used by
    # both the pip and the uv args builders.
    assert _extra_index_url(None) is None
    assert _extra_index_url('/no/such/index-dir') is None
    assert _extra_index_url('https://example.com/simple') == (
        'https://example.com/simple')
    assert _extra_index_url(str(tmp_path)) == (
        tmp_path.expanduser().resolve().as_uri())


def test_dispatch_uv_uses_uv_args(monkeypatch, tmp_path):
    calls = _record_install(monkeypatch)
    monkeypatch.setattr(easy_install, '_uv_executable', lambda: '/uv')
    monkeypatch.setattr(easy_install.Installer, '_installer', 'uv')
    result = easy_install.call_pip_install('demo', str(tmp_path), editable=True)
    assert result == 'demo'
    args = calls[0][0]
    assert args[:2] == ['/uv', 'pip']
    assert '--python' in args


def test_dispatch_uv_skips_no_python_version_warning(monkeypatch, tmp_path):
    calls = _record_install(monkeypatch)
    monkeypatch.setattr(easy_install, '_uv_executable', lambda: '/uv')
    monkeypatch.setattr(easy_install.Installer, '_installer', 'uv')
    # The pip-only quirk records a one-shot 'displayed' attribute on
    # call_pip_install; it must never run on the uv path.
    monkeypatch.delattr(easy_install.call_pip_install, 'displayed',
                        raising=False)
    easy_install.call_pip_install('demo', str(tmp_path), editable=True)
    easy_install.call_pip_install('demo', str(tmp_path), editable=True)
    for args, env in calls:
        assert '--no-python-version-warning' not in args
    assert not hasattr(easy_install.call_pip_install, 'displayed')


def test_dispatch_pip_uses_pip_args_and_warning_quirk(monkeypatch, tmp_path):
    calls = _record_install(monkeypatch)
    monkeypatch.setattr(easy_install.Installer, '_installer', 'pip')
    monkeypatch.delattr(easy_install.call_pip_install, 'displayed',
                        raising=False)
    result = easy_install.call_pip_install('demo', str(tmp_path), editable=True)
    assert result == 'demo'
    args = calls[0][0]
    assert args[:3] == [sys.executable, '-m', 'pip']
    # One-shot quirk: the flag is appended from the second call on.
    assert '--no-python-version-warning' not in args
    easy_install.call_pip_install('demo', str(tmp_path), editable=True)
    args = calls[1][0]
    assert '--no-python-version-warning' in args


def test_pip_install_env_prepends_pip_path(monkeypatch):
    monkeypatch.setenv('PYTHONPATH', '/ambient')
    env = _pip_install_env()
    python_path = env['PYTHONPATH'].split(os.pathsep)
    assert python_path[:len(easy_install.pip_path)] == easy_install.pip_path
    assert python_path[-1] == '/ambient'


def test_dispatch_uv_passes_pythonpath_through_unchanged(
        monkeypatch, tmp_path):
    calls = _record_install(monkeypatch)
    monkeypatch.setattr(easy_install, '_uv_executable', lambda: '/uv')
    monkeypatch.setattr(easy_install.Installer, '_installer', 'uv')
    monkeypatch.setenv('PYTHONPATH', '/ambient')
    easy_install.call_pip_install('demo', str(tmp_path), editable=True)
    env = calls[0][1]
    assert env['PYTHONPATH'] == '/ambient'


def test_installer_getter_setter_round_trip(monkeypatch):
    monkeypatch.setattr(easy_install.Installer, '_installer', 'pip')
    assert easy_install.installer() == 'pip'
    assert easy_install.installer('uv') == 'pip'
    assert easy_install.installer() == 'uv'
    assert easy_install.installer('pip') == 'uv'
    assert easy_install.installer() == 'pip'


def test_installer_rejects_invalid_value(monkeypatch):
    monkeypatch.setattr(easy_install.Installer, '_installer', 'pip')
    with pytest.raises(zc.buildout.UserError) as excinfo:
        easy_install.installer('conda')
    message = str(excinfo.value)
    assert "'installer'" in message
    assert "'conda'" in message
    assert "'pip'" in message
    assert "'uv'" in message
    assert easy_install.installer() == 'pip'


def test_uv_executable_from_path(monkeypatch):
    monkeypatch.setattr(
        easy_install.shutil, 'which', lambda name: '/usr/bin/uv')
    assert _uv_executable() == '/usr/bin/uv'


def test_uv_executable_falls_back_to_sibling_of_python(
        monkeypatch, tmp_path):
    monkeypatch.setattr(easy_install.shutil, 'which', lambda name: None)
    sibling = tmp_path / 'uv'
    sibling.write_text('#!/bin/sh\n')
    sibling.chmod(0o755)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'python'))
    assert _uv_sibling_executable() == str(sibling)
    assert _uv_executable() == str(sibling)


def test_uv_sibling_executable_finds_uv_exe_on_windows(
        monkeypatch, tmp_path):
    # pip lays the uv console script down as uv.exe on Windows; a lookup
    # for the bare name misses the pip-installed binary there.
    monkeypatch.setattr(easy_install.shutil, 'which', lambda name: None)
    monkeypatch.setattr(sys, 'platform', 'win32')
    sibling = tmp_path / 'uv.exe'
    sibling.write_text('binary')
    sibling.chmod(0o755)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'python.exe'))
    assert _uv_sibling_executable() == str(sibling)
    assert _uv_executable() == str(sibling)


def test_uv_executable_missing_raises_user_error(monkeypatch, tmp_path):
    monkeypatch.setattr(easy_install.shutil, 'which', lambda name: None)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'python'))
    with pytest.raises(zc.buildout.UserError) as excinfo:
        _uv_executable()
    message = str(excinfo.value)
    assert "'installer'" in message
    assert "'uv'" in message


def test_hermetic_env_covers_uv_and_cleans_its_cache():
    # The seed must exist for the function to engage; the suite always
    # runs after prepare.sh created it.
    from zc.buildout import testing
    restore = testing.hermetic_pip_env()
    if restore is None:
        pytest.skip('downloads/test-seed absent (no prepare.sh run)')
    try:
        # uv honors no UV_NO_INDEX, and UV_OFFLINE would block the
        # corpus's localhost link server once uv does the resolving, so
        # hermeticity comes from a dead file: index URL.  uv converts
        # the URL back to a local path and rejects a drive-letterless
        # spelling outright on Windows ("Expected a file URL"), so the
        # dead index must spell a native path.  Anchoring it under the
        # fresh cache makes it nonexistent by construction.
        index_url = os.environ['UV_INDEX_URL']
        assert urlsplit(index_url).scheme == 'file'
        index_path = Path(url2pathname(urlsplit(index_url).path))
        assert index_path.is_absolute()
        assert not index_path.exists()
        assert index_path.parent == Path(os.environ['UV_CACHE_DIR'])
        # The seam fallback index feeds every in-process uv resolve the
        # same dead spelling; it must convert natively too.
        seam_url = os.environ['buildout_testing_seam_index_url']
        assert urlsplit(seam_url).scheme == 'file'
        seam_path = Path(url2pathname(urlsplit(seam_url).path))
        assert seam_path.is_absolute()
        assert not seam_path.exists()
        assert seam_path.parent == Path(os.environ['UV_CACHE_DIR'])
        # Not 'not in': an ambient UV_OFFLINE is the caller's own
        # business, the harness just must not force it.
        assert os.environ.get('UV_OFFLINE') != '1'
        assert os.environ['UV_FIND_LINKS'].endswith(
            os.path.join('downloads', 'test-seed'))
        cache = os.environ['UV_CACHE_DIR']
        assert os.path.isdir(cache)
        # uv's cache holds symlinked entries that doctest teardown cannot
        # rmtree; the redirect and its cleanup are what keep doc tests safe.
        link = os.path.join(cache, 'wheel-dir')
        os.symlink(cache, link)
    finally:
        restore()
    assert not os.path.exists(cache)
    assert os.environ.get('UV_CACHE_DIR') != cache


def test_drop_build_output_normalizer_is_mode_conditional(monkeypatch):
    from zc.buildout import testing
    text = 'Installing extdemo.\nHave environment test_environment_variable: foo\n'
    monkeypatch.setattr(easy_install.Installer, '_installer', 'pip')
    assert testing.drop_build_output_relayed_by_pip(text) == text
    monkeypatch.setattr(easy_install.Installer, '_installer', 'uv')
    assert testing.drop_build_output_relayed_by_pip(text) == (
        'Installing extdemo.\n')


def test_drop_uv_requests_normalizer_is_mode_conditional(monkeypatch):
    from zc.buildout import testing
    text = (
        'GET 200 /\n'
        'GET 404 /index/demo/\n'
        'HEAD 200 /demo-0.2-py3-none-any.whl\n'
        'GET 200 /demo-0.2-py3-none-any.whl\n'
        'GET 200 /demo-0.2-py3-none-any.whl\n'
        'GET 200 /demoneeded-1.1.tar.gz\n')
    monkeypatch.setattr(easy_install.Installer, '_installer', 'pip')
    assert testing.drop_uv_link_server_requests(text) == text
    monkeypatch.setattr(easy_install.Installer, '_installer', 'uv')
    assert testing.drop_uv_link_server_requests(text) == ''


def test_download_cache_deprecation_is_uv_only(monkeypatch, caplog):
    monkeypatch.setattr(easy_install.Installer, '_installer', 'pip')
    with caplog.at_level('WARNING', logger='zc.buildout.easy_install'):
        easy_install.download_cache('/some/dir')
    assert caplog.records == []
    monkeypatch.setattr(easy_install.Installer, '_installer', 'uv')
    with caplog.at_level('WARNING', logger='zc.buildout.easy_install'):
        easy_install.download_cache('/some/dir')
    assert len(caplog.records) == 1
    assert 'deprecated' in caplog.records[0].getMessage()
    assert 'download-cache' in caplog.records[0].getMessage()
    easy_install.download_cache(None)


def test_drop_deprecation_normalizer_is_mode_conditional(monkeypatch):
    from zc.buildout import testing
    text = ('Installing demo.\n'
            'With installer = uv the download-cache is not populated; '
            'the option is deprecated (uv keeps downloads in its own '
            'cache).\n')
    monkeypatch.setattr(easy_install.Installer, '_installer', 'pip')
    assert testing.drop_uv_download_cache_deprecation(text) == text
    monkeypatch.setattr(easy_install.Installer, '_installer', 'uv')
    assert testing.drop_uv_download_cache_deprecation(text) == (
        'Installing demo.\n')


class TestHgFindLinksGuard:
    """Mercurial find-links entries fail before uv is spawned."""

    def _forbid_resolve(self, monkeypatch):
        def resolve_must_not_run(*args, **kwargs):
            raise AssertionError('uv_resolve.resolve must not run')
        monkeypatch.setattr(
            easy_install.uv_resolve, 'resolve', resolve_must_not_run)

    def test_hg_plus_entry_raises_user_error(self, monkeypatch):
        self._forbid_resolve(monkeypatch)
        req = pkg_resources.Requirement.parse('demo')
        with pytest.raises(zc.buildout.UserError) as excinfo:
            easy_install._uv_available_dists(
                req, None, {}, ['hg+https://example.invalid/repo'], None,
                True)
        message = str(excinfo.value)
        assert 'installer = uv' in message
        assert 'hg+https://example.invalid/repo' in message
        assert 'wheel or sdist' in message
        assert 'installer = pip' in message

    def test_hg_scheme_entry_raises_user_error(self, monkeypatch):
        self._forbid_resolve(monkeypatch)
        req = pkg_resources.Requirement.parse('demo')
        with pytest.raises(zc.buildout.UserError) as excinfo:
            easy_install._uv_available_dists(
                req, None, {}, ['hg:ssh://example.invalid/repo'], None, True)
        assert 'hg:ssh://example.invalid/repo' in str(excinfo.value)

    def test_plain_entries_pass_the_guard(self, monkeypatch):
        def fail_resolve(**kwargs):
            raise easy_install.uv_resolve.ResolutionError('no', 'boom')
        monkeypatch.setattr(easy_install.uv_resolve, 'resolve', fail_resolve)
        req = pkg_resources.Requirement.parse('demo')
        assert easy_install._uv_available_dists(
            req, None, {},
            ['https://example.invalid/links', '/local/links'],
            None, True) is None


class TestFragmentFindLinksGuard:
    """``#egg=``/``#md5=`` fragments on find-links fail before uv runs."""

    def _forbid_resolve(self, monkeypatch):
        def resolve_must_not_run(*args, **kwargs):
            raise AssertionError('uv_resolve.resolve must not run')
        monkeypatch.setattr(
            easy_install.uv_resolve, 'resolve', resolve_must_not_run)

    def test_egg_fragment_raises_user_error(self, monkeypatch):
        self._forbid_resolve(monkeypatch)
        link = 'https://example.invalid/files/demo-1.0.tar.gz#egg=demo'
        req = pkg_resources.Requirement.parse('demo')
        with pytest.raises(zc.buildout.UserError) as excinfo:
            easy_install._uv_available_dists(
                req, None, {}, [link], None, True)
        message = str(excinfo.value)
        assert 'installer = uv' in message
        assert '#egg=' in message
        assert link in message
        assert 'wheel or sdist' in message
        assert 'installer = pip' in message

    def test_md5_fragment_raises_user_error(self, monkeypatch):
        self._forbid_resolve(monkeypatch)
        link = 'https://example.invalid/files/demo-1.0.tar.gz#md5=0123456789abcdef0123456789abcdef'
        req = pkg_resources.Requirement.parse('demo')
        with pytest.raises(zc.buildout.UserError) as excinfo:
            easy_install._uv_available_dists(
                req, None, {}, [link], None, True)
        message = str(excinfo.value)
        assert '#md5=' in message
        assert link in message

    def test_fragment_free_entries_pass_the_guard(self, monkeypatch):
        def fail_resolve(**kwargs):
            raise easy_install.uv_resolve.ResolutionError('no', 'boom')
        monkeypatch.setattr(easy_install.uv_resolve, 'resolve', fail_resolve)
        req = pkg_resources.Requirement.parse('demo')
        assert easy_install._uv_available_dists(
            req, None, {},
            ['https://example.invalid/files/demo-1.0.tar.gz'],
            None, True) is None


class TestUvResolveRequirements:
    """The multi-requirement resolve seam behind ``_uv_available_dists``."""

    def test_requirements_reach_resolve_in_order(self, monkeypatch):
        captured = {}

        def fake_resolve(**kwargs):
            captured.update(kwargs)
            return uv_resolve.PinnedSet(())

        monkeypatch.setattr(uv_resolve, 'resolve', fake_resolve)
        reqs = [pkg_resources.Requirement.parse('demo'),
                pkg_resources.Requirement.parse('other')]
        result = easy_install._uv_resolve_requirements(
            reqs, {'demo': '1.0'}, ['https://example.invalid/links'],
            'https://example.invalid/index', False, offline=True,
            fallback_index_url='https://example.invalid/fallback')
        assert result is not None
        assert captured['requirements'] == ['demo', 'other']
        assert captured['constraints'] == {'demo': '1.0'}
        assert captured['links'] == ['https://example.invalid/links']
        assert captured['index_url'] == 'https://example.invalid/index'
        assert captured['prefer_final'] is False
        assert captured['offline'] is True
        assert (captured['fallback_index_url']
                == 'https://example.invalid/fallback')

    def test_overrides_reach_resolve_verbatim(self, monkeypatch):
        captured = {}

        def fake_resolve(**kwargs):
            captured.update(kwargs)
            return uv_resolve.PinnedSet(())

        monkeypatch.setattr(uv_resolve, 'resolve', fake_resolve)
        result = easy_install._uv_resolve_requirements(
            [pkg_resources.Requirement.parse('demo')], {}, [], None, True,
            overrides=['devpkg @ file:///dev/pkg'])
        assert result is not None
        assert captured['overrides'] == ['devpkg @ file:///dev/pkg']

    def test_resolve_error_returns_none_and_notes_stderr(self, monkeypatch):
        def fail_resolve(**kwargs):
            raise uv_resolve.ResolutionError('no', 'first\n\nsecond\nthird')
        monkeypatch.setattr(uv_resolve, 'resolve', fail_resolve)
        tail = []
        result = easy_install._uv_resolve_requirements(
            [pkg_resources.Requirement.parse('demo')], {}, [], None, True,
            tail)
        assert result is None
        assert tail == ['second', 'third']

    def test_guard_fails_on_a_later_requirement(self, monkeypatch):
        def resolve_must_not_run(*args, **kwargs):
            raise AssertionError('uv_resolve.resolve must not run')
        monkeypatch.setattr(uv_resolve, 'resolve', resolve_must_not_run)
        reqs = [pkg_resources.Requirement.parse('demo'),
                pkg_resources.Requirement.parse('other')]
        with pytest.raises(zc.buildout.UserError) as excinfo:
            easy_install._uv_resolve_requirements(
                reqs, {}, ['hg+https://example.invalid/repo'], None, True)
        assert 'hg+https://example.invalid/repo' in str(excinfo.value)


class TestJunkVersionsHardening:
    """Junk [versions] entries no longer abort unrelated uv resolutions."""

    LOCK = '''\
lock-version = "1.0"
created-by = "uv"

[[packages]]
name = "demo"
version = "1.0"

[[packages.wheels]]
url = "https://files.example.com/demo-1.0-py3-none-any.whl"
hashes = { sha256 = "aaaa" }
'''

    def _record_constraints(self, monkeypatch):
        """Stub ``uv_resolve._run``; return a box for the constraints text."""
        box = {}

        def fake_run(args):
            if '-c' in args:
                box['constraints'] = Path(
                    args[args.index('-c') + 1]).read_text()
            Path(args[args.index('-o') + 1]).write_text(self.LOCK)
            return subprocess.CompletedProcess(args, 0, '', '')

        monkeypatch.setattr(uv_resolve, '_run', fake_run)
        return box

    def _resolve(self, requirements, constraints):
        return uv_resolve.resolve(
            requirements=requirements, constraints=constraints,
            links=[], index_url=None, uv='/uv', python=sys.executable)

    def test_junk_for_other_project_is_skipped_with_warning(
            self, monkeypatch, caplog):
        box = self._record_constraints(monkeypatch)
        with caplog.at_level('WARNING', logger='zc.buildout.uv_resolve'):
            pinned = self._resolve(['demo'], {'wtf': '{wtf}'})
        assert pinned.for_project('demo').version == '1.0'
        # No valid line survives, so no constraints file reaches uv.
        assert 'constraints' not in box
        assert len(caplog.records) == 1
        message = caplog.records[0].getMessage()
        assert 'wtf' in message
        assert '{wtf}' in message

    def test_valid_lines_survive_alongside_junk(self, monkeypatch, caplog):
        box = self._record_constraints(monkeypatch)
        with caplog.at_level('WARNING', logger='zc.buildout.uv_resolve'):
            self._resolve(['demo'], {'demo': '1.0', 'wtf': '{wtf}'})
        assert box['constraints'] == 'demo==1.0\n'
        assert len(caplog.records) == 1

    def test_empty_pin_is_skipped_like_pip(self, monkeypatch, caplog):
        # Installer._constrain skips a falsy [versions] value, so pip
        # mode treats an empty pin as no pin at all, without a warning.
        box = self._record_constraints(monkeypatch)
        with caplog.at_level('WARNING', logger='zc.buildout.uv_resolve'):
            pinned = self._resolve(['demo'], {'demo': '', 'wtf': '{wtf}'})
        assert pinned.for_project('demo').version == '1.0'
        assert 'constraints' not in box
        assert len(caplog.records) == 1  # only the junk warning for wtf

    def test_junk_for_resolved_project_raises_parity_error(
            self, monkeypatch):
        def resolve_must_not_run(args):
            raise AssertionError('uv must not be spawned')
        monkeypatch.setattr(uv_resolve, '_run', resolve_must_not_run)
        with pytest.raises(
                easy_install.IncompatibleConstraintError) as excinfo:
            self._resolve(['demo'], {'demo': '{wtf}'})
        assert str(excinfo.value) == (
            "The requirement ('demo') is not allowed"
            " by your [versions] constraint ({wtf})")

    def test_junk_match_is_canonicalized(self, monkeypatch):
        monkeypatch.setattr(
            uv_resolve, '_run',
            lambda args: (_ for _ in ()).throw(AssertionError('no uv')))
        with pytest.raises(easy_install.IncompatibleConstraintError):
            self._resolve(['Demo'], {'demo': '{wtf}'})

    def _bare_installer(self, installer, versions):
        instance = easy_install.Installer.__new__(easy_install.Installer)
        instance._installer = installer
        instance._versions = versions
        instance._requirements_and_constraints = ()
        return instance

    def test_constrain_reports_junk_pin_in_uv_mode(self):
        instance = self._bare_installer('uv', {'demo': '{wtf}'})
        with pytest.raises(
                easy_install.IncompatibleConstraintError) as excinfo:
            instance._constrain(pkg_resources.Requirement.parse('demo>=1'))
        assert str(excinfo.value) == (
            "The requirement ('demo>=1') is not allowed"
            " by your [versions] constraint ({wtf})")

    def test_constrain_ignores_junk_for_other_projects(self):
        instance = self._bare_installer('uv', {'wtf': '{wtf}'})
        req = pkg_resources.Requirement.parse('demo')
        assert instance._constrain(req) == req

    def test_constrain_pip_mode_keeps_invalid_specifier(self):
        # Legacy pip-mode behavior depends on the setuptools in use:
        # 69.5.1 raises IncompatibleConstraintError from the old
        # containment check, other pins let the junk escape as
        # InvalidSpecifier. Both predate the uv junk hardening; pip
        # mode keeps whichever legacy error comes out.
        from packaging import specifiers
        instance = self._bare_installer('pip', {'demo': '{wtf}'})
        with pytest.raises(
                (specifiers.InvalidSpecifier,
                 easy_install.IncompatibleConstraintError)):
            instance._constrain(pkg_resources.Requirement.parse('demo'))


class TestErrorTranslation:
    """uv failures surface in buildout vocabulary, never as raw errors."""

    def test_parse_lock_missing_url_raises_resolution_error(self):
        with pytest.raises(uv_resolve.ResolutionError) as excinfo:
            uv_resolve._parse_lock({'packages': [
                {'name': 'demo', 'version': '1.0', 'wheels': [{}]}]})
        message = str(excinfo.value)
        assert 'pylock.toml' in message
        assert "'url'" in message
        assert 'demo' in message

    def test_parse_lock_missing_name_raises_resolution_error(self):
        with pytest.raises(uv_resolve.ResolutionError) as excinfo:
            uv_resolve._parse_lock({'packages': [
                {'version': '1.0',
                 'sdist': {'url': 'https://x/demo-1.0.tar.gz'}}]})
        message = str(excinfo.value)
        assert 'pylock.toml' in message
        assert "'name'" in message

    def test_resolve_translates_invalid_toml(self, monkeypatch):
        def fake_run(args):
            Path(args[args.index('-o') + 1]).write_text('not [valid toml')
            return subprocess.CompletedProcess(args, 0, '', 'shim stderr')
        monkeypatch.setattr(uv_resolve, '_run', fake_run)
        with pytest.raises(uv_resolve.ResolutionError) as excinfo:
            uv_resolve.resolve(
                requirements=['demo'], constraints={}, links=[],
                index_url=None, uv='/uv', python=sys.executable)
        assert 'pylock.toml' in str(excinfo.value)
        assert excinfo.value.stderr == 'shim stderr'

    def test_uv_available_dists_captures_stderr_tail(self, monkeypatch):
        def fail_resolve(**kwargs):
            raise uv_resolve.ResolutionError('no', 'first\n\nsecond\nthird')
        monkeypatch.setattr(uv_resolve, 'resolve', fail_resolve)
        tail = []
        result = easy_install._uv_available_dists(
            pkg_resources.Requirement.parse('demo'), None, {}, [], None,
            True, tail)
        assert result is None
        assert tail == ['second', 'third']

    def test_stderr_tail_skips_blank_lines(self):
        assert easy_install._stderr_tail('one\n\n two \nthree\n') == [
            ' two ', 'three']

    def test_missing_distribution_without_detail_is_unchanged(self):
        err = easy_install.MissingDistribution(
            pkg_resources.Requirement.parse('demo'),
            pkg_resources.WorkingSet([]))
        assert str(err) == "Couldn't find a distribution for 'demo'."

    def test_missing_distribution_carries_uv_stderr_tail(self):
        err = easy_install.MissingDistribution(
            pkg_resources.Requirement.parse('demo'),
            pkg_resources.WorkingSet([]),
            detail='error: No solution found\nBecause demo was not found')
        assert str(err) == (
            "Couldn't find a distribution for 'demo'.\n"
            '  uv: error: No solution found\n'
            '  uv: Because demo was not found')

    def test_fetch_new_dists_passes_detail_to_missing_distribution(
            self, tmp_path):
        with pytest.raises(easy_install.MissingDistribution) as excinfo:
            easy_install._fetch_new_dists(
                pkg_resources.Requirement.parse('demo'), None,
                pkg_resources.WorkingSet([]), str(tmp_path), None,
                lambda *args: None, pkg_resources.Environment([]),
                lambda: None, detail='Because demo was not found')
        assert '  uv: Because demo was not found' in str(excinfo.value)

    def test_obtain_collects_uv_stderr_tail(self, monkeypatch):
        instance = easy_install.Installer.__new__(easy_install.Installer)
        instance._installer = 'uv'
        instance._index_url = None
        instance._versions = {}
        instance._links = []
        instance._prefer_final = True
        instance._uv_stderr_tail = None

        def fake_available(requirement, source, versions, links, index_url,
                           prefer_final, uv_stderr, offline=False,
                           fallback_index_url=None):
            uv_stderr.append('Because demo was not found')
            return None
        monkeypatch.setattr(
            easy_install, '_uv_available_dists', fake_available)
        req = pkg_resources.Requirement.parse('demo')
        assert instance._obtain(req) is None
        assert instance._uv_stderr_tail == 'Because demo was not found'

    def test_drop_uv_resolution_stderr_tail_is_mode_conditional(
            self, monkeypatch):
        from zc.buildout import testing
        text = ("Error: Couldn't find a distribution for 'demo'.\n"
                '  uv: Because demo was not found\n')
        monkeypatch.setattr(easy_install.Installer, '_installer', 'pip')
        assert testing.drop_uv_resolution_stderr_tail(text) == text
        monkeypatch.setattr(easy_install.Installer, '_installer', 'uv')
        assert testing.drop_uv_resolution_stderr_tail(text) == (
            "Error: Couldn't find a distribution for 'demo'.\n")


def test_drop_uv_getting_got_lines_is_mode_conditional(monkeypatch):
    from zc.buildout import testing
    text = ("Installing eggs.\n"
            "Getting distribution for 'demo'.\n"
            'Got demo 0.3.\n'
            'While:\n'
            '  Installing eggs.\n'
            "  Getting distribution for 'demo'.\n"
            "Error: Couldn't find a distribution for 'demo'.\n"
            'zc.buildout.easy_install INFO\n'
            "  Getting distribution for 'other'.\n"
            'zc.buildout.easy_install INFO\n'
            '  Got other 1.0.\n')
    monkeypatch.setattr(easy_install.Installer, '_installer', 'pip')
    assert testing.drop_uv_getting_got_lines(text) == text
    monkeypatch.setattr(easy_install.Installer, '_installer', 'uv')
    # Bare INFO lines drop; the While-block activity line stays.
    assert testing.drop_uv_getting_got_lines(text) == (
        'Installing eggs.\n'
        'While:\n'
        '  Installing eggs.\n'
        "  Getting distribution for 'demo'.\n"
        "Error: Couldn't find a distribution for 'demo'.\n")
    # A bare line that a While-block immediately replays stays: both
    # modes emit it on the error path, and the expectation's `...`
    # slack ahead of the While-block needs a line to chew on.
    echoed = ("Installing eggs.\n"
              "Getting distribution for 'kss.core'.\n"
              'While:\n'
              '  Installing eggs.\n'
              "  Getting distribution for 'kss.core'.\n"
              "Error: Couldn't find a distribution for 'kss.core'.\n")
    assert testing.drop_uv_getting_got_lines(echoed) == echoed
    # A bare line ahead of a While-block that does not replay it
    # drops like any other.
    unechoed = ("Installing eggs.\n"
                "Getting distribution for 'demo'.\n"
                'While:\n'
                '  Installing eggs.\n'
                'Error: something else.\n')
    assert testing.drop_uv_getting_got_lines(unechoed) == (
        'Installing eggs.\n'
        'While:\n'
        '  Installing eggs.\n'
        'Error: something else.\n')
    # uv's resolve chatter (Using uv ..., the could-not-resolve block)
    # logs between the bare line and its While: replay; the sibling
    # droppers own those lines, but they run later in the checker
    # chain, so the keep-rule must see past them or the slack line
    # ahead of a trailing ellipsis is lost (GH run 35833561014).
    chatter = ("Installing eggs.\n"
               "Getting distribution for 'demoneeded'.\n"
               'Using uv 0.12.11 (aarch64-apple-darwin) (/nix/store/uv)\n'
               "uv could not resolve 'demoneeded':\n"
               '  × No solution found when resolving dependencies:\n'
               '  ╰─▶ Because demoneeded was not found in the registry\n'
               'While:\n'
               '  Installing eggs.\n'
               "  Getting distribution for 'demoneeded'.\n"
               "Error: Couldn't find a distribution for 'demoneeded'.\n")
    assert testing.drop_uv_getting_got_lines(chatter) == (
        'Installing eggs.\n'
        "Getting distribution for 'demoneeded'.\n"
        'While:\n'
        '  Installing eggs.\n'
        "  Getting distribution for 'demoneeded'.\n"
        "Error: Couldn't find a distribution for 'demoneeded'.\n")


def test_drop_uv_install_debug_chatter_is_mode_conditional(monkeypatch):
    from zc.buildout import testing
    text = ("zc.buildout.easy_install DEBUG\n"
            "  Installing 'demo'.\n"
            'zc.buildout.easy_install DEBUG\n'
            '  Running pip install:\n'
            '"/nix/store/uv" "pip" "install" "--no-deps" "-t" "/tmp/x"\n'
            'PYTHONPATH=/nix/store/sitecustomize.py\n'
            '\n'
            'Using CPython 3.12.6 interpreter at: /usr/bin/python3\n'
            'Resolved 2 packages in 3ms\n'
            '   Building demoneeded @ http://localhost/demoneeded.tar.gz\n'
            '      Built demoneeded @ http://localhost/demoneeded.tar.gz\n'
            'Installed 2 packages in 1ms\n'
            ' + demo==0.3 (from http://localhost/demo-0.3-py3-none-any.whl)\n'
            '\n'
            'Pip install completed successfully.\n'
            'Contents of /tmp/x:\n'
            ' - .lock\n'
            ' - demo-0.3.dist-info\n'
            'Making egg in /tmp/x from pip installation in demo-0.3.dist-info\n'
            'No namespace __init__.py files found.\n'
            'zc.buildout.easy_install DEBUG\n'
            '  Picked: demo = 0.3\n'
            'zc.buildout.easy_install DEBUG\n'
            '  Fetching demo 0.3 from: http://localhost/demo-0.3.whl\n'
            'zc.buildout.easy_install DEBUG\n'
            '  Turning dist demo 0.3 into egg, and moving to eggs dir.\n')
    monkeypatch.setattr(easy_install.Installer, '_installer', 'pip')
    assert testing.drop_uv_install_debug_chatter(text) == text
    monkeypatch.setattr(easy_install.Installer, '_installer', 'uv')
    assert testing.drop_uv_install_debug_chatter(text) == (
        "zc.buildout.easy_install DEBUG\n"
        "  Installing 'demo'.\n"
        'zc.buildout.easy_install DEBUG\n'
        '  Picked: demo = 0.3\n')


def test_drop_uv_install_debug_chatter_drops_windows_argv(monkeypatch):
    from zc.buildout import testing
    # The relayed argv line of the Running-pip-install record starts
    # with the quoted uv path.  On Windows that is a drive-letter path
    # ("D:/..."), which the continuation rule's posix-only `"/` did not
    # match, so the argv leaked into the transcript (GH run
    # 35921276587, Windows leg).
    text = ("zc.buildout.easy_install DEBUG\n"
            "  Installing 'demo'.\n"
            'zc.buildout.easy_install DEBUG\n'
            '  Running pip install:\n'
            '"D:/a/buildout/buildout/venvs/python/Scripts/uv.exe" "pip"'
            ' "install" "--no-deps" "-t" "/sample-install/tmpxyz"'
            ' "--python" "D:/a/buildout/buildout/venvs/python/Scripts'
            '/python3.exe" "-v"'
            ' "http://localhost:21748/demo-0.3-py3-none-any.whl"\n'
            'PYTHONPATH=\n'
            '\n'
            'zc.buildout.easy_install DEBUG\n'
            '  Picked: demo = 0.3\n')
    monkeypatch.setattr(easy_install.Installer, '_installer', 'pip')
    assert testing.drop_uv_install_debug_chatter(text) == text
    monkeypatch.setattr(easy_install.Installer, '_installer', 'uv')
    assert testing.drop_uv_install_debug_chatter(text) == (
        "zc.buildout.easy_install DEBUG\n"
        "  Installing 'demo'.\n"
        'zc.buildout.easy_install DEBUG\n'
        '  Picked: demo = 0.3\n')


def test_drop_uv_install_debug_chatter_drops_leveled_uv_log(monkeypatch):
    from zc.buildout import testing
    # uv relays its own leveled internal log (``DEBUG ...``, ``WARN
    # ...``) into the -v transcript when the ambient environment cranks
    # its tracing (RUST_LOG=debug reproduces the easy_install.txt
    # log-handler flood of GH run 35850441947).  The leveled lines are
    # uv internals too: they join the chatter families the dropper
    # removes, or the doctest transcript depends on the host's logging
    # environment.
    text = ("zc.buildout.easy_install DEBUG\n"
            "  Installing 'demo'.\n"
            'zc.buildout.easy_install DEBUG\n'
            '  DEBUG Searching for user configuration in:'
            ' `/home/runner/.config/uv/uv.toml`\n'
            'DEBUG uv 0.12.11 (x86_64-unknown-linux-gnu)\n'
            'DEBUG Checking for Python interpreter at path'
            ' `/usr/bin/python3`\n'
            'DEBUG Using `--target` directory at /sample-install/tmpxyz\n'
            'DEBUG Adding direct dependency: demo*\n'
            'WARN Range requests not supported for'
            ' demo-0.3-py3-none-any.whl; streaming wheel\n'
            '   Building demoneeded @ http://localhost/demoneeded.tar.gz\n'
            '      Built demoneeded @ http://localhost/demoneeded.tar.gz\n'
            'DEBUG Failed to reflink `/cache/setuptools.dist-info/LICENSE`'
            ' to `/tmp/x`: Operation not supported (os error 95),'
            ' falling back\n'
            'zc.buildout.easy_install DEBUG\n'
            '  Picked: demo = 0.3\n')
    monkeypatch.setattr(easy_install.Installer, '_installer', 'pip')
    assert testing.drop_uv_install_debug_chatter(text) == text
    monkeypatch.setattr(easy_install.Installer, '_installer', 'uv')
    assert testing.drop_uv_install_debug_chatter(text) == (
        "zc.buildout.easy_install DEBUG\n"
        "  Installing 'demo'.\n"
        'zc.buildout.easy_install DEBUG\n'
        '  Picked: demo = 0.3\n')


def test_drop_uv_resolution_narrative_is_mode_conditional(monkeypatch):
    from zc.buildout import testing
    text = ("Installing 'demo'.\n"
            "Getting required 'demoneeded'\n"
            '  required by demo 0.3.\n'
            'We have a develop egg: devpkg 0.1\n'
            'zc.buildout.easy_install DEBUG\n'
            "  Getting required 'other'\n"
            'zc.buildout.easy_install DEBUG\n'
            '    required by demo 0.3.\n'
            "uv could not resolve 'pack5':\n"
            '  \u00d7 No solution found when resolving dependencies:\n'
            '  \u2570\u2500\u25b6 Because pack5 was not found in the package'
            ' registry and you require\n'
            '      pack5, your requirements are unsatisfiable.\n'
            '\n'
            'While:\n'
            '  Installing eggs.\n')
    monkeypatch.setattr(easy_install.Installer, '_installer', 'pip')
    assert testing.drop_uv_resolution_narrative(text) == text
    monkeypatch.setattr(easy_install.Installer, '_installer', 'uv')
    # The develop-egg line stays: both modes emit it, and dropping
    # lines wholesale can starve `...`-delimited anchors of slack.
    assert testing.drop_uv_resolution_narrative(text) == (
        "Installing 'demo'.\n"
        'We have a develop egg: devpkg 0.1\n'
        'While:\n'
        '  Installing eggs.\n')


def _capture_obtain_offline(monkeypatch, dest, **class_attrs):
    """Run ``Installer._obtain`` against a stub seam; return what it
    forwarded as the ``offline`` argument."""
    instance = easy_install.Installer.__new__(easy_install.Installer)
    instance._installer = 'uv'
    instance._index_url = None
    instance._versions = {}
    instance._links = []
    instance._prefer_final = True
    instance._uv_stderr_tail = None
    instance._dest = dest
    captured = {}

    def fake_available(requirement, source, versions, links, index_url,
                       prefer_final, uv_stderr, offline=False,
                       fallback_index_url=None):
        captured['offline'] = offline
        return None
    monkeypatch.setattr(easy_install, '_uv_available_dists', fake_available)
    for name, value in class_attrs.items():
        monkeypatch.setattr(easy_install.Installer, name, value)
    req = pkg_resources.Requirement.parse('demo')
    assert instance._obtain(req) is None
    return captured['offline']


class TestOfflineForwarding:
    """buildout -o reaches the uv seam as ``--offline``."""

    def test_buildout_offline_option_reaches_the_seam(self, monkeypatch,
                                                      tmp_path):
        assert _capture_obtain_offline(
            monkeypatch, str(tmp_path), _offline=True) is True

    def test_no_destination_alone_does_not_forward_offline(
            self, monkeypatch):
        # A None destination is the API-level no-install mode; it keeps
        # its own semantics and does not put --offline on the uv argv.
        assert _capture_obtain_offline(
            monkeypatch, None, _offline=False) is False

    def test_online_run_does_not_forward_offline(self, monkeypatch, tmp_path):
        assert _capture_obtain_offline(
            monkeypatch, str(tmp_path), _offline=False) is False

    def test_pip_mode_never_forwards_offline(self, monkeypatch):
        # Pip mode keeps its historical no-install offline semantics:
        # the flag only exists on the uv branch.
        instance = easy_install.Installer.__new__(easy_install.Installer)
        instance._installer = 'pip'
        # never read: _available_dists below is stubbed
        instance._index = None  # ty: ignore[invalid-assignment]
        monkeypatch.setattr(easy_install.Installer, '_offline', True)
        seen = []

        def fake_available_dists(index, requirement, source):
            seen.append(requirement)
            return None
        monkeypatch.setattr(
            easy_install, '_available_dists', fake_available_dists)
        req = pkg_resources.Requirement.parse('demo')
        assert instance._obtain(req) is None
        assert seen == [req]

    def test_uv_available_dists_forwards_offline_to_resolve(
            self, monkeypatch):
        seen = {}

        def fake_resolve(**kwargs):
            seen.update(kwargs)
            raise uv_resolve.ResolutionError('no')
        monkeypatch.setattr(uv_resolve, 'resolve', fake_resolve)
        result = easy_install._uv_available_dists(
            pkg_resources.Requirement.parse('demo'), None, {}, [], None,
            True, offline=True)
        assert result is None
        assert seen['offline'] is True

    def test_uv_available_dists_defaults_to_online(self, monkeypatch):
        seen = {}

        def fake_resolve(**kwargs):
            seen.update(kwargs)
            raise uv_resolve.ResolutionError('no')
        monkeypatch.setattr(uv_resolve, 'resolve', fake_resolve)
        result = easy_install._uv_available_dists(
            pkg_resources.Requirement.parse('demo'), None, {}, [], None,
            True)
        assert result is None
        assert seen['offline'] is False

    def test_offline_setter_round_trip(self, monkeypatch):
        monkeypatch.setattr(easy_install.Installer, '_offline', False)
        assert easy_install.offline() is False
        assert easy_install.offline(True) is False
        assert easy_install.offline() is True


class TestInstallFromCacheMapping:
    """install-from-cache maps onto uv's own cache through --offline."""

    def test_install_from_cache_resolves_offline(self, monkeypatch,
                                                 tmp_path):
        assert _capture_obtain_offline(
            monkeypatch, str(tmp_path), _offline=False,
            _install_from_cache=True) is True

    def test_uv_install_from_cache_keeps_links_and_index(
            self, monkeypatch, tmp_path):
        # The pip-mode download-cache restriction has no uv equivalent:
        # uv serves from its own cache, so the configured sources stay.
        monkeypatch.setattr(easy_install.Installer, '_installer', 'uv')
        monkeypatch.setattr(
            easy_install.Installer, '_install_from_cache', True)
        monkeypatch.setattr(easy_install.Installer, '_download_cache', None)
        installer = easy_install.Installer(
            dest=str(tmp_path / 'eggs'),
            links=('https://example.com/links',),
            index='https://example.com/simple')
        assert list(installer._links) == ['https://example.com/links']
        assert installer._index_url == 'https://example.com/simple'

    def test_pip_install_from_cache_still_requires_download_cache(
            self, monkeypatch, tmp_path):
        monkeypatch.setattr(easy_install.Installer, '_installer', 'pip')
        monkeypatch.setattr(
            easy_install.Installer, '_install_from_cache', True)
        monkeypatch.setattr(easy_install.Installer, '_download_cache', None)
        with pytest.raises(ValueError, match='no download cache'):
            easy_install.Installer(dest=str(tmp_path / 'eggs'))


def _capture_obtain_sources(monkeypatch, index_url=None):
    """Run ``Installer._obtain`` against a stub seam; return what it
    forwarded as ``links``, ``index_url`` and ``fallback_index_url``."""
    instance = easy_install.Installer.__new__(easy_install.Installer)
    instance._installer = 'uv'
    instance._index_url = index_url
    instance._versions = {}
    instance._links = ['https://example.com/configured-links']
    instance._prefer_final = True
    instance._uv_stderr_tail = None
    instance._dest = None
    captured = {}

    def fake_available(requirement, source, versions, links, index_url,
                       prefer_final, uv_stderr, offline=False,
                       fallback_index_url=None):
        captured.update(links=list(links), index_url=index_url,
                        fallback_index_url=fallback_index_url)
        return None
    monkeypatch.setattr(easy_install, '_uv_available_dists', fake_available)
    req = pkg_resources.Requirement.parse('demo')
    assert instance._obtain(req) is None
    return captured


class TestSeamTestingSources:
    """The hermetic harness feeds uv resolves through seam env vars."""

    def test_seam_links_join_and_index_falls_back(self, monkeypatch):
        monkeypatch.setenv(
            'buildout_testing_seam_find_links', '/seed /other-seed')
        monkeypatch.setenv(
            'buildout_testing_seam_index_url',
            'file:///nonexistent-hermetic-index')
        captured = _capture_obtain_sources(monkeypatch)
        assert captured['links'] == [
            'https://example.com/configured-links', '/seed',
            '/other-seed']
        # An unset configured index keeps the default fallback; the
        # seam index goes as the fallback that plugs the PyPI hole.
        assert captured['index_url'] == easy_install.default_index_url
        assert captured['fallback_index_url'] == (
            'file:///nonexistent-hermetic-index')

    def test_seam_index_never_shadows_a_configured_index(
            self, monkeypatch):
        monkeypatch.setenv(
            'buildout_testing_seam_index_url',
            'file:///nonexistent-hermetic-index')
        captured = _capture_obtain_sources(
            monkeypatch, index_url='https://example.com/simple')
        assert captured['index_url'] == 'https://example.com/simple'

    def test_seam_env_vars_unset_mean_no_injection(self, monkeypatch):
        monkeypatch.delenv('buildout_testing_seam_find_links',
                           raising=False)
        monkeypatch.delenv('buildout_testing_seam_index_url',
                           raising=False)
        captured = _capture_obtain_sources(monkeypatch)
        assert captured['links'] == ['https://example.com/configured-links']
        assert captured['fallback_index_url'] is None

    def test_pip_mode_never_consults_the_seam_vars(self, monkeypatch):
        monkeypatch.setenv(
            'buildout_testing_seam_find_links', '/seed')
        monkeypatch.setenv(
            'buildout_testing_seam_index_url',
            'file:///nonexistent-hermetic-index')
        instance = easy_install.Installer.__new__(easy_install.Installer)
        instance._installer = 'pip'
        # Passed to the _available_dists stub below, never dereferenced.
        instance._index = cast(Any, None)
        seen = []

        def fake_available_dists(index, requirement, source):
            seen.append((index, requirement))
            return None
        monkeypatch.setattr(
            easy_install, '_available_dists', fake_available_dists)
        req = pkg_resources.Requirement.parse('demo')
        assert instance._obtain(req) is None
        assert seen == [(None, req)]


class TestAllowHostsWarning:
    """A non-default allow-hosts warns under uv: uv has no host filter."""

    def _check(self, monkeypatch, caplog, allow_hosts, installer):
        from zc.buildout import buildout as buildout_module
        monkeypatch.setattr(easy_install.Installer, '_installer', installer)
        logger = logging.getLogger('zc.buildout')
        with caplog.at_level('WARNING', logger='zc.buildout'):
            buildout_module._check_allow_hosts_with_uv(allow_hosts, logger)
        return caplog.records

    def test_non_default_allow_hosts_warns_under_uv(
            self, monkeypatch, caplog):
        records = self._check(monkeypatch, caplog, ('example.com',), 'uv')
        assert len(records) == 1
        message = records[0].getMessage()
        assert 'allow-hosts' in message
        assert 'installer = uv' in message

    def test_default_allow_hosts_is_silent_under_uv(
            self, monkeypatch, caplog):
        assert self._check(monkeypatch, caplog, ('*',), 'uv') == []

    def test_non_default_allow_hosts_is_silent_under_pip(
            self, monkeypatch, caplog):
        assert self._check(
            monkeypatch, caplog, ('example.com',), 'pip') == []


class TestPypircWarning:
    """installer = uv warns when ~/.pypirc exists: uv reads ~/.netrc.

    The home directory is patched through both HOME and USERPROFILE:
    ``os.path.expanduser`` reads HOME on POSIX but only USERPROFILE on
    Windows.
    """

    def test_warns_when_pypirc_exists(self, monkeypatch, caplog, tmp_path):
        (tmp_path / '.pypirc').write_text('[pypi]\n')
        monkeypatch.setenv('HOME', str(tmp_path))
        monkeypatch.setenv('USERPROFILE', str(tmp_path))
        monkeypatch.setattr(easy_install.Installer, '_installer', 'pip')
        with caplog.at_level('WARNING', logger='zc.buildout.easy_install'):
            easy_install.installer('uv')
        assert len(caplog.records) == 1
        message = caplog.records[0].getMessage()
        assert '.pypirc' in message
        assert '.netrc' in message
        assert easy_install.installer() == 'uv'

    def test_silent_when_pypirc_absent(self, monkeypatch, caplog, tmp_path):
        monkeypatch.setenv('HOME', str(tmp_path))
        monkeypatch.setenv('USERPROFILE', str(tmp_path))
        monkeypatch.setattr(easy_install.Installer, '_installer', 'pip')
        with caplog.at_level('WARNING', logger='zc.buildout.easy_install'):
            easy_install.installer('uv')
        assert caplog.records == []

    def test_silent_when_setting_pip(self, monkeypatch, caplog, tmp_path):
        (tmp_path / '.pypirc').write_text('[pypi]\n')
        monkeypatch.setenv('HOME', str(tmp_path))
        monkeypatch.setenv('USERPROFILE', str(tmp_path))
        monkeypatch.setattr(easy_install.Installer, '_installer', 'uv')
        with caplog.at_level('WARNING', logger='zc.buildout.easy_install'):
            easy_install.installer('pip')
        assert caplog.records == []


def _make_dist(
    project_name: str = 'demo',
    version: str = '0.3',
    precedence: int = pkg_resources.EGG_DIST,
) -> pkg_resources.Distribution:
    """Fabricate the dist the install step would have produced."""
    return pkg_resources.Distribution(
        project_name=project_name, version=version, precedence=precedence)


def _capture_get_dist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    installer_mode: str,
    requirement_text: str = 'demo',
    precedence: int = pkg_resources.EGG_DIST,
    allow_picked: bool = True,
) -> tuple[easy_install.Installer, list, list[logging.LogRecord]]:
    """Run ``Installer._get_dist`` with the seam and the install step
    stubbed; return the installer, the installed dists, and the records
    logged on ``zc.buildout.easy_install``.

    The stubbed seam (``_uv_available_dists`` or ``_available_dists``)
    offers one dist, so selection flows through ``_obtain`` exactly as in
    a real run, and the reporting in ``_get_dist`` sees the seam's pick.
    """
    monkeypatch.setattr(easy_install.Installer, '_installer', installer_mode)
    monkeypatch.setattr(
        easy_install.Installer, '_allow_picked_versions', allow_picked)
    monkeypatch.setattr(easy_install.Installer, '_picked_versions', {})
    monkeypatch.delenv('buildout_testing_seam_find_links', raising=False)
    monkeypatch.delenv('buildout_testing_seam_index_url', raising=False)
    dist = _make_dist(precedence=precedence)
    if installer_mode == 'uv':
        monkeypatch.setattr(
            easy_install, '_uv_available_dists',
            lambda *args, **kwargs: [dist])
    else:
        monkeypatch.setattr(
            easy_install, '_available_dists',
            lambda index, requirement, source: [dist])

    def fake_fetch_new_dists(requirement, avail, ws, dest, download_cache,
                             fetch, env, rescan_dest, detail=None):
        # The dist the seam picked is the dist that gets installed.
        assert avail is dist
        return [dist]

    monkeypatch.setattr(easy_install, '_fetch_new_dists', fake_fetch_new_dists)
    installer = easy_install.Installer(dest=str(tmp_path))
    requirement = pkg_resources.Requirement.parse(requirement_text)
    ws = pkg_resources.WorkingSet([])
    with caplog.at_level('DEBUG', logger='zc.buildout.easy_install'):
        dists = installer._get_dist(requirement, ws)
    return installer, dists, caplog.records


class TestPickedVersionsParity:
    """uv mode reports picked versions exactly like pip mode.

    The corpus (tests/easy_install.txt, tests/repeatable.txt) already
    runs these scenarios in both modes.  These tests lock the wiring at
    unit level, so a future refactor of the uv seam cannot drop the
    picked-version report without a failure here.
    """

    def test_uv_reports_picked_version(
            self, monkeypatch, tmp_path, caplog):
        installer, dists, records = _capture_get_dist(
            monkeypatch, tmp_path, caplog, 'uv')
        assert 'Picked: demo = 0.3' in [r.getMessage() for r in records]
        assert installer._picked_versions == {'demo': '0.3'}
        assert [d.version for d in dists] == ['0.3']

    def test_pip_reports_picked_version(
            self, monkeypatch, tmp_path, caplog):
        installer, dists, records = _capture_get_dist(
            monkeypatch, tmp_path, caplog, 'pip')
        assert 'Picked: demo = 0.3' in [r.getMessage() for r in records]
        assert installer._picked_versions == {'demo': '0.3'}
        assert [d.version for d in dists] == ['0.3']

    def test_uv_not_allowed_raises_with_guidance(
            self, monkeypatch, tmp_path, caplog):
        with pytest.raises(zc.buildout.UserError) as excinfo:
            _capture_get_dist(
                monkeypatch, tmp_path, caplog, 'uv', allow_picked=False)
        assert str(excinfo.value) == (
            easy_install.NOT_PICKED_AND_NOT_ALLOWED.format(
                name='demo', version='0.3'))

    def test_uv_and_pip_raise_identical_message(
            self, monkeypatch, tmp_path, caplog):
        messages = []
        for mode in ('uv', 'pip'):
            dest = tmp_path / mode
            dest.mkdir()
            with pytest.raises(zc.buildout.UserError) as excinfo:
                _capture_get_dist(
                    monkeypatch, dest, caplog, mode, allow_picked=False)
            messages.append(str(excinfo.value))
        assert messages[0] == messages[1]
        assert messages[0] == (
            easy_install.NOT_PICKED_AND_NOT_ALLOWED.format(
                name='demo', version='0.3'))

    def test_uv_pinned_requirement_is_not_picked(
            self, monkeypatch, tmp_path, caplog):
        installer, _dists, records = _capture_get_dist(
            monkeypatch, tmp_path, caplog, 'uv',
            requirement_text='demo ==0.3')
        assert [r.getMessage() for r in records
                if 'Picked' in r.getMessage()] == []
        assert installer._picked_versions == {}

    def test_uv_develop_dist_is_not_picked(
            self, monkeypatch, tmp_path, caplog):
        installer, _dists, records = _capture_get_dist(
            monkeypatch, tmp_path, caplog, 'uv',
            precedence=pkg_resources.DEVELOP_DIST)
        assert [r.getMessage() for r in records
                if 'Picked' in r.getMessage()] == []
        assert installer._picked_versions == {}
