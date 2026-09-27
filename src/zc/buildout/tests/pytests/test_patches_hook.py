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


def test_importing_buildout_does_not_import_pkg_resources():
    # The uv-mode property: importing zc.buildout installs the patch
    # trigger but must not load pkg_resources.
    result = _run_in_subprocess(
        'import sys\n'
        'import zc.buildout\n'
        "assert 'pkg_resources' not in sys.modules, "
        "'pkg_resources loaded at import'\n"
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
