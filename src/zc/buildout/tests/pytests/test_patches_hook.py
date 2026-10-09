"""Tests for the lazy pkg_resources patch trigger in zc.buildout.patches."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[4])


def _run_in_subprocess(code: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env['PYTHONPATH'] = SRC + os.pathsep + env.get('PYTHONPATH', '')
    return subprocess.run(
        [sys.executable, '-c', code],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_importing_pkg_resources_aliases_the_vendored_copy():
    # Post-vendoring contract: after importing zc.buildout,
    # `import pkg_resources` resolves to buildout's own vendored copy
    # (setuptools >= 82 no longer ships one), the same object under
    # both sys.modules names — never an installed setuptools' copy.
    # Except when some code imported a real pkg_resources before the
    # bridge fires (possible with setuptools < 82): that copy is kept
    # by design (module identity, see zc/buildout/__init__.py).
    result = _run_in_subprocess(
        'import sys\n'
        'import zc.buildout\n'
        'preexisting = sys.modules.get("pkg_resources")\n'
        'import pkg_resources\n'
        'if preexisting is not None:\n'
        '    assert pkg_resources is preexisting, pkg_resources.__name__\n'
        'else:\n'
        '    vendored = sys.modules["zc.buildout._vendor.pkg_resources"]\n'
        '    assert pkg_resources is vendored\n'
    )
    assert result.returncode == 0, result.stderr


def test_pkg_resources_import_applies_the_patches():
    # Legacy property: the first pkg_resources import applies the
    # patches before any pkg_resources object is used.  The patched
    # Requirement.__contains__ compares normalized names.
    result = _run_in_subprocess(
        'import zc.buildout\n'
        'import pkg_resources\n'
        'qualname = pkg_resources.Requirement.__contains__.__qualname__\n'
        'assert qualname.startswith("patch_pkg_resources_requirement_contains."), \\\n'
        '    "Requirement.__contains__ patch not applied: " + qualname\n'
    )
    assert result.returncode == 0, result.stderr


def test_pkg_resources_import_does_not_import_the_package_index():
    # uv-mode property: the index module is legacy pip-mode-only, so
    # importing pkg_resources alone must not drag it in.
    result = _run_in_subprocess(
        'import sys\n'
        'import zc.buildout\n'
        'import pkg_resources\n'
        "assert 'zc.buildout._package_index' not in sys.modules, "
        "'_package_index loaded with pkg_resources'\n"
    )
    assert result.returncode == 0, result.stderr


def test_package_index_import_applies_its_patch():
    # Legacy property: importing the index module applies
    # patch_PackageIndex before the class can be used.
    result = _run_in_subprocess(
        'import zc.buildout\n'
        'from zc.buildout import _package_index\n'
        'qualname = _package_index.PackageIndex.process_url.__qualname__\n'
        'assert qualname.startswith("patch_PackageIndex."), \\\n'
        '    "PackageIndex.process_url patch not applied: " + qualname\n'
    )
    assert result.returncode == 0, result.stderr


def test_easy_install_import_does_not_import_the_package_index():
    # uv-mode property: easy_install builds the index class lazily, so
    # importing it must not load the legacy index module.
    result = _run_in_subprocess(
        'import sys\n'
        'import zc.buildout.easy_install\n'
        "assert 'zc.buildout._package_index' not in sys.modules, "
        "'_package_index loaded with easy_install'\n"
    )
    assert result.returncode == 0, result.stderr


def test_apply_patches_is_idempotent():
    from zc.buildout import patches
    patches.apply_patches()
    patches.apply_patches()


def test_hook_installed_once():
    from zc.buildout import patches
    before = [f for f in sys.meta_path if isinstance(f, patches._PatchTriggerFinder)]
    patches.install_import_hook()
    after = [f for f in sys.meta_path if isinstance(f, patches._PatchTriggerFinder)]
    assert len(before) == 1
    assert len(after) == 1
