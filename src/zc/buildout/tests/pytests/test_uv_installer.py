"""Unit tests for the uv installer fork in zc.buildout.easy_install."""
import logging
import os
import sys

import pytest

import zc.buildout
from zc.buildout import easy_install
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
        assert os.environ['UV_OFFLINE'] == '1'
        assert os.environ['UV_FIND_LINKS'].endswith('downloads/test-seed')
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
