"""Pytest port of test_increment.py — no DocTestRunner."""
from zc.buildout.tests.pytests.conftest import assert_output, capture_print, NORMALIZERS_INCREMENT

N = NORMALIZERS_INCREMENT


def test_default_cfg(easy_install_env):
    buildout = easy_install_env['buildout']
    system = easy_install_env['system']
    tmpdir = easy_install_env['tmpdir']
    mkdir = easy_install_env['mkdir']
    join = easy_install_env['join']
    write = easy_install_env['write']
    print_ = easy_install_env['print_']

    home = tmpdir('home')
    mkdir(home, '.buildout')
    default_cfg = join(home, '.buildout', 'default.cfg')
    write(default_cfg, '''
[debug]
dec = 1
      2
inc = 1
''')
    write('buildout.cfg', '''
[buildout]

[debug]
dec -= 2
inc += 2
''')
    env = dict(HOME=home, USERPROFILE=home)
    assert_output(
        system(buildout + ' annotate debug', env=env),
        '''
Annotated sections
==================

[debug]
dec= 1
    /home/.buildout/default.cfg
-=  buildout.cfg
inc= 1
2
    /home/.buildout/default.cfg
+=  buildout.cfg''',
        N,
    )


def test_default_cfg_extensions(easy_install_env):
    buildout = easy_install_env['buildout']
    system = easy_install_env['system']
    tmpdir = easy_install_env['tmpdir']
    mkdir = easy_install_env['mkdir']
    join = easy_install_env['join']
    write = easy_install_env['write']
    ls = easy_install_env['ls']

    mkdir('demo')
    write('demo', 'demo.py', '''
import sys
def ext(buildout):
    sys.stdout.write('demo %s %s\\n' % ('ext', sorted(buildout)))
def unload(buildout):
    sys.stdout.write('demo %s %s\\n' % ('unload', sorted(buildout)))
''')
    write('demo', 'setup.py', '''
from setuptools import setup

setup(
    name = "demo",
    entry_points = {
       'zc.buildout.extension': ['ext = demo:ext'],
       'zc.buildout.unloadextension': ['ext = demo:unload'],
       },
    )
''')
    mkdir('demo2')
    write('demo2', 'demo2.py', '''
import sys
def ext(buildout):
    sys.stdout.write('demo2 %s %s\\n' % ('ext', sorted(buildout)))
def unload(buildout):
    sys.stdout.write('demo2 %s %s\\n' % ('unload', sorted(buildout)))
''')
    write('demo2', 'setup.py', '''
from setuptools import setup

setup(
    name = "demo2",
    entry_points = {
       'zc.buildout.extension': ['ext = demo2:ext'],
       'zc.buildout.unloadextension': ['ext = demo2:unload'],
       },
    )
''')
    write('buildout.cfg', '''
[buildout]
develop = demo demo2
parts =
''')

    assert_output(
        system(buildout),
        """
Develop: '/sample-buildout/demo'
Develop: '/sample-buildout/demo2'
""",
        N,
    )
    assert_output(
        capture_print(ls, 'develop-eggs'),
        """
-  demo.egg-link
-  demo2.egg-link
-  zc.recipe.egg.egg-link
""",
        N,
    )

    home = tmpdir('home')
    mkdir(home, '.buildout')
    default_cfg = join(home, '.buildout', 'default.cfg')
    write(default_cfg, '''
[buildout]
extensions = demo
''')
    write('buildout.cfg', '''
[buildout]
develop = demo demo2
extensions += demo2
parts =
''')
    env = dict(HOME=home, USERPROFILE=home)
    assert_output(
        system(buildout + ' annotate buildout', env=env),
        '''
Annotated sections
==================

[buildout]
...
extensions= demo
demo2
    /home/.buildout/default.cfg
+=  buildout.cfg
...
versions= versions
    DEFAULT_VALUE''',
        N,
    )


def test_with_extends_increment_in_base(easy_install_env):
    buildout = easy_install_env['buildout']
    system = easy_install_env['system']
    tmpdir = easy_install_env['tmpdir']
    mkdir = easy_install_env['mkdir']
    join = easy_install_env['join']
    write = easy_install_env['write']

    home = tmpdir('home')
    mkdir(home, '.buildout')
    default_cfg = join(home, '.buildout', 'default.cfg')
    write(default_cfg, '''
[buildout]
extensions = demo
''')
    write('base.cfg', '''
[buildout]
extensions += demo2
''')
    write('buildout.cfg', '''
[buildout]
extends = base.cfg
parts =
''')
    env = dict(HOME=home, USERPROFILE=home)
    assert_output(
        system(buildout + ' annotate buildout', env=env),
        '''
Annotated sections
==================

[buildout]
...
extensions= demo
demo2
    /home/.buildout/default.cfg
+=  base.cfg
...
versions= versions
    DEFAULT_VALUE''',
        N,
    )


def test_with_extends_increment_in_base2(easy_install_env):
    buildout = easy_install_env['buildout']
    system = easy_install_env['system']
    tmpdir = easy_install_env['tmpdir']
    mkdir = easy_install_env['mkdir']
    join = easy_install_env['join']
    write = easy_install_env['write']

    home = tmpdir('home')
    mkdir(home, '.buildout')
    default_cfg = join(home, '.buildout', 'default.cfg')
    write(default_cfg, '''
[buildout]
extensions = demo
''')
    write('base.cfg', '''
[buildout]
''')
    write('base2.cfg', '''
[buildout]
extensions += demo2
''')
    write('buildout.cfg', '''
[buildout]
extends = base.cfg
          base2.cfg
parts =
''')
    env = dict(HOME=home, USERPROFILE=home)
    assert_output(
        system(buildout + ' annotate buildout', env=env),
        '''
Annotated sections
==================

[buildout]
...
extensions= demo
demo2
    /home/.buildout/default.cfg
+=  base2.cfg
...
versions= versions
    DEFAULT_VALUE''',
        N,
    )


