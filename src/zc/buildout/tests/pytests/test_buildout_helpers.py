"""Unit tests for the pure helpers extracted from zc.buildout.buildout."""
import logging
import os
from typing import Dict, Union

import pkg_resources
import pytest

import zc.buildout
import zc.buildout.easy_install
from zc.buildout.buildout import (
    Options,
    SectionKey,
    _absolutize_cache_dirs,
    _absolutize_standard_dirs,
    _apply_cl_extends,
    _buildout_default_options,
    _check_install_from_cache,
    _cloptions_dict,
    _create_cache_dirs,
    _default_versions,
    _develop_source_dir,
    _filename_for_logging,
    _finalize_installed_options,
    _links_and_hosts,
    _load_config,
    _load_user_defaults,
    _log_part_option_changes,
    _merge_config_data,
    _merged_updated_files,
    _new_develop_eggs,
    _normalize_installed_files,
    _part_is_up_to_date,
    _pin_buildout_version,
    _previous_develop_links,
    _print_configuration_data,
    _record_installed_part,
    _resolve_config_file,
    _resolve_config_location,
    _save_or_update_installed,
    _setup_download_cache,
    _split_parts,
    _uninstall_stale_parts,
    _update_part,
    _update_recipe_callable,
    _use_default_options,
    _validated_extends_cache,
    _version_eggs_directory,
)


def test_extends_cache_absent():
    assert _validated_extends_cache({}) is None


def test_extends_cache_plain_value_passes():
    assert _validated_extends_cache({'extends-cache': '/tmp/cache'}) == '/tmp/cache'


def test_extends_cache_empty_string_passes():
    assert _validated_extends_cache({'extends-cache': ''}) == ''


def test_extends_cache_with_substitution_rejected():
    with pytest.raises(ValueError):
        _validated_extends_cache(
            {'extends-cache': '${buildout:directory}/cache'})


def test_resolve_url_filename_downloads_with_url_base():
    filename, base, needs_download = _resolve_config_location(
        'ignored', 'http://example.com/buildout.cfg')
    assert filename == 'http://example.com/buildout.cfg'
    assert base == 'http://example.com'
    assert needs_download


def test_resolve_url_base_with_absolute_filename_opens_local():
    absolute = os.path.abspath(os.path.join(os.sep, 'abs', 'local.cfg'))
    filename, base, needs_download = _resolve_config_location(
        'http://example.com/configs', absolute)
    assert filename == absolute
    assert base == os.path.dirname(absolute)
    assert not needs_download


def test_resolve_url_base_with_relative_filename_downloads():
    filename, base, needs_download = _resolve_config_location(
        'http://example.com/configs', 'sub.cfg')
    assert filename == 'http://example.com/configs/sub.cfg'
    assert base == 'http://example.com/configs'
    assert needs_download


def test_resolve_local_base_joins_filename():
    filename, base, needs_download = _resolve_config_location(
        'base-dir', 'sub.cfg')
    assert filename == os.path.join('base-dir', 'sub.cfg')
    assert base == 'base-dir'
    assert not needs_download


def test_resolve_local_base_with_absolute_filename():
    absolute = os.path.abspath(os.path.join(os.sep, 'abs', 'local.cfg'))
    filename, base, needs_download = _resolve_config_location(
        'base-dir', absolute)
    assert filename == absolute
    assert base == os.path.dirname(absolute)
    assert not needs_download


def test_filename_for_logging_without_download():
    assert _filename_for_logging('buildout.cfg', None) == 'buildout.cfg'


def test_filename_for_logging_with_download():
    assert _filename_for_logging(
        'http://example.com/b.cfg', '/tmp/tmp123'
        ) == 'http://example.com/b.cfg (downloaded as /tmp/tmp123)'


def test_merge_config_data_empty_list():
    assert _merge_config_data([]) == {}


def test_merge_config_data_single_result():
    eresult = {'buildout': {'a': SectionKey('1', 'one.cfg')}}
    merged = _merge_config_data([eresult])
    assert merged['buildout']['a'].value == '1'
    assert merged['buildout']['a'].source == 'one.cfg'


def test_merge_config_data_later_file_wins():
    first = {'buildout': {'a': SectionKey('1', 'one.cfg'),
                          'b': SectionKey('x', 'one.cfg')}}
    second = {'buildout': {'b': SectionKey('y', 'two.cfg')},
              'extra': {'c': SectionKey('z', 'two.cfg')}}
    merged = _merge_config_data([first, second])
    assert merged['buildout']['a'].value == '1'
    assert merged['buildout']['b'].value == 'y'
    assert merged['buildout']['b'].source == 'two.cfg'
    assert merged['extra']['c'].value == 'z'


def test_develop_source_dir_plain_directory_is_unchanged():
    assert _develop_source_dir('/x/y/proj') == '/x/y/proj'


def test_develop_source_dir_src_layout_resolves_to_parent(tmp_path):
    src = tmp_path / 'proj' / 'src'
    src.mkdir(parents=True)
    (tmp_path / 'proj' / 'setup.py').touch()
    assert _develop_source_dir(str(src)) == str(tmp_path / 'proj')


