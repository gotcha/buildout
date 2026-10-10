"""Byte-identity pins for the uv-mode dist model.

The facade classes in ``zc.buildout._workingset`` (``Requirement``,
``Distribution``, ``Environment``) replace pkg_resources objects on
the installer=uv path.  Everything observable about them — string
forms, reprs, ordering, containment, scan results — must match what
pkg_resources produces, because doctest transcripts and
``.installed.cfg`` signatures record these spellings.  These tests
assert that equality against the real pkg_resources (and buildout's
own ``easy_install.Environment``) on fixture trees and case tables.
"""

import os
import sys
import zipfile

import pkg_resources
import pytest

import zc.buildout.easy_install
from zc.buildout import _workingset

# Egg file names carry the running interpreter's tag: the Environment
# scanners reject dists tagged for a different Python, so a hard-coded
# tag silently empties the fixtures on any other interpreter (the CI
# sweep legs run 3.10 while this module was written under 3.12).
PYVER = f'py{sys.version_info.major}.{sys.version_info.minor}'

REQUIREMENT_CASES = [
    'zc.buildout',
    'foo>=1.0',
    'foo>=1.0, <2',
    'foo[bar] >= 1.0',
    "foo; python_version<'3'",
    'foo (>=1.0)',
    'Foo_Bar==2.0',
    'foo!=1.5',
    'foo~=1.4',
    'foo[bar,baz]',
    'foo[bar]>1.0; python_version>"3.8"',
    'setuptools',
]


def test_requirement_str_repr_key_specs_match_pkg_resources():
    for case in REQUIREMENT_CASES:
        legacy = pkg_resources.Requirement.parse(case)
        adapted = _workingset.Requirement.parse(case)
        assert str(adapted) == str(legacy), case
        assert repr(adapted) == repr(legacy), case
        assert adapted.key == legacy.key, case
        assert adapted.project_name == legacy.project_name, case
        # .specs order is the underlying packaging's SpecifierSet
        # iteration order: canonical-sorted in modern packaging, but
        # raw set order in the packagings old setuptools vendor —
        # hash-random per process there.  The constraint set is the
        # parity contract, not the incidental order.
        assert sorted(adapted.specs) == sorted(legacy.specs), case
        assert list(adapted.extras) == list(legacy.extras), case


def test_requirement_equality_and_hash_match_within_shape():
    legacy_a = pkg_resources.Requirement.parse('foo[bar]>=1.0')
    legacy_b = pkg_resources.Requirement.parse('foo[bar]>=1.0')
    legacy_c = pkg_resources.Requirement.parse('foo[bar]>=2.0')
    adapted_a = _workingset.Requirement.parse('foo[bar]>=1.0')
    adapted_b = _workingset.Requirement.parse('foo[bar]>=1.0')
    adapted_c = _workingset.Requirement.parse('foo[bar]>=2.0')
    assert (adapted_a == adapted_b) == (legacy_a == legacy_b)
    assert (adapted_a == adapted_c) == (legacy_a == legacy_c)
    assert (adapted_a != adapted_b) == (legacy_a != legacy_b)
    # Hash semantics match: equal requirements hash equal.
    assert hash(adapted_a) == hash(adapted_b)
    # Set dedup behaves identically (the installers' `processed` set).
    legacy_set = {legacy_a, legacy_b, legacy_c}
    adapted_set = {adapted_a, adapted_b, adapted_c}
    assert len(adapted_set) == len(legacy_set) == 2


def _dist_attrs(dist) -> tuple:
    """The observable attribute tuple compared across implementations."""
    extras = list(dist.extras)
    requires = [str(r) for r in dist.requires()]
    return (
        str(dist),
        repr(dist),
        dist.key,
        dist.project_name,
        dist.version,
        str(dist.parsed_version),
        dist.precedence,
        dist.location,
        dist.py_version,
        dist.platform,
        dist.egg_name(),
        dist.has_version(),
        extras,
        requires,
    )


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _pkg_info(name, version):
    return f'Metadata-Version: 1.0\nName: {name}\nVersion: {version}\n'


