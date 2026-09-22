"""Unit tests for the uv-mode install-loop bypass (Installer._install_uv)."""
import logging

import pkg_resources
import pytest

import zc.buildout
from zc.buildout import easy_install, uv_resolve
from zc.buildout.errors import MissingDistribution


def _dist(name, version, location=None, precedence=pkg_resources.EGG_DIST):
    return pkg_resources.Distribution(
        project_name=name, version=version,
        location=location or f'/eggs/{name}', precedence=precedence)


def _pin(name, version, directory=None):
    return uv_resolve.PinnedDist(
        name=name, version=version,
        url=('' if directory is not None
             else f'file:///wheels/{name}-{version}-py3-none-any.whl'),
        sha256=None, sdist_url=None, sdist_sha256=None,
        directory=directory)


def _installer(monkeypatch, tmp_path, newest=False, versions=None,
               env_dists=(), dest='eggs'):
    """An Installer in uv mode whose ``_env`` holds exactly ``env_dists``."""
    monkeypatch.setattr(easy_install.Installer, '_installer', 'uv')
    monkeypatch.setattr(easy_install.Installer, '_picked_versions', {})
    dest_dir = None if dest is None else str(tmp_path / dest)
    installer = easy_install.Installer(
        dest=dest_dir, newest=newest, versions=versions)
    # Environment([]) scans nothing; a default Environment would scan
    # sys.path and leak the test runner's own distributions in.
    env = easy_install.Environment([])
    for dist in env_dists:
        env.add(dist)
    installer._env = env
    return installer


def _record_resolve(monkeypatch, results):
    """Stub the compile seam: record calls, answer from ``results`` in order."""
    calls = []

    def fake_resolve(requirements, versions, links, index_url, prefer_final,
                     uv_stderr=None, offline=False, fallback_index_url=None,
                     overrides=()):
        calls.append({
            'requirements': list(requirements),
            'versions': versions,
            'links': list(links),
            'index_url': index_url,
            'prefer_final': prefer_final,
            'offline': offline,
            'overrides': list(overrides),
        })
        return results[len(calls) - 1]

    monkeypatch.setattr(easy_install, '_uv_resolve_requirements', fake_resolve)
    return calls


def _fail_resolve(monkeypatch):
    def fake_resolve(*args, **kwargs):
        pytest.fail('compile spawned')
    monkeypatch.setattr(easy_install, '_uv_resolve_requirements', fake_resolve)


def _record_install(monkeypatch):
    """Stub install_pinned_dists: record pin lists, answer one dist per pin."""
    calls = []

    def fake_install(pinned, dest):
        calls.append(list(pinned))
        return [_dist(pin.name, pin.version) for pin in pinned]

    monkeypatch.setattr(easy_install, 'install_pinned_dists', fake_install)
    return calls


def _develop(tmp_path, name='devpkg', version='0.1'):
    """A develop dist whose location is a buildable project directory."""
    project = tmp_path / name
    project.mkdir()
    (project / 'setup.py').write_text(f'from setuptools import setup; setup(name={name!r})')
    return _dist(name, version, location=str(project),
                 precedence=pkg_resources.DEVELOP_DIST)


def test_everything_satisfied_spawns_no_compile(monkeypatch, tmp_path):
    installer = _installer(monkeypatch, tmp_path,
                           env_dists=[_dist('demo', '1.0')])
    _fail_resolve(monkeypatch)
    ws = installer.install(['demo'])
    assert [dist.project_name for dist in ws] == ['demo']


def test_exact_pin_shortcut_holds_under_newest(monkeypatch, tmp_path):
    installer = _installer(monkeypatch, tmp_path, newest=True,
                           env_dists=[_dist('demo', '1.0')])
    _fail_resolve(monkeypatch)
    ws = installer.install(['demo==1.0'])
    assert [dist.project_name for dist in ws] == ['demo']


def test_develop_dist_settles_the_requirement_without_a_compile(
        monkeypatch, tmp_path):
    develop = _develop(tmp_path)
    installer = _installer(monkeypatch, tmp_path, newest=True,
                           env_dists=[develop])
    _fail_resolve(monkeypatch)
    ws = installer.install(['devpkg'])
    assert [dist.precedence for dist in ws] == [pkg_resources.DEVELOP_DIST]


def test_newest_upgrades_to_the_pinned_version(monkeypatch, tmp_path):
    installer = _installer(monkeypatch, tmp_path, newest=True,
                           env_dists=[_dist('demo', '1.0')])
    resolve_calls = _record_resolve(
        monkeypatch, [uv_resolve.PinnedSet((_pin('demo', '1.1'),))])
    install_calls = _record_install(monkeypatch)
    ws = installer.install(['demo'])
    assert [str(req) for req in resolve_calls[0]['requirements']] == ['demo']
    assert [(pin.name, pin.version) for pin in install_calls[0]] == [
        ('demo', '1.1')]
    assert [(dist.project_name, dist.version) for dist in ws] == [
        ('demo', '1.1')]