def test_develop_source_dir_src_layout_accepts_any_metadata_name(tmp_path):
    for name in ('setup.py', 'setup.cfg', 'pyproject.toml'):
        proj = tmp_path / name.replace('.', '_')
        src = proj / 'src'
        src.mkdir(parents=True)
        (proj / name).touch()
        assert _develop_source_dir(str(src)) == str(proj)


def test_develop_source_dir_src_without_parent_metadata_is_unchanged(tmp_path):
    src = tmp_path / 'proj' / 'src'
    src.mkdir(parents=True)
    assert _develop_source_dir(str(src)) == str(src)


def test_develop_source_dir_metadata_in_src_wins_over_parent(tmp_path):
    src = tmp_path / 'proj' / 'src'
    src.mkdir(parents=True)
    (tmp_path / 'proj' / 'setup.py').touch()
    (src / 'pyproject.toml').touch()
    assert _develop_source_dir(str(src)) == str(src)


def test_develop_source_dir_flat_layout_in_dir_named_src(tmp_path):
    # A flat layout in a directory itself called 'src' holds its metadata
    # in that directory, so it is its own source directory.
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'setup.py').touch()
    assert _develop_source_dir(str(src)) == str(src)


def test_previous_develop_links_empty_input():
    assert _previous_develop_links('', lambda f: f) == {}


def test_previous_develop_links_skips_non_egg_link_entries():
    assert _previous_develop_links('foo.txt\nbar', lambda f: f) == {}


def test_previous_develop_links_skips_missing_files(tmp_path):
    missing = str(tmp_path / 'demo.egg-link')
    assert _previous_develop_links(missing, lambda f: f) == {}


def test_previous_develop_links_maps_real_source_to_link(tmp_path):
    project = tmp_path / 'demo'
    project.mkdir()
    link = tmp_path / 'demo.egg-link'
    link.write_text(str(project) + '\n')
    result = _previous_develop_links(str(link), lambda f: f)
    assert result == {os.path.realpath(str(project)): str(link)}


def test_previous_develop_links_applies_buildout_path(tmp_path):
    project = tmp_path / 'demo'
    project.mkdir()
    (tmp_path / 'demo.egg-link').write_text(str(project) + '\n')
    result = _previous_develop_links(
        'demo.egg-link', lambda f: os.path.join(str(tmp_path), f))
    assert result == {
        os.path.realpath(str(project)): str(tmp_path / 'demo.egg-link')}


def test_previous_develop_links_src_layout_uses_parent(tmp_path):
    project = tmp_path / 'demo'
    src = project / 'src'
    src.mkdir(parents=True)
    (project / 'pyproject.toml').touch()
    link = tmp_path / 'demo.egg-link'
    link.write_text(str(src) + '\n')
    result = _previous_develop_links(str(link), lambda f: f)
    assert result == {os.path.realpath(str(project)): str(link)}


def test_previous_develop_links_mixed_entries_and_blank_lines(tmp_path):
    project = tmp_path / 'demo'
    project.mkdir()
    link = tmp_path / 'demo.egg-link'
    link.write_text(str(project) + '\n')
    listing = '\n'.join(['', 'not-a-link.txt', str(link), ''])
    result = _previous_develop_links(listing, lambda f: f)
    assert result == {os.path.realpath(str(project)): str(link)}


def test_new_develop_eggs_nothing_new(tmp_path):
    (tmp_path / 'old.egg-link').touch()
    assert _new_develop_eggs(str(tmp_path), ['old.egg-link']) == ''


def test_new_develop_eggs_empty_directory(tmp_path):
    assert _new_develop_eggs(str(tmp_path), []) == ''


def test_new_develop_eggs_one_new_file(tmp_path):
    (tmp_path / 'old.egg-link').touch()
    (tmp_path / 'demo.egg-link').touch()
    assert _new_develop_eggs(str(tmp_path), ['old.egg-link']) == str(
        tmp_path / 'demo.egg-link')


def test_new_develop_eggs_lists_only_new_files(tmp_path):
    (tmp_path / 'old.egg-link').touch()
    (tmp_path / 'one.egg-link').touch()
    (tmp_path / 'two.egg-link').touch()
    result = _new_develop_eggs(str(tmp_path), ['old.egg-link'])
    assert set(result.split('\n')) == {
        str(tmp_path / 'one.egg-link'), str(tmp_path / 'two.egg-link')}


def _failing_init(config_file, args):
    raise AssertionError('init_config must not be called')


def test_resolve_config_file_none_stays_none():
    assert _resolve_config_file(None, None, (), _failing_init) == (None, None)


def test_resolve_config_file_url_is_untouched():
    url = 'http://example.com/buildout.cfg'
    assert _resolve_config_file(url, None, (), _failing_init) == (url, None)


def test_resolve_config_file_existing_file(tmp_path):
    cfg = tmp_path / 'buildout.cfg'
    cfg.write_text('[buildout]\n')
    config_file, directory = _resolve_config_file(
        str(cfg), None, (), _failing_init)
    assert config_file == os.path.abspath(str(cfg))
    assert directory is not None
    assert directory.value == os.path.dirname(os.path.abspath(str(cfg)))
    assert directory.source == 'COMPUTED_VALUE'


def test_resolve_config_file_missing_raises(tmp_path):
    with pytest.raises(zc.buildout.UserError, match="Couldn't open"):
        _resolve_config_file(
            str(tmp_path / 'missing.cfg'), None, (), _failing_init)


