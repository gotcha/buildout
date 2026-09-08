"""Corpus tests for buildout-lint.

tree-sitter-buildout/linter/corpus/
    clean/    files that must lint with no findings at all
    warnings/ files that must produce at least one WARNING and no ERROR
    errors/   files that must produce at least one ERROR

Run with: python -m pytest tree-sitter-buildout/linter/
"""
from pathlib import Path

import pytest

pytest.importorskip('tree_sitter')

from zc.buildout import lint  # noqa: E402

CORPUS = Path(__file__).resolve().parent / 'corpus'


@pytest.fixture(scope='module')
def parser():
    return lint.make_parser()


def corpus_files(kind):
    return sorted((CORPUS / kind).glob('*.cfg'))


@pytest.mark.parametrize('path', corpus_files('clean'),
                         ids=[p.name for p in corpus_files('clean')])
def test_clean(parser, path):
    assert lint.lint_file(str(path), parser) == []


@pytest.mark.parametrize('path', corpus_files('warnings'),
                         ids=[p.name for p in corpus_files('warnings')])
def test_warnings(parser, path):
    findings = lint.lint_file(str(path), parser)
    assert any(f.level == 'WARNING' for f in findings)
    assert not any(f.level == 'ERROR' for f in findings)


@pytest.mark.parametrize('path', corpus_files('errors'),
                         ids=[p.name for p in corpus_files('errors')])
def test_errors(parser, path):
    findings = lint.lint_file(str(path), parser)
    assert any(f.level == 'ERROR' for f in findings)


def test_corpus_is_not_empty():
    # guard against the corpus silently disappearing (e.g. moved dirs)
    assert len(corpus_files('clean')) >= 5
    assert len(corpus_files('warnings')) >= 3
    assert len(corpus_files('errors')) >= 3
