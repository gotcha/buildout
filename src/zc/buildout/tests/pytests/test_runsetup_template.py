"""Contract: the runsetup template pre-imports setuptools in pip mode only.

``bin/buildout setup`` (alias ``runsetup``) emits a temp script
assembled from ``easy_install.runsetup_template``.  In pip/legacy mode
the script still pre-imports setuptools — behavior unchanged.  In uv
mode it must not: uv installs carry no setuptools runtime dependency,
so a setup.py that needs setuptools imports it itself.  The check runs
in a subprocess so the installer mode is chosen by the environment,
exactly as in a real invocation.  See PLAN_UV_DEP_REMOVAL.md, Phase 4
item 2.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[4])

_EMIT = (
    'import zc.buildout.easy_install as ei\n'
    "fill = dict(setupdir='/d', setup='/d/setup.py',"
    " __file__='/d/setup.py', extra='')\n"
    'print(ei.runsetup_template % fill)\n'
)

SETUPTOOLS_IMPORT = re.compile(
    r'^\s*(from\s+setuptools\b|import\s[^#\n]*\bsetuptools\b)',
    re.MULTILINE)


def _emit_script(installer: str) -> str:
    env = dict(os.environ)
    env['PYTHONPATH'] = SRC + os.pathsep + env.get('PYTHONPATH', '')
    env['buildout_testing_installer'] = installer
    result = subprocess.run(
        [sys.executable, '-c', _EMIT],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_uv_mode_emitted_script_has_no_setuptools_import():
    assert not SETUPTOOLS_IMPORT.search(_emit_script('uv'))


def test_pip_mode_emitted_script_still_preimports_setuptools():
    assert SETUPTOOLS_IMPORT.search(_emit_script('pip'))