def test_newest_keeps_installed_at_the_pinned_version(
        monkeypatch, tmp_path, caplog):
    installer = _installer(monkeypatch, tmp_path, newest=True,
                           env_dists=[_dist('demo', '1.0')])
    _record_resolve(
        monkeypatch, [uv_resolve.PinnedSet((_pin('demo', '1.0'),))])
    install_calls = _record_install(monkeypatch)
    with caplog.at_level(logging.DEBUG, logger='zc.buildout.easy_install'):
        ws = installer.install(['demo'])
    assert install_calls == [[]]
    assert [(dist.project_name, dist.version) for dist in ws] == [
        ('demo', '1.0')]
    assert 'We have the best distribution that satisfies' in caplog.text


def test_unsatisfied_compile_installs_the_closure_in_lock_order(
        monkeypatch, tmp_path):
    installer = _installer(monkeypatch, tmp_path)
    _record_resolve(monkeypatch, [uv_resolve.PinnedSet((
        _pin('demo', '1.0'), _pin('demoneeded', '1.1')))])
    install_calls = _record_install(monkeypatch)
    ws = installer.install(['demo'])
    assert [(pin.name, pin.version) for pin in install_calls[0]] == [
        ('demo', '1.0'), ('demoneeded', '1.1')]
    assert sorted(dist.project_name for dist in ws) == ['demo', 'demoneeded']


def test_transitive_develop_dependency_rides_an_override(
        monkeypatch, tmp_path):
    develop = _develop(tmp_path)
    installer = _installer(monkeypatch, tmp_path, env_dists=[develop])
    resolve_calls = _record_resolve(monkeypatch, [uv_resolve.PinnedSet((
        _pin('demo', '1.0'),
        _pin('devpkg', '', directory=str(tmp_path / 'devpkg'))))])
    install_calls = _record_install(monkeypatch)
    ws = installer.install(['demo'])
    assert resolve_calls[0]['overrides'] == [
        f'devpkg @ {(tmp_path / "devpkg").as_uri()}']
    assert [pin.name for pin in install_calls[0]] == ['demo']
    assert {dist.project_name for dist in ws} == {'demo', 'devpkg'}


def test_unreferenced_develop_project_stays_out_of_the_working_set(
        monkeypatch, tmp_path):
    develop = _develop(tmp_path)
    installer = _installer(monkeypatch, tmp_path, env_dists=[develop])
    resolve_calls = _record_resolve(
        monkeypatch, [uv_resolve.PinnedSet((_pin('demo', '1.0'),))])
    _record_install(monkeypatch)
    ws = installer.install(['demo'])
    assert resolve_calls[0]['overrides'] == [
        f'devpkg @ {(tmp_path / "devpkg").as_uri()}']
    assert [dist.project_name for dist in ws] == ['demo']


def test_stale_develop_egg_link_yields_no_override(monkeypatch, tmp_path):
    develop = _dist('devpkg', '0.1', location=str(tmp_path / 'vanished'),
                    precedence=pkg_resources.DEVELOP_DIST)
    installer = _installer(monkeypatch, tmp_path, env_dists=[develop])
    resolve_calls = _record_resolve(
        monkeypatch, [uv_resolve.PinnedSet((_pin('demo', '1.0'),))])
    _record_install(monkeypatch)
    installer.install(['demo'])
    assert resolve_calls[0]['overrides'] == []


def test_non_buildable_develop_location_yields_no_override(
        monkeypatch, tmp_path):
    # A develop egg faked onto a plain directory (no pyproject.toml or
    # setup.py, the way the test harness links site-packages installs)
    # must not become an override: uv reads override metadata even for
    # projects the compile never references and would fail the compile
    # over the directory it cannot parse.
    location = tmp_path / 'site-packages'
    location.mkdir()
    develop = _dist('devpkg', '0.1', location=str(location),
                    precedence=pkg_resources.DEVELOP_DIST)
    installer = _installer(monkeypatch, tmp_path, env_dists=[develop])
    resolve_calls = _record_resolve(
        monkeypatch, [uv_resolve.PinnedSet((_pin('demo', '1.0'),))])
    _record_install(monkeypatch)
    installer.install(['demo'])
    assert resolve_calls[0]['overrides'] == []


def test_compile_failure_raises_missing_distribution_naming_the_requirement(
        monkeypatch, tmp_path):
    installer = _installer(monkeypatch, tmp_path)
    _record_resolve(monkeypatch, [None])
    with pytest.raises(MissingDistribution) as excinfo:
        installer.install(['demo'])
    assert "Couldn't find a distribution for 'demo'" in str(excinfo.value)