def test_resolve_config_file_missing_init_creates(tmp_path):
    cfg = tmp_path / 'buildout.cfg'
    calls = []
    config_file, directory = _resolve_config_file(
        str(cfg), 'init', ('arg',), lambda f, a: calls.append((f, a)))
    assert calls == [(os.path.abspath(str(cfg)), ('arg',))]
    assert config_file == os.path.abspath(str(cfg))
    assert directory is not None
    assert directory.value == os.path.dirname(os.path.abspath(str(cfg)))


def test_resolve_config_file_missing_setup_roots_at_cwd(tmp_path):
    config_file, directory = _resolve_config_file(
        str(tmp_path / 'buildout.cfg'), 'setup', (), _failing_init)
    assert config_file is None
    assert directory is not None
    assert directory.value == '.'
    assert directory.source == 'COMPUTED_VALUE'


def test_resolve_config_file_existing_init_raises(tmp_path):
    cfg = tmp_path / 'buildout.cfg'
    cfg.write_text('[buildout]\n')
    with pytest.raises(zc.buildout.UserError, match='already exists'):
        _resolve_config_file(str(cfg), 'init', (), _failing_init)


def test_cloptions_dict_empty():
    assert _cloptions_dict([]) == {}


def test_cloptions_dict_groups_by_section():
    result = _cloptions_dict([
        ('buildout', 'newest', 'false'),
        ('buildout', 'parts', 'demo'),
        ('versions', 'demo', '1.0'),
    ])
    assert set(result) == {'buildout', 'versions'}
    assert result['buildout']['parts'].value == 'demo'
    assert result['buildout']['newest'].source == 'COMMAND_LINE_VALUE'
    assert result['versions']['demo'].value == '1.0'


def test_load_user_defaults_disabled_returns_copy():
    data = {'buildout': {'eggs-directory': SectionKey('eggs', 'DEFAULT_VALUE')}}
    user_defaults, for_download_options = _load_user_defaults(False, data, {})
    assert user_defaults == {}
    assert for_download_options['buildout']['eggs-directory'].value == 'eggs'
    assert for_download_options['buildout'] is not data['buildout']


def test_load_user_defaults_missing_config_returns_copy(
        tmp_path, monkeypatch):
    monkeypatch.setenv('BUILDOUT_HOME', str(tmp_path))
    user_defaults, for_download_options = _load_user_defaults(
        True, {'buildout': {}}, {})
    assert user_defaults == {}
    assert for_download_options == {'buildout': {}}


def test_load_user_defaults_merges_user_config(tmp_path, monkeypatch):
    monkeypatch.setenv('BUILDOUT_HOME', str(tmp_path))
    (tmp_path / 'default.cfg').write_text(
        '[buildout]\neggs-directory = /user/eggs\n')
    data = {'buildout': {'eggs-directory': SectionKey('eggs', 'DEFAULT_VALUE')}}
    user_defaults, for_download_options = _load_user_defaults(True, data, {})
    assert user_defaults['buildout']['eggs-directory'].value == '/user/eggs'
    merged = for_download_options['buildout']['eggs-directory']
    assert merged.value == '/user/eggs'


def test_load_config_updates_data(tmp_path):
    cfg = tmp_path / 'buildout.cfg'
    cfg.write_text('[buildout]\neggs-directory = /cfg/eggs\nparts = demo\n')
    data = {'buildout': {'eggs-directory': SectionKey('eggs', 'DEFAULT_VALUE')}}
    result = _load_config(
        data, str(tmp_path), str(cfg), {'buildout': {}}, {}, {})
    assert result['buildout']['eggs-directory'].value == '/cfg/eggs'
    assert result['buildout']['parts'].value == 'demo'
    # the input data is not mutated
    assert data['buildout']['eggs-directory'].value == 'eggs'


def test_apply_cl_extends_without_buildout_section_is_noop():
    data = {'buildout': {}}
    assert _apply_cl_extends(data, {}, {'buildout': {}}, {}, {}) is data


def test_apply_cl_extends_without_extends_option_is_noop():
    data = {'buildout': {}}
    cloptions = {'buildout': {'parts': SectionKey('demo', 'COMMAND_LINE_VALUE')}}
    assert _apply_cl_extends(
        data, cloptions, {'buildout': {}}, {}, {}) is data
    assert 'parts' in cloptions['buildout']


def test_apply_cl_extends_loads_file_and_pops_option(tmp_path):
    ext = tmp_path / 'base.cfg'
    ext.write_text('[buildout]\neggs-directory = /ext/eggs\n')
    cloptions = {'buildout': {'extends': SectionKey(str(ext), 'COMMAND_LINE_VALUE')}}
    result = _apply_cl_extends(
        {'buildout': {}}, cloptions, {'buildout': {}}, {}, {})
    assert result['buildout']['eggs-directory'].value == '/ext/eggs'
    assert 'extends' not in cloptions['buildout']


def test_default_versions_adds_section_and_pins():
    data: dict = {'buildout': {}}
    name, versions = _default_versions(data)
    assert name == 'versions'
    assert data['buildout']['versions'].value == 'versions'
    assert data['versions'] is versions
    assert versions['zc.buildout'].value.startswith('>=')
    assert versions['zc.buildout'].source == 'DEFAULT_VALUE'
    assert versions['zc.recipe.egg'].value == '>=2.0.6'


