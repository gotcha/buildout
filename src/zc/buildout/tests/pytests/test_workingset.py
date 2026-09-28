"""Tests for the uv-mode working-set facade in zc.buildout._workingset."""

from __future__ import annotations

import os
import sys

import pkg_resources
import pytest
from packaging.requirements import Requirement as PackagingRequirement

from zc.buildout import _workingset
from zc.buildout.buildout import _dir_hash, _dists_sig


@pytest.fixture(autouse=True)
def _clean_global_working_set():
    """Restore the global pkg_resources working set after each test.

    The facade's add() forwards to it while pkg_resources is loaded,
    so tests that graft 'foo' dists must not leak them into each
    other.
    """
    by_key_before = dict(pkg_resources.working_set.by_key)
    entry_keys_before = {
        key: list(keys)
        for key, keys in pkg_resources.working_set.entry_keys.items()
    }
    yield
    pkg_resources.working_set.by_key.clear()
    pkg_resources.working_set.by_key.update(by_key_before)
    pkg_resources.working_set.entry_keys.clear()
    pkg_resources.working_set.entry_keys.update(entry_keys_before)


def _pkg_dist(location, project_name, version, precedence):
    return pkg_resources.Distribution(
        location=str(location),
        project_name=project_name,
        version=version,
        precedence=precedence,
    )


def _legacy_dists_sig(dists):
    """The pre-facade _dists_sig, kept here as the byte-identity oracle."""
    seen = set()
    result = []
    for dist in sorted(dists):
        if dist in seen:
            continue
        seen.add(dist)
        location = dist.location
        if dist.precedence == pkg_resources.DEVELOP_DIST:
            result.append(dist.project_name + '-' + _dir_hash(location))
        else:
            result.append(os.path.basename(location))
    return result


def test_dists_sig_matches_legacy_byte_for_byte(tmp_path):
    # A develop dist (sorted by hashcmp: parsed_version, precedence,
    # key, location) plus regular dists whose name order disagrees
    # with their version order, so the test proves the sort key
    # reproduces pkg_resources' version-first ordering.
    develop = tmp_path / 'develop-egg'
    develop.mkdir()
    (develop / 'setup.py').write_text('from setuptools import setup\n')
    dists = [
        _pkg_dist(tmp_path / 'eggs' / 'aaa-10.0.egg', 'aaa', '10.0',
                  pkg_resources.EGG_DIST),
        _pkg_dist(tmp_path / 'eggs' / 'zzz-9.0.egg', 'zzz', '9.0',
                  pkg_resources.EGG_DIST),
        _pkg_dist(develop, 'ddd', '0.1', pkg_resources.DEVELOP_DIST),
        # A duplicate of zzz: pkg_resources equality dedupes it.
        _pkg_dist(tmp_path / 'eggs' / 'zzz-9.0.egg', 'zzz', '9.0',
                  pkg_resources.EGG_DIST),
    ]
    assert _dists_sig(dists) == _legacy_dists_sig(dists)
    # aaa 10.0 sorts after zzz 9.0 (version first, not name).
    assert _dists_sig(dists) == [
        _legacy_dists_sig([dists[2]])[0],
        'zzz-9.0.egg',
        'aaa-10.0.egg',
    ]


def test_dists_sig_dotted_project_names(tmp_path):
    # project_name casing/spelling is metadata-exact; the key is the
    # lowercased (not canonicalized) name.
    location = tmp_path / 'eggs' / 'zc.recipe.egg-3.2.egg'
    dist = _pkg_dist(location, 'zc.recipe.egg', '3.2',
                     pkg_resources.EGG_DIST)
    assert _workingset.dist_key(dist) == 'zc.recipe.egg'
    assert _dists_sig([dist]) == ['zc.recipe.egg-3.2.egg']


def test_ambient_add_mirrors_pkg_resources_sys_path(tmp_path):
    location = str(tmp_path / 'foo-1.0.egg')
    dist = _pkg_dist(location, 'foo', '1.0', pkg_resources.EGG_DIST)
    ws = _workingset.AmbientWorkingSet()
    assert location not in sys.path
    try:
        ws.add(dist)
        assert location in sys.path
        assert dist in ws
        assert ws.by_key['foo'] is dist
        assert list(ws) == [dist]
    finally:
        if location in sys.path:
            sys.path.remove(location)


