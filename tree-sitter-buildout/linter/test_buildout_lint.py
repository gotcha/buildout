"""Tests for zc.buildout.lint (the buildout-lint console script).

Needs the tree-sitter Python package (py-tree-sitter) importable; skips
cleanly otherwise. Run with: python -m pytest tree-sitter-buildout/linter/
"""
import pytest

pytest.importorskip('tree_sitter')

from zc.buildout import lint  # noqa: E402


@pytest.fixture(scope='module')
def parser():
    return lint.make_parser()


def lint_text(parser, tmp_path, text):
    path = tmp_path / 'test.cfg'
    path.write_text(text)
    return lint.lint_file(str(path), parser)


def levels(findings):
    return [(f.level, f.message) for f in findings]


def test_clean_file(parser, tmp_path):
    findings = lint_text(parser, tmp_path, (
        '[buildout]\n'
        'parts = demo\n'
        '\n'
        '[demo]\n'
        'recipe = my.recipe\n'
        'x = ${buildout:directory}\n'
    ))
    assert findings == []


def test_syntax_error_is_error(parser, tmp_path):
    findings = lint_text(parser, tmp_path, '[a\nb = 1\n')
    assert any(f.level == 'ERROR' for f in findings)


def test_unsupported_hash_in_condition_is_error_via_syntax(parser, tmp_path):
    # the reference parser rejects unescaped '#' in conditional expressions
    findings = lint_text(parser, tmp_path, "[a:'#' in '#;']\nb = 1\n")
    assert any(f.level == 'ERROR' for f in findings)


def test_unknown_section_reference(parser, tmp_path):
    findings = lint_text(parser, tmp_path, '[a]\nx = ${nope:opt}\n')
    assert levels(findings) == [
        ('WARNING', 'substitution references unknown section [nope]')]


def test_unknown_option_reference(parser, tmp_path):
    findings = lint_text(parser, tmp_path, '[a]\nx = 1\ny = ${a:nope}\n')
    assert levels(findings) == [
        ('WARNING', 'substitution references unknown option a:nope')]


def test_same_section_shorthand(parser, tmp_path):
    findings = lint_text(parser, tmp_path, '[a]\nx = 1\ny = ${:x}\n')
    assert findings == []
    findings = lint_text(parser, tmp_path, '[a]\ny = ${:x}\n')
    assert [f.level for f in findings] == ['WARNING']


def test_macro_reference_unknown(parser, tmp_path):
    findings = lint_text(parser, tmp_path, '[a]\n<= nowhere\n')
    assert [f.level for f in findings] == ['WARNING']
    findings = lint_text(parser, tmp_path, '[a]\nx = 1\n\n[b]\n<= a\n')
    assert findings == []


def test_malformed_substitution_missing_colon(parser, tmp_path):
    findings = lint_text(parser, tmp_path, '[a]\nx = ${nocolon}\n')
    assert any(f.level == 'ERROR' and 'expected' in f.message
               for f in findings)


def test_malformed_substitution_bad_chars(parser, tmp_path):
    findings = lint_text(parser, tmp_path, '[a]\nx = ${b+c:d}\n')
    assert any(f.level == 'ERROR' and 'identifiers' in f.message
               for f in findings)


def test_conditional_duplicate_sections_are_fine(parser, tmp_path):
    findings = lint_text(parser, tmp_path, (
        '[versions]\n'
        'a = 1\n'
        '\n'
        '[versions:python_version >= "3.13"]\n'
        'a = 2\n'
        '\n'
        '[versions:python_version >= "3.14"]\n'
        'a = 3\n'
    ))
    assert findings == []


def test_true_duplicate_section_warns(parser, tmp_path):
    findings = lint_text(parser, tmp_path, '[a]\nx = 1\n\n[a]\ny = 2\n')
    assert [f.level for f in findings] == ['WARNING']


def test_environ_is_not_unknown(parser, tmp_path):
    findings = lint_text(parser, tmp_path, '[a]\nx = ${__environ__:HOME}\n')
    assert findings == []


def test_invalid_condition_expression_warns(parser, tmp_path):
    findings = lint_text(parser, tmp_path, '[a: this is not python $$]\nx = 1\n')
    assert any(f.level == 'WARNING' and 'conditional expression' in f.message
               for f in findings)
