"""Unit tests for install_pinned_dists: batched uv installs of a pin set."""
import logging
import os
import sys

import pkg_resources
import pytest

import zc.buildout
from zc.buildout import easy_install
from zc.buildout.easy_install import _uv_install_args
from zc.buildout.install_backend import install_pinned_dists
from zc.buildout.uv_resolve import PinnedDist


def _pin(name, version):
    return PinnedDist(
        name=name,
        version=version,
        url=f'https://example.com/packages/{name}-{version}.tar.gz',
        sha256=None,
        sdist_url=None,
        sdist_sha256=None,
    )


def _write_dist_tree(dest, project_name, version, module):
    """Materialize a fake install: a top-level module and its .dist-info.

    METADATA, top_level.txt and RECORD are the minimum
    make_egg_after_pip_install reads; RECORD in particular must exist,
    it is read unconditionally after the dist-info moves into the egg.
    """
    distinfo = os.path.join(
        dest, f"{project_name.replace('-', '_')}-{version}.dist-info")
    os.makedirs(distinfo)
    with open(os.path.join(distinfo, 'METADATA'), 'w') as f:
        f.write('Metadata-Version: 2.1\n'
                f'Name: {project_name}\n'
                f'Version: {version}\n')
    with open(os.path.join(distinfo, 'top_level.txt'), 'w') as f:
        f.write(module + '\n')
    with open(os.path.join(distinfo, 'RECORD'), 'w') as f:
        f.write(f'{module}.py,,\n')
    with open(os.path.join(dest, module + '.py'), 'w') as f:
        f.write('# written by the fake uv subprocess\n')


def _record_uv_install(monkeypatch, materialize=()):
    """Stub the uv binary and ``_run_pip``; record (args, env) per call.

    The fake subprocess materializes the fake install trees named by
    ``materialize`` ((project_name, version, module) triples) into the
    tmp dest it is handed.
    """
    calls = []

    def fake_run_pip(args, env, dest, level):
        calls.append((args, env))
        for project_name, version, module in materialize:
            _write_dist_tree(dest, project_name, version, module)
        return ''

    monkeypatch.setattr(easy_install, '_uv_executable', lambda: '/uv')
    monkeypatch.setattr(easy_install, '_run_pip', fake_run_pip)
    return calls


def test_empty_pin_set_spawns_no_subprocess(monkeypatch, tmp_path):
    calls = _record_uv_install(monkeypatch)
    dest = str(tmp_path / 'eggs')
    assert install_pinned_dists([], dest) == []
    assert calls == []
    # Not even the destination directory is created for an empty set.
    assert not os.path.exists(dest)


def test_one_subprocess_with_specs_in_pin_order(monkeypatch, tmp_path):
    pins = [_pin('demo', '1.0'), _pin('other-lib', '2.0')]
    calls = _record_uv_install(monkeypatch, materialize=[
        ('demo', '1.0', 'demo'),
        ('other-lib', '2.0', 'other_lib'),
    ])
    monkeypatch.setattr(easy_install.Installer, '_index_url', None)
    dest = str(tmp_path / 'eggs')
    install_pinned_dists(pins, dest)
    assert len(calls) == 1
    args, env = calls[0]
    assert env is not os.environ
    assert args[-2:] == [pins[0].url, pins[1].url]
    assert '--no-deps' in args
    assert args[args.index('--python') + 1] == sys.executable
    # The install target is a temporary sibling inside dest.
    tmp_dest = args[args.index('-t') + 1]
    assert os.path.dirname(tmp_dest) == dest
    # The batch argv is the unchanged single-spec _uv_install_args
    # output with the remaining urls appended.
    level = logging.getLogger('zc.buildout.easy_install').getEffectiveLevel()
    expected = _uv_install_args(
        '/uv', pins[0].url, tmp_dest, False, easy_install.index_url(), level)
    assert args == expected + [pins[1].url]


def test_eggs_land_in_dest_in_pin_order(monkeypatch, tmp_path):
    pins = [_pin('demo', '1.0'), _pin('other-lib', '2.0')]
    _record_uv_install(monkeypatch, materialize=[
        ('demo', '1.0', 'demo'),
        ('other-lib', '2.0', 'other_lib'),
    ])
    dest = str(tmp_path / 'eggs')
    newdists = install_pinned_dists(pins, dest)
    assert [d.project_name for d in newdists] == ['demo', 'other-lib']
    assert [d.version for d in newdists] == ['1.0', '2.0']
    assert [d.precedence for d in newdists] == [
        pkg_resources.EGG_DIST, pkg_resources.EGG_DIST]
    eggs = sorted(os.listdir(dest))
    assert len(eggs) == 2
    assert any(e.startswith('demo-1.0') and e.endswith('.egg')
               for e in eggs)
    assert any(e.startswith('other_lib-2.0') and e.endswith('.egg')
               for e in eggs)
    # Every entry in dest is a returned egg: the temporary install
    # directory was cleaned up.
    locations = []
    for dist in newdists:
        assert dist.location is not None
        locations.append(os.path.basename(dist.location))
    assert sorted(locations) == eggs


def test_missing_dist_info_raises_user_error_naming_pin(
        monkeypatch, tmp_path):
    pins = [_pin('demo', '1.0'), _pin('other-lib', '2.0')]
    _record_uv_install(monkeypatch, materialize=[('demo', '1.0', 'demo')])
    dest = str(tmp_path / 'eggs')
    with pytest.raises(zc.buildout.UserError) as excinfo:
        install_pinned_dists(pins, dest)
    assert 'other-lib' in str(excinfo.value)
    assert 'other_lib-2.0.dist-info' in str(excinfo.value)
    # demo was fully processed before the failure; the tmp dir inside
    # dest was still cleaned up.
    assert [e for e in os.listdir(dest) if not e.endswith('.egg')] == []