def test_default_versions_keeps_named_section_and_pins():
    data = {
        'buildout': {'versions': SectionKey('my-versions', 'buildout.cfg')},
        'my-versions': {'zc.recipe.egg': SectionKey('1.0', 'buildout.cfg')},
    }
    name, versions = _default_versions(data)
    assert name == 'my-versions'
    assert versions is data['my-versions']
    # an existing pin is not overwritten
    assert versions['zc.recipe.egg'].value == '1.0'
    assert versions['zc.buildout'].value.startswith('>=')


def test_default_versions_empty_section_name_uses_plain_dict():
    data = {'buildout': {'versions': SectionKey('', 'buildout.cfg')}}
    name, versions = _default_versions(data)
    assert name == ''
    assert versions['zc.buildout'].value.startswith('>=')
    assert versions['zc.recipe.egg'].value == '>=2.0.6'


class _StubDist:
    def __init__(self, version):
        self.version = version


class _StubWorkingSet:
    def __init__(self, dists):
        self._dists = dists

    def find(self, req):
        return self._dists.get(req.project_name)


def test_pin_buildout_version_pins_running_dist():
    versions: dict = {}
    _pin_buildout_version(versions)
    dist = pkg_resources.working_set.find(
        pkg_resources.Requirement.parse('zc-buildout'))
    if dist is None:
        dist = pkg_resources.working_set.find(
            pkg_resources.Requirement.parse('zc.buildout'))
    assert dist is not None
    assert versions['zc.buildout'].value == '>=' + dist.version
    assert versions['zc.buildout'].source == 'DEFAULT_VALUE'


def test_pin_buildout_version_falls_back_to_dotted_name(monkeypatch):
    monkeypatch.setattr(
        pkg_resources, 'working_set',
        _StubWorkingSet({'zc.buildout': _StubDist('9.9')}))
    versions: dict = {}
    _pin_buildout_version(versions)
    assert versions['zc.buildout'].value == '>=9.9'


def test_pin_buildout_version_without_dist_raises(monkeypatch):
    monkeypatch.setattr(
        pkg_resources, 'working_set', _StubWorkingSet({}))
    with pytest.raises(ValueError, match='Could not find distribution'):
        _pin_buildout_version({})


def test_absolutize_cache_dirs_relative_resolves_under_directory():
    data = {'buildout': {
        'directory': SectionKey('/base', 'COMPUTED_VALUE'),
        'download-cache': SectionKey('dl', 'DEFAULT_VALUE'),
        'eggs-directory': SectionKey('eggs', 'DEFAULT_VALUE'),
        'extends-cache': SectionKey('ext', 'DEFAULT_VALUE'),
    }}
    _absolutize_cache_dirs(data, '/cwd')
    assert data['buildout']['download-cache'].value == '/base/dl'
    assert data['buildout']['eggs-directory'].value == '/base/eggs'
    assert data['buildout']['extends-cache'].value == '/base/ext'
    # the source annotation is preserved
    assert data['buildout']['eggs-directory'].source == 'DEFAULT_VALUE'


def test_absolutize_cache_dirs_without_directory_uses_buildout_dir():
    data = {'buildout': {'eggs-directory': SectionKey('eggs', 'DEFAULT_VALUE')}}
    _absolutize_cache_dirs(data, '/cwd')
    assert data['buildout']['eggs-directory'].value == '/cwd/eggs'


def test_absolutize_cache_dirs_command_line_source_uses_directory():
    data = {'buildout': {
        'directory': SectionKey('/base', 'COMPUTED_VALUE'),
        'eggs-directory': SectionKey('eggs', 'COMMAND_LINE_VALUE'),
    }}
    _absolutize_cache_dirs(data, '/cwd')
    assert data['buildout']['eggs-directory'].value == '/base/eggs'


def test_absolutize_cache_dirs_absolute_is_untouched():
    data = {'buildout': {'eggs-directory': SectionKey('/abs/eggs', 'DEFAULT_VALUE')}}
    _absolutize_cache_dirs(data, '/cwd')
    assert data['buildout']['eggs-directory'].value == '/abs/eggs'


def test_absolutize_cache_dirs_keeps_substitutions():
    data = {'buildout': {'eggs-directory': SectionKey(
        '${buildout:directory}/eggs', 'DEFAULT_VALUE')}}
    _absolutize_cache_dirs(data, '/cwd')
    assert (data['buildout']['eggs-directory'].value
            == '${buildout:directory}/eggs')


def test_absolutize_cache_dirs_expands_user():
    data = {'buildout': {'eggs-directory': SectionKey('~/eggs', 'DEFAULT_VALUE')}}
    _absolutize_cache_dirs(data, '/cwd')
    assert data['buildout']['eggs-directory'].value == os.path.abspath(
        os.path.expanduser('~/eggs'))


def test_absolutize_cache_dirs_relative_to_source_file():
    data = {'buildout': {'eggs-directory': SectionKey(
        'rel', '/some/dir/buildout.cfg')}}
    _absolutize_cache_dirs(data, '/cwd')
    assert data['buildout']['eggs-directory'].value == '/some/dir/rel'