@pytest.fixture
def fixture_tree(tmp_path):
    """A directory tree covering the shapes buildout scans."""
    eggs = tmp_path / 'eggs'
    site = tmp_path / 'site'
    proj = tmp_path / 'proj'
    for directory in (eggs, site, proj):
        directory.mkdir()

    # Classic unpacked egg with the full metadata set.
    egg_info = eggs / f'foo-1.0-{PYVER}.egg' / 'EGG-INFO'
    _write(egg_info / 'PKG-INFO', _pkg_info('foo', '1.0'))
    _write(egg_info / 'requires.txt',
           '# comment line\n'
           'baz>=1.0\n'
           '\n'
           '[test]\n'
           'pytest\n'
           '[docs:python_version>"3"]\n'
           'sphinx\n')
    _write(egg_info / 'entry_points.txt',
           '[console_scripts]\nfoo = foo.cli:main\n')
    _write(egg_info / 'namespace_packages.txt', 'foo\n')
    _write(egg_info / 'top_level.txt', 'foo\n')

    # Platform egg from an older macOS major (exercises the can_add
    # machine-type override on darwin).
    _write(eggs / f'bar-2.0-{PYVER}-macosx-11.0-arm64.egg'
           / 'EGG-INFO' / 'PKG-INFO',
           _pkg_info('bar', '2.0'))

    # Egg for a different Python version (rejected everywhere).
    _write(eggs / 'old-1.0-py2.7.egg' / 'EGG-INFO' / 'PKG-INFO',
           _pkg_info('old', '1.0'))

    # Zipped egg.
    zip_path = eggs / f'zipped-3.1-{PYVER}.egg'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr('EGG-INFO/PKG-INFO', _pkg_info('zipped', '3.1'))
        zf.writestr('EGG-INFO/requires.txt', 'qux\n')

    # Zipped egg without metadata: invisible to pkg_resources.
    with zipfile.ZipFile(eggs / f'meta-less-1.0-{PYVER}.egg', 'w') as zf:
        zf.writestr('meta/__init__.py', '')

    # dist-info directly on the path entry (site-packages style).
    _write(site / 'qux-4.2.dist-info' / 'METADATA',
           'Metadata-Version: 2.1\nName: qux\nVersion: 4.2\n'
           'Requires-Dist: foo>=1.0\n'
           'Provides-Extra: test\n'
           'Requires-Dist: pytest; extra == "test"\n'
           'Requires-Dist: wheel; python_version > "3"\n')
    # dist-info whose directory name and metadata disagree: the
    # directory name wins (pkg_resources rule).
    _write(site / 'baz-1.0-1.dist-info' / 'METADATA',
           'Metadata-Version: 2.1\nName: baz\nVersion: 1.0.post1\n')

    # dist-info in wheel-escaped spelling: the directory name carries
    # the dot of 'zc.buildout' as an underscore, so both environments
    # key the dist 'zc-buildout' (safe_name runs to dashes) while
    # requirement strings keep spelling 'zc.buildout'.  Matching the
    # requirement to the dist goes through the canonicalized seams:
    # the Environment keying and the normalized keys in the patched
    # Requirement.__contains__ (patches.py).
    _write(site / 'zc_buildout-3.5.0.dist-info' / 'METADATA',
           'Metadata-Version: 2.1\nName: zc.buildout\nVersion: 3.5.0\n')

    # Single-file egg-info.
    _write(site / 'legacy-0.1.egg-info', _pkg_info('legacy', '0.1'))

    # A develop project reached through an egg-link.
    _write(proj / 'zbc.egg-info' / 'PKG-INFO', _pkg_info('zbc', '5.0'))
    _write(proj / 'zbc.egg-info' / 'requires.txt', 'foo\n')
    _write(eggs / 'zbc.egg-link', f'{proj}\n.\n')

    # Empty metadata dir: skipped by pkg_resources.
    (site / 'empty-1.0.dist-info').mkdir()

    return eggs, site, proj


def _environment_dists(env, facade: bool) -> dict:
    """{project key: [attribute tuples]} for an environment."""
    result = {}
    for project_name in env:
        result[project_name] = [_dist_attrs(dist)
                                for dist in env[project_name]]
    return result


