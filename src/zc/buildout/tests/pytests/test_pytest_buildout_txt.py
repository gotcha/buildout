"""Pytest port of buildout.txt, configuration.txt, extending.txt, options.txt, init.txt, extensions.txt — no DocTestRunner."""
import os
import re
import shutil
import sys
import textwrap

import pkg_resources
import zc.buildout.easy_install
import zc.buildout.buildout
import zc.buildout.testing

from zc.buildout.tests.pytests.conftest import (
    assert_output,
    capture_print,
    NORMALIZERS_BUILDOUT_TXT,
)

N = NORMALIZERS_BUILDOUT_TXT


def test_buildout(buildout_txt_env):
    buildout = buildout_txt_env['buildout']
    cat = buildout_txt_env['cat']
    clean_up_pyc = buildout_txt_env['clean_up_pyc']
    ls = buildout_txt_env['ls']
    os = buildout_txt_env['os']
    print_ = buildout_txt_env['print_']
    remove = buildout_txt_env['remove']
    rmdir = buildout_txt_env['rmdir']
    sample_buildout = buildout_txt_env['sample_buildout']
    system = buildout_txt_env['system']
    write = buildout_txt_env['write']

    assert_output(capture_print(ls, sample_buildout), """
d  bin
-  buildout.cfg
d  develop-eggs
d  eggs
d  parts
d  recipes
""", N)
    assert_output(capture_print(ls, sample_buildout, 'bin'), '-  buildout', N)
    assert_output(capture_print(ls, sample_buildout, 'eggs'), 'd  v5', N)
    assert_output(capture_print(ls, sample_buildout, 'eggs', 'v5'), """
-  packaging.egg-link
-  pip.egg-link
-  setuptools.egg-link
-  wheel.egg-link
-  zc.buildout.egg-link
""", N)
    ls(sample_buildout, 'develop-eggs')
    ls(sample_buildout, 'parts')
    assert_output(capture_print(cat, sample_buildout, 'buildout.cfg'), """
[buildout]
parts =
""", N)
    assert_output(capture_print(ls, sample_buildout, 'recipes'), """
-  README.txt
-  setup.py
d  src
""", N)
    assert_output(capture_print(ls, sample_buildout, 'recipes', 'src'), """
-  debug.py
-  environ.py
-  mkdir.py
""", N)
    write(sample_buildout, 'recipes', 'src', 'mkdir.py',
    """
    import logging, os, zc.buildout
    
    class Mkdir:
    
        def __init__(self, buildout, name, options):
            self.name, self.options = name, options
            options['path'] = os.path.join(
                                  buildout['buildout']['directory'],
                                  options['path'],
                                  )
            if not os.path.isdir(os.path.dirname(options['path'])):
                logging.getLogger(self.name).error(
                    'Cannot create %s. %s is not a directory.',
                    options['path'], os.path.dirname(options['path']))
                raise zc.buildout.UserError('Invalid Path')
    
    
        def install(self):
            path = self.options['path']
            logging.getLogger(self.name).info(
                'Creating directory %s', os.path.basename(path))
            os.mkdir(path)
            return path
    
        def update(self):
            pass
    """)
    write(sample_buildout, 'recipes', 'setup.py',
    """
    from setuptools import setup
    
    setup(
        name = "recipes",
        entry_points = {'zc.buildout': ['mkdir = mkdir:Mkdir']},
        )
    """)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = data-dir
    
    [data-dir]
    recipe = recipes:mkdir
    path = mystuff
    """)
    os.chdir(sample_buildout)
    buildout = os.path.join(sample_buildout, 'bin', 'buildout')
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Installing data-dir.
data-dir: Creating directory mystuff
""", N)
    assert_output(capture_print(ls, sample_buildout), """
-  .installed.cfg
d  bin
-  buildout.cfg
d  develop-eggs
d  eggs
d  mystuff
d  parts
d  recipes
""", N)
    assert_output(capture_print(cat, sample_buildout, '.installed.cfg'), """
[buildout]
installed_develop_eggs = /sample-buildout/develop-eggs/recipes.egg-link
parts = data-dir

[data-dir]
__buildout_installed__ = /sample-buildout/mystuff
__buildout_signature__ = recipes-c7vHV6ekIDUPy/7fjAaYjg==
path = /sample-buildout/mystuff
recipe = recipes:mkdir
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = data-dir
    
    [data-dir]
    recipe = recipes:mkdir
    path = mydata
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Uninstalling data-dir.
Installing data-dir.
data-dir: Creating directory mydata
""", N)
    assert_output(capture_print(ls, sample_buildout), """
-  .installed.cfg
d  bin
-  buildout.cfg
d  develop-eggs
d  eggs
d  mydata
d  parts
d  recipes
""", N)
    rmdir(sample_buildout, 'mydata')
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Uninstalling data-dir.
Installing data-dir.
data-dir: Creating directory mydata
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = data-dir
    
    [data-dir]
    recipe = recipes:mkdir
    path = /xxx/mydata
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
data-dir: Cannot create .../xxx/mydata. .../xxx is not a directory.
While:
  Installing.
  Getting section data-dir.
  Initializing section data-dir.
Error: Invalid Path
""", N)
    write(sample_buildout, 'recipes', 'src', 'mkdir.py',
    """
    import logging, os, zc.buildout
    
    class Mkdir:
    
        def __init__(self, buildout, name, options):
            self.name, self.options = name, options
    
            # Normalize paths and check that their parent
            # directories exist:
            paths = []
            for path in options['path'].split():
                path = os.path.join(buildout['buildout']['directory'], path)
                if not os.path.isdir(os.path.dirname(path)):
                    logging.getLogger(self.name).error(
                        'Cannot create %s. %s is not a directory.',
                        options['path'], os.path.dirname(options['path']))
                    raise zc.buildout.UserError('Invalid Path')
                paths.append(path)
            options['path'] = ' '.join(paths)
    
        def install(self):
            paths = self.options['path'].split()
            for path in paths:
                logging.getLogger(self.name).info(
                    'Creating directory %s', os.path.basename(path))
                os.mkdir(path)
            return paths
    
        def update(self):
            pass
    """)
    clean_up_pyc(sample_buildout, 'recipes', 'src', 'mkdir.py')
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = data-dir
    
    [data-dir]
    recipe = recipes:mkdir
    path = foo bin
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Uninstalling data-dir.
Installing data-dir.
data-dir: Creating directory foo
data-dir: Creating directory bin
While:
  Installing data-dir.

An internal error occurred due to a bug in either zc.buildout or in a
recipe being used:
Traceback (most recent call last):
... exists...
""", N)
    _val = (os.path.exists('foo'))
    assert repr(_val) == 'True' or str(_val) == 'True'
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = data-dir
    
    [data-dir]
    recipe = recipes:mkdir
    path = foo bins
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Installing data-dir.
data-dir: Creating directory foo
While:
  Installing data-dir.

