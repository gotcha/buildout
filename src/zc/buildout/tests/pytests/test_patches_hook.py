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


def _setuptools_import_drags_pkg_resources() -> bool:
    """Whether ``import setuptools`` loads an installed pkg_resources.

    True on setuptools < 68: its own import drags pkg_resources into
    sys.modules, so the vendored-copy alias finds the module already
    loaded and keeps it (module identity, see zc/buildout/__init__.py).
    Probe in a fresh interpreter — this test process has long imported
    both, so its sys.modules cannot answer the question.
    """
    result = _run_in_subprocess(
        'import sys\n'
        'import setuptools\n'
        "print('pkg_resources' in sys.modules)\n"
    )
    return result.stdout.strip() == 'True'


def test_importing_buildout_aliases_the_vendored_pkg_resources():
    # Post-vendoring contract: importing zc.buildout installs its own
    # pkg_resources copy as plain `pkg_resources` (setuptools >= 82 no
    # longer ships one), so the module is present right away — and it
    # must be ours, not an installed setuptools' copy.  Except on
    # setuptools < 68: there `import setuptools` itself drags the
    # installed copy in before the alias can install, and that copy is
    # kept by design.
    expected = ('pkg_resources'
                if _setuptools_import_drags_pkg_resources()
                else 'zc.buildout._vendor.pkg_resources')
    result = _run_in_subprocess(
        'import sys\n'
        'import zc.buildout\n'
        "name = sys.modules['pkg_resources'].__name__\n"
        f"assert name == {expected!r}, name\n"
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
