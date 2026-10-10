"""Develop (editable install) of a pyproject-only package, PEP 660 shape.

A ``develop =`` source whose build backend never writes metadata into
the checkout (hatchling) yields only a ``.dist-info`` and a plain-path
``.pth`` from ``pip/uv install -e``.  The develop dist must still be
visible to the working set, generated scripts must import the package,
and the buildout process itself must import it when the package
provides a recipe entry point (group ``zc.buildout``).

The sample package needs hatchling at build time; the suites are
index-hermetic, so hatchling and its dependencies are seeded into
``downloads/test-seed`` by prepare.sh (the same seed the test-spawned
installers' build isolation resolves from).
"""
import os
import sys

import pytest

from zc.buildout import develop, utils


def test_get_pth_paths(tmp_path):
    # An absolute .pth entry passes through unchanged, a relative one
    # resolves against the .pth directory — mirroring site's reading.
    # A path needs the drive prefix to be absolute on Windows; spell the
    # entry natively so the expectation holds on both platforms.
    absolute = os.path.splitdrive(str(tmp_path))[0] + '/opt/p5/src'
    (tmp_path / 'plain.pth').write_text(
        absolute + '\n# a comment\n\nimport some_finder\nrelative-dir\n')
    assert utils.get_pth_paths(str(tmp_path)) == [
        os.path.normpath(absolute), str(tmp_path / 'relative-dir')]


def test_get_pth_paths_without_directory(tmp_path):
    assert utils.get_pth_paths(str(tmp_path / 'missing')) == []
    (tmp_path / 'lone.pth').write_text('/opt/p5/src\n')
    assert utils.get_pth_paths(str(tmp_path / 'lone.pth')) == []


def test_copy_metadata_moves_pep660_artifacts(tmp_path):
    src = tmp_path / 'tmp3'
    dest = tmp_path / 'develop-eggs'
    src.mkdir()
    dest.mkdir()
    (src / 'demo-1.dist-info').mkdir()
    (src / 'plain.pth').write_text('/x\n')
    (src / '__editable___demo_finder.py').write_text('')
    (src / '.lock').write_text('')
    (src / 'stray.py').write_text('')
    develop._copy_metadata(str(src), str(dest), [])
    assert sorted(os.listdir(dest)) == [
        '__editable___demo_finder.py', 'demo-1.dist-info', 'plain.pth']
    assert sorted(os.listdir(src)) == ['.lock', 'stray.py']


def test_dist_metadata_present(tmp_path):
    assert not develop._dist_metadata_present(str(tmp_path))
    (tmp_path / 'demo-1.egg-info').mkdir()
    assert develop._dist_metadata_present(str(tmp_path))


def test_pep660_pth_paths_skips_locations_and_duplicates(tmp_path):
    from zc.buildout.scripts import _pep660_pth_paths

    (tmp_path / 'a.pth').write_text(f'{tmp_path / "src"}\n')
    locations = [str(tmp_path), str(tmp_path / 'src')]
    assert _pep660_pth_paths(locations) == []
    (tmp_path / 'b.pth').write_text(f'{tmp_path / "lib"}\n{tmp_path / "lib"}\n')
    found = _pep660_pth_paths([str(tmp_path)])
    assert sorted(found) == sorted([str(tmp_path / 'src'), str(tmp_path / 'lib')])
    assert len(found) == len(set(found))


def test_expected_develop_eggs_entry(tmp_path):
    from zc.buildout.configsetup import _expected_develop_eggs_entry

    (tmp_path / 'demo.egg-link').write_text('/x\n.')
    (tmp_path / 'plain.pth').write_text('/x\n')
    (tmp_path / '__editable___demo_finder.py').write_text('')
    (tmp_path / 'demo-1.dist-info').mkdir()
    (tmp_path / 'demo-1.egg-info').mkdir()
    (tmp_path / 'stray.py').write_text('')
    (tmp_path / 'odd-dir').mkdir()

    def ask(name):
        return _expected_develop_eggs_entry(str(tmp_path / name), ['kept.zip'])

    assert ask('kept.zip')
    assert ask('demo.egg-link')
    assert ask('plain.pth')
    assert ask('__editable___demo_finder.py')
    assert ask('demo-1.dist-info')
    assert ask('demo-1.egg-info')
    assert not ask('stray.py')
    assert not ask('odd-dir')


