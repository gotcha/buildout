"""Contract: importing zc.buildout.buildout must not import setuptools.

A top-level ``import distutils.errors`` is a runtime setuptools import
on Python 3.12+: with no stdlib distutils, setuptools'
``_distutils_hack`` meta-finder resolves it and loads setuptools
itself, so a grep for ``setuptools`` cannot see those pullers.  This
subprocess contract can.  See PLAN_UV_DEP_REMOVAL.md, Phase 1 item 3.
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
    # pkg_resources stays in sys.modules by design: it is the vendored
    # copy, out of scope for this contract.
    result = _run_in_subprocess(
        'import sys\n'
        'import zc.buildout.buildout\n'
        "print('setuptools' in sys.modules)\n"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'False', result.stdout
