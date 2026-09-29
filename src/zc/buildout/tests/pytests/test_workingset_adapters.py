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
        assert adapted.specs == legacy.specs, case
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
    egg_info = eggs / 'foo-1.0-py3.12.egg' / 'EGG-INFO'
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
    _write(eggs / 'bar-2.0-py3.12-macosx-11.0-arm64.egg'
           / 'EGG-INFO' / 'PKG-INFO',
           _pkg_info('bar', '2.0'))

    # Egg for a different Python version (rejected everywhere).
    _write(eggs / 'old-1.0-py2.7.egg' / 'EGG-INFO' / 'PKG-INFO',
           _pkg_info('old', '1.0'))

    # Zipped egg.
    zip_path = eggs / 'zipped-3.1-py3.12.egg'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr('EGG-INFO/PKG-INFO', _pkg_info('zipped', '3.1'))
        zf.writestr('EGG-INFO/requires.txt', 'qux\n')

    # Zipped egg without metadata: invisible to pkg_resources.
    with zipfile.ZipFile(eggs / 'meta-less-1.0-py3.12.egg', 'w') as zf:
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
    # Guard against a vacuous equality on an empty scan.
    assert {'foo', 'bar', 'qux', 'baz', 'legacy', 'zbc',
            'zipped'} <= set(adapted_dists)
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
    location = str(tmp_path / 'foo-1.0-py3.12.egg')
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


def _insertion_scenarios(tmp_path):
    egg = str(tmp_path / 'eggs' / 'foo-1.0-py3.12.egg')
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
        egg = str(tmp_path / 'eggs' / 'foo-1.0-py3.12.egg')
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
