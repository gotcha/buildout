"""Unit tests for the uv installer fork in zc.buildout.easy_install."""
import logging
import os
import subprocess
import sys
from pathlib import Path

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
        # hermeticity comes from a dead file: index URL.
        assert os.environ['UV_INDEX_URL'] == (
            'file:///nonexistent-hermetic-index')
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
        from packaging import specifiers
        instance = self._bare_installer('pip', {'demo': '{wtf}'})
        with pytest.raises(specifiers.InvalidSpecifier):
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
                           prefer_final, uv_stderr):
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
