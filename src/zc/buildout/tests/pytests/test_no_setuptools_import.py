"""Contract: importing zc.buildout.buildout must not import setuptools.

A top-level ``import distutils.errors`` is a runtime setuptools import
on Python 3.12+: with no stdlib distutils, setuptools'
``_distutils_hack`` meta-finder resolves it and loads setuptools
itself, so a grep for ``setuptools`` cannot see those pullers.  This
subprocess contract can.  See PLAN_UV_DEP_REMOVAL.md, Phase 1 item 3.

The same contract covers pkg_resources in any lineage, including the
vendored copy in ``zc.buildout._vendor``: a uv-mode run that never
resolves distributions must not pay for loading it.  See
PLAN_UV_DEP_REMOVAL.md, "Close the program" item 2.
"""

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


def test_importing_buildout_does_not_import_setuptools():
    # pkg_resources came up as blocked lineage in the next test now.
    result = _run_in_subprocess(
        'import sys\n'
        'import zc.buildout.buildout\n'
        "print('setuptools' in sys.modules)\n"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'False', result.stdout


def test_no_setuptools_or_pkg_resources_import():
    # Import-hook proof, not a grep: a meta_path blocker RAISES on any
    # import attempt of setuptools, pkg_resources, or the vendored
    # pkg_resources lineage while zc.buildout.buildout imports; a
    # post-import sys.modules sweep then double-checks that nothing of
    # those lineages slipped in.  The vendored copy is served on demand
    # by the bridge in zc/buildout/__init__.py, so a plain
    # ``import zc.buildout.buildout`` must not load any of it.
    result = _run_in_subprocess(
        'import sys\n'
        "VENDORED = 'zc.buildout._vendor.pkg_resources'\n"
        'class Blocker:\n'
        '    def find_spec(self, name, path=None, target=None):\n'
        "        top = name.split('.')[0]\n"
        "        if top in ('setuptools', 'pkg_resources') or name.startswith(VENDORED):\n"
        "            raise ImportError('blocked by import hook: ' + name)\n"
        '        return None\n'
        'sys.meta_path.insert(0, Blocker())\n'
        'import zc.buildout.buildout\n'
        'offenders = sorted(\n'
        '    m for m in sys.modules\n'
        "    if m.split('.')[0] in ('setuptools', 'pkg_resources')\n"
        '    or m.startswith(VENDORED))\n'
        'print(offenders)\n'
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '[]', result.stdout
