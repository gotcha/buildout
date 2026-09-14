"""Unit tests for the pure helpers extracted from easy_install.call_pip_install."""
import logging
import sys

import pytest

from zc.buildout import easy_install
from zc.buildout.easy_install import (
    _dist_info_dirname,
    _installed_dist_name,
    _is_url,
    _pip_install_args,
    _run_pip,
    _scan_editable_install,
)

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


def test_run_pip_returns_output_and_forwards_call(monkeypatch):
    calls = []

    def fake_output(args, env=None):
        calls.append((args, env))
        return 'PIP OUTPUT'

    monkeypatch.setattr(easy_install, 'get_subprocess_output', fake_output)
    env = {'PYTHONPATH': '/x'}
    assert _run_pip(['pip', 'install'], env, '/dest', logging.INFO) == 'PIP OUTPUT'
    assert calls == [(['pip', 'install'], env)]


def test_run_pip_info_level_logs_nothing(monkeypatch, caplog):
    monkeypatch.setattr(
        easy_install, 'get_subprocess_output', lambda args, env=None: 'OUT')
    with caplog.at_level(logging.DEBUG, logger='zc.buildout.easy_install'):
        assert _run_pip(['pip'], {}, '/dest', logging.INFO) == 'OUT'
    assert caplog.records == []


def test_run_pip_debug_logs_output_and_dest_contents(
        tmp_path, monkeypatch, caplog):
    (tmp_path / 'demo-1.0.dist-info').mkdir()
    monkeypatch.setattr(
        easy_install, 'get_subprocess_output', lambda args, env=None: 'PIP OUT')
    with caplog.at_level(logging.DEBUG, logger='zc.buildout.easy_install'):
        assert _run_pip(['pip'], {}, str(tmp_path), logging.DEBUG) == 'PIP OUT'
    assert 'Running pip install' in caplog.text
    assert 'PIP OUT' in caplog.text
    assert 'Pip install completed successfully.' in caplog.text
    assert '- demo-1.0.dist-info' in caplog.text


def test_run_pip_debug_with_empty_output_skips_output_line(
        tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(
        easy_install, 'get_subprocess_output', lambda args, env=None: '')
    with caplog.at_level(logging.DEBUG, logger='zc.buildout.easy_install'):
        assert _run_pip(['pip'], {}, str(tmp_path), logging.DEBUG) == ''
    messages = [record.getMessage() for record in caplog.records]
    assert 'Pip install completed successfully.' in messages
    assert '' not in messages


def test_scan_editable_install_without_egg_link():
    entries = [('demo', '.dist-info'), ('demo-nspkg', '.pth')]
    assert _scan_editable_install(entries) == ('', None)


def test_scan_editable_install_egg_link_without_nspkg():
    entries = [('demo', '.egg-link'), ('demo-1.0', '.dist-info')]
    assert _scan_editable_install(entries) == ('demo', None)


def test_scan_editable_install_ignores_plain_pth():
    entries = [('demo', '.egg-link'), ('easy-install', '.pth')]
    assert _scan_editable_install(entries) == ('demo', None)


def test_scan_editable_install_first_egg_link_wins():
    entries = [('first', '.egg-link'), ('second', '.egg-link')]
    assert _scan_editable_install(entries) == ('first', None)


def test_scan_editable_install_namespace_single_name():
    entries = [('foo', '.egg-link'), ('foo-nspkg', '.pth')]
    assert _scan_editable_install(entries) == ('foo', '')


def test_scan_editable_install_namespace_one_dot():
    entries = [('a.b', '.egg-link'), ('a.b-nspkg', '.pth')]
    assert _scan_editable_install(entries) == ('a.b', 'a')


def test_scan_editable_install_namespace_two_dots():
    entries = [('a.b.c', '.egg-link'), ('a.b.c-nspkg', '.pth')]
    assert _scan_editable_install(entries) == ('a.b.c', 'a\na.b')


def test_scan_editable_install_namespace_capped_at_two_dots():
    entries = [('a.b.c.d', '.egg-link'), ('a.b.c.d-nspkg', '.pth')]
    assert _scan_editable_install(entries) == ('a.b.c.d', 'a\na.b')


def test_dist_info_dirname_returns_first_match():
    entries = [
        ('demo', '.egg-link'),
        ('demo-1.0', '.dist-info'),
        ('other-2.0', '.dist-info'),
    ]
    assert _dist_info_dirname(entries) == 'demo-1.0.dist-info'


def test_dist_info_dirname_raises_without_match():
    with pytest.raises(IndexError):
        _dist_info_dirname([('demo', '.egg-link')])


def test_installed_dist_name_reads_metadata(tmp_path):
    distinfo = tmp_path / 'demo-1.0.dist-info'
    distinfo.mkdir()
    (distinfo / 'METADATA').write_text(
        'Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n')
    assert _installed_dist_name(str(distinfo)) == 'demo'


def test_installed_dist_name_missing_name_returns_none(tmp_path):
    distinfo = tmp_path / 'demo-1.0.dist-info'
    distinfo.mkdir()
    (distinfo / 'METADATA').write_text('Metadata-Version: 2.1\nVersion: 1.0\n')
    assert _installed_dist_name(str(distinfo)) is None