An internal error occurred due to a bug in either zc.buildout or in a
recipe being used:
Traceback (most recent call last):
... exists...
""", N)
    remove('foo')
    write(sample_buildout, 'recipes', 'src', 'mkdir.py',
    """
    import logging, os, zc.buildout, sys
    
    class Mkdir:
    
        def __init__(self, buildout, name, options):
            self.name, self.options = name, options
    
            # Normalize paths and check that their parent
            # directories exist:
            paths = []
            for path in options['path'].split():
                path = os.path.join(buildout['buildout']['directory'], path)
                if not os.path.isdir(os.path.dirname(path)):
                    logging.getLogger(self.name).error(
                        'Cannot create %s. %s is not a directory.',
                        options['path'], os.path.dirname(options['path']))
                    raise zc.buildout.UserError('Invalid Path')
                paths.append(path)
            options['path'] = ' '.join(paths)
    
        def install(self):
            paths = self.options['path'].split()
            created = []
            try:
                for path in paths:
                    logging.getLogger(self.name).info(
                        'Creating directory %s', os.path.basename(path))
                    os.mkdir(path)
                    created.append(path)
            except Exception:
                for d in created:
                    os.rmdir(d)
                    assert not os.path.exists(d)
                    logging.getLogger(self.name).info(
                        'Removed %s due to error',
                         os.path.basename(d))
                sys.stderr.flush()
                sys.stdout.flush()
                raise
    
            return paths
    
        def update(self):
            pass
    """)
    clean_up_pyc(sample_buildout, 'recipes', 'src', 'mkdir.py')
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = data-dir
    
    [data-dir]
    recipe = recipes:mkdir
    path = foo bin
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Installing data-dir.
data-dir: Creating directory foo
data-dir: Creating directory bin
data-dir: Removed foo due to error
While:
  Installing data-dir.

An internal error occurred due to a bug in either zc.buildout or in a
recipe being used:
Traceback (most recent call last):
... exists...
""", N)
    _val = (os.path.exists('foo'))
    assert repr(_val) == 'False' or str(_val) == 'False'
    write(sample_buildout, 'recipes', 'src', 'mkdir.py',
    """
    import logging, os, zc.buildout
    
    class Mkdir:
    
        def __init__(self, buildout, name, options):
            self.name, self.options = name, options
    
            # Normalize paths and check that their parent
            # directories exist:
            paths = []
            for path in options['path'].split():
                path = os.path.join(buildout['buildout']['directory'], path)
                if not os.path.isdir(os.path.dirname(path)):
                    logging.getLogger(self.name).error(
                        'Cannot create %s. %s is not a directory.',
                        options['path'], os.path.dirname(options['path']))
                    raise zc.buildout.UserError('Invalid Path')
                paths.append(path)
            options['path'] = ' '.join(paths)
    
        def install(self):
            paths = self.options['path'].split()
            for path in paths:
                logging.getLogger(self.name).info(
                    'Creating directory %s', os.path.basename(path))
                os.mkdir(path)
                self.options.created(path)
    
            return self.options.created()
    
        def update(self):
            pass
    """)
    clean_up_pyc(sample_buildout, 'recipes', 'src', 'mkdir.py')
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Installing data-dir.
data-dir: Creating directory foo
data-dir: Creating directory bin
While:
  Installing data-dir.

An internal error occurred due to a bug in either zc.buildout or in a
recipe being used:
Traceback (most recent call last):
... exists...
""", N)
    _val = (os.path.exists('foo'))
    assert repr(_val) == 'False' or str(_val) == 'False'
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = data-dir
    
    [data-dir]
    recipe = recipes:mkdir
    path = foo bins
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Installing data-dir.
data-dir: Creating directory foo
data-dir: Creating directory bins
""", N)
    _val = (os.path.exists('foo'))
    assert repr(_val) == 'True' or str(_val) == 'True'
    _val = (os.path.exists('bins'))
    assert repr(_val) == 'True' or str(_val) == 'True'