def test_environment_scan_matches_easy_install(fixture_tree):
    eggs, site, _proj = fixture_tree
    paths = [str(eggs), str(site)]
    legacy = zc.buildout.easy_install.Environment(paths)
    adapted = _workingset.Environment(paths)
    adapted_dists = _environment_dists(adapted, True)
    # Guard against a vacuous equality on an empty scan.  'bar' is a
    # macosx platform egg: off macOS both environments reject it (the
    # equality below is still checked there); on Apple silicon the
    # machine-type override accepts it.
    expected = {'foo', 'qux', 'baz', 'legacy', 'zbc', 'zipped'}
    if sys.platform == 'darwin':
        expected.add('bar')
    assert expected <= set(adapted_dists)
    assert adapted_dists == _environment_dists(legacy, False)


def test_environment_lookup_normalizes_names(fixture_tree):
    eggs, _site, _proj = fixture_tree
    adapted = _workingset.Environment([str(eggs)])
    assert [str(d) for d in adapted['foo']] == ['foo 1.0']
    assert [str(d) for d in adapted['Foo']] == ['foo 1.0']
    assert [str(d) for d in adapted['FOO']] == ['foo 1.0']
    assert adapted['nonexistent'] == []


def test_egg_link_dist_is_develop_at_project_root(fixture_tree):
    eggs, _site, proj = fixture_tree
    adapted = _workingset.Environment([str(eggs)])
    dists = adapted['zbc']
    assert len(dists) == 1
    dist = dists[0]
    assert dist.precedence == _workingset.DEVELOP_DIST
    assert dist.location is not None
    assert os.path.realpath(dist.location) == os.path.realpath(
        str(proj))
    assert [str(r) for r in dist.requires()] == ['foo']


def test_egg_requires_extras_and_unknown_extra(fixture_tree):
    eggs, _site, _proj = fixture_tree
    legacy_env = zc.buildout.easy_install.Environment([str(eggs)])
    adapted_env = _workingset.Environment([str(eggs)])
    legacy = legacy_env['foo'][0]
    adapted = adapted_env['foo'][0]
    for extras in ((), ('test',)):
        assert [str(r) for r in adapted.requires(extras)] == \
            [str(r) for r in legacy.requires(extras)]
    with pytest.raises(_workingset.UnknownExtra):
        adapted.requires(('nope',))
    with pytest.raises(pkg_resources.UnknownExtra):
        legacy.requires(('nope',))
    assert list(adapted.extras) == list(legacy.extras)


def test_dist_info_requires_and_extras(fixture_tree):
    _eggs, site, _proj = fixture_tree
    legacy_env = zc.buildout.easy_install.Environment([str(site)])
    adapted_env = _workingset.Environment([str(site)])
    legacy = legacy_env['qux'][0]
    adapted = adapted_env['qux'][0]
    assert [str(r) for r in adapted.requires()] == \
        [str(r) for r in legacy.requires()]
    assert [str(r) for r in adapted.requires(('test',))] == \
        [str(r) for r in legacy.requires(('test',))]
    assert list(adapted.extras) == list(legacy.extras)


def test_dist_info_version_comes_from_directory_name(fixture_tree):
    _eggs, site, _proj = fixture_tree
    adapted = _workingset.Environment([str(site)])
    dist = adapted['baz'][0]
    assert dist.version == '1.0'
    assert str(dist.parsed_version) == '1.0'


def test_distribution_comparison_semantics():
    def legacy(location, version='1.0'):
        return pkg_resources.Distribution(
            location=location, project_name='foo', version=version)

    def adapted(location, version='1.0'):
        return _workingset.Distribution(
            location=location, project_name='foo', version=version)

    a_legacy, a_adapted = legacy('/x'), adapted('/x')
    b_legacy, b_adapted = legacy('/y'), adapted('/y')
    assert (a_adapted == a_adapted) == (a_legacy == a_legacy)
    assert (a_adapted == b_adapted) == (a_legacy == b_legacy)
    assert (a_adapted < b_adapted) == (a_legacy < b_legacy)
    assert hash(a_adapted) == hash(adapted('/x'))
    assert sorted([b_adapted, a_adapted]) == [a_adapted, b_adapted]


