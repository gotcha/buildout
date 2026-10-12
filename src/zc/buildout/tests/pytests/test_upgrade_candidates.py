"""Unit pins for the metadata-derived upgrade candidate list.

``buildout._upgrade_candidates`` derives the self-upgrade seek list
from zc.buildout's own Requires-Dist lines: mode extras are
marker-evaluated (uv mode: base only; pip mode: base plus the
``zc.buildout[pip]`` extra — and pip mode never touches uv), names are
canonicalized, deduped first-occurrence, kept in declaration order,
and zc.buildout itself is prepended.  The full 8-cell table
(installer x sys_platform x python_version) is pinned here against
fabricated Requires-Dist lines mirroring setup.py; the transcript
corpora assert only the canonical ``Installing`` lines folded by
``testing.normalize_upgrade_install_line``.
"""

from __future__ import annotations

import logging
from importlib import metadata as importlib_metadata

import packaging.markers
import pytest

from zc.buildout import buildout

REQUIRES_DIST = [
    # Mirrors setup.py: install_requires, then the [pip] extra's
    # entries, in declaration order.
    'setuptools>=75.8.2; sys_platform == "win32"',
    'packaging>=23.2',
    'platformdirs',
    'uv>=0.12.11',
    'tomli; python_version < "3.11"',
    'pip>=25.0; extra == "pip"',
    'setuptools>=75.8.2; extra == "pip"',
]


def _marker_environment(sys_platform: str, python_version: str) -> dict:
    return {
        'implementation_name': 'cpython',
        'implementation_version': f'{python_version}.0',
        'os_name': 'nt' if sys_platform == 'win32' else 'posix',
        'platform_machine': 'x86_64',
        'platform_python_implementation': 'CPython',
        'platform_release': '',
        'platform_system': 'Windows' if sys_platform == 'win32' else 'Linux',
        'platform_version': '',
        'python_full_version': f'{python_version}.0',
        'python_version': python_version,
        'sys_platform': sys_platform,
        'extra': '',
    }


@pytest.fixture
def fabricated_environment(monkeypatch, sys_platform, python_version):
    """Fabricated Requires-Dist lines evaluated under a fabricated platform.

    ``metadata.requires`` is patched on the importlib.metadata module
    object that buildout imported; ``default_environment`` feeds
    ``Marker.evaluate`` the pinned sys_platform/python_version while the
    code under test overrides ``extra`` per installer mode.
    """
    monkeypatch.setattr(
        buildout.metadata, 'requires', lambda name: list(REQUIRES_DIST))
    monkeypatch.setattr(
        packaging.markers, 'default_environment',
        lambda: _marker_environment(sys_platform, python_version))


OS_PY = [('linux', '3.12'), ('linux', '3.10'),
         ('win32', '3.12'), ('win32', '3.10')]

# The declared candidate table: one cell per (installer, platform).  The
# uv cells seek the base requires only (uv included: an upgraded uv dist
# carries its own binary); the pip cells seek base plus the [pip] extra,
# never uv.  tomli sorts after uv and before pip because setup.py
# declares it last in install_requires (declaration order, Q5); win32
# setuptools sits first as the first declared line.
UV_CANDIDATES = {
    ('linux', '3.12'): ('zc.buildout', 'packaging', 'platformdirs', 'uv'),
    ('linux', '3.10'): ('zc.buildout', 'packaging', 'platformdirs', 'uv',
                        'tomli'),
    ('win32', '3.12'): ('zc.buildout', 'setuptools', 'packaging',
                        'platformdirs', 'uv'),
    ('win32', '3.10'): ('zc.buildout', 'setuptools', 'packaging',
                        'platformdirs', 'uv', 'tomli'),
}
PIP_CANDIDATES = {
    ('linux', '3.12'): ('zc.buildout', 'packaging', 'platformdirs', 'pip',
                        'setuptools'),
    ('linux', '3.10'): ('zc.buildout', 'packaging', 'platformdirs', 'tomli',
                        'pip', 'setuptools'),
    ('win32', '3.12'): ('zc.buildout', 'setuptools', 'packaging',
                        'platformdirs', 'pip'),
    ('win32', '3.10'): ('zc.buildout', 'setuptools', 'packaging',
                        'platformdirs', 'tomli', 'pip'),
}


@pytest.mark.parametrize('installer,table', [('uv', UV_CANDIDATES),
                                             ('pip', PIP_CANDIDATES)])
@pytest.mark.parametrize('sys_platform,python_version', OS_PY)
def test_candidate_table_cell(fabricated_environment, installer, table,
                              sys_platform, python_version):
    assert buildout._upgrade_candidates(installer) == table[
        (sys_platform, python_version)]


def test_duplicate_names_dedupe_first_occurrence(monkeypatch):
    # setuptools declared twice (win32 base + [pip] extra) lands once, in
    # its first position, whichever extra activated it.
    monkeypatch.setattr(buildout.metadata, 'requires', lambda name: [
        'setuptools>=75.8.2; sys_platform == "win32"',
        'packaging',
        'setuptools>=75.8.2; extra == "pip"',
    ])
    monkeypatch.setattr(
        packaging.markers, 'default_environment',
        lambda: _marker_environment('win32', '3.12'))
    assert buildout._upgrade_candidates('pip') == (
        'zc.buildout', 'setuptools', 'packaging')


def test_declaration_order_is_kept_not_sorted(monkeypatch):
    monkeypatch.setattr(buildout.metadata, 'requires', lambda name: [
        'zzz-project', 'aaa-project',
    ])
    monkeypatch.setattr(
        packaging.markers, 'default_environment',
        lambda: _marker_environment('linux', '3.12'))
    assert buildout._upgrade_candidates('uv') == (
        'zc.buildout', 'zzz-project', 'aaa-project')


def test_pip_mode_drops_uv_entirely(monkeypatch):
    # Owner directive: in pip mode the uv dependency is neither upgraded
    # nor explored — it never reaches the resolver, even when the
    # metadata declares it unconditionally.
    monkeypatch.setattr(buildout.metadata, 'requires', lambda name: [
        'uv>=0.12.11', 'packaging',
    ])
    monkeypatch.setattr(
        packaging.markers, 'default_environment',
        lambda: _marker_environment('linux', '3.12'))
    candidates = buildout._upgrade_candidates('pip')
    assert candidates == ('zc.buildout', 'packaging')
    assert 'uv' not in candidates


def test_missing_metadata_falls_back_to_self_only(monkeypatch, caplog):
    def no_metadata(name):
        raise importlib_metadata.PackageNotFoundError(name)
    monkeypatch.setattr(buildout.metadata, 'requires', no_metadata)
    with caplog.at_level(logging.DEBUG, logger='zc.buildout'):
        candidates = buildout._upgrade_candidates('uv')
    assert candidates == ('zc.buildout',)
    assert any(
        'No distribution metadata for zc.buildout' in record.getMessage()
        for record in caplog.records)