def test_configuration(buildout_txt_env):
    buildout = buildout_txt_env['buildout']
    cat = buildout_txt_env['cat']
    print_ = buildout_txt_env['print_']
    sample_buildout = buildout_txt_env['sample_buildout']
    system = buildout_txt_env['system']
    write = buildout_txt_env['write']

    from io import StringIO
    import pprint, zc.buildout.configparser
    text = "[foo]\nbar = 1\nbaz = a\n      b\n\n      c\n"
    _val = zc.buildout.configparser.parse(StringIO(text), 'test')
    assert _val == {'foo': {'bar': '1', 'baz': 'a\nb\nc'}}
    text = "[foo]\nbar =\nbaz =\n\n  a\n    b\n\n  c\n"
    _val = zc.buildout.configparser.parse(StringIO(text), 'test')
    assert _val == {'foo': {'bar': '', 'baz': 'a\n  b\n\nc'}}
    assert_output(system([buildout, 'annotate']), """

Annotated sections
==================

[buildout]
allow-hosts= *
    DEFAULT_VALUE
allow-picked-versions= true
    DEFAULT_VALUE
allow-unknown-extras= false
    DEFAULT_VALUE
bin-directory= bin
    DEFAULT_VALUE
develop-eggs-directory= develop-eggs
    DEFAULT_VALUE
directory= /sample-buildout
    COMPUTED_VALUE
eggs-directory= /sample-buildout/eggs
    DEFAULT_VALUE
eggs-directory-version= v5
    DEFAULT_VALUE
executable= ...
    DEFAULT_VALUE
find-links=
    DEFAULT_VALUE
install-from-cache= false
    DEFAULT_VALUE
installed= .installed.cfg
    DEFAULT_VALUE
log-format=
    DEFAULT_VALUE
log-level= INFO
    DEFAULT_VALUE
newest= true
    DEFAULT_VALUE
offline= false
    DEFAULT_VALUE
parts=
    buildout.cfg
parts-directory= parts
    DEFAULT_VALUE
prefer-final= true
    DEFAULT_VALUE
python= buildout
    DEFAULT_VALUE
show-picked-versions= false
    DEFAULT_VALUE
socket-timeout=
    DEFAULT_VALUE
update-versions-file=
    DEFAULT_VALUE
use-dependency-links= true
    DEFAULT_VALUE
versions= versions
    DEFAULT_VALUE

[versions]
zc.buildout = >=1.99
    DEFAULT_VALUE
zc.recipe.egg = >=1.99
    DEFAULT_VALUE
""", N)
    assert_output(system([buildout, '-v', 'annotate']), """

Annotated sections
==================

[buildout]
allow-hosts= *

   AS DEFAULT_VALUE
   SET VALUE = *

allow-picked-versions= true

   AS DEFAULT_VALUE
   SET VALUE = true

allow-unknown-extras= false

   AS DEFAULT_VALUE
   SET VALUE = false

bin-directory= bin

   AS DEFAULT_VALUE
   SET VALUE = bin

develop-eggs-directory= develop-eggs

   AS DEFAULT_VALUE
   SET VALUE = develop-eggs

directory= /sample-buildout

   AS COMPUTED_VALUE
   SET VALUE = /sample-buildout

eggs-directory= /sample-buildout/eggs

   AS DEFAULT_VALUE
   DIRECTORY VALUE = /sample-buildout/eggs
   AS DEFAULT_VALUE
   SET VALUE = eggs

eggs-directory-version= v5

   AS DEFAULT_VALUE
   SET VALUE = v5

executable= ...

   AS DEFAULT_VALUE
   SET VALUE = ...

find-links=

   AS DEFAULT_VALUE
   SET VALUE =

install-from-cache= false

   AS DEFAULT_VALUE
   SET VALUE = false

installed= .installed.cfg

   AS DEFAULT_VALUE
   SET VALUE = .installed.cfg

log-format=

   AS DEFAULT_VALUE
   SET VALUE =

log-level= INFO

   AS DEFAULT_VALUE
   SET VALUE = INFO

newest= true

   AS DEFAULT_VALUE
   SET VALUE = true

offline= false

   AS DEFAULT_VALUE
   SET VALUE = false

parts=

   IN buildout.cfg
   SET VALUE =

parts-directory= parts

   AS DEFAULT_VALUE
   SET VALUE = parts

prefer-final= true

   AS DEFAULT_VALUE
   SET VALUE = true

python= buildout

   AS DEFAULT_VALUE
   SET VALUE = buildout

show-picked-versions= false

   AS DEFAULT_VALUE
   SET VALUE = false

socket-timeout=

   AS DEFAULT_VALUE
   SET VALUE =

update-versions-file=

   AS DEFAULT_VALUE
   SET VALUE =

use-dependency-links= true

   AS DEFAULT_VALUE
   SET VALUE = true

verbosity= 10

   AS COMMAND_LINE_VALUE
   SET VALUE = 10

versions= versions

   AS DEFAULT_VALUE
   SET VALUE = versions


[versions]
...
""", N)
    assert_output(system([buildout, 'annotate', 'versions']), """

Annotated sections
==================

[versions]
zc.buildout= >=1.99
    DEFAULT_VALUE
zc.recipe.egg= >=1.99
    DEFAULT_VALUE
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = .
    
    [values]
    host = buildout.org
    multiline =
      first
      second
    """)
    assert_output(system([buildout, 'query', 'buildout:develop']), '.', N)
    assert_output(system([buildout, 'query', 'values:host']), 'buildout.org', N)
    assert_output(system([buildout, 'query', 'values:multiline']), """
first
second
""", N)
    assert_output(system([buildout, 'query', 'develop']), '.', N)
    assert_output(system([buildout, '-v', 'query', 'develop']), """
${buildout:develop}
.
""", N)
    assert_output(system([buildout, '-v', 'query', 'values:host']), """
${values:host}
buildout.org
""", N)
    assert_output(system([buildout, 'query', 'versions', 'parts']), 'Error: The query command requires a single argument.', N)
    assert_output(system([buildout, 'query']), 'Error: The query command requires a single argument.', N)
    assert_output(system([buildout, 'query', 'invalid:section:key']), 'Error: Invalid option: invalid:section:key', N)
    assert_output(system([buildout, '-v', 'query', 'values:port']), """
${values:port}
Error: Key not found: port
""", N)
    assert_output(system([buildout, '-v', 'query', 'versionx']), """
${buildout:versionx}
Error: Key not found: versionx
""", N)
    assert_output(system([buildout, '-v', 'query', 'specific:port']), """
${specific:port}
Error: Section not found: specific
""", N)
    write(sample_buildout, 'recipes', 'setup.py',
    """
    from setuptools import setup
    entry_points = (
    '''
    [zc.buildout]
    mkdir = mkdir:Mkdir
    debug = debug:Debug
    environ = environ:Environ
    ''')
    setup(name="recipes", entry_points=entry_points)
    """)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = data-dir debug
    log-level = INFO
    
    [debug]
    recipe = recipes:debug
    File-1 = ${data-dir:path}/file
    File-2 = ${debug:File-1}/log
    
    [data-dir]
    recipe = recipes:mkdir
    path = mydata
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Installing data-dir.
data-dir: Creating directory mydata
Installing debug.
File-1 /sample-buildout/mydata/file
File-2 /sample-buildout/mydata/file/log
recipe recipes:debug
""", N)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Updating data-dir.
Updating debug.
File-1 /sample-buildout/mydata/file
File-2 /sample-buildout/mydata/file/log
recipe recipes:debug
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = data-dir debug
    log-level = INFO
    
    [debug]
    recipe = recipes:debug
    File-1 = ${data-dir:path}/file
    File-2 = ${:File-1}/log
    my_name = ${:_buildout_section_name_}
    
    [data-dir]
    recipe = recipes:mkdir
    path = mydata
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Updating data-dir.
Installing debug.
File-1 /sample-buildout/mydata/file
File-2 /sample-buildout/mydata/file/log
my_name debug
recipe recipes:debug
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = debug
    log-level = INFO
    
    [debug]
    recipe = recipes:debug
    File-1 = ${data-dir:path}/file
    File-2 = ${debug:File-1}/log
    
    [data-dir]
    recipe = recipes:mkdir
    path = mydata
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Updating data-dir.
Installing debug.
File-1 /sample-buildout/mydata/file
File-2 /sample-buildout/mydata/file/log
recipe recipes:debug
""", N)
    assert_output(capture_print(cat, '.installed.cfg'), """
[buildout]
installed_develop_eggs = /sample-buildout/develop-eggs/recipes.egg-link
parts = data-dir debug
...
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = debug data-dir
    log-level = INFO
    
    [debug]
    recipe = recipes:debug
    File-1 = ${data-dir:path}/file
    File-2 = ${debug:File-1}/log
    
    [data-dir]
    recipe = recipes:mkdir
    path = mydata
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Updating data-dir.
Updating debug.
File-1 /sample-buildout/mydata/file
File-2 /sample-buildout/mydata/file/log
recipe recipes:debug
""", N)
    assert_output(capture_print(cat, '.installed.cfg'), """
[buildout]
installed_develop_eggs = /sample-buildout/develop-eggs/recipes.egg-link
parts = data-dir debug
...
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = myfiles
    log-level = INFO
    
    [debug]
    recipe = recipes:debug
    
    [with_file1]
    <= debug
    file1 = ${:path}/file1
    color = red
    
    [with_file2]
    <= debug
    file2 = ${:path}/file2
    color = blue
    
    [myfiles]
    <= with_file1
       with_file2
    path = mydata
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Uninstalling data-dir.
Installing myfiles.
color blue
file1 mydata/file1
file2 mydata/file2
path mydata
recipe recipes:debug
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts =
    """)
    _ = system(buildout)

