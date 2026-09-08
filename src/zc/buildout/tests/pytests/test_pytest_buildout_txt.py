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

    assert_output(capture_print(ls, sample_buildout), 'd  bin\n-  buildout.cfg\nd  develop-eggs\nd  eggs\nd  parts\nd  recipes', N)
    assert_output(capture_print(ls, sample_buildout, 'bin'), '-  buildout', N)
    assert_output(capture_print(ls, sample_buildout, 'eggs'), 'd  v5', N)
    assert_output(capture_print(ls, sample_buildout, 'eggs', 'v5'), '-  packaging.egg-link\n-  pip.egg-link\n-  setuptools.egg-link\n-  wheel.egg-link\n-  zc.buildout.egg-link', N)
    ls(sample_buildout, 'develop-eggs')
    ls(sample_buildout, 'parts')
    assert_output(capture_print(cat, sample_buildout, 'buildout.cfg'), '[buildout]\nparts =', N)
    assert_output(capture_print(ls, sample_buildout, 'recipes'), '-  README.txt\n-  setup.py\nd  src', N)
    assert_output(capture_print(ls, sample_buildout, 'recipes', 'src'), '-  debug.py\n-  environ.py\n-  mkdir.py', N)
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
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nInstalling data-dir.\ndata-dir: Creating directory mystuff", N)
    assert_output(capture_print(ls, sample_buildout), '-  .installed.cfg\nd  bin\n-  buildout.cfg\nd  develop-eggs\nd  eggs\nd  mystuff\nd  parts\nd  recipes', N)
    assert_output(capture_print(cat, sample_buildout, '.installed.cfg'), '[buildout]\ninstalled_develop_eggs = /sample-buildout/develop-eggs/recipes.egg-link\nparts = data-dir\n\n[data-dir]\n__buildout_installed__ = /sample-buildout/mystuff\n__buildout_signature__ = recipes-c7vHV6ekIDUPy/7fjAaYjg==\npath = /sample-buildout/mystuff\nrecipe = recipes:mkdir', N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = data-dir
    
    [data-dir]
    recipe = recipes:mkdir
    path = mydata
    """)
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUninstalling data-dir.\nInstalling data-dir.\ndata-dir: Creating directory mydata", N)
    assert_output(capture_print(ls, sample_buildout), '-  .installed.cfg\nd  bin\n-  buildout.cfg\nd  develop-eggs\nd  eggs\nd  mydata\nd  parts\nd  recipes', N)
    rmdir(sample_buildout, 'mydata')
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUninstalling data-dir.\nInstalling data-dir.\ndata-dir: Creating directory mydata", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = data-dir
    
    [data-dir]
    recipe = recipes:mkdir
    path = /xxx/mydata
    """)
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\ndata-dir: Cannot create .../xxx/mydata. .../xxx is not a directory.\nWhile:\n  Installing.\n  Getting section data-dir.\n  Initializing section data-dir.\nError: Invalid Path", N)
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
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUninstalling data-dir.\nInstalling data-dir.\ndata-dir: Creating directory foo\ndata-dir: Creating directory bin\nWhile:\n  Installing data-dir.\n\nAn internal error occurred due to a bug in either zc.buildout or in a\nrecipe being used:\nTraceback (most recent call last):\n... exists...", N)
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
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nInstalling data-dir.\ndata-dir: Creating directory foo\nWhile:\n  Installing data-dir.\n\nAn internal error occurred due to a bug in either zc.buildout or in a\nrecipe being used:\nTraceback (most recent call last):\n... exists...", N)
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
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nInstalling data-dir.\ndata-dir: Creating directory foo\ndata-dir: Creating directory bin\ndata-dir: Removed foo due to error\nWhile:\n  Installing data-dir.\n\nAn internal error occurred due to a bug in either zc.buildout or in a\nrecipe being used:\nTraceback (most recent call last):\n... exists...", N)
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
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nInstalling data-dir.\ndata-dir: Creating directory foo\ndata-dir: Creating directory bin\nWhile:\n  Installing data-dir.\n\nAn internal error occurred due to a bug in either zc.buildout or in a\nrecipe being used:\nTraceback (most recent call last):\n... exists...", N)
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
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nInstalling data-dir.\ndata-dir: Creating directory foo\ndata-dir: Creating directory bins", N)
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
    _val = (pprint.pprint(zc.buildout.configparser.parse(StringIO(
    text), 'test')))
    assert repr(_val) == "{'foo': {'bar': '1', 'baz': 'a\\nb\\nc'}}" or str(_val) == "{'foo': {'bar': '1', 'baz': 'a\\nb\\nc'}}"
    _val = (pprint.pprint(zc.buildout.configparser.parse(StringIO(
    text), 'test')))
    assert repr(_val) == "{'foo': {'bar': '', 'baz': 'a\\n  b\\n\\nc'}}" or str(_val) == "{'foo': {'bar': '', 'baz': 'a\\n  b\\n\\nc'}}"
    assert_output(system([buildout, 'annotate']), '\nAnnotated sections\n==================\n\n[buildout]\nallow-hosts= *\n    DEFAULT_VALUE\nallow-picked-versions= true\n    DEFAULT_VALUE\nallow-unknown-extras= false\n    DEFAULT_VALUE\nbin-directory= bin\n    DEFAULT_VALUE\ndevelop-eggs-directory= develop-eggs\n    DEFAULT_VALUE\ndirectory= /sample-buildout\n    COMPUTED_VALUE\neggs-directory= /sample-buildout/eggs\n    DEFAULT_VALUE\neggs-directory-version= v5\n    DEFAULT_VALUE\nexecutable= ...\n    DEFAULT_VALUE\nfind-links=\n    DEFAULT_VALUE\ninstall-from-cache= false\n    DEFAULT_VALUE\ninstalled= .installed.cfg\n    DEFAULT_VALUE\nlog-format=\n    DEFAULT_VALUE\nlog-level= INFO\n    DEFAULT_VALUE\nnewest= true\n    DEFAULT_VALUE\noffline= false\n    DEFAULT_VALUE\nparts=\n    buildout.cfg\nparts-directory= parts\n    DEFAULT_VALUE\nprefer-final= true\n    DEFAULT_VALUE\npython= buildout\n    DEFAULT_VALUE\nshow-picked-versions= false\n    DEFAULT_VALUE\nsocket-timeout=\n    DEFAULT_VALUE\nupdate-versions-file=\n    DEFAULT_VALUE\nuse-dependency-links= true\n    DEFAULT_VALUE\nversions= versions\n    DEFAULT_VALUE\n\n[versions]\nzc.buildout = >=1.99\n    DEFAULT_VALUE\nzc.recipe.egg = >=1.99\n    DEFAULT_VALUE', N)
    assert_output(system([buildout, '-v', 'annotate']), '\nAnnotated sections\n==================\n\n[buildout]\nallow-hosts= *\n\n   AS DEFAULT_VALUE\n   SET VALUE = *\n\nallow-picked-versions= true\n\n   AS DEFAULT_VALUE\n   SET VALUE = true\n\nallow-unknown-extras= false\n\n   AS DEFAULT_VALUE\n   SET VALUE = false\n\nbin-directory= bin\n\n   AS DEFAULT_VALUE\n   SET VALUE = bin\n\ndevelop-eggs-directory= develop-eggs\n\n   AS DEFAULT_VALUE\n   SET VALUE = develop-eggs\n\ndirectory= /sample-buildout\n\n   AS COMPUTED_VALUE\n   SET VALUE = /sample-buildout\n\neggs-directory= /sample-buildout/eggs\n\n   AS DEFAULT_VALUE\n   DIRECTORY VALUE = /sample-buildout/eggs\n   AS DEFAULT_VALUE\n   SET VALUE = eggs\n\neggs-directory-version= v5\n\n   AS DEFAULT_VALUE\n   SET VALUE = v5\n\nexecutable= ...\n\n   AS DEFAULT_VALUE\n   SET VALUE = ...\n\nfind-links=\n\n   AS DEFAULT_VALUE\n   SET VALUE =\n\ninstall-from-cache= false\n\n   AS DEFAULT_VALUE\n   SET VALUE = false\n\ninstalled= .installed.cfg\n\n   AS DEFAULT_VALUE\n   SET VALUE = .installed.cfg\n\nlog-format=\n\n   AS DEFAULT_VALUE\n   SET VALUE =\n\nlog-level= INFO\n\n   AS DEFAULT_VALUE\n   SET VALUE = INFO\n\nnewest= true\n\n   AS DEFAULT_VALUE\n   SET VALUE = true\n\noffline= false\n\n   AS DEFAULT_VALUE\n   SET VALUE = false\n\nparts=\n\n   IN buildout.cfg\n   SET VALUE =\n\nparts-directory= parts\n\n   AS DEFAULT_VALUE\n   SET VALUE = parts\n\nprefer-final= true\n\n   AS DEFAULT_VALUE\n   SET VALUE = true\n\npython= buildout\n\n   AS DEFAULT_VALUE\n   SET VALUE = buildout\n\nshow-picked-versions= false\n\n   AS DEFAULT_VALUE\n   SET VALUE = false\n\nsocket-timeout=\n\n   AS DEFAULT_VALUE\n   SET VALUE =\n\nupdate-versions-file=\n\n   AS DEFAULT_VALUE\n   SET VALUE =\n\nuse-dependency-links= true\n\n   AS DEFAULT_VALUE\n   SET VALUE = true\n\nverbosity= 10\n\n   AS COMMAND_LINE_VALUE\n   SET VALUE = 10\n\nversions= versions\n\n   AS DEFAULT_VALUE\n   SET VALUE = versions\n\n\n[versions]\n...', N)
    assert_output(system([buildout, 'annotate', 'versions']), '\nAnnotated sections\n==================\n\n[versions]\nzc.buildout= >=1.99\n    DEFAULT_VALUE\nzc.recipe.egg= >=1.99\n    DEFAULT_VALUE\n', N)
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
    assert_output(system([buildout, 'query', 'values:multiline']), 'first\nsecond', N)
    assert_output(system([buildout, 'query', 'develop']), '.', N)
    assert_output(system([buildout, '-v', 'query', 'develop']), '${buildout:develop}\n.', N)
    assert_output(system([buildout, '-v', 'query', 'values:host']), '${values:host}\nbuildout.org', N)
    assert_output(system([buildout, 'query', 'versions', 'parts']), 'Error: The query command requires a single argument.', N)
    assert_output(system([buildout, 'query']), 'Error: The query command requires a single argument.', N)
    assert_output(system([buildout, 'query', 'invalid:section:key']), 'Error: Invalid option: invalid:section:key', N)
    assert_output(system([buildout, '-v', 'query', 'values:port']), '${values:port}\nError: Key not found: port', N)
    assert_output(system([buildout, '-v', 'query', 'versionx']), '${buildout:versionx}\nError: Key not found: versionx', N)
    assert_output(system([buildout, '-v', 'query', 'specific:port']), '${specific:port}\nError: Section not found: specific', N)
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
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nInstalling data-dir.\ndata-dir: Creating directory mydata\nInstalling debug.\nFile-1 /sample-buildout/mydata/file\nFile-2 /sample-buildout/mydata/file/log\nrecipe recipes:debug", N)
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUpdating data-dir.\nUpdating debug.\nFile-1 /sample-buildout/mydata/file\nFile-2 /sample-buildout/mydata/file/log\nrecipe recipes:debug", N)
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
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUninstalling debug.\nUpdating data-dir.\nInstalling debug.\nFile-1 /sample-buildout/mydata/file\nFile-2 /sample-buildout/mydata/file/log\nmy_name debug\nrecipe recipes:debug", N)
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
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUninstalling debug.\nUpdating data-dir.\nInstalling debug.\nFile-1 /sample-buildout/mydata/file\nFile-2 /sample-buildout/mydata/file/log\nrecipe recipes:debug", N)
    assert_output(capture_print(cat, '.installed.cfg'), '[buildout]\ninstalled_develop_eggs = /sample-buildout/develop-eggs/recipes.egg-link\nparts = data-dir debug\n...', N)
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
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUpdating data-dir.\nUpdating debug.\nFile-1 /sample-buildout/mydata/file\nFile-2 /sample-buildout/mydata/file/log\nrecipe recipes:debug", N)
    assert_output(capture_print(cat, '.installed.cfg'), '[buildout]\ninstalled_develop_eggs = /sample-buildout/develop-eggs/recipes.egg-link\nparts = data-dir debug\n...', N)
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
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUninstalling debug.\nUninstalling data-dir.\nInstalling myfiles.\ncolor blue\nfile1 mydata/file1\nfile2 mydata/file2\npath mydata\nrecipe recipes:debug", N)
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
    assert_output(system(os.path.join('bin', 'buildout')), "['a1/na2', 'a2/nc3 c4', 'c3 c4/nd2/nc5 d1 d6']\nDevelop: '/sample-buildout/demo'", N)
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
    assert_output(system(os.path.join('bin', 'buildout')), "['a1 a2/na3 a4/na5', 'b1 b2 b3 b4', 'c1 c2/nc3 c4 c5', 'd2/nd3/nd1/nd4', 'h1 h2', 'e1', '']\nDevelop: '/sample-buildout/demo'", N)
    assert_output(system(os.path.join('bin', 'buildout') + ' annotate'), '\nAnnotated sections\n==================\n...\n\n[part1]\noption= a1 a2\na3 a4\na5\n    base.cfg\n+=  extension1.cfg\n+=  extension2.cfg\nrecipe=\n    base.cfg\n\n[part2]\noption= b1 b2 b3 b4\n    base.cfg\n-=  extension1.cfg\n-=  extension2.cfg\nrecipe=\n    base.cfg\n\n[part3]\noption= c1 c2\nc3 c4 c5\n    base.cfg\n+=  extension1.cfg\nrecipe=\n    base.cfg\n\n[part4]\noption= d2\nd3\nd1\nd4\n    base.cfg\n+=  extension1.cfg\n-=  extension1.cfg\nrecipe=\n    base.cfg\n\n[part5]\noption= h1 h2\n    extension1.cfg\n\n[part6]\noption= e1\n    base.cfg\n\n[part7]\noption=\n    base.cfg\n-=  IMPLICIT_VALUE\n\n[versions]\nzc.buildout= >=1.99\n    DEFAULT_VALUE\nzc.recipe.egg= >=1.99\n    DEFAULT_VALUE\n', N)
    assert_output(system(os.path.join('bin', 'buildout') + ' -v annotate'), '\nAnnotated sections\n==================\n...\n[part1]\noption= a1 a2\na3 a4\na5\n\n   IN extension2.cfg\n   ADD VALUE = a5\n   IN extension1.cfg\n   ADD VALUE = a3 a4\n   IN base.cfg\n   SET VALUE = a1 a2\n\n...\n[part2]\noption= b1 b2 b3 b4\n\n   IN extension2.cfg\n   REMOVE VALUE = b1 b2 b3\n   IN extension1.cfg\n   REMOVE VALUE = b1 b2\n   IN base.cfg\n   SET VALUE = b1 b2 b3 b4\n\n...\n[part3]\noption=\n   c1 c2\n   c3 c4 c5\n\n   IN extension1.cfg\n   ADD VALUE = c3 c4 c5\n   IN base.cfg\n   SET VALUE = c1 c2\n\n...\n[part4]\noption=\n   d2\n   d3\n   d1\n   d4\n\n   IN extension1.cfg\n   REMOVE VALUE = d5\n   IN extension1.cfg\n   ADD VALUE =\n      d1\n      d4\n   IN base.cfg\n   SET VALUE =\n      d2\n      d3\n      d5\n\n...\n[part5]\noption= h1 h2\n\n   IN extension1.cfg\n   SET VALUE = h1 h2\n\n[part6]\noption= e1\n\n   IN base.cfg\n   SET VALUE = e1\n\n\n[part7]\noption=\n\n   IN IMPLICIT_VALUE\n   REMOVE VALUE = f1\n   IN base.cfg\n   SET VALUE = f1\n\n\n\n...', N)
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
    assert_output(system(os.path.join('bin', 'buildout')), "['a/nb/nc/nd/ne']\nDevelop: '/sample-buildout/demo'", N)
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
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nInstalling debug.\nop buildout\nrecipe recipes:debug", N)
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
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUninstalling debug.\nInstalling debug.\nname base\nop buildout\nop1 b1 1\nop2 b2 2\nop3 b2 3\nop4 b3 4\nop5 b3base 5\nrecipe recipes:debug", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    extends = b1.cfg
    
    [debug]
    op = buildout
    """)
    assert_output(system([buildout, 'buildout:extends=b2.cfg']), "Develop: '/sample-buildout/recipes'\nUninstalling debug.\nInstalling debug.\nname base\nop buildout\nop1 b1 1\nop2 b2 2\nop3 b2 3\nrecipe recipes:debug", N)
    assert_output(system([buildout, 'buildout:extends=b2.cfg %(b3)s' % dict(b3=os.path.join(other, 'b3.cfg'))]), "Develop: '/sample-buildout/recipes'\nUninstalling debug.\nInstalling debug.\nname base\nop buildout\nop1 b1 1\nop2 b2 2\nop3 b2 3\nop4 b3 4\nop5 b3base 5\nrecipe recipes:debug", N)
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
    assert_output(system(buildout), "optional-extends file not found: optional.cfg\nDevelop: '/sample-buildout/recipes'\nUninstalling debug.\nInstalling debug.\nname base\nop buildout\nop1 b1 1\nop2 b1 2\nrecipe recipes:debug", N)
    write('optional.cfg', """
    [debug]
    op2 = optional2 2
    """)
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUninstalling debug.\nInstalling debug.\nname base\nop buildout\nop1 b1 1\nop2 optional2 2\nrecipe recipes:debug", N)
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
    assert_output(system([buildout, '-c', 'client.cfg']), "Develop: '/sample-buildout/recipes'\nUninstalling debug.\nInstalling debug.\nname base\nop1 r1 1\nop2 r2 2\nop3 r2 3\nrecipe recipes:debug", N)
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
    assert_output(system([buildout, '-c', server_url + '/remote.cfg']), 'While:\n  Initializing.\nError: Missing option: buildout:directory', N)
    assert_output(system([buildout, '-c', server_url + '/remote.cfg', 'buildout:directory=' + sample_buildout]), "Develop: '/sample-buildout/recipes'\nUninstalling debug.\nInstalling debug.\nname remote\nop1 r1 1\nop2 r2 2\nop3 r2 3\nrecipe recipes:debug", N)
    home = tmpdir('home')
    mkdir(home, '.buildout')
    default_cfg = join(home, '.buildout', 'default.cfg')
    write(default_cfg, """
    [debug]
    op1 = 1
    op7 = 7
    """)
    env = dict(HOME=home, USERPROFILE=home)
    assert_output(system(buildout, env=env), "Develop: '/sample-buildout/recipes'\nUninstalling debug.\nInstalling debug.\nname base\nop buildout\nop1 b1 1\nop2 b2 2\nop3 b2 3\nop4 b3 4\nop5 b3base 5\nop7 7\nrecipe recipes:debug", N)
    assert_output(system([buildout, '-U'], env=env), "Develop: '/sample-buildout/recipes'\nUninstalling debug.\nInstalling debug.\nname base\nop buildout\nop1 b1 1\nop2 b2 2\nop3 b2 3\nop4 b3 4\nop5 b3base 5\nrecipe recipes:debug", N)
    alterhome = tmpdir('alterhome')
    write(alterhome, 'default.cfg',
    """
    [debug]
    op1 = 1'
    op7 = 7'
    op8 = eight!
    """)
    env['BUILDOUT_HOME'] = alterhome
    assert_output(system(buildout, env=env), "Develop: '/sample-buildout/recipes'\nUninstalling debug.\nInstalling debug.\nname base\nop buildout\nop1 b1 1\nop2 b2 2\nop3 b2 3\nop4 b3 4\nop5 b3base 5\nop7 7'\nop8 eight!\nrecipe recipes:debug", N)
    assert_output(system([buildout, '-U'], env=env), "Develop: '/sample-buildout/recipes'\nUninstalling debug.\nInstalling debug.\nname base\nop buildout\nop1 b1 1\nop2 b2 2\nop3 b2 3\nop4 b3 4\nop5 b3base 5\nrecipe recipes:debug", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    log-level = WARNING
    extends = b1.cfg b2.cfg
    """)
    assert_output(system(buildout), 'name base\nop1 b1 1\nop2 b2 2\nop3 b2 3\nrecipe recipes:debug', N)
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
    assert_output(system(buildout), "Setting socket time out to 5 seconds.\nDevelop: '/sample-buildout/recipes'\nInstalling debug.\nop timeout\nrecipe recipes:debug", N)
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
    assert_output(system(buildout), "Default socket timeout is used !\nValue in configuration is not numeric: [5s].\n\nDevelop: '/sample-buildout/recipes'\nUpdating debug.\nop timeout\nrecipe recipes:debug", N)
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
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUninstalling debug.\nInstalling service.\nchkconfig --add /path/to/script", N)
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUpdating service.", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = service
    
    [service]
    recipe = recipes:service
    script = /path/to/a/different/script
    """)
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUninstalling service.\nRunning uninstall recipe.\nchkconfig --del /path/to/script\nInstalling service.\nchkconfig --add /path/to/a/different/script", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = debug
    
    [debug]
    recipe = recipes:debug
    """)
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUninstalling service.\nRunning uninstall recipe.\nchkconfig --del /path/to/a/different/script\nInstalling debug.\nrecipe recipes:debug", N)
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
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUninstalling debug.\nInstalling dir.\ndir: Creating directory my_directory\nInstalling debug.\nrecipe recipes:debug", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = debug
    
    [debug]
    recipe = recipes:debug
    """)
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUninstalling dir.\nRunning uninstall recipe.\nbacking up directory /sample-buildout/my_directory of size 0\nUpdating debug.\nrecipe recipes:debug", N)
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
    assert_output(system([buildout, '-c', 'other.cfg', 'debug:op1=foo', '-v']), "Develop: '/sample-buildout/recipes'\nInstalling debug.\nname other\nop1 foo\nrecipe recipes:debug", N)
    assert_output(system([buildout, '-vcother.cfg', 'debug:op1=foo']), "Develop: '/sample-buildout/recipes'\nUpdating debug.\nname other\nop1 foo\nrecipe recipes:debug", N)
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
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUninstalling debug.\nInstalling debug.\nrecipe recipes:debug\nInstalling d1.\nd1: Creating directory d1\nInstalling d2.\nd2: Creating directory d2\nInstalling d3.\nd3: Creating directory d3", N)
    assert_output(capture_print(ls, sample_buildout), '-  .installed.cfg\nd  bin\n-  buildout.cfg\nd  d1\nd  d2\nd  d3\nd  develop-eggs\nd  eggs\nd  parts\nd  recipes', N)
    assert_output(capture_print(cat, sample_buildout, '.installed.cfg'), '[buildout]\ninstalled_develop_eggs = /sample-buildout/develop-eggs/recipes.egg-link\nparts = debug d1 d2 d3\n\n[debug]\n__buildout_installed__ =\n__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==\nrecipe = recipes:debug\n\n[d1]\n__buildout_installed__ = /sample-buildout/d1\n__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==\npath = /sample-buildout/d1\nrecipe = recipes:mkdir\n\n[d2]\n__buildout_installed__ = /sample-buildout/d2\n__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==\npath = /sample-buildout/d2\nrecipe = recipes:mkdir\n\n[d3]\n__buildout_installed__ = /sample-buildout/d3\n__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==\npath = /sample-buildout/d3\nrecipe = recipes:mkdir', N)
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
    assert_output(system([buildout, 'install', 'd3', 'd4']), "Develop: '/sample-buildout/recipes'\nUninstalling d3.\nInstalling d3.\nd3: Creating directory data3\nInstalling d4.\nd4: Creating directory data2-extra", N)
    assert_output(capture_print(ls, sample_buildout), '-  .installed.cfg\nd  bin\n-  buildout.cfg\nd  d1\nd  d2\nd  data2-extra\nd  data3\nd  develop-eggs\nd  eggs\nd  parts\nd  recipes', N)
    assert_output(capture_print(cat, sample_buildout, '.installed.cfg'), '[buildout]\ninstalled_develop_eggs = /sample-buildout/develop-eggs/recipes.egg-link\nparts = debug d1 d2 d3 d4\n\n[debug]\n__buildout_installed__ =\n__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==\nrecipe = recipes:debug\n\n[d1]\n__buildout_installed__ = /sample-buildout/d1\n__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==\npath = /sample-buildout/d1\nrecipe = recipes:mkdir\n\n[d2]\n__buildout_installed__ = /sample-buildout/d2\n__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==\npath = /sample-buildout/d2\nrecipe = recipes:mkdir\n\n[d3]\n__buildout_installed__ = /sample-buildout/data3\n__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==\npath = /sample-buildout/data3\nrecipe = recipes:mkdir\n\n[d4]\n__buildout_installed__ = /sample-buildout/data2-extra\n__buildout_signature__ = recipes-PiIFiO8ny5yNZ1S3JfT0xg==\npath = /sample-buildout/data2-extra\nrecipe = recipes:mkdir', N)
    assert_output(system(buildout), "Develop: '/sample-buildout/recipes'\nUninstalling d2.\nUninstalling d1.\nUninstalling debug.\nInstalling debug.\nrecipe recipes:debug\nx 1\nInstalling d2.\nd2: Creating directory data2\nUpdating d3.\nUpdating d4.", N)
    assert_output(capture_print(ls, sample_buildout), '-  .installed.cfg\nd  bin\n-  buildout.cfg\nd  data2\nd  data2-extra\nd  data3\nd  develop-eggs\nd  eggs\nd  parts\nd  recipes', N)
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
    assert_output(system(buildout), "Creating directory '/sample-alt/basket/v2'.\nCreating directory '/sample-alt/scripts'.\nCreating directory '/sample-alt/work'.\nCreating directory '/sample-alt/developbasket'.\nDevelop: '/sample-buildout/recipes'\nUninstalling d4.\nUninstalling d3.\nUninstalling d2.\nUninstalling debug.", N)
    assert_output(capture_print(ls, alt), 'd  basket\nd  developbasket\nd  scripts\nd  work', N)
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
    assert_output(system(buildout), "Creating directory '/sample-alt/eggs/v5'.\nCreating directory '/sample-alt/bin'.\nCreating directory '/sample-alt/parts'.\nCreating directory '/sample-alt/develop-eggs'.\nDevelop: '/sample-buildout/recipes'", N)
    assert_output(capture_print(ls, alt), '-  .installed.cfg\nd  bin\nd  develop-eggs\nd  eggs\nd  parts', N)
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
    assert_output(system([buildout, '-vv']), "Installing 'zc.buildout', 'wheel', 'pip', 'setuptools'.\n...\nConfiguration data:\n[buildout]\nallow-hosts = *\nallow-picked-versions = true\nallow-unknown-extras = false\nbin-directory = /sample-buildout/bin\ndevelop-eggs-directory = /sample-buildout/develop-eggs\ndirectory = /sample-buildout\neggs-directory = /sample-buildout/eggs/v5\neggs-directory-version = v5\nexecutable = python\nfind-links =\ninstall-from-cache = false\ninstalled = /sample-buildout/.installed.cfg\nlog-format =\nlog-level = INFO\nnewest = true\noffline = false\nparts =\nparts-directory = /sample-buildout/parts\nprefer-final = true\npython = buildout\nshow-picked-versions = false\nsocket-timeout =\nupdate-versions-file =\nuse-dependency-links = true\nverbosity = 20\nversions = versions\n[versions]\nzc.buildout = >=1.99\nzc.recipe.egg = >=1.99\n", N)

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
    assert_output(system([buildout, '-c' + os.path.join(sample_bootstrapped, 'setup.cfg'), 'init']), "Creating '/sample-bootstrapped/setup.cfg'.\nCreating directory '/sample-bootstrapped/eggs/v5'.\nCreating directory '/sample-bootstrapped/bin'.\nCreating directory '/sample-bootstrapped/parts'.\nCreating directory '/sample-bootstrapped/develop-eggs'.\nGenerated script '/sample-bootstrapped/bin/buildout'.", N)
    assert_output(capture_print(cat, sample_bootstrapped, 'setup.cfg'), '[buildout]\nparts =', N)
    assert_output(capture_print(ls, sample_bootstrapped), 'd  bin\nd  develop-eggs\nd  eggs\nd  parts\n-  setup.cfg', N)
    assert_output(capture_print(ls, sample_bootstrapped, 'bin'), '-  buildout', N)
    _ = (ls(sample_bootstrapped, 'eggs', 'v5'),
         ls(sample_bootstrapped, 'develop-eggs'))
    # TODO assert: '-  packaging.egg-link\n-  pip.egg-link\n-  setuptools.egg-link'
    sample_bootstrapped2 = tmpdir('sample-bootstrapped2')
    assert_output(system([buildout, '-c' + os.path.join(sample_bootstrapped2, 'setup.cfg'), 'bootstrap']), "While:\n  Initializing.\nError: Couldn't open /sample-bootstrapped2/setup.cfg", N)
    write(sample_bootstrapped2, 'setup.cfg',
    """
    [buildout]
    parts =
    """)
    assert_output(system([buildout, '-c' + os.path.join(sample_bootstrapped2, 'setup.cfg'), 'bootstrap']), "Creating directory '/sample-bootstrapped2/eggs/v5'.\nCreating directory '/sample-bootstrapped2/bin'.\nCreating directory '/sample-bootstrapped2/parts'.\nCreating directory '/sample-bootstrapped2/develop-eggs'.\nGenerated script '/sample-bootstrapped2/bin/buildout'.", N)
    assert_output(system([buildout, '-c' + os.path.join(sample_bootstrapped, 'setup.cfg'), 'init']), "While:\n  Initializing.\nError: '/sample-bootstrapped/setup.cfg' already exists.", N)
    cd(sample_bootstrapped)
    remove('setup.cfg')
    assert_output(system([buildout, '-csetup.cfg', 'init', 'demo', 'other', './src']), "Creating '/sample-bootstrapped/setup.cfg'.\nCreating directory '/sample-bootstrapped/develop-eggs'.\nGetting distribution for 'zc.recipe.egg>=2.0.6'.\nGot zc.recipe.egg\nInstalling py.\nGetting distribution for 'demo'.\nGot demo 0.3.\nGetting distribution for 'other'.\nGot other 1.0.\nGetting distribution for 'demoneeded'.\nGot demoneeded 1.1.\nGenerated script '/sample-bootstrapped/bin/demo'.\nGenerated interpreter '/sample-bootstrapped/bin/py'.", N)
    assert_output(capture_print(cat, 'setup.cfg'), '[buildout]\nparts = py\n\n[py]\nrecipe = zc.recipe.egg\ninterpreter = py\neggs =\n  demo\n  other\nextra-paths =\n  ./src', N)
    assert_output(capture_print(ls, '.'), '-  .installed.cfg\nd  bin\nd  develop-eggs\nd  eggs\nd  parts\n-  setup.cfg\nd  src', N)
    uncd()
    cd(sample_bootstrapped)
    _ = system([buildout, '-csetup.cfg', 'buildout:parts='])
    remove('setup.cfg')
    assert_output(system([buildout, '-csetup.cfg', 'init', 'demo', 'other', './src']), "Creating '/sample-bootstrapped/setup.cfg'.\nCreating directory '/sample-bootstrapped/develop-eggs'.\nInstalling py.\nGenerated script '/sample-bootstrapped/bin/demo'.\nGenerated interpreter '/sample-bootstrapped/bin/py'.", N)
    _ = system([buildout, '-csetup.cfg', 'buildout:parts='])
    uncd()
    write('buildout.cfg', """
    [buildout]
    develop = recipes
    parts = debug
    
    [debug]
    recipe = recipes:debug
    """)
    assert_output(system([buildout, 'buildout:installed=inst.cfg']), "Develop: '/sample-buildout/recipes'\nInstalling debug.\nrecipe recipes:debug", N)
    assert_output(capture_print(ls, sample_buildout), 'd  bin\n-  buildout.cfg\nd  develop-eggs\nd  eggs\n-  inst.cfg\nd  parts\nd  recipes', N)
    os.remove('inst.cfg')
    assert_output(system([buildout, 'buildout:installed=']), "Develop: '/sample-buildout/recipes'\nInstalling debug.\nrecipe recipes:debug", N)
    assert_output(capture_print(ls, sample_buildout), 'd  bin\n-  buildout.cfg\nd  develop-eggs\nd  eggs\nd  parts\nd  recipes', N)
    write('buildout.cfg', """
    [buildout]
    parts =
    """)
    print_(system([buildout, 'buildout:installed=inst.cfg']), end='')
    assert_output(capture_print(ls, sample_buildout), 'd  bin\n-  buildout.cfg\nd  develop-eggs\nd  eggs\nd  parts\nd  recipes', N)

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
    assert_output(system(os.path.join(sample_buildout, 'bin', 'buildout')), "ext ['buildout', 'versions']\nDevelop: '/sample-buildout/demo'\nunload ['buildout', 'versions']", N)