def test_distribution_str_and_repr_match_pkg_resources(tmp_path):
    location = str(tmp_path / f'foo-1.0-{PYVER}.egg')
    legacy = pkg_resources.Distribution(
        location=location, project_name='Foo_Bar', version='1.0')
    adapted = _workingset.Distribution(
        location=location, project_name='Foo_Bar', version='1.0')
    assert str(adapted) == str(legacy) == 'Foo-Bar 1.0'
    assert repr(adapted) == repr(legacy)
    assert adapted.key == legacy.key == 'foo-bar'
    assert adapted.egg_name() == legacy.egg_name()


def test_requirement_contains_matches_pkg_resources(tmp_path):
    def pair(version):
        legacy = pkg_resources.Distribution(
            location=str(tmp_path), project_name='foo',
            version=version)
        adapted = _workingset.Distribution(
            location=str(tmp_path), project_name='foo',
            version=version)
        return legacy, adapted

    for spec in ('foo>=1.0', 'foo>1.0', 'foo==1.0', 'foo',
                 'foo>=1.0a1', 'bar>=1.0'):
        legacy_req = pkg_resources.Requirement.parse(spec)
        adapted_req = _workingset.Requirement.parse(spec)
        legacy_dist, adapted_dist = pair('1.0')
        assert (adapted_dist in adapted_req) == \
            (legacy_dist in legacy_req), spec
    # Prereleases always allowed, both shapes.
    legacy_req = pkg_resources.Requirement.parse('foo>=1.0')
    adapted_req = _workingset.Requirement.parse('foo>=1.0')
    legacy_dist, adapted_dist = pair('1.1a1')
    assert (adapted_dist in adapted_req) == (legacy_dist in legacy_req)


def test_requirement_contains_normalizes_divergent_keys(fixture_tree):
    # A zc.buildout-lookalike installed from a wheel: the dist-info
    # directory spells the dot as an underscore, so the dist is keyed
    # 'zc-buildout' (safe_name, directory name) while the requirement
    # string spells 'zc.buildout'.  Requirement.__contains__ must
    # treat them as the same project, as the patched pkg_resources
    # does (patches.patch_pkg_resources_requirement_contains): this is
    # the lookup the offline toolchain resolve relies on, and its
    # failure is the "can't install one in offline (no-install) mode"
    # boot error against wheel-installed buildouts.
    _eggs, site, _proj = fixture_tree
    legacy_env = zc.buildout.easy_install.Environment([str(site)])
    adapted_env = _workingset.Environment([str(site)])
    for spec in ('zc.buildout', 'zc-buildout', 'zc_buildout'):
        legacy_req = pkg_resources.Requirement.parse(spec)
        adapted_req = _workingset.Requirement.parse(spec)
        legacy_matches = [d.version
                          for d in legacy_env['zc.buildout']
                          if d in legacy_req]
        adapted_matches = [d.version
                           for d in adapted_env['zc.buildout']
                           if d in adapted_req]
        assert adapted_matches == legacy_matches == ['3.5.0'], spec


def test_dist_entry_points_matches_across_dist_shapes(fixture_tree):
    # easy_install re-exports scripts._dist_entry_points; it dispatches
    # on the dist shape, not the installer mode: legacy recipes
    # (zc.recipe.egg 2.0.7, pulled in by plone.recipe.zope2instance
    # 8.0.0 — the Plone 6.0 pin) rebuild the working set with
    # pkg_resources.WorkingSet, so a uv-mode run holds pkg-shaped
    # dists, and mode-keyed extraction probed the facade-only
    # `entry_points` attribute and crashed.  The foo egg carries
    # console_scripts metadata; both shapes must extract the same
    # triples in the same order.
    eggs, _site, _proj = fixture_tree
    legacy_env = zc.buildout.easy_install.Environment([str(eggs)])
    adapted_env = _workingset.Environment([str(eggs)])
    extract = zc.buildout.easy_install._dist_entry_points
    expected = [('foo', 'foo.cli', 'main')]
    assert extract(adapted_env['foo'][0]) == expected
    assert extract(legacy_env['foo'][0]) == expected