def test_extending(buildout_txt_env):
    buildout = buildout_txt_env['buildout']
    join = buildout_txt_env['join']
    mkdir = buildout_txt_env['mkdir']
    os = buildout_txt_env['os']
    print_ = buildout_txt_env['print_']
    remove = buildout_txt_env['remove']
    rmdir = buildout_txt_env['rmdir']
    sample_buildout = buildout_txt_env['sample_buildout']
    start_server = buildout_txt_env['start_server']
    stop_server = buildout_txt_env['stop_server']
    system = buildout_txt_env['system']
    tmpdir = buildout_txt_env['tmpdir']
    write = buildout_txt_env['write']

    import os
    write(sample_buildout, 'base.cfg',
    """
    [buildout]
    parts = part1 part2 part3
    
    [part1]
    recipe =
    option = a1
             a2
    
    [part2]
    <= part1
    option -= a1
    option += c3 c4
    
    [part3]
    <= part2
    option += d2
               c5 d1 d6
    option -= a2
    """)
    mkdir(sample_buildout, 'demo')
    write(sample_buildout, 'demo', 'demo.py',
    """
    import sys
    def ext(buildout):
        sys.stdout.write(str(
            [part['option'] for name, part in sorted(buildout.items())
             if name.startswith('part')])+'\\n')
    """)
    write(sample_buildout, 'demo', 'setup.py',
    """
    from setuptools import setup
    
    setup(
        name="demo",
        entry_points={'zc.buildout.extension': ['ext = demo:ext']},
        )
    """)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = demo
    parts =
    """)
    os.chdir(sample_buildout)
    assert_output(system(os.path.join(sample_buildout, 'bin', 'buildout')), "Develop: '/sample-buildout/demo'", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = demo
    extensions = demo
    extends = base.cfg
    """)
    assert_output(system(os.path.join('bin', 'buildout')), """
['a1/na2', 'a2/nc3 c4', 'c3 c4/nd2/nc5 d1 d6']
Develop: '/sample-buildout/demo'
""", N)
    os.remove(os.path.join(sample_buildout, 'base.cfg'))
    rmdir(sample_buildout, 'demo')
    write(sample_buildout, 'base.cfg',
    """
    [buildout]
    parts = part1 part2 part3
    
    [part1]
    recipe =
    option = a1 a2
    
    [part2]
    recipe =
    option = b1 b2 b3 b4
    
    [part3]
    recipe =
    option = c1 c2
    
    [part4]
    recipe =
    option = d2
        d3
        d5
    
    # Issue #641 - Properly handle options which are initially defined
    # using += / -=
    [part6]
    option += e1
    
    [part7]
    option -= f1
    
    """)
    write(sample_buildout, 'extension1.cfg',
    """
    [buildout]
    extends = base.cfg
    
    # appending values
    [part1]
    option += a3 a4
    
    # removing values
    [part2]
    option -= b1 b2
    
    # alt. spelling
    [part3]
    option+=c3 c4 c5
    
    # combining both adding and removing
    [part4]
    option += d1
         d4
    option -= d5
    
    # normal assignment
    [part5]
    option = h1 h2
    
    """)
    write(sample_buildout, 'extension2.cfg',
    """
    [buildout]
    extends = extension1.cfg
    
    # appending values
    [part1]
    option += a5
    
    # removing values
    [part2]
    option -= b1 b2 b3
    
    """)
    mkdir(sample_buildout, 'demo')
    write(sample_buildout, 'demo', 'demo.py',
    """
    import sys
    def ext(buildout):
        sys.stdout.write(str(
            [part.get('option') for name, part in sorted(buildout.items())
             if name.startswith('part')])+'\\n')
    """)
    write(sample_buildout, 'demo', 'setup.py',
    """
    from setuptools import setup
    
    setup(
        name="demo",
        entry_points={'zc.buildout.extension': ['ext = demo:ext']},
        )
    """)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = demo
    parts =
    """)
    os.chdir(sample_buildout)
    assert_output(system(os.path.join(sample_buildout, 'bin', 'buildout')), "Develop: '/sample-buildout/demo'...", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = demo
    extensions = demo
    extends = extension2.cfg
    """)
    assert_output(system(os.path.join('bin', 'buildout')), """
['a1 a2/na3 a4/na5', 'b1 b2 b3 b4', 'c1 c2/nc3 c4 c5', 'd2/nd3/nd1/nd4', 'h1 h2', 'e1', '']
Develop: '/sample-buildout/demo'
""", N)
    assert_output(system(os.path.join('bin', 'buildout') + ' annotate'), """

Annotated sections
==================
...

[part1]
option= a1 a2
a3 a4
a5
    base.cfg
+=  extension1.cfg
+=  extension2.cfg
recipe=
    base.cfg

[part2]
option= b1 b2 b3 b4
    base.cfg
-=  extension1.cfg
-=  extension2.cfg
recipe=
    base.cfg

[part3]
option= c1 c2
c3 c4 c5
    base.cfg
+=  extension1.cfg
recipe=
    base.cfg

[part4]
option= d2
d3
d1
d4
    base.cfg
+=  extension1.cfg
-=  extension1.cfg
recipe=
    base.cfg

[part5]
option= h1 h2
    extension1.cfg

[part6]
option= e1
    base.cfg

[part7]
option=
    base.cfg
-=  IMPLICIT_VALUE

[versions]
zc.buildout= >=1.99
    DEFAULT_VALUE
zc.recipe.egg= >=1.99
    DEFAULT_VALUE
""", N)
    assert_output(system(os.path.join('bin', 'buildout') + ' -v annotate'), """
Annotated sections
...
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    extends =
        extension1.cfg
        extension2.cfg
    develop = demo
    extensions = demo
    parts = part1
    """)
    write(sample_buildout, 'extension1.cfg',
    """
    [part1]
    recipe =
    option =
        a
        b
    """)
    write(sample_buildout, 'extension2.cfg',
    """
    [part1]
    option +=
        c
        d
    
    [part1:False]
    option +=
        z
    
    [part1:True]
    option +=
        e
    """)
    assert_output(system(os.path.join('bin', 'buildout')), """
['a/nb/nc/nd/ne']
Develop: '/sample-buildout/demo'
""", N)
    os.remove(os.path.join(sample_buildout, 'base.cfg'))
    os.remove(os.path.join(sample_buildout, 'extension1.cfg'))
    os.remove(os.path.join(sample_buildout, 'extension2.cfg'))
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    extends = base.cfg
    
    [debug]
    op = buildout
    """)
    write(sample_buildout, 'base.cfg',
    """
    [buildout]
    develop = recipes
    parts = debug
    
    [debug]
    recipe = recipes:debug
    op = base
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Installing debug.
op buildout
recipe recipes:debug
""", N)
    other = tmpdir('other')
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    extends = b1.cfg b2.cfg %(b3)s
    
    [debug]
    op = buildout
    """ % dict(b3=os.path.join(other, 'b3.cfg')))
    write(sample_buildout, 'b1.cfg',
    """
    [buildout]
    extends = base.cfg
    
    [debug]
    op1 = b1 1
    op2 = b1 2
    """)
    write(sample_buildout, 'b2.cfg',
    """
    [buildout]
    extends = base.cfg
    
    [debug]
    op2 = b2 2
    op3 = b2 3
    """)
    write(other, 'b3.cfg',
    """
    [buildout]
    extends = b3base.cfg
    
    [debug]
    op4 = b3 4
    """)
    write(other, 'b3base.cfg',
    """
    [debug]
    op5 = b3base 5
    """)
    write(sample_buildout, 'base.cfg',
    """
    [buildout]
    develop = recipes
    parts = debug
    
    [debug]
    recipe = recipes:debug
    name = base
    
    [environ]
    recipe = recipes:environ
    name = base
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Installing debug.
name base
op buildout
op1 b1 1
op2 b2 2
op3 b2 3
op4 b3 4
op5 b3base 5
recipe recipes:debug
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    extends = b1.cfg
    
    [debug]
    op = buildout
    """)
    assert_output(system([buildout, 'buildout:extends=b2.cfg']), """
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Installing debug.
name base
op buildout
op1 b1 1
op2 b2 2
op3 b2 3
recipe recipes:debug
""", N)
    assert_output(system([buildout, 'buildout:extends=b2.cfg %(b3)s' % dict(b3=os.path.join(other, 'b3.cfg'))]), """
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Installing debug.
name base
op buildout
op1 b1 1
op2 b2 2
op3 b2 3
op4 b3 4
op5 b3base 5
recipe recipes:debug
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    extends = b1.cfg b2.cfg %(b3)s
    
    [debug]
    op = buildout
    """ % dict(b3=os.path.join(other, 'b3.cfg')))
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    extends = b1.cfg
    optional-extends = optional.cfg
    
    [debug]
    op = buildout
    """)
    assert_output(system(buildout), """
