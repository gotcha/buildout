"""Run doc/*.rst and doc/topics/*.rst through pytest using manuel.

The RST files use the `.. -> varname` manuel capture directive alongside
standard `>>>` doctest blocks.  They must be collected via manuel — plain
`--doctest-glob` would miss the capture assignments.

Each RST file becomes one pytest-visible unittest.TestCase.  Pytest discovers
and runs unittest items natively via its built-in unittest integration.
"""
import doctest
import os
import sys
import unittest
from pathlib import Path

import manuel.capture
import manuel.doctest
import manuel.testing
from zope.testing import renormalizing, setupstack

import zc.buildout.testing

_DOC_DIR = Path(__file__).parents[5] / 'doc'

_NORMALIZERS = renormalizing.RENormalizing([
    zc.buildout.testing.easyinstall_deprecated,
    zc.buildout.testing.setuptools_deprecated,
    zc.buildout.testing.pkg_resources_deprecated,
    zc.buildout.testing.warnings_warn,
    zc.buildout.testing.ignore_root_logger,
])

_RST_PATHS = [
    ('getting_started',                    _DOC_DIR / 'getting-started.rst'),
    ('reference',                          _DOC_DIR / 'reference.rst'),
    ('bootstrapping',                      _DOC_DIR / 'topics' / 'bootstrapping.rst'),
    ('implicit_parts',                     _DOC_DIR / 'topics' / 'implicit-parts.rst'),
    ('variables_extending_substitutions',  _DOC_DIR / 'topics' / 'variables-extending-and-substitutions.rst'),
    ('writing_recipes',                    _DOC_DIR / 'topics' / 'writing-recipes.rst'),
    ('optimizing',                         _DOC_DIR / 'topics' / 'optimizing.rst'),
    ('meta_recipes',                       _DOC_DIR / 'topics' / 'meta-recipes.rst'),
]


def _doc_setup(test):
    """Mirror of docSetUp in test_all.py — provides the globals doc examples use."""
    def write(text, *path):
        with open(os.path.join(*path), 'w') as f:
            f.write(text)

    test.globs.update(
        run_buildout=zc.buildout.testing.run_buildout_in_process,
        yup=lambda cond, orelse='Nope': None if cond else orelse,
        nope=lambda cond, orelse='Nope': orelse if cond else None,
        eq=lambda a, b: None if a == b else (a, b),
        eqs=zc.buildout.testing.eqs,
        read=zc.buildout.testing.read,
        write=write,
        ls=lambda d='.', *rest: os.listdir(os.path.join(d, *rest)),
        join=os.path.join,
        clear_here=zc.buildout.testing.clear_here,
        os=os,
    )
    setupstack.setUpDirectory(test)


def _make_manuel():
    return (
        manuel.doctest.Manuel(
            optionflags=doctest.NORMALIZE_WHITESPACE | doctest.ELLIPSIS,
            checker=_NORMALIZERS,
        )
        + manuel.capture.Manuel()
    )


def _make_test_class(label, rst_path):
    """Return a unittest.TestCase class that runs one RST file via manuel."""

    class DocRstTest(unittest.TestCase):
        """Runs an RST file through manuel as a single unittest."""

        # Override __str__ so pytest shows a useful name
        def __str__(self):
            return f'test_doc_{label}'

        def runTest(self):
            suite = manuel.testing.TestSuite(
                _make_manuel(),
                str(rst_path),
                setUp=_doc_setup,
                tearDown=setupstack.tearDown,
            )
            result = unittest.TestResult()
            suite.run(result)
            errors = result.errors + result.failures
            if errors:
                self.fail('\n\n'.join(msg for _, msg in errors))

    DocRstTest.__name__ = f'test_doc_{label}'
    DocRstTest.__qualname__ = f'test_doc_{label}'
    return DocRstTest


# Skip entire module on Windows (doc tests use Unix paths)
if not sys.platform.startswith('win') and _DOC_DIR.exists():
    for _label, _path in _RST_PATHS:
        if _path.exists():
            _injected = _make_test_class(_label, _path)
            globals()[_injected.__name__] = _injected
    del _label, _path, _injected
