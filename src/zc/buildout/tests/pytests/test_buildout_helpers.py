"""Unit tests for the pure helpers extracted from buildout._open."""
import os

import pytest

from zc.buildout.buildout import (
    SectionKey,
    _filename_for_logging,
    _merge_config_data,
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