optional-extends file not found: optional.cfg
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Installing debug.
name base
op buildout
op1 b1 1
op2 b1 2
recipe recipes:debug
""", N)
    write('optional.cfg', """
    [debug]
    op2 = optional2 2
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Installing debug.
name base
op buildout
op1 b1 1
op2 optional2 2
recipe recipes:debug
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    extends = b1.cfg b2.cfg %(b3)s
    
    [debug]
    op = buildout
    """ % dict(b3=os.path.join(other, 'b3.cfg')))
    remove(sample_buildout, 'optional.cfg')
    server_data = tmpdir('server_data')
    write(server_data, "r1.cfg",
    """
    [debug]
    op1 = r1 1
    op2 = r1 2
    """)
    write(server_data, "r2.cfg",
    """
    [buildout]
    extends = r1.cfg
    
    [debug]
    op2 = r2 2
    op3 = r2 3
    """)
    server_url = start_server(server_data)
    write('client.cfg', """
    [buildout]
    develop = recipes
    parts = debug
    extends = %(url)s/r2.cfg
    
    [debug]
    recipe = recipes:debug
    name = base
    """ % dict(url=server_url))
    assert_output(system([buildout, '-c', 'client.cfg']), """
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Installing debug.
name base
op1 r1 1
op2 r2 2
op3 r2 3
recipe recipes:debug
""", N)
    os.remove('client.cfg')
    write(server_data, 'remote.cfg',
    """
    [buildout]
    develop = recipes
    parts = debug
    extends = r2.cfg
    
    [debug]
    recipe = recipes:debug
    name = remote
    """)
    assert_output(system([buildout, '-c', server_url + '/remote.cfg']), """
While:
  Initializing.
Error: Missing option: buildout:directory
""", N)
    assert_output(system([buildout, '-c', server_url + '/remote.cfg', 'buildout:directory=' + sample_buildout]), """
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Installing debug.
name remote
op1 r1 1
op2 r2 2
op3 r2 3
recipe recipes:debug
""", N)
    home = tmpdir('home')
    mkdir(home, '.buildout')
    default_cfg = join(home, '.buildout', 'default.cfg')
    write(default_cfg, """
    [debug]
    op1 = 1
    op7 = 7
    """)
    env = dict(HOME=home, USERPROFILE=home)
    assert_output(system(buildout, env=env), """
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Installing debug.
name base
op buildout
op1 b1 1
op2 b2 2
op3 b2 3
op4 b3 4
op5 b3base 5
op7 7
recipe recipes:debug
""", N)
    assert_output(system([buildout, '-U'], env=env), """
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Installing debug.
name base
op buildout
op1 b1 1
op2 b2 2
op3 b2 3
op4 b3 4
op5 b3base 5
recipe recipes:debug
""", N)
    alterhome = tmpdir('alterhome')
    write(alterhome, 'default.cfg',
    """
    [debug]
    op1 = 1'
    op7 = 7'
    op8 = eight!
    """)
    env['BUILDOUT_HOME'] = alterhome
    assert_output(system(buildout, env=env), """
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Installing debug.
name base
op buildout
op1 b1 1
op2 b2 2
op3 b2 3
op4 b3 4
op5 b3base 5
op7 7'
op8 eight!
recipe recipes:debug
""", N)
    assert_output(system([buildout, '-U'], env=env), """
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Installing debug.
name base
op buildout
op1 b1 1
op2 b2 2
op3 b2 3
op4 b3 4
op5 b3base 5
recipe recipes:debug
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    log-level = WARNING
    extends = b1.cfg b2.cfg
    """)
    assert_output(system(buildout), """