def test_absolutize_cache_dirs_remote_relative_is_ambiguous():
    data = {'buildout': {'eggs-directory': SectionKey(
        'rel', 'http://example.com/buildout.cfg')}}
    with pytest.raises(zc.buildout.UserError, match='is ambiguous'):
        _absolutize_cache_dirs(data, '/cwd')


def test_links_and_hosts_empty_links_becomes_empty_tuple():
    links, hosts = _links_and_hosts('', '*')
    assert links == ()
    assert hosts == ('*',)


def test_links_and_hosts_splits_links_on_whitespace():
    links, hosts = _links_and_hosts('http://a  http://b', '*')
    assert links == ['http://a', 'http://b']
    assert hosts == ('*',)


def test_links_and_hosts_strips_hosts_and_drops_blanks():
    links, hosts = _links_and_hosts('', 'a\n\n b \n\t\n')
    assert links == ()
    assert hosts == ('a', 'b')


def test_absolutize_standard_dirs_rewrites_all_four():
    section = {
        'bin-directory': 'bin',
        'parts-directory': 'parts',
        'eggs-directory': 'eggs',
        'develop-eggs-directory': 'develop-eggs',
    }
    _absolutize_standard_dirs(section, lambda n: os.path.join('/base', n))
    assert section == {
        'bin-directory': '/base/bin',
        'parts-directory': '/base/parts',
        'eggs-directory': '/base/eggs',
        'develop-eggs-directory': '/base/develop-eggs',
    }


def test_absolutize_standard_dirs_feeds_values_through_buildout_path():
    seen = []
    section = {
        'bin-directory': 'bin',
        'parts-directory': 'parts',
        'eggs-directory': 'eggs',
        'develop-eggs-directory': 'develop-eggs',
    }
    _absolutize_standard_dirs(section, lambda n: seen.append(n) or n)
    assert seen == ['bin', 'parts', 'eggs', 'develop-eggs']


def test_version_eggs_directory_appends_version():
    options = {'eggs-directory': '/eggs', 'eggs-directory-version': 'v5'}
    _version_eggs_directory(options)
    assert options['eggs-directory'] == os.path.join('/eggs', 'v5')


def test_version_eggs_directory_empty_version_keeps_directory():
    options = {'eggs-directory': '/eggs', 'eggs-directory-version': ''}
    _version_eggs_directory(options)
    assert options['eggs-directory'] == '/eggs'


def test_version_eggs_directory_appends_abi_tag(monkeypatch):
    monkeypatch.setattr(
        'zc.buildout.pep425tags.get_abi_tag', lambda: 'cp312')
    options = {'eggs-directory': '/eggs', 'eggs-directory-version': '',
               'abi-tag-eggs': 'true'}
    _version_eggs_directory(options)
    assert options['eggs-directory'] == os.path.join('/eggs', 'cp312')


def test_version_eggs_directory_appends_version_then_abi_tag(monkeypatch):
    monkeypatch.setattr(
        'zc.buildout.pep425tags.get_abi_tag', lambda: 'cp312')
    options = {'eggs-directory': '/eggs', 'eggs-directory-version': 'v5',
               'abi-tag-eggs': 'true'}
    _version_eggs_directory(options)
    assert options['eggs-directory'] == os.path.join('/eggs', 'v5', 'cp312')


def test_create_cache_dirs_creates_missing_and_skips_empty(
        tmp_path, caplog):
    logger = logging.getLogger('zc.buildout')
    with caplog.at_level(logging.INFO, logger='zc.buildout'):
        _create_cache_dirs(str(tmp_path), ['dl', None, ''], logger)
    assert (tmp_path / 'dl').is_dir()
    assert "Creating directory %r." % str(tmp_path / 'dl') in caplog.text


def test_create_cache_dirs_existing_is_quiet(tmp_path, caplog):
    (tmp_path / 'dl').mkdir()
    logger = logging.getLogger('zc.buildout')
    with caplog.at_level(logging.INFO, logger='zc.buildout'):
        _create_cache_dirs(str(tmp_path), ['dl'], logger)
    assert caplog.records == []


def test_setup_download_cache_none_is_noop(monkeypatch):
    calls = []
    monkeypatch.setattr(
        zc.buildout.easy_install, 'download_cache', calls.append)
    _setup_download_cache(None)
    assert calls == []


def test_setup_download_cache_creates_dist_subdir(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        zc.buildout.easy_install, 'download_cache', calls.append)
    _setup_download_cache(str(tmp_path))
    assert (tmp_path / 'dist').is_dir()
    assert calls == [os.path.join(str(tmp_path), 'dist')]


def test_setup_download_cache_existing_dist_is_not_recreated(
        tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        zc.buildout.easy_install, 'download_cache', calls.append)
    (tmp_path / 'dist').mkdir()
    _setup_download_cache(str(tmp_path))
    assert calls == [os.path.join(str(tmp_path), 'dist')]


def test_check_install_from_cache_off_is_noop(monkeypatch):
    calls = []
    monkeypatch.setattr(
        zc.buildout.easy_install, 'install_from_cache', calls.append)
    _check_install_from_cache({'install-from-cache': 'false'}, False)
    assert calls == []


def test_check_install_from_cache_enables(monkeypatch):
    calls = []
    monkeypatch.setattr(
        zc.buildout.easy_install, 'install_from_cache', calls.append)
    _check_install_from_cache({'install-from-cache': 'true'}, False)
    assert calls == [True]


