"""Unit tests for the pure helpers extracted from configparser.parse."""
import pytest

from zc.buildout.configparser import (
    MissingSectionHeaderError,
    ParsingError,
    _append_continuation,
    _evaluate_section_condition,
    _expression_context,
    _finalize_sections,
    _handle_continuation,
    _handle_option_line,
    _handle_preamble_line,
    _merge_option,
    _start_section,
    section_header,
)


def _header(line: str):
    match = section_header(line)
    assert match is not None
    return match


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


def test_handle_continuation_ignores_non_space_line():
    assert not _handle_continuation('x = 1\n', {'x': '1'}, 'x', True, False)


def test_handle_continuation_ignores_line_outside_section():
    assert not _handle_continuation('  x\n', None, 'x', True, False)


def test_handle_continuation_ignores_line_without_option():
    assert not _handle_continuation('  x\n', {}, None, True, False)


def test_handle_continuation_appends_stripped_line():
    sect = {'opt': 'base'}
    assert _handle_continuation('  extra  \n', sect, 'opt', True, False)
    assert sect == {'opt': 'base\nextra'}


def test_handle_continuation_skips_conditionally_ignored_section():
    sect = {'opt': 'base'}
    assert _handle_continuation('  extra\n', sect, 'opt', False, False)
    assert sect == {'opt': 'base'}


def test_handle_continuation_skips_blank_line_unless_blockmode():
    sect = {'opt': 'base'}
    assert _handle_continuation('   \n', sect, 'opt', True, False)
    assert sect == {'opt': 'base'}
    assert _handle_continuation('   \n', sect, 'opt', True, True)
    assert sect == {'opt': 'base\n'}


def test_expression_context_is_lazily_populated_once():
    context = []
    calls = []

    def exp_globals():
        calls.append(1)
        return {'x': 1}

    assert _expression_context(context, exp_globals) == {'x': 1}
    assert _expression_context(context, exp_globals) == {'x': 1}
    assert calls == [1]


def test_expression_context_refetches_falsy_context():
    context = []
    calls = []

    def exp_globals():
        calls.append(1)
        return {}

    assert _expression_context(context, exp_globals) == {}
    assert _expression_context(context, exp_globals) == {}
    assert calls == [1, 1]


def test_start_section_creates_section():
    sections = {}
    cursect, condition = _start_section(
        _header('[name]'), sections, [], dict)
    assert condition
    assert cursect == {}
    assert sections == {'name': cursect}


def test_start_section_reuses_existing_section():
    existing = {'opt': 'value'}
    sections = {'name': existing}
    cursect, condition = _start_section(
        _header('[name]'), sections, [], dict)
    assert condition
    assert cursect is existing


def test_start_section_false_condition_ignores_section():
    sections = {}
    assert _start_section(
        _header('[name:False]'), sections, [], dict) == (None, False)
    assert sections == {}


def test_start_section_true_condition_enters_section():
    sections = {}
    cursect, condition = _start_section(
        _header('[name:True]'), sections, [], dict)
    assert condition
    assert cursect == {}


def test_start_section_marker_does_not_touch_exp_globals():
    sections = {}

    def boom():
        raise AssertionError('context must stay lazy for markers')

    cursect, condition = _start_section(
        _header('[name: python_version >= "2.0"]'), sections, [], boom)
    assert condition
    assert sections == {'name': cursect}


def test_handle_preamble_line_allows_blank_lines():
    assert _handle_preamble_line('   \n', 'file.cfg', 1) is None


def test_handle_preamble_line_rejects_content():
    with pytest.raises(MissingSectionHeaderError):
        _handle_preamble_line('x = 1\n', 'file.cfg', 1)


def test_handle_option_line_merges_option():
    sect = {}
    assert _handle_option_line(
        'name = value\n', sect, None, False, True, 'file.cfg', 1, None,
    ) == ('name', False, None)
    assert sect == {'name': 'value'}


def test_handle_option_line_empty_value_enters_blockmode():
    sect = {}
    assert _handle_option_line(
        'name =\n', sect, None, False, True, 'file.cfg', 1, None,
    ) == ('name', True, None)
    assert sect == {'name': ''}


def test_handle_option_line_rewrites_arrow_operator():
    sect = {}
    assert _handle_option_line(
        '=> some/directory\n', sect, None, False, True, 'file.cfg', 1, None,
    ) == ('<part-dependencies>', False, None)
    assert sect == {'<part-dependencies>': 'some/directory'}


def test_handle_option_line_filters_ignored_section():
    sect = {}
    assert _handle_option_line(
        'name = value\n', sect, None, False, False, 'file.cfg', 1, None,
    ) is None
    assert sect == {}


def test_handle_option_line_collects_parsing_error():
    sect = {}
    result = _handle_option_line(
        'bogus line\n', sect, 'opt', False, True, 'file.cfg', 7, None)
    assert result is not None
    optname, _blockmode, error = result
    assert optname == 'opt'
    assert isinstance(error, ParsingError)
    assert error.errors == [(7, "'bogus line\\n'")]


def test_handle_option_line_appends_to_existing_error():
    existing = ParsingError('file.cfg')
    result = _handle_option_line(
        'bogus line\n', {}, 'opt', False, True, 'file.cfg', 8, existing)
    assert result is not None
    _optname, _blockmode, error = result
    assert error is existing
    assert error.errors == [(8, "'bogus line\\n'")]


def test_handle_option_line_blank_line_after_section_start():
    assert _handle_option_line(
        '\n', {}, None, False, True, 'file.cfg', 1, None,
    ) == (None, False, None)