PACKAGE_PYPROJECT = '''
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo-pep660"
version = "0.1.0"

[project.scripts]
demo-pep660 = "demo_pep660:main"

[project.entry-points."zc.buildout"]
demorecipe = "demo_pep660:Recipe"
'''

PACKAGE_INIT = '''
def main():
    print("Hello from demo_pep660.")


class Recipe:
    def __init__(self, buildout, name, options):
        options['marker'] = 'recipe-imported-in-process'

    def install(self):
        return []

    update = install
'''


def _write_package(env):
    mkdir = env['mkdir']
    write = env['write']
    mkdir('demo-pep660')
    mkdir('demo-pep660', 'src')
    mkdir('demo-pep660', 'src', 'demo_pep660')
    write('demo-pep660', 'src', 'demo_pep660', '__init__.py', PACKAGE_INIT)
    write('demo-pep660', 'pyproject.toml', PACKAGE_PYPROJECT)


def _develop_eggs_entries(sample_buildout):
    return os.listdir(os.path.join(sample_buildout, 'develop-eggs'))


@pytest.mark.parametrize('installer_line', ['', 'installer = uv'],
                         ids=['pip', 'uv'])
def test_develop_pep660_package(easy_install_env, installer_line):
    buildout = easy_install_env['buildout']
    sample_buildout = easy_install_env['sample_buildout']
    system = easy_install_env['system']
    write = easy_install_env['write']

    _write_package(easy_install_env)
    write('buildout.cfg',
          '''
          [buildout]
          develop = demo-pep660
          parts = eggs
          ''' + installer_line + '''
          [eggs]
          recipe = zc.recipe.egg
          eggs = demo-pep660
          ''')

    output = system(buildout)
    assert "Couldn't find a distribution for 'demo-pep660'" not in output
    assert 'Error:' not in output

    entries = _develop_eggs_entries(sample_buildout)
    assert 'demo-pep660.egg-link' in entries, entries
    assert any(entry.endswith('.dist-info') for entry in entries), entries
    assert any(entry.endswith('.pth') for entry in entries), entries

    # On Windows a console script lands as ``demo-pep660.exe`` paired
    # with ``demo-pep660-script.py`` (see scripts._create_script); the
    # .exe is the directly runnable entry point there.
    suffix = '.exe' if sys.platform == 'win32' else ''
    script = os.path.join(sample_buildout, 'bin', 'demo-pep660' + suffix)
    assert os.path.exists(script), os.listdir(os.path.join(sample_buildout, 'bin'))
    output = system(os.path.join('bin', 'demo-pep660' + suffix))
    assert 'Hello from demo_pep660.' in output


@pytest.mark.parametrize('installer_line', ['', 'installer = uv'],
                         ids=['pip', 'uv'])
def test_pep660_develop_package_provides_recipe(easy_install_env,
                                                installer_line):
    buildout = easy_install_env['buildout']
    sample_buildout = easy_install_env['sample_buildout']
    system = easy_install_env['system']
    write = easy_install_env['write']

    _write_package(easy_install_env)
    write('buildout.cfg',
          '''
          [buildout]
          develop = demo-pep660
          parts = custom
          ''' + installer_line + '''
          [custom]
          recipe = demo-pep660:demorecipe
          ''')

    output = system(buildout)
    assert 'Error' not in output
    assert 'ModuleNotFoundError' not in output

    with open(os.path.join(sample_buildout, '.installed.cfg')) as f:
        assert 'recipe-imported-in-process' in f.read()