def test_check_install_from_cache_offline_raises():
    with pytest.raises(
            zc.buildout.UserError, match="can't be used with offline mode"):
        _check_install_from_cache({'install-from-cache': 'true'}, True)


def test_use_default_options_reads_every_default():
    reads = []

    class _CountingDict(dict):
        def __getitem__(self, key):
            reads.append(key)
            return super().__getitem__(key)

    options = _CountingDict((name, '') for name in _buildout_default_options)
    _use_default_options(options)
    assert sorted(reads) == sorted(_buildout_default_options)


def test_split_parts_empty():
    assert _split_parts('') == []


def test_split_parts_whitespace_separated():
    assert _split_parts('  a\tb  c\n') == ['a', 'b', 'c']


def test_print_configuration_data(capsys):
    data = {'b': {'x': '2'}, 'a': {'y': '1'}}
    _print_configuration_data(data, lambda section: data[section])
    assert capsys.readouterr().out == (
        '\nConfiguration data:\n[a]\ny = 1\n[b]\nx = 2\n\n')


def test_part_is_up_to_date_unchanged_options_and_files_present(tmp_path):
    (tmp_path / 'f').write_text('x')
    assert _part_is_up_to_date(
        {'a': '1'}, 'f', {'a': '1'},
        lambda p: str(tmp_path / p))


def test_part_is_up_to_date_changed_options():
    assert not _part_is_up_to_date(
        {'a': '1'}, '', {'a': '2'}, lambda p: p)


def test_part_is_up_to_date_no_installed_files():
    # No recorded files: considered up to date when options are unchanged.
    assert _part_is_up_to_date({'a': '1'}, '', {'a': '1'}, lambda p: p)


def test_part_is_up_to_date_missing_installed_file(tmp_path):
    (tmp_path / 'kept.txt').write_text('x')
    assert not _part_is_up_to_date(
        {'a': '1'}, 'kept.txt\ngone.txt', {'a': '1'},
        lambda p: str(tmp_path / p))


def test_log_part_option_changes_dropped(caplog):
    logger = logging.getLogger('test.partchanges')
    with caplog.at_level(logging.DEBUG, logger='test.partchanges'):
        _log_part_option_changes(logger, 'p', {'old': '1'}, {})
    assert 'Part p, dropped option old.' in caplog.text


def test_log_part_option_changes_changed(caplog):
    logger = logging.getLogger('test.partchanges')
    with caplog.at_level(logging.DEBUG, logger='test.partchanges'):
        _log_part_option_changes(logger, 'p', {'k': '1'}, {'k': '2'})
    assert "Part p, option k changed:\n'2' != '1'" in caplog.text


def test_log_part_option_changes_new(caplog):
    logger = logging.getLogger('test.partchanges')
    with caplog.at_level(logging.DEBUG, logger='test.partchanges'):
        _log_part_option_changes(logger, 'p', {}, {'n': '1'})
    assert 'Part p, new option n.' in caplog.text


def test_log_part_option_changes_unchanged_logs_nothing(caplog):
    logger = logging.getLogger('test.partchanges')
    with caplog.at_level(logging.DEBUG, logger='test.partchanges'):
        _log_part_option_changes(logger, 'p', {'k': '1'}, {'k': '1'})
    assert caplog.text == ''


def _uninstall_spy(calls):
    def uninstall_part(part, installed_part_options):
        calls.append(part)
    return uninstall_part


def test_uninstall_stale_parts_keeps_up_to_date_part(tmp_path):
    (tmp_path / 'f').write_text('x')
    calls = []
    updates = []
    installed_part_options: Dict[str, Union[Options, Dict[str, str]]] = {
        'buildout': {'parts': 'a'},
        'a': {'__buildout_installed__': 'f', 'mode': '1'},
    }
    result = _uninstall_stale_parts(
        ['a'], ['a'], installed_part_options,
        uninstall_missing=True, installed_exists=True,
        get_options=lambda part: {'mode': '1'},
        buildout_path=lambda p: str(tmp_path / p),
        logger=logging.getLogger('test.uninstall'),
        uninstall_part=_uninstall_spy(calls),
        update_installed=lambda **kw: updates.append(kw))
    assert result == ['a']
    assert calls == []
    assert updates == []


def test_uninstall_stale_parts_reinstalls_changed_part():
    calls = []
    updates = []
    installed_part_options: Dict[str, Union[Options, Dict[str, str]]] = {
        'buildout': {'parts': 'a'},
        'a': {'__buildout_installed__': '', 'mode': '1'},
    }
    result = _uninstall_stale_parts(
        ['a'], ['a'], installed_part_options,
        uninstall_missing=True, installed_exists=True,
        get_options=lambda part: {'mode': '2'},
        buildout_path=lambda p: p,
        logger=logging.getLogger('test.uninstall'),
        uninstall_part=_uninstall_spy(calls),
        update_installed=lambda **kw: updates.append(kw))
    assert result == []
    assert calls == ['a']
    assert updates == [{'parts': ''}]


