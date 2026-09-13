"""Unit tests for the pure helpers extracted from configparser.parse."""
from zc.buildout.configparser import (
    _append_continuation,
    _evaluate_section_condition,
    _finalize_sections,
    _merge_option,
)


def test_merge_option_assign():
    sect = {}
    _merge_option(sect, 'name ', ' value ')
    assert sect == {'name': 'value'}


def test_merge_option_extend_accumulates():
    sect = {}
    _merge_option(sect, 'name +', 'a')
    _merge_option(sect, 'name +', 'b')
    assert sect == {'name +': 'a\nb'}


def test_merge_option_assign_overrides_extend():
    sect = {}
    _merge_option(sect, 'name +', 'a')
    _merge_option(sect, 'name', 'b')
    assert sect == {'name': 'b'}


def test_merge_option_remove():
    sect = {}
    _merge_option(sect, 'name -', 'a')
    assert sect == {'name -': 'a'}


def test_merge_option_extend_strips_trailing_newline():
    sect = {'name +': 'a\n'}
    _merge_option(sect, 'name +', 'b')
    assert sect == {'name +': 'a\nb'}


def test_merge_option_empty_extend_keeps_value():
    sect = {'name +': 'a\n'}
    _merge_option(sect, 'name +', '')
    assert sect == {'name +': 'a'}


def test_evaluate_marker_true():
    assert _evaluate_section_condition('[', 'python_version >= "2.0"', ']', dict)


def test_evaluate_marker_false():
    assert not _evaluate_section_condition('[', 'python_version < "2.0"', ']', dict)


def test_evaluate_marker_never_touches_context():
    def boom():
        raise AssertionError('context must stay lazy for markers')
    assert _evaluate_section_condition('[', 'python_version >= "2.0"', ']', boom)


def test_evaluate_old_style_expression():
    assert _evaluate_section_condition('[', 'True', ']', dict)
    assert not _evaluate_section_condition('[', 'False', ']', dict)


def test_evaluate_unescapes_hash_and_semicolon():
    assert _evaluate_section_condition(
        '[', r"'a\x23b' == 'a#b' and 'a\x3bb' == 'a;b' and True", ']', dict)


def test_append_continuation_strips_unless_blockmode():
    sect = {'opt': 'base'}
    _append_continuation(sect, 'opt', '  extra  \n', False)
    assert sect['opt'] == 'base\nextra'
    _append_continuation(sect, 'opt', '  raw  \n', True)
    assert sect['opt'] == 'base\nextra\n  raw'


def test_finalize_sections_dedents_multiline_values():
    sections = {'s': {'opt': '\n    a\n    b\n'}}
    assert _finalize_sections(sections) == {'s': {'opt': 'a\nb'}}
