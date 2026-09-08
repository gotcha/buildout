"""Unit tests for assert_output, capture_print, and apply_normalizers in conftest.py."""
import re
import sys

import pytest

from zc.buildout.tests.pytests.conftest import (
    apply_normalizers,
    assert_output,
    capture_print,
)


# ---------------------------------------------------------------------------
# assert_output — exact match
# ---------------------------------------------------------------------------

def test_exact_match():
    assert_output("hello world", "hello world")


def test_exact_match_fails():
    with pytest.raises(AssertionError):
        assert_output("hello world", "goodbye world")


# ---------------------------------------------------------------------------
# assert_output — whitespace normalisation
# ---------------------------------------------------------------------------

def test_horizontal_whitespace_collapsed():
    assert_output("a  b\tc", "a b c")


def test_leading_trailing_whitespace_stripped_per_line():
    assert_output("  hello  \n  world  ", "hello\nworld")


def test_blank_lines_ignored():
    assert_output("a\n\nb", "a\nb")


def test_blank_lines_in_expected_ignored():
    assert_output("a\nb", "a\n\nb")


def test_leading_newline_ignored():
    assert_output("\nhello", "hello")


def test_trailing_newline_ignored():
    assert_output("hello\n", "hello")


# ---------------------------------------------------------------------------
# assert_output — standalone '...' wildcard (multi-line skip)
# ---------------------------------------------------------------------------

def test_standalone_ellipsis_skips_lines():
    assert_output("a\nb\nc\nd", "a\n...\nd")


def test_standalone_ellipsis_can_skip_zero_lines():
    assert_output("a\nb", "a\n...\nb")


def test_standalone_ellipsis_at_start():
    assert_output("x\ny\nz", "...\nz")


def test_standalone_ellipsis_at_end():
    assert_output("a\nb\nc", "a\n...")


def test_multiple_standalone_ellipsis():
    assert_output("a\nb\nc\nd\ne", "a\n...\nc\n...\ne")


def test_standalone_ellipsis_chunks_must_be_in_order():
    with pytest.raises(AssertionError):
        assert_output("a\nb\nc", "c\n...\na")


# ---------------------------------------------------------------------------
# assert_output — inline '...' (single-line wildcard)
# ---------------------------------------------------------------------------

def test_inline_ellipsis_matches_suffix():
    assert_output("hello world", "hello...")


def test_inline_ellipsis_matches_prefix():
    assert_output("hello world", "...world")


def test_inline_ellipsis_matches_middle():
    assert_output("hello beautiful world", "hello...world")


def test_inline_ellipsis_does_not_span_lines():
    with pytest.raises(AssertionError):
        assert_output("hello\nworld", "hello...world")


# ---------------------------------------------------------------------------
# assert_output — normalizers
# ---------------------------------------------------------------------------

def test_normalizer_replaces_pattern():
    normalizers = [(re.compile(r'\d+'), 'N')]
    assert_output("version 123", "version N", normalizers)


def test_callable_normalizer():
    normalizers = [(re.compile(r'\d+'), lambda m: 'NUM')]
    assert_output("x 42 y", "x NUM y", normalizers)


def test_normalizer_applied_to_both_actual_and_expected():
    normalizers = [(re.compile(r'/tmp/[a-z0-9]+/'), '/tmp/XXX/')]
    assert_output("/tmp/abc123/file", "/tmp/XXX/file", normalizers)


def test_multiple_normalizers_applied_in_order():
    normalizers = [
        (re.compile(r'foo'), 'bar'),
        (re.compile(r'bar'), 'baz'),
    ]
    assert_output("foo", "baz", normalizers)


def test_non_tuple_items_in_normalizer_list_skipped():
    normalizers = [None, (re.compile(r'x'), 'y'), None]
    assert_output("x", "y", normalizers)


# ---------------------------------------------------------------------------
# assert_output — chunk ordering
# ---------------------------------------------------------------------------

def test_second_chunk_found_after_first():
    assert_output("start\nmiddle\nend", "start\n...\nend")


def test_chunks_sequential_not_overlapping():
    actual = "a a a"
    assert_output(actual, "a\n...\na")


def test_error_message_includes_chunk():
    try:
        assert_output("hello", "goodbye")
    except AssertionError as e:
        assert "goodbye" in str(e)
        assert "hello" in str(e)
    else:
        pytest.fail("Expected AssertionError")


def test_error_message_includes_position():
    try:
        assert_output("line1\nline2\nline3", "line1\n...\nmissing")
    except AssertionError as e:
        assert "chunk" in str(e).lower()
    else:
        pytest.fail("Expected AssertionError")


# ---------------------------------------------------------------------------
# assert_output — edge cases
# ---------------------------------------------------------------------------

def test_empty_expected_passes():
    assert_output("anything", "")


def test_empty_actual_with_empty_expected_passes():
    assert_output("", "")


def test_only_ellipsis_expected_passes():
    assert_output("any content here", "...")


def test_special_regex_chars_in_expected_are_escaped():
    assert_output("a.b+c*d", "a.b+c*d")


def test_parentheses_in_expected_escaped():
    assert_output("fn(x)", "fn(x)")


def test_brackets_in_expected_escaped():
    assert_output("[buildout]", "[buildout]")


# ---------------------------------------------------------------------------
# capture_print
# ---------------------------------------------------------------------------

def test_capture_print_captures_output():
    result = capture_print(print, "hello")
    assert result == "hello\n"


def test_capture_print_with_args():
    result = capture_print(print, "a", "b", "c")
    assert result == "a b c\n"


def test_capture_print_with_kwargs():
    result = capture_print(print, "x", end="!")
    assert result == "x!"


def test_capture_print_with_no_output():
    result = capture_print(lambda: None)
    assert result == ""


def test_capture_print_restores_stdout_on_exception():
    original_stdout = sys.stdout

    def bad_fn():
        print("before")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        capture_print(bad_fn)

    assert sys.stdout is original_stdout


def test_capture_print_captures_multiple_prints():
    def multi():
        print("line1")
        print("line2")

    result = capture_print(multi)
    assert result == "line1\nline2\n"


def test_capture_print_passes_positional_args():
    def fn(a, b):
        print(a + b)

    result = capture_print(fn, 3, 4)
    assert result == "7\n"


def test_capture_print_passes_keyword_args():
    def fn(sep="-"):
        print("a", "b", sep=sep)

    result = capture_print(fn, sep=":")
    assert result == "a:b\n"


# ---------------------------------------------------------------------------
# apply_normalizers
# ---------------------------------------------------------------------------

def test_apply_normalizers_empty_list():
    assert apply_normalizers("hello", []) == "hello"


def test_apply_normalizers_none_entries_skipped():
    result = apply_normalizers("hello", [None])
    assert result == "hello"


def test_apply_normalizers_string_replacement():
    result = apply_normalizers("foo bar", [(re.compile(r'foo'), 'baz')])
    assert result == "baz bar"


def test_apply_normalizers_callable_replacement():
    result = apply_normalizers("x42y", [(re.compile(r'\d+'), lambda m: 'N')])
    assert result == "xNy"


def test_apply_normalizers_multiple():
    result = apply_normalizers("a1b2", [
        (re.compile(r'a'), 'X'),
        (re.compile(r'\d'), 'N'),
    ])
    assert result == "XNbN"
