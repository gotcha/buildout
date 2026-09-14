"""Unit tests for the pure helpers extracted from zc.buildout.easy_install."""
import logging
import sys

import pkg_resources
import pytest

import zc.buildout
from zc.buildout import easy_install
from zc.buildout.easy_install import (
    _dist_info_dirname,
    _installed_dist_name,
    _is_url,
    _parse_requirements,
    _pip_install_args,
    _resolve_extra_requirements,
    _run_pip,
    _scan_editable_install,
    _working_set_or_default,
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


def _make_dist(tmp_path, requires_txt=None):
    """Build a real ``demo 1.0`` distribution from a requires.txt body."""
    egg_info = tmp_path / 'demo.egg-info'
    egg_info.mkdir()
    (egg_info / 'PKG-INFO').write_text(
        'Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n')
    if requires_txt is not None:
        (egg_info / 'requires.txt').write_text(requires_txt)
    (dist,) = pkg_resources.find_distributions(str(tmp_path))
    return dist


def test_parse_requirements_parses_and_constrains_specs():
    constrained = []

    def constrain(requirement):
        constrained.append(requirement)
        return requirement

    requirements = _parse_requirements(['demo', 'other >= 1.0'], constrain)
    assert requirements == [
        pkg_resources.Requirement.parse('demo'),
        pkg_resources.Requirement.parse('other >= 1.0'),
    ]
    assert constrained == requirements


def test_parse_requirements_keeps_requirement_without_marker():
    requirements = _parse_requirements(['demo'], lambda r: r)
    assert requirements == [pkg_resources.Requirement.parse('demo')]


def test_parse_requirements_keeps_requirement_with_true_marker():
    requirements = _parse_requirements(
        ['demo; python_version >= "3.0"'], lambda r: r)
    assert requirements == [
        pkg_resources.Requirement.parse('demo; python_version >= "3.0"')]


def test_parse_requirements_drops_requirement_with_false_marker():
    constrained = []

    def constrain(requirement):
        constrained.append(requirement)
        return requirement

    requirements = _parse_requirements(
        ['demo; python_version < "1.0"'], constrain)
    assert requirements == []
    # The constraint applies only to surviving requirements.
    assert constrained == []


def test_working_set_or_default_returns_fresh_empty_set():
    ws = _working_set_or_default(None)
    assert isinstance(ws, pkg_resources.WorkingSet)
    assert ws.entries == []


def test_working_set_or_default_keeps_given_set():
    given = pkg_resources.WorkingSet([])
    assert _working_set_or_default(given) is given


def test_resolve_extra_requirements_without_extras_asks_dist(tmp_path):
    req = pkg_resources.Requirement.parse('demo')
    dist = _make_dist(tmp_path, 'dep1\ndep2 >= 1.0\n')
    assert _resolve_extra_requirements(req, dist, False) == [
        pkg_resources.Requirement.parse('dep2 >= 1.0'),
        pkg_resources.Requirement.parse('dep1'),
    ]


def test_resolve_extra_requirements_forwards_requested_extras(tmp_path):
    req = pkg_resources.Requirement.parse('demo[web]')
    dist = _make_dist(tmp_path, 'base-dep\n\n[web]\nweb-dep\n')
    # The base dependency alone would mean requires() got no extras.
    assert _resolve_extra_requirements(req, dist, False) == [
        pkg_resources.Requirement.parse('web-dep'),
        pkg_resources.Requirement.parse('base-dep'),
    ]


def test_resolve_extra_requirements_missing_extra_warns_and_intersects(
        tmp_path, caplog):
    req = pkg_resources.Requirement.parse('demo[web,nothere]')
    dist = _make_dist(tmp_path, '[web]\nweb-dep\n')
    with caplog.at_level(logging.WARNING, logger='zc.buildout.easy_install'):
        result = _resolve_extra_requirements(req, dist, True)
    assert result == ['web']
    assert "does not provide the extra 'nothere'" in caplog.text


def test_resolve_extra_requirements_missing_extra_rejected(tmp_path, caplog):
    req = pkg_resources.Requirement.parse('demo[nothere]')
    dist = _make_dist(tmp_path)
    with caplog.at_level(logging.WARNING, logger='zc.buildout.easy_install'):
        with pytest.raises(zc.buildout.UserError):
            _resolve_extra_requirements(req, dist, False)
    assert "does not provide the extra 'nothere'" in caplog.text