name base
op1 b1 1
op2 b2 2
op3 b2 3
recipe recipes:debug
""", N)
    stop_server(server_url)

def test_options(buildout_txt_env):
    buildout = buildout_txt_env['buildout']
    cat = buildout_txt_env['cat']
    ls = buildout_txt_env['ls']
    os = buildout_txt_env['os']
    print_ = buildout_txt_env['print_']
    rmdir = buildout_txt_env['rmdir']
    sample_buildout = buildout_txt_env['sample_buildout']
    system = buildout_txt_env['system']
    tmpdir = buildout_txt_env['tmpdir']
    write = buildout_txt_env['write']

    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    socket-timeout = 5
    develop = recipes
    parts = debug
    
    [debug]
    recipe = recipes:debug
    op = timeout
    """)
    assert_output(system(buildout), """
Setting socket time out to 5 seconds.
Develop: '/sample-buildout/recipes'
Installing debug.
op timeout
recipe recipes:debug
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    socket-timeout = 5s
    develop = recipes
    parts = debug
    
    [debug]
    recipe = recipes:debug
    op = timeout
    """)
    assert_output(system(buildout), """
Default socket timeout is used !
Value in configuration is not numeric: [5s].

Develop: '/sample-buildout/recipes'
Updating debug.
op timeout
recipe recipes:debug
""", N)
    write(sample_buildout, 'recipes', 'src', 'service.py',
    """
    import sys
    class Service:
    
        def __init__(self, buildout, name, options):
            self.buildout = buildout
            self.name = name
            self.options = options
    
        def install(self):
            sys.stdout.write("chkconfig --add %s\\n"
                             % self.options['script'])
            return ()
    
        def update(self):
            pass
    
    
    def uninstall_service(name, options):
        sys.stdout.write("chkconfig --del %s\\n" % options['script'])
    """)
    write(sample_buildout, 'recipes', 'setup.py',
    """
    from setuptools import setup
    entry_points = (
    '''
    [zc.buildout]
    mkdir = mkdir:Mkdir
    debug = debug:Debug
    service = service:Service
    
    [zc.buildout.uninstall]
    service = service:uninstall_service
    ''')
    setup(name="recipes", entry_points=entry_points)
    """)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = service
    
    [service]
    recipe = recipes:service
    script = /path/to/script
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Installing service.
chkconfig --add /path/to/script
""", N)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Updating service.
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = service
    
    [service]
    recipe = recipes:service
    script = /path/to/a/different/script
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Uninstalling service.
Running uninstall recipe.
chkconfig --del /path/to/script
Installing service.
chkconfig --add /path/to/a/different/script
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = debug
    
    [debug]
    recipe = recipes:debug
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Uninstalling service.
Running uninstall recipe.
chkconfig --del /path/to/a/different/script
Installing debug.
recipe recipes:debug
""", N)
    write(sample_buildout, 'recipes', 'src', 'backup.py',
    """
    import os, sys
    def backup_directory(name, options):
        path = options['path']
        size = len(os.listdir(path))
        sys.stdout.write("backing up directory %s of size %s\\n"
                         % (path, size))
    """)
    write(sample_buildout, 'recipes', 'setup.py',
    """
    from setuptools import setup
    entry_points = (
    '''
    [zc.buildout]
    mkdir = mkdir:Mkdir
    debug = debug:Debug
    service = service:Service
    
    [zc.buildout.uninstall]
    uninstall_service = service:uninstall_service
    mkdir = backup:backup_directory
    ''')
    setup(name="recipes", entry_points=entry_points)
    """)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = dir debug
    
    [dir]
    recipe = recipes:mkdir
    path = my_directory
    
    [debug]
    recipe = recipes:debug
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Installing dir.
dir: Creating directory my_directory
Installing debug.
recipe recipes:debug
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = debug
    
    [debug]
    recipe = recipes:debug
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Uninstalling dir.
Running uninstall recipe.
backing up directory /sample-buildout/my_directory of size 0
Updating debug.
recipe recipes:debug
""", N)
    write(sample_buildout, 'recipes', 'setup.py',
    """
    from setuptools import setup
    entry_points = (
    '''
    [zc.buildout]
    mkdir = mkdir:Mkdir
    debug = debug:Debug
    ''')
    setup(name="recipes", entry_points=entry_points)
    """)
    write(sample_buildout, 'other.cfg',
    """
    [buildout]
    develop = recipes
    parts = debug
    installed = .other.cfg
    log-level = WARNING
    
    [debug]
    name = other
    recipe = recipes:debug
    """)
    assert_output(system([buildout, '-c', 'other.cfg', 'debug:op1=foo', '-v']), """
Develop: '/sample-buildout/recipes'
Installing debug.
name other
op1 foo
recipe recipes:debug
""", N)
    assert_output(system([buildout, '-vcother.cfg', 'debug:op1=foo']), """
Develop: '/sample-buildout/recipes'
Updating debug.
name other
op1 foo
recipe recipes:debug
""", N)
    os.remove(os.path.join(sample_buildout, 'other.cfg'))
    os.remove(os.path.join(sample_buildout, '.other.cfg'))
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = debug d1 d2 d3
    
    [d1]
    recipe = recipes:mkdir
    path = d1
    
    [d2]
    recipe = recipes:mkdir
    path = d2
    
    [d3]
    recipe = recipes:mkdir
    path = d3
    
    [debug]
    recipe = recipes:debug
    """)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Uninstalling debug.
Installing debug.
recipe recipes:debug
Installing d1.
d1: Creating directory d1
Installing d2.
d2: Creating directory d2
Installing d3.
d3: Creating directory d3
""", N)
    assert_output(capture_print(ls, sample_buildout), """
-  .installed.cfg
d  bin
-  buildout.cfg
d  d1
d  d2
d  d3
d  develop-eggs
d  eggs
d  parts
d  recipes
""", N)
    assert_output(capture_print(cat, sample_buildout, '.installed.cfg'), """
[buildout]
installed_develop_eggs = /sample-buildout/develop-eggs/recipes.egg-link
parts = debug d1 d2 d3

[debug]
__buildout_installed__ =
__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==
recipe = recipes:debug

