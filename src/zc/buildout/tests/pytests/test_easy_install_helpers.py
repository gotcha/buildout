"""Unit tests for the pure helpers extracted from easy_install.call_pip_install."""
import logging
import sys

from zc.buildout.easy_install import _is_url, _pip_install_args

BASE_ARGS = [sys.executable, '-m', 'pip', 'install', '--no-deps', '-t', '/dest']


def test_no_index_url():
    args = _pip_install_args('demo', '/dest', False, None, logging.INFO)
    assert args == BASE_ARGS + ['-q', 'demo']


def test_remote_index_becomes_extra_index_url():
    args = _pip_install_args(
        'demo', '/dest', False, 'https://example.com/simple', logging.INFO)
    assert args == BASE_ARGS + [
        '--extra-index-url', 'https://example.com/simple', '-q', 'demo']


def test_existing_directory_index_becomes_file_uri(tmp_path):
    args = _pip_install_args('demo', '/dest', False, str(tmp_path), logging.INFO)
    expected = tmp_path.expanduser().resolve().as_uri()
    assert args == BASE_ARGS + ['--extra-index-url', expected, '-q', 'demo']


def test_missing_directory_index_is_dropped():
    args = _pip_install_args(
        'demo', '/dest', False, '/no/such/index-dir', logging.INFO)
    assert '--extra-index-url' not in args
    assert args == BASE_ARGS + ['-q', 'demo']


def test_debug_log_level_selects_verbose():
    args = _pip_install_args('demo', '/dest', False, None, logging.DEBUG)
    assert args == BASE_ARGS + ['-v', 'demo']


def test_editable_flag_goes_before_spec():
    args = _pip_install_args('demo', '/dest', True, None, logging.INFO)
    assert args[-2:] == ['-e', 'demo']


def test_spec_is_always_last():
    args = _pip_install_args(
        'demo', '/dest', True, 'https://example.com/simple', logging.DEBUG)
    assert args[-1] == 'demo'


def test_windows_drive_path_is_not_a_url():
    assert not _is_url('C:\\index')
    assert not _is_url('C:/index')


def test_http_and_file_schemes_are_urls():
    assert _is_url('https://example.com/simple')
    assert _is_url('http://example.com/simple')
    assert _is_url('file:///srv/index')


def test_bare_paths_are_not_urls():
    assert not _is_url('/srv/index')
    assert not _is_url('index')
