"""Integration tests: real ``bin/buildout`` runs through the uv pipeline.

Each test drives a spawned buildout in a sample sandbox and asserts both
the subprocess that ran (the debug log prints the installer argv) and the
installed result on disk. The ``--python`` token only appears in uv
invocations, which is what discriminates uv from ``python -m pip``.
"""
import os

from zc.buildout.tests.pytests.conftest import NORMALIZERS_EASY_INSTALL, assert_output

N = NORMALIZERS_EASY_INSTALL

UV_DEBUG_LINE = '...uv" "pip" "install"..."--python"...'

CONFIG = '''
[buildout]
parts = eggs
find-links = {link_server}
{installer_line}
[eggs]
recipe = zc.recipe.egg
eggs = demo ==0.2
'''


def _write_config(write, link_server, installer_line=''):
    write('buildout.cfg',
          CONFIG.format_map({
              'link_server': link_server,
              'installer_line': installer_line,
          }))


def _assert_demo_egg_installed(sample_buildout):
    entries = os.listdir(os.path.join(sample_buildout, 'eggs', 'v5'))
    assert any(entry.startswith('demo-0.2-') for entry in entries), entries


def test_installer_option_from_config(easy_install_env):
    buildout = easy_install_env['buildout']
    link_server = easy_install_env['link_server']
    sample_buildout = easy_install_env['sample_buildout']
    system = easy_install_env['system']
    write = easy_install_env['write']

    _write_config(write, link_server, 'installer = uv')
    assert_output(system(buildout + ' -vvv'), """
    ...
    Installing eggs.
    ...
    Running pip install:
    """ + UV_DEBUG_LINE + """
    ...
    """, N)
    _assert_demo_egg_installed(sample_buildout)


def test_installer_option_from_command_line(easy_install_env):
    buildout = easy_install_env['buildout']
    link_server = easy_install_env['link_server']
    sample_buildout = easy_install_env['sample_buildout']
    system = easy_install_env['system']
    write = easy_install_env['write']

    _write_config(write, link_server)
    assert_output(system(buildout + ' -vvv buildout:installer=uv'), """
    ...
    Installing eggs.
    ...
    Running pip install:
    """ + UV_DEBUG_LINE + """
    ...
    """, N)
    _assert_demo_egg_installed(sample_buildout)


def test_installer_default_from_testing_env_var(easy_install_env, monkeypatch):
    buildout = easy_install_env['buildout']
    link_server = easy_install_env['link_server']
    sample_buildout = easy_install_env['sample_buildout']
    system = easy_install_env['system']
    write = easy_install_env['write']

    monkeypatch.setenv('buildout_testing_installer', 'uv')
    _write_config(write, link_server)
    assert_output(system(buildout + ' -vvv'), """
    ...
    Installing eggs.
    ...
    Running pip install:
    """ + UV_DEBUG_LINE + """
    ...
    """, N)
    _assert_demo_egg_installed(sample_buildout)


def test_uv_build_subprocess_inherits_environment(easy_install_env,
                                                  monkeypatch, tmp_path):
    """uv does not relay build output, so prove env propagation by effect.

    The legacy corpus watches pip relay a print from extdemo's setup.py.
    uv swallows that output, so this test has the build write the
    observed variable to a marker file instead: the evidence is on disk,
    not in a log line.
    """
    buildout = easy_install_env['buildout']
    sample_buildout = easy_install_env['sample_buildout']
    sdist = easy_install_env['sdist']
    system = easy_install_env['system']
    tmpdir = easy_install_env['tmpdir']
    write = easy_install_env['write']

    dists = tmpdir('envprobe-dists')
    src = tmpdir('envprobe-src')
    write(src, 'envprobe.py', 'VALUE = 1\n')
    write(src, 'setup.py', '''
import os
from distutils.core import setup

marker = os.environ.get('ENV_PROBE_MARKER')
if marker:
    with open(marker, 'w') as f:
        f.write(os.environ.get('test_environment_variable', 'ABSENT'))

setup(name='envprobe', version='0.1', py_modules=['envprobe'])
''')
    sdist(src, dists)

    marker = tmp_path / 'marker.txt'
    monkeypatch.setenv('test_environment_variable', 'uv-propagates')
    monkeypatch.setenv('ENV_PROBE_MARKER', str(marker))
    write('buildout.cfg', '''
    [buildout]
    parts = eggs
    find-links = {dists}
    installer = uv

    [eggs]
    recipe = zc.recipe.egg
    eggs = envprobe
    '''.format_map({'dists': dists}))
    system(buildout)
    assert marker.read_text() == 'uv-propagates'
    entries = os.listdir(os.path.join(sample_buildout, 'eggs', 'v5'))
    assert any(entry.startswith('envprobe-0.1-') for entry in entries), entries


def test_uv_debug_line_matches_uv_exe_argv0_on_windows():
    # The spawned buildout prints the resolved uv path as argv[0]; pip
    # lays the console script down as uv.exe on Windows.
    actual = (
        'Running pip install:\n'
        '"D:/a/buildout/venvs/python/Scripts/uv.exe" "pip" "install"'
        ' "--no-deps" "--python" "python3.exe" "-v" "pkg"\n')
    assert_output(actual, 'Running pip install:\n' + UV_DEBUG_LINE, N)


def test_installer_rejects_invalid_value(easy_install_env):
    buildout = easy_install_env['buildout']
    link_server = easy_install_env['link_server']
    system = easy_install_env['system']
    write = easy_install_env['write']

    _write_config(write, link_server, 'installer = bogus')
    assert_output(system(buildout), """
    ...
    Error: Invalid value for 'installer' option: 'bogus'. Valid values are 'pip' and 'uv'.
    ...
    """, N)