[d1]
__buildout_installed__ = /sample-buildout/d1
__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==
path = /sample-buildout/d1
recipe = recipes:mkdir

[d2]
__buildout_installed__ = /sample-buildout/d2
__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==
path = /sample-buildout/d2
recipe = recipes:mkdir

[d3]
__buildout_installed__ = /sample-buildout/d3
__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==
path = /sample-buildout/d3
recipe = recipes:mkdir
""", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = debug d2 d3 d4
    
    [d2]
    recipe = recipes:mkdir
    path = data2
    
    [d3]
    recipe = recipes:mkdir
    path = data3
    
    [d4]
    recipe = recipes:mkdir
    path = ${d2:path}-extra
    
    [debug]
    recipe = recipes:debug
    x = 1
    """)
    assert_output(system([buildout, 'install', 'd3', 'd4']), """
Develop: '/sample-buildout/recipes'
Uninstalling d3.
Installing d3.
d3: Creating directory data3
Installing d4.
d4: Creating directory data2-extra
""", N)
    assert_output(capture_print(ls, sample_buildout), """
-  .installed.cfg
d  bin
-  buildout.cfg
d  d1
d  d2
d  data2-extra
d  data3
d  develop-eggs
d  eggs
d  parts
d  recipes
""", N)
    assert_output(capture_print(cat, sample_buildout, '.installed.cfg'), """
[buildout]
installed_develop_eggs = /sample-buildout/develop-eggs/recipes.egg-link
parts = debug d1 d2 d3 d4

[debug]
__buildout_installed__ =
__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==
recipe = recipes:debug

[d1]
__buildout_installed__ = /sample-buildout/d1
__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==
path = /sample-buildout/d1
recipe = recipes:mkdir

[d2]
__buildout_installed__ = /sample-buildout/d2
__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==
path = /sample-buildout/d2
recipe = recipes:mkdir

[d3]
__buildout_installed__ = /sample-buildout/data3
__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==
path = /sample-buildout/data3
recipe = recipes:mkdir

[d4]
__buildout_installed__ = /sample-buildout/data2-extra
__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==
path = /sample-buildout/data2-extra
recipe = recipes:mkdir
""", N)
    assert_output(system(buildout), """
Develop: '/sample-buildout/recipes'
Uninstalling d2.
Uninstalling d1.
Uninstalling debug.
Installing debug.
recipe recipes:debug
x 1
Installing d2.
d2: Creating directory data2
Updating d3.
Updating d4.
""", N)
    assert_output(capture_print(ls, sample_buildout), """
-  .installed.cfg
d  bin
-  buildout.cfg
d  data2
d  data2-extra
d  data3
d  develop-eggs
d  eggs
d  parts
d  recipes
""", N)
    alt = tmpdir('sample-alt')
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts =
    develop-eggs-directory = %(developbasket)s
    eggs-directory = %(basket)s
    eggs-directory-version = v2
    bin-directory = %(scripts)s
    parts-directory = %(work)s
    """ % dict(
       developbasket = os.path.join(alt, 'developbasket'),
       basket = os.path.join(alt, 'basket'),
       scripts = os.path.join(alt, 'scripts'),
       work = os.path.join(alt, 'work'),
    ))
    assert_output(system(buildout), """
Creating directory '/sample-alt/basket/v2'.
Creating directory '/sample-alt/scripts'.
Creating directory '/sample-alt/work'.
Creating directory '/sample-alt/developbasket'.
Develop: '/sample-buildout/recipes'
Uninstalling d4.
Uninstalling d3.
Uninstalling d2.
Uninstalling debug.
""", N)
    assert_output(capture_print(ls, alt), """
d  basket
d  developbasket
d  scripts
d  work
""", N)
    assert_output(capture_print(ls, alt, 'developbasket'), '-  recipes.egg-link', N)
    rmdir(alt)
    alt = tmpdir('sample-alt')
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    directory = %(alt)s
    develop = %(recipes)s
    parts =
    """ % dict(
       alt=alt,
       recipes=os.path.join(sample_buildout, 'recipes'),
       ))
    assert_output(system(buildout), """
Creating directory '/sample-alt/eggs/v5'.
Creating directory '/sample-alt/bin'.
Creating directory '/sample-alt/parts'.
Creating directory '/sample-alt/develop-eggs'.
Develop: '/sample-buildout/recipes'
""", N)
    assert_output(capture_print(ls, alt), """
-  .installed.cfg
d  bin
d  develop-eggs
d  eggs
d  parts
""", N)
    assert_output(capture_print(ls, alt, 'develop-eggs'), '-  recipes.egg-link', N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts =
    log-level = 25
    verbosity = 5
    log-format = %(levelname)s %(message)s
    """)
    assert_output(system(buildout), "INFO Develop: '/sample-buildout/recipes'", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    parts =
    """)
    assert_output(system([buildout, '-vv']), """
Installing 'zc.buildout', 'wheel', 'pip', 'setuptools'.
...
Configuration data:
[buildout]
allow-hosts = *
allow-picked-versions = true
allow-unknown-extras = false
bin-directory = /sample-buildout/bin
develop-eggs-directory = /sample-buildout/develop-eggs
directory = /sample-buildout
eggs-directory = /sample-buildout/eggs/v5
eggs-directory-version = v5
executable = python
find-links =
install-from-cache = false
installed = /sample-buildout/.installed.cfg
log-format =
log-level = INFO
newest = true
offline = false
parts =
parts-directory = /sample-buildout/parts
prefer-final = true
python = buildout
show-picked-versions = false
socket-timeout =
update-versions-file =
use-dependency-links = true
verbosity = 20
versions = versions
[versions]
zc.buildout = >=1.99
zc.recipe.egg = >=1.99
""", N)