def test_metadata_isdir_and_listdir_match_pkg_resources(tmp_path):
    # The distutils-scripts discovery in scripts.py reads
    # metadata_isdir/metadata_listdir; pkg_resources' Distribution
    # reaches them through provider delegation.
    egg = tmp_path / f'foo-1.0-{PYVER}.egg'
    _write(egg / 'EGG-INFO' / 'PKG-INFO', _pkg_info('foo', '1.0'))
    _write(egg / 'EGG-INFO' / 'scripts' / 'run.sh', '#!/bin/sh\n')
    _write(egg / 'EGG-INFO' / 'scripts' / 'sub' / 'deep.sh', '#!/bin/sh\n')
    zip_path = tmp_path / f'zip-2.0-{PYVER}.egg'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr('EGG-INFO/PKG-INFO', _pkg_info('zip', '2.0'))
        zf.writestr('EGG-INFO/scripts/tool.sh', '#!/bin/sh\n')
        zf.writestr('EGG-INFO/scripts/sub/deep.sh', '')

    # Construction must go through the Environment scan: only the
    # scanner attaches the metadata provider pkg_resources delegates
    # to (Distribution.from_location without metadata leaves an
    # EmptyProvider that reports False/[] for everything).
    legacy_env = pkg_resources.Environment([str(tmp_path)])
    adapted_env = _workingset.Environment([str(tmp_path)])
    for project in ('foo', 'zip'):
        legacy = legacy_env[project][0]
        adapted = adapted_env[project][0]
        for name in ('scripts', 'scripts/sub', 'missing', ''):
            assert adapted.metadata_isdir(name) == \
                legacy.metadata_isdir(name), (project, name)
            if legacy.metadata_isdir(name):
                assert sorted(adapted.metadata_listdir(name)) == \
                    sorted(legacy.metadata_listdir(name)), (project, name)


def test_clone_matches_pkg_resources(tmp_path):
    # Installer.build's uv branch clones the fetched dist with the
    # downloaded location; pkg_resources.Distribution.clone semantics
    # (carry-over plus keyword substitution) are the contract.
    _write(tmp_path / 'qux-4.2.dist-info' / 'METADATA',
           'Metadata-Version: 2.1\nName: qux\nVersion: 4.2\n')
    _write(tmp_path / f'foo-1.0-{PYVER}.egg' / 'EGG-INFO' / 'PKG-INFO',
           _pkg_info('foo', '1.0'))
    legacy_env = pkg_resources.Environment([str(tmp_path)])
    adapted_env = _workingset.Environment([str(tmp_path)])
    new_location = str(tmp_path / 'downloaded')
    for project in ('qux', 'foo'):
        legacy = legacy_env[project][0]
        adapted = adapted_env[project][0]
        legacy_clone = legacy.clone(location=new_location)
        adapted_clone = adapted.clone(location=new_location)
        for attr in ('project_name', 'version', 'py_version',
                     'platform', 'precedence', 'key'):
            assert getattr(adapted_clone, attr) == \
                getattr(legacy_clone, attr), (project, attr)
        assert adapted_clone.location == legacy_clone.location == \
            new_location
        # The metadata provider carries over untouched.
        assert adapted_clone._provider is adapted._provider
        assert legacy_clone._provider is legacy._provider
        # PKG_INFO stays what the shape dictates ('METADATA' for
        # dist-info, 'PKG-INFO' for the egg): pkg keeps it through
        # the DistInfoDistribution class attribute, the facade
        # through its instance-override copy.
        assert adapted_clone.PKG_INFO == legacy_clone.PKG_INFO, project
    # A no-kwarg clone is an attribute-identical copy (pkg semantics:
    # the __init__ normalizers are idempotent on normalized values).
    adapted = adapted_env['qux'][0]
    clone = adapted.clone()
    for attr in ('project_name', 'version', 'py_version', 'platform',
                 'precedence', 'key', 'location'):
        assert getattr(clone, attr) == getattr(adapted, attr), attr


def test_working_set_iteration_follows_entry_order():
    # pkg_resources iterates a working set in entries order, where
    # insert_on's replace front-insertion can invert the add order;
    # the easy_install graft relies on that to list freshly installed
    # closures dependency-first.
    legacy_ws = pkg_resources.WorkingSet([])
    adapted_ws = _workingset.AmbientWorkingSet([])
    for name in ('demo', 'demoneeded'):
        location = f'/eggs/{name}-1.0-{PYVER}.egg'
        legacy_ws.add(
            pkg_resources.Distribution(
                location=location, project_name=name, version='1.0'),
            replace=True)
        adapted_ws.add(
            _workingset.Distribution(
                location=location, project_name=name, version='1.0'),
            replace=True)
    assert [d.key for d in adapted_ws] == [d.key for d in legacy_ws] \
        == ['demoneeded', 'demo']