def test_uninstall_stale_parts_reinstalls_when_installed_file_missing():
    calls = []
    installed_part_options: Dict[str, Union[Options, Dict[str, str]]] = {
        'buildout': {'parts': 'a'},
        'a': {'__buildout_installed__': 'gone', 'mode': '1'},
    }
    result = _uninstall_stale_parts(
        ['a'], ['a'], installed_part_options,
        uninstall_missing=True, installed_exists=False,
        get_options=lambda part: {'mode': '1'},
        buildout_path=lambda p: p,
        logger=logging.getLogger('test.uninstall'),
        uninstall_part=_uninstall_spy(calls),
        update_installed=lambda **kw: None)
    assert result == []
    assert calls == ['a']


def test_uninstall_stale_parts_keeps_missing_part_when_not_uninstalling():
    calls = []
    installed_part_options: Dict[str, Union[Options, Dict[str, str]]] = {'buildout': {'parts': 'a'}}
    result = _uninstall_stale_parts(
        [], ['a'], installed_part_options,
        uninstall_missing=False, installed_exists=True,
        get_options=lambda part: None,
        buildout_path=lambda p: p,
        logger=logging.getLogger('test.uninstall'),
        uninstall_part=_uninstall_spy(calls),
        update_installed=lambda **kw: None)
    assert result == ['a']
    assert calls == []


def test_uninstall_stale_parts_removes_missing_parts_in_reverse():
    calls = []
    updates = []
    installed_part_options: Dict[str, Union[Options, Dict[str, str]]] = {'buildout': {'parts': 'a b'}}
    result = _uninstall_stale_parts(
        [], ['a', 'b'], installed_part_options,
        uninstall_missing=True, installed_exists=True,
        get_options=lambda part: None,
        buildout_path=lambda p: p,
        logger=logging.getLogger('test.uninstall'),
        uninstall_part=_uninstall_spy(calls),
        update_installed=lambda **kw: updates.append(kw))
    assert result == []
    assert calls == ['b', 'a']
    assert updates == [{'parts': 'a'}, {'parts': ''}]


def test_uninstall_stale_parts_logs_option_changes_at_debug(caplog):
    logger = logging.getLogger('test.uninstall.debug')
    installed_part_options: Dict[str, Union[Options, Dict[str, str]]] = {
        'buildout': {'parts': 'a'},
        'a': {'__buildout_installed__': '', 'mode': '1'},
    }
    # The caller gate is effective level *below* logging.DEBUG.
    with caplog.at_level(1, logger='test.uninstall.debug'):
        _uninstall_stale_parts(
            ['a'], ['a'], installed_part_options,
            uninstall_missing=True, installed_exists=False,
            get_options=lambda part: {'mode': '2'},
            buildout_path=lambda p: p,
            logger=logger,
            uninstall_part=_uninstall_spy([]),
            update_installed=lambda **kw: None)
    assert "Part a, option mode changed:\n'2' != '1'" in caplog.text


def test_update_recipe_callable_prefers_update():
    class Recipe:
        def install(self):
            return ['install']

        def update(self):
            return ['update']

    recipe = Recipe()
    assert _update_recipe_callable(
        recipe, 'p', logging.getLogger('test.updcall')) == recipe.update


def test_update_recipe_callable_falls_back_to_install_with_warning(caplog):
    class Recipe:
        def install(self):
            return ['install']

    recipe = Recipe()
    logger = logging.getLogger('test.updcall')
    with caplog.at_level(logging.WARNING, logger='test.updcall'):
        result = _update_recipe_callable(recipe, 'p', logger)
    assert result == recipe.install
    assert ("The recipe for p doesn't define an update method. "
            "Using its install method.") in caplog.text


def test_merged_updated_files_none_keeps_previous():
    assert _merged_updated_files(None, 'a\nb') == (['a', 'b'], [])


def test_merged_updated_files_string_result_is_merged():
    assert _merged_updated_files('c', 'a\nb') == (['a', 'b', 'c'], ['c'])


def test_merged_updated_files_result_without_new_files():
    assert _merged_updated_files(['a', 'b'], 'a\nb') == (['a', 'b'], [])


def test_merged_updated_files_merges_only_new_files():
    assert _merged_updated_files(['b', 'c'], 'a\nb') == (['a', 'b', 'c'], ['c'])


def test_normalize_installed_files_none_warns(caplog):
    logger = logging.getLogger('test.norm')
    with caplog.at_level(logging.WARNING, logger='test.norm'):
        result = _normalize_installed_files(None, 'p', logger)
    assert result == ()
    assert 'The p install returned None.' in caplog.text


def test_normalize_installed_files_string():
    assert _normalize_installed_files(
        'f', 'p', logging.getLogger('test.norm')) == ['f']


def test_normalize_installed_files_iterable():
    assert _normalize_installed_files(
        ('a', 'b'), 'p', logging.getLogger('test.norm')) == ['a', 'b']


def test_update_part_success_merges_files():
    class Recipe:
        def update(self):
            return ['old2', 'new1']

    installed_part_options: Dict[str, Union[Options, Dict[str, str]]] = {
        'buildout': {'parts': 'p'},
        'p': {'__buildout_installed__': 'old1\nold2'},
    }
    installed_files, new_files = _update_part(
        'p', Recipe(), lambda f: f(),
        installed_part_options, ['p'], True,
        logging.getLogger('test.updatepart'),
        lambda installed: None, lambda **kw: None)
    assert installed_files == ['old1', 'old2', 'new1']
    assert new_files == ['new1']