def test_with_extends_increment_in_base2_and_base3(easy_install_env):
    buildout = easy_install_env['buildout']
    system = easy_install_env['system']
    tmpdir = easy_install_env['tmpdir']
    mkdir = easy_install_env['mkdir']
    join = easy_install_env['join']
    write = easy_install_env['write']

    home = tmpdir('home')
    mkdir(home, '.buildout')
    default_cfg = join(home, '.buildout', 'default.cfg')
    write(default_cfg, '''
[buildout]
extensions = demo
''')
    write('base.cfg', '''
[buildout]
''')
    write('base2.cfg', '''
[buildout]
extensions += demo2
''')
    write('base3.cfg', '''
[buildout]
extensions += demo3
''')
    write('buildout.cfg', '''
[buildout]
extends = base.cfg
          base2.cfg
          base3.cfg
parts =
''')
    env = dict(HOME=home, USERPROFILE=home)
    assert_output(
        system(buildout + ' annotate buildout', env=env),
        '''
Annotated sections
==================

[buildout]
...
extensions= demo
demo2
demo3
    /home/.buildout/default.cfg
+=  base2.cfg
+=  base3.cfg
...
versions= versions
    DEFAULT_VALUE''',
        N,
    )


def test_with_extends_increment_in_buildout(easy_install_env):
    buildout = easy_install_env['buildout']
    system = easy_install_env['system']
    tmpdir = easy_install_env['tmpdir']
    mkdir = easy_install_env['mkdir']
    join = easy_install_env['join']
    write = easy_install_env['write']

    home = tmpdir('home')
    mkdir(home, '.buildout')
    default_cfg = join(home, '.buildout', 'default.cfg')
    write(default_cfg, '''
[buildout]
extensions = demo
''')
    write('base.cfg', '''
[buildout]
''')
    write('buildout.cfg', '''
[buildout]
extends = base.cfg
extensions += demo2
parts =
''')
    env = dict(HOME=home, USERPROFILE=home)
    assert_output(
        system(buildout + ' annotate buildout', env=env),
        '''
Annotated sections
==================

[buildout]
...
extensions= demo
demo2
    /home/.buildout/default.cfg
+=  buildout.cfg
...
versions= versions
    DEFAULT_VALUE''',
        N,
    )


def test_with_extends_increment_in_buildout_with_base_and_root(easy_install_env):
    buildout = easy_install_env['buildout']
    system = easy_install_env['system']
    tmpdir = easy_install_env['tmpdir']
    mkdir = easy_install_env['mkdir']
    join = easy_install_env['join']
    write = easy_install_env['write']

    home = tmpdir('home')
    mkdir(home, '.buildout')
    default_cfg = join(home, '.buildout', 'default.cfg')
    write(default_cfg, '''
[buildout]
extensions = demo
''')
    write('root.cfg', '''
[buildout]
''')
    write('base.cfg', '''
[buildout]
extends = root.cfg
''')
    write('buildout.cfg', '''
[buildout]
extends = base.cfg
extensions += demo2
parts =
''')
    env = dict(HOME=home, USERPROFILE=home)
    assert_output(
        system(buildout + ' annotate buildout', env=env),
        '''
Annotated sections
==================

[buildout]
...
extensions= demo
demo2
    /home/.buildout/default.cfg
+=  buildout.cfg
...
versions= versions
    DEFAULT_VALUE''',
        N,
    )


def test_no_default_with_extends_increment_in_base2_and_base3(easy_install_env):
    buildout = easy_install_env['buildout']
    system = easy_install_env['system']
    write = easy_install_env['write']

    write('base.cfg', '''
[buildout]
''')
    write('base2.cfg', '''
[buildout]
extensions += demo2
''')
    write('base3.cfg', '''
[buildout]
extensions += demo3
''')
    write('buildout.cfg', '''
[buildout]
extends = base.cfg
          base2.cfg
          base3.cfg
parts =
''')
    assert_output(
        system(buildout + ' annotate buildout'),
        '''
Annotated sections
==================

[buildout]
...
extensions=
demo2
demo3
    IMPLICIT_VALUE
+=  base2.cfg
+=  base3.cfg
...
versions= versions
    DEFAULT_VALUE''',
        N,
    )


def test_increment_buildout_with_multiple_extended_without_base_equals(easy_install_env):
    buildout = easy_install_env['buildout']
    system = easy_install_env['system']
    write = easy_install_env['write']

    write('buildout.cfg', '''
[buildout]
extends = base1.cfg base2.cfg
parts += foo
[foo]
recipe = zc.buildout:debug
[base1]
recipe = zc.buildout:debug
[base2]
recipe = zc.buildout:debug
''')
    write('base1.cfg', '''
[buildout]
extends = base3.cfg
parts += base1
''')
    write('base2.cfg', '''
[buildout]
extends = base3.cfg
parts += base2
''')
    write('base3.cfg', '''
[buildout]
''')

    assert_output(
        system(buildout),
        "Installing base1.\n  recipe='zc.buildout:debug'\n"
        "Installing base2.\n  recipe='zc.buildout:debug'\n"
        "Installing foo.\n  recipe='zc.buildout:debug'",
        N,
    )