def test_init(buildout_txt_env):
    buildout = buildout_txt_env['buildout']
    cat = buildout_txt_env['cat']
    cd = buildout_txt_env['cd']
    ls = buildout_txt_env['ls']
    os = buildout_txt_env['os']
    print_ = buildout_txt_env['print_']
    remove = buildout_txt_env['remove']
    sample_buildout = buildout_txt_env['sample_buildout']
    system = buildout_txt_env['system']
    tmpdir = buildout_txt_env['tmpdir']
    uncd = buildout_txt_env['uncd']
    write = buildout_txt_env['write']

    sample_bootstrapped = tmpdir('sample-bootstrapped')
    assert_output(system([buildout, '-c' + os.path.join(sample_bootstrapped, 'setup.cfg'), 'init']), """
Creating '/sample-bootstrapped/setup.cfg'.
Creating directory '/sample-bootstrapped/eggs/v5'.
Creating directory '/sample-bootstrapped/bin'.
Creating directory '/sample-bootstrapped/parts'.
Creating directory '/sample-bootstrapped/develop-eggs'.
Generated script '/sample-bootstrapped/bin/buildout'.
""", N)
    assert_output(capture_print(cat, sample_bootstrapped, 'setup.cfg'), """
[buildout]
parts =
""", N)
    assert_output(capture_print(ls, sample_bootstrapped), """
d  bin
d  develop-eggs
d  eggs
d  parts
-  setup.cfg
""", N)
    assert_output(capture_print(ls, sample_bootstrapped, 'bin'), '-  buildout', N)
    _ = (ls(sample_bootstrapped, 'eggs', 'v5'),
         ls(sample_bootstrapped, 'develop-eggs'))
    # TODO assert: '-  packaging.egg-link\n-  pip.egg-link\n-  setuptools.egg-link'
    sample_bootstrapped2 = tmpdir('sample-bootstrapped2')
    assert_output(system([buildout, '-c' + os.path.join(sample_bootstrapped2, 'setup.cfg'), 'bootstrap']), """
While:
  Initializing.
Error: Couldn't open /sample-bootstrapped2/setup.cfg
""", N)
    write(sample_bootstrapped2, 'setup.cfg',
    """
    [buildout]
    parts =
    """)
    assert_output(system([buildout, '-c' + os.path.join(sample_bootstrapped2, 'setup.cfg'), 'bootstrap']), """
Creating directory '/sample-bootstrapped2/eggs/v5'.
Creating directory '/sample-bootstrapped2/bin'.
Creating directory '/sample-bootstrapped2/parts'.
Creating directory '/sample-bootstrapped2/develop-eggs'.
Generated script '/sample-bootstrapped2/bin/buildout'.
""", N)
    assert_output(system([buildout, '-c' + os.path.join(sample_bootstrapped, 'setup.cfg'), 'init']), """
While:
  Initializing.
Error: '/sample-bootstrapped/setup.cfg' already exists.
""", N)
    cd(sample_bootstrapped)
    remove('setup.cfg')
    assert_output(system([buildout, '-csetup.cfg', 'init', 'demo', 'other', './src']), """
Creating '/sample-bootstrapped/setup.cfg'.
Creating directory '/sample-bootstrapped/develop-eggs'.
Getting distribution for 'zc.recipe.egg>=2.0.6'.
Got zc.recipe.egg
Installing py.
Getting distribution for 'demo'.
Got demo 0.3.
Getting distribution for 'other'.
Got other 1.0.
Getting distribution for 'demoneeded'.
Got demoneeded 1.1.
Generated script '/sample-bootstrapped/bin/demo'.
Generated interpreter '/sample-bootstrapped/bin/py'.
""", N)
    assert_output(capture_print(cat, 'setup.cfg'), """
[buildout]
parts = py

[py]
recipe = zc.recipe.egg
interpreter = py
eggs =
  demo
  other
extra-paths =
  ./src
""", N)
    assert_output(capture_print(ls, '.'), """
-  .installed.cfg
d  bin
d  develop-eggs
d  eggs
d  parts
-  setup.cfg
d  src
""", N)
    uncd()
    cd(sample_bootstrapped)
    _ = system([buildout, '-csetup.cfg', 'buildout:parts='])
    remove('setup.cfg')
    assert_output(system([buildout, '-csetup.cfg', 'init', 'demo', 'other', './src']), """
Creating '/sample-bootstrapped/setup.cfg'.
Creating directory '/sample-bootstrapped/develop-eggs'.
Installing py.
Generated script '/sample-bootstrapped/bin/demo'.
Generated interpreter '/sample-bootstrapped/bin/py'.
""", N)
    _ = system([buildout, '-csetup.cfg', 'buildout:parts='])
    uncd()
    write('buildout.cfg', """
    [buildout]
    develop = recipes
    parts = debug
    
    [debug]
    recipe = recipes:debug
    """)
    assert_output(system([buildout, 'buildout:installed=inst.cfg']), """
Develop: '/sample-buildout/recipes'
Installing debug.
recipe recipes:debug
""", N)
    assert_output(capture_print(ls, sample_buildout), """
d  bin
-  buildout.cfg
d  develop-eggs
d  eggs
-  inst.cfg
d  parts
d  recipes
""", N)
    os.remove('inst.cfg')
    assert_output(system([buildout, 'buildout:installed=']), """
Develop: '/sample-buildout/recipes'
Installing debug.
recipe recipes:debug
""", N)
    assert_output(capture_print(ls, sample_buildout), """
d  bin
-  buildout.cfg
d  develop-eggs
d  eggs
d  parts
d  recipes
""", N)
    write('buildout.cfg', """
    [buildout]
    parts =
    """)
    print_(system([buildout, 'buildout:installed=inst.cfg']), end='')
    assert_output(capture_print(ls, sample_buildout), """
d  bin
-  buildout.cfg
d  develop-eggs
d  eggs
d  parts
d  recipes
""", N)

def test_extensions(buildout_txt_env):
    mkdir = buildout_txt_env['mkdir']
    os = buildout_txt_env['os']
    print_ = buildout_txt_env['print_']
    sample_buildout = buildout_txt_env['sample_buildout']
    system = buildout_txt_env['system']
    write = buildout_txt_env['write']

    mkdir(sample_buildout, 'demo')
    write(sample_buildout, 'demo', 'demo.py',
    """
    import sys
    def ext(buildout):
        sys.stdout.write('%s %s\\n' % ('ext', sorted(buildout)))
    def unload(buildout):
        sys.stdout.write('%s %s\\n' % ('unload', sorted(buildout)))
    """)
    write(sample_buildout, 'demo', 'setup.py',
    """
    from setuptools import setup
    
    setup(
        name = "demo",
        entry_points = {
           'zc.buildout.extension': ['ext = demo:ext'],
           'zc.buildout.unloadextension': ['ext = demo:unload'],
           },
        )
    """)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = demo
    parts =
    """)
    os.chdir(sample_buildout)
    assert_output(system(os.path.join(sample_buildout, 'bin', 'buildout')), "Develop: '/sample-buildout/demo'", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = demo
    extensions = demo
    parts =
    """)
    assert_output(system(os.path.join(sample_buildout, 'bin', 'buildout')), """
ext ['buildout', 'versions']
Develop: '/sample-buildout/demo'
unload ['buildout', 'versions']
""", N)
