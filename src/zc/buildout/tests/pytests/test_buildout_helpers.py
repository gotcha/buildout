"""Unit tests for the pure helpers extracted from zc.buildout.buildout."""
import os

import pytest

from zc.buildout.buildout import (
    SectionKey,
    _develop_source_dir,
    _filename_for_logging,
    _merge_config_data,
    _new_develop_eggs,
    _previous_develop_links,
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
