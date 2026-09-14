"""Unit tests for the pure helpers extracted from zc.buildout.buildout."""
import os

import pkg_resources
import pytest

import zc.buildout
from zc.buildout.buildout import (
    SectionKey,
    _absolutize_cache_dirs,
    _apply_cl_extends,
    _cloptions_dict,
    _default_versions,
    _develop_source_dir,
    _filename_for_logging,
    _load_config,
    _load_user_defaults,
    _merge_config_data,
    _new_develop_eggs,
    _pin_buildout_version,
    _previous_develop_links,
    _resolve_config_file,
    _resolve_config_location,
    _validated_extends_cache,
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