def test_update_part_none_result_keeps_previous_files():
    class Recipe:
        def update(self):
            return None

    installed_part_options: Dict[str, Union[Options, Dict[str, str]]] = {
        'p': {'__buildout_installed__': 'old1'},
    }
    installed_files, new_files = _update_part(
        'p', Recipe(), lambda f: f(),
        installed_part_options, ['p'], True,
        logging.getLogger('test.updatepart'),
        lambda installed: None, lambda **kw: None)
    assert installed_files == ['old1']
    assert new_files == []


def test_update_part_failure_rolls_back():
    class Recipe:
        def update(self):
            raise RuntimeError('boom')

    uninstalled = []
    updates = []
    installed_parts = ['p', 'q']
    installed_part_options: Dict[str, Union[Options, Dict[str, str]]] = {
        'p': {'__buildout_installed__': 'old1'},
    }
    with pytest.raises(RuntimeError):
        _update_part(
            'p', Recipe(), lambda f: f(),
            installed_part_options, installed_parts, True,
            logging.getLogger('test.updatepart'),
            uninstalled.append, lambda **kw: updates.append(kw))
    assert installed_parts == ['q']
    assert uninstalled == ['old1']
    assert updates == [{'parts': 'q'}]


def test_update_part_failure_without_installed_file_skips_update():
    class Recipe:
        def update(self):
            raise RuntimeError('boom')

    updates = []
    installed_part_options: Dict[str, Union[Options, Dict[str, str]]] = {
        'p': {'__buildout_installed__': 'old1'},
    }
    with pytest.raises(RuntimeError):
        _update_part(
            'p', Recipe(), lambda f: f(),
            installed_part_options, ['p'], False,
            logging.getLogger('test.updatepart'),
            lambda installed: None, lambda **kw: updates.append(kw))
    assert updates == []


def test_update_part_without_update_method_warns_and_uses_install(caplog):
    class Recipe:
        def install(self):
            return ['f']

    logger = logging.getLogger('test.updatepart.fallback')
    installed_part_options: Dict[str, Union[Options, Dict[str, str]]] = {
        'p': {'__buildout_installed__': ''},
    }
    with caplog.at_level(logging.WARNING, logger='test.updatepart.fallback'):
        installed_files, new_files = _update_part(
            'p', Recipe(), lambda f: f(),
            installed_part_options, ['p'], False,
            logger, lambda installed: None, lambda **kw: None)
    assert installed_files == ['', 'f']
    assert new_files == ['f']
    assert "The recipe for p doesn't define an update method." in caplog.text


def test_record_installed_part_moves_part_to_end():
    saved = {'recipe': 'x'}
    installed_part_options: Dict[str, Union[Options, Dict[str, str]]] = {
        'buildout': {'parts': 'a b'},
    }
    result = _record_installed_part(
        'a', 'sig', saved, ['f1', 'f2'], ['a', 'b'], installed_part_options)
    assert result == ['b', 'a']
    assert saved['__buildout_installed__'] == 'f1\nf2'
    assert saved['__buildout_signature__'] == 'sig'
    assert installed_part_options['a'] is saved


def test_record_installed_part_empty_files_list():
    saved: Dict[str, str] = {}
    result = _record_installed_part('p', 'sig', saved, [], [], {})
    assert result == ['p']
    assert saved['__buildout_installed__'] == ''


def test_save_or_update_installed_saves_when_needed():
    saved = []
    installed_part_options: Dict[str, Union[Options, Dict[str, str]]] = {
        'buildout': {'parts': ''},
    }
    exists = _save_or_update_installed(
        True, False, ['a', 'b'], installed_part_options,
        saved.append, lambda **kw: None)
    assert exists is True
    assert installed_part_options['buildout']['parts'] == 'a b'
    assert saved == [installed_part_options]


def test_save_or_update_installed_updates_when_not_needed():
    updates = []
    exists = _save_or_update_installed(
        [], True, ['a'], {'buildout': {'parts': 'a'}},
        lambda options: None, lambda **kw: updates.append(kw))
    assert exists is True
    assert updates == [{'parts': 'a'}]


def test_save_or_update_installed_asserts_without_installed_file():
    with pytest.raises(AssertionError):
        _save_or_update_installed(
            False, False, [], {'buildout': {'parts': ''}},
            lambda options: None, lambda **kw: None)


def test_finalize_installed_options_saves_develop_eggs_state():
    saved = []
    _finalize_installed_options(
        'egg1', False, [], {'buildout': {'parts': ''}}, {'installed': 'x'},
        saved.append)
    assert saved == [{'buildout': {'parts': ''}}]


def test_finalize_installed_options_keeps_existing_state():
    saved = []
    _finalize_installed_options(
        'egg1', True, [], {}, {'installed': 'x'}, saved.append)
    assert saved == []


def test_finalize_installed_options_removes_installed_file(tmp_path):
    installed = tmp_path / 'installed.cfg'
    installed.write_text('x')
    _finalize_installed_options(
        '', True, [], {}, {'installed': str(installed)}, lambda o: None)
    assert not installed.exists()


def test_finalize_installed_options_keeps_file_while_parts_remain(tmp_path):
    installed = tmp_path / 'installed.cfg'
    installed.write_text('x')
    _finalize_installed_options(
        '', True, ['a'], {}, {'installed': str(installed)}, lambda o: None)
    assert installed.exists()
