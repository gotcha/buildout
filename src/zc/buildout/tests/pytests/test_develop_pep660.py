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

import pytest

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

    script = os.path.join(sample_buildout, 'bin', 'demo-pep660')
    assert os.path.exists(script), os.listdir(os.path.join(sample_buildout, 'bin'))
    output = system(os.path.join('bin', 'demo-pep660'))
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