def test_ambient_add_forwards_to_loaded_pkg_resources(tmp_path):
    # pkg_resources EntryPoint.load() resolves requirements against the
    # global working set, so while pkg_resources is loaded the facade's
    # add() must register there too — exactly as when easy_install
    # received the global set directly.
    location = str(tmp_path / 'foo-1.0.egg')
    dist = _pkg_dist(location, 'foo', '1.0', pkg_resources.EGG_DIST)
    ws = _workingset.AmbientWorkingSet()
    ws.add(dist, insert=False)
    assert pkg_resources.working_set.by_key.get('foo') is dist


def test_ambient_truthiness_stays_truthy():
    # Installer.install reads bool(working_set) as for_buildout_run;
    # pkg_resources WorkingSet has no __len__, so even empty it is
    # truthy.  The facade must match.
    assert bool(_workingset.AmbientWorkingSet())


def test_ambient_find_and_conflict(tmp_path):
    dist = _pkg_dist(tmp_path / 'foo-1.0.egg', 'foo', '1.0',
                     pkg_resources.EGG_DIST)
    ws = _workingset.AmbientWorkingSet()
    ws.add(dist, insert=False)
    req = pkg_resources.Requirement.parse('foo>=1.0')
    assert ws.find(req) is dist
    with pytest.raises(pkg_resources.VersionConflict):
        ws.find(pkg_resources.Requirement.parse('foo>=99'))
    assert ws.find(pkg_resources.Requirement.parse('bar')) is None
    # packaging.Requirement works the same on held dists.
    assert ws.find(PackagingRequirement('foo>=1.0')) is dist


def test_ambient_find_bridges_to_loaded_pkg_resources(tmp_path):
    # While pkg_resources is loaded, environment lookups delegate to
    # its global working set — bit-identical to the legacy behavior.
    location = str(tmp_path / 'foo-1.0.egg')
    dist = _pkg_dist(location, 'foo', '1.0', pkg_resources.EGG_DIST)
    pkg_resources.working_set.add(dist, insert=False)
    ws = _workingset.AmbientWorkingSet()
    req = pkg_resources.Requirement.parse('foo')
    assert ws.find(req) is dist


def test_requirement_discrimination():
    # setuptools >= 75 makes pkg_resources.Requirement a subclass of
    # packaging.Requirement; the facade must not rely on isinstance.
    pkg_req = pkg_resources.Requirement.parse('foo>=1.0')
    assert _workingset._is_pkg_requirement(pkg_req)
    assert not _workingset._is_pkg_requirement(
        PackagingRequirement('foo>=1.0'))


def test_load_entry_point_and_missing_errors():
    # zc.buildout's own console script is always present in the test
    # environment.
    main = _workingset.load_entry_point(
        'zc.buildout', 'console_scripts', 'buildout')
    assert callable(main)
    import importlib.metadata
    with pytest.raises(importlib.metadata.PackageNotFoundError):
        _workingset.load_entry_point(
            'zc.buildout.no-such-dist', 'console_scripts', 'buildout')
    with pytest.raises(ImportError):
        _workingset.load_entry_point(
            'zc.buildout', 'console_scripts', 'no-such-script')


def test_iter_entry_points_finds_buildout_itself():
    names = [ep.name for ep in _workingset.iter_entry_points(
        'console_scripts', 'buildout')]
    assert 'buildout' in names


def test_resolve_bridges_to_pkg_resources():
    reqs = [pkg_resources.Requirement.parse('zc.buildout')]
    expected = pkg_resources.working_set.resolve(reqs)
    assert _workingset.resolve(reqs) == expected


def test_resolve_walker_signature_matches_legacy():
    # The uv-mode resolve walks requires metadata to importlib-shaped
    # dists; _dists_sig over them must be byte-identical to the legacy
    # pkg_resources resolve + signature, because the signatures
    # persist in .installed.cfg.
    legacy = _legacy_dists_sig(pkg_resources.working_set.resolve(
        [pkg_resources.Requirement.parse('zc.buildout')]))
    walked = _dists_sig(_workingset.resolve(
        [PackagingRequirement('zc.buildout')]))
    assert walked == legacy


def test_not_found_errors_includes_both_kinds():
    import importlib.metadata
    errors = _workingset.not_found_errors()
    assert importlib.metadata.PackageNotFoundError in errors
    # pkg_resources is loaded by this test module, so the pip-mode
    # error type is bridged in.
    assert pkg_resources.DistributionNotFound in errors