def test_dest_none_with_unsatisfied_requirement_raises_offline_error(
        monkeypatch, tmp_path):
    installer = _installer(monkeypatch, tmp_path, dest=None)
    _fail_resolve(monkeypatch)
    with pytest.raises(zc.buildout.UserError) as excinfo:
        installer.install(['demo'])
    assert str(excinfo.value) == (
        "We don't have a distribution for demo\n"
        "and can't install one in offline (no-install) mode.\n")


def test_newest_degrades_to_installed_when_the_compile_fails(
        monkeypatch, tmp_path, caplog):
    installer = _installer(monkeypatch, tmp_path, newest=True,
                           env_dists=[_dist('demo', '1.0')])
    _record_resolve(monkeypatch, [None])
    _record_install(monkeypatch)
    with caplog.at_level(logging.DEBUG, logger='zc.buildout.easy_install'):
        ws = installer.install(['demo'])
    assert [(dist.project_name, dist.version) for dist in ws] == [
        ('demo', '1.0')]
    assert 'Using our best' in caplog.text


def test_newest_partial_degradation_retries_with_the_never_installed(
        monkeypatch, tmp_path):
    installer = _installer(monkeypatch, tmp_path, newest=True,
                           env_dists=[_dist('demo', '1.0')])
    resolve_calls = _record_resolve(
        monkeypatch, [None, uv_resolve.PinnedSet((_pin('other', '2.0'),))])
    install_calls = _record_install(monkeypatch)
    ws = installer.install(['demo', 'other'])
    assert [[str(req) for req in call['requirements']]
            for call in resolve_calls] == [['demo', 'other'], ['other']]
    assert [pin.name for pin in install_calls[0]] == ['other']
    assert {(dist.project_name, dist.version) for dist in ws} == {
        ('demo', '1.0'), ('other', '2.0')}


def test_picked_versions_recorded_for_the_unpinned_closure(
        monkeypatch, tmp_path):
    installer = _installer(monkeypatch, tmp_path)
    _record_resolve(monkeypatch, [uv_resolve.PinnedSet((
        _pin('demo', '1.0'), _pin('demoneeded', '1.1')))])
    _record_install(monkeypatch)
    installer.install(['demo'])
    assert installer._picked_versions == {'demo': '1.0', 'demoneeded': '1.1'}


def test_versions_pinned_transitive_is_not_picked(monkeypatch, tmp_path):
    installer = _installer(monkeypatch, tmp_path,
                           versions={'demoneeded': '1.1'})
    _record_resolve(monkeypatch, [uv_resolve.PinnedSet((
        _pin('demo', '1.0'), _pin('demoneeded', '1.1')))])
    _record_install(monkeypatch)
    installer.install(['demo'])
    assert installer._picked_versions == {'demo': '1.0'}


def test_allow_picked_versions_false_gates_unpinned_transitives(
        monkeypatch, tmp_path):
    monkeypatch.setattr(
        easy_install.Installer, '_allow_picked_versions', False)
    installer = _installer(monkeypatch, tmp_path, versions={'demo': '1.0'})
    _record_resolve(monkeypatch, [uv_resolve.PinnedSet((
        _pin('demo', '1.0'), _pin('demoneeded', '1.1')))])
    _record_install(monkeypatch)
    with pytest.raises(zc.buildout.UserError) as excinfo:
        installer.install(['demo'])
    assert 'demoneeded' in str(excinfo.value)


def test_unknown_extra_raises_user_error(monkeypatch, tmp_path):
    installer = _installer(monkeypatch, tmp_path)
    _record_resolve(
        monkeypatch, [uv_resolve.PinnedSet((_pin('demo', '1.0'),))])
    _record_install(monkeypatch)
    with pytest.raises(zc.buildout.UserError) as excinfo:
        installer.install(['demo[bogus]'])
    assert "Couldn't find the required extra" in str(excinfo.value)


def test_unknown_extra_allowed_warns_and_passes(
        monkeypatch, tmp_path, caplog):
    installer = _installer(monkeypatch, tmp_path)
    monkeypatch.setattr(installer, '_allow_unknown_extras', True)
    _record_resolve(
        monkeypatch, [uv_resolve.PinnedSet((_pin('demo', '1.0'),))])
    _record_install(monkeypatch)
    with caplog.at_level(logging.WARNING, logger='zc.buildout.easy_install'):
        ws = installer.install(['demo[bogus]'])
    assert [dist.project_name for dist in ws] == ['demo']
    assert "does not provide the extra 'bogus'" in caplog.text