def _insertion_scenarios(tmp_path):
    egg = str(tmp_path / 'eggs' / f'foo-1.0-{PYVER}.egg')
    parent = str(tmp_path / 'eggs')
    other = str(tmp_path / 'other')
    return [
        ('empty', [], {}),
        ('parent present', [parent], {}),
        ('already there', [egg], {}),
        ('replace with parent', [parent], {'replace': True}),
        ('unrelated', [other], {}),
    ]


def test_insert_on_matches_pkg_resources(tmp_path):
    for name, initial, kwargs in _insertion_scenarios(tmp_path):
        egg = str(tmp_path / 'eggs' / f'foo-1.0-{PYVER}.egg')
        legacy = pkg_resources.Distribution(
            location=egg, project_name='foo', version='1.0',
            precedence=pkg_resources.EGG_DIST)
        adapted = _workingset.Distribution(
            location=egg, project_name='foo', version='1.0',
            precedence=_workingset.EGG_DIST)
        legacy_path = list(initial)
        adapted_path = list(initial)
        legacy.insert_on(legacy_path, **kwargs)
        adapted.insert_on(adapted_path, **kwargs)
        assert [os.path.realpath(p) for p in adapted_path] == \
            [os.path.realpath(p) for p in legacy_path], name


def test_working_set_add_find_and_conflict(fixture_tree):
    eggs, _site, _proj = fixture_tree
    env = _workingset.Environment([str(eggs)])
    dist = env['foo'][0]
    ws = _workingset.AmbientWorkingSet([])
    assert dist not in ws
    ws.add(dist)
    assert dist in ws
    assert ws.by_key['foo'] == dist
    adapted_req = _workingset.Requirement.parse('foo>=2.0')
    found = ws.find(_workingset.Requirement.parse('foo>=1.0'))
    assert found == dist
    # The conflict class bridges: pkg_resources' own while it is
    # loaded (as in this test process), the facade's otherwise.  Both
    # carry (dist, req) in args, which errors.VersionConflict formats.
    with pytest.raises(
            (pkg_resources.VersionConflict,
             _workingset.VersionConflict)) as excinfo:
        ws.find(_workingset.Requirement.parse('foo>=2.0'))
    assert excinfo.value.args[0] == dist
    assert str(excinfo.value.args[1]) == 'foo>=2.0'
    # The pkg-absent class directly, since the bridge hides it here.
    err = _workingset.VersionConflict(dist, adapted_req)
    assert err.args == (dist, adapted_req)
    # Unknown project: a plain miss, like pkg_resources.
    assert ws.find(_workingset.Requirement.parse('nope')) is None


def test_ambient_working_set_entries_is_sys_path_by_default():
    assert _workingset.AmbientWorkingSet().entries is sys.path
    assert _workingset.AmbientWorkingSet([]).entries == []
    assert _workingset.AmbientWorkingSet([]).entries is not sys.path


def test_can_add_matrix_matches_easy_install(fixture_tree):
    """can_add parity across platform/python combinations."""
    eggs, _site, _proj = fixture_tree
    for platform, python in (
            (None, None),
            ('macosx-14.8-arm64', None),
            ('macosx-11.0-arm64', None),
            ('linux-x86_64', None),
            (None, '2.7'),
    ):
        legacy = zc.buildout.easy_install.Environment(
            [], platform=platform, python=python)
        adapted = _workingset.Environment(
            [], platform=platform, python=python)
        for entry in sorted(os.listdir(eggs)):
            full = str(eggs / entry)
            if not entry.endswith('.egg') or not os.path.isdir(full):
                continue
            legacy_dist = pkg_resources.Distribution.from_filename(full)
            adapted_dist = _workingset.Distribution.from_egg(full)
            assert legacy.can_add(legacy_dist) == \
                adapted.can_add(adapted_dist), (platform, python, entry)
