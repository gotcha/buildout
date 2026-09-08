"""Pytest port of runsetup.txt, repeatable.txt, setup.txt, debugging.txt, windows.txt — no DocTestRunner."""
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
    NORMALIZERS_BUILDOUT,
)

N = NORMALIZERS_BUILDOUT


def test_runsetup(buildout_env):
    buildout = buildout_env['buildout']
    ls = buildout_env['ls']
    mkdir = buildout_env['mkdir']
    print_ = buildout_env['print_']
    system = buildout_env['system']
    write = buildout_env['write']

    mkdir('hello')
    write('hello', 'hello.py',
         'import sys; sys.stdout.write("Hello World!\\n")\n')
    write('hello', 'README', 'This is hello')
    write('hello', 'setup.py',
    """
    from distutils.core import setup
    setup(name="hello",
          version="1.0",
          py_modules=["hello"],
          author="Bob",
          author_email="bob@foo.com",
          )
    """)
    assert_output(system(buildout + ' setup hello -q bdist_egg'), "Running setup script 'hello/setup.py'.\nzip_safe flag not set; analyzing archive contents...", N)
    assert_output(capture_print(ls, 'hello', 'dist'), '-  hello-1.0-py2.4.egg', N)

def test_repeatable(buildout_env):
    buildout = buildout_env['buildout']
    join = buildout_env['join']
    mkdir = buildout_env['mkdir']
    print_ = buildout_env['print_']
    rmdir = buildout_env['rmdir']
    sample_buildout = buildout_env['sample_buildout']
    system = buildout_env['system']
    write = buildout_env['write']

    mkdir('recipe')
    write('recipe', 'recipe.py',
    '''
    import sys
    print_ = lambda *a: sys.stdout.write(' '.join(map(str, a))+'\\n')
    class Recipe:
        def __init__(*a): pass
        def install(self):
            print_('recipe v1')
            return ()
        update = install
    ''')
    write('recipe', 'setup.py',
    '''
    from setuptools import setup
    setup(name='spam', version='1', py_modules=['recipe'],
          entry_points={'zc.buildout': ['default = recipe:Recipe']},
          )
    ''')
    write('recipe', 'README', '')
    assert_output(system(buildout + ' setup recipe bdist_egg'), "Running setup script 'recipe/setup.py'.\n...", N)
    rmdir('recipe', 'build')
    write('recipe', 'recipe.py',
    '''
    import sys
    print_ = lambda *a: sys.stdout.write(' '.join(map(str, a))+'\\n')
    class Recipe:
        def __init__(*a): pass
        def install(self):
            print_('recipe v2')
            return ()
        update = install
    ''')
    write('recipe', 'setup.py',
    '''
    from setuptools import setup
    setup(name='spam', version='2', py_modules=['recipe'],
          entry_points={'zc.buildout': ['default = recipe:Recipe']},
          )
    ''')
    assert_output(system(buildout + ' setup recipe bdist_egg'), "Running setup script 'recipe/setup.py'.\n...", N)
    write('buildout.cfg',
    '''
    [buildout]
    parts = foo
    find-links = %s
    
    [foo]
    recipe = spam
    ''' % join('recipe', 'dist'))
    assert_output(system(buildout), "Getting distribution for 'spam'.\nGot spam 2.\nInstalling foo.\nrecipe v2", N)
    write('buildout.cfg',
    '''
    [buildout]
    parts = foo
    find-links = %s
    
    [versions]
    spam = 1
    eggs = 2.2
    
    [foo]
    recipe = spam
    ''' % join('recipe', 'dist'))
    assert_output(system(buildout), "Getting distribution for 'spam==1'.\nGot spam 1.\nUninstalling foo.\nInstalling foo.\nrecipe v1", N)
    assert_output(system(buildout + ' buildout:versions= -v'), "Installing 'zc.buildout', 'wheel', 'pip', 'setuptools'.\n...\nInstalling 'spam'.\nWe have the best distribution that satisfies 'spam'.\nPicked: spam = 2.\nUninstalling foo.\nInstalling foo.\nrecipe v2", N)
    assert_output(system(buildout + ' -v'), "Installing 'zc.buildout', 'wheel', 'pip', 'setuptools'.\n...\nInstalling 'spam'.\nWe have the distribution that satisfies 'spam==1'.\nUninstalling foo.\nInstalling foo.\nrecipe v1", N)
    write('buildout.cfg',
    '''
    [buildout]
    parts = foo
    find-links = %s
    
    [versions]
    spam = 1
    eggs = 2.2
    
    [foo]
    recipe = spam >0
    ''' % join('recipe', 'dist'))
    assert_output(system(buildout + ' -v'), "Installing 'zc.buildout', 'wheel', 'pip', 'setuptools'.\n...\nInstalling 'spam >0'.\nWe have the distribution that satisfies 'spam==1'.\nUninstalling foo.\nInstalling foo.\nrecipe v1", N)
    write('buildout.cfg',
    '''
    [buildout]
    allow-picked-versions = false
    #show-picked-versions = true
    parts = foo
    find-links = %s
    test = ${foo:option}
    
    [versions]
    spam = 1
    
    [foo]
    recipe = spam
    option = TEST
    ''' % join('recipe', 'dist'))
    assert_output(system(buildout), "Uninstalling foo.\nSection `buildout` contains unused option(s): 'test'.\n...\nInstalling foo.\nrecipe v1", N)
    write('buildout.cfg',
    '''
    [buildout]
    parts = foo
    find-links = %s
    allow-picked-versions = false
    
    [versions]
    eggs = 2.2
    
    [foo]
    recipe = spam
    ''' % join('recipe', 'dist'))
    assert_output(system(buildout), "While:\n  Installing.\n  Getting section foo.\n  Initializing section foo.\n  Installing recipe spam.\n  Getting distribution for 'spam'.\nError: Picked: spam = 2\n...", N)
    write('buildout.cfg',
    '''
    [buildout]
    parts = foo
    find-links = %s
    versions = release1
    
    [release1]
    spam = 1
    eggs = 2.2
    
    [foo]
    recipe = spam
    ''' % join('recipe', 'dist'))
    assert_output(system(buildout), 'Uninstalling foo.\nInstalling foo.\nrecipe v1', N)
    write('buildout.cfg',
    '''
    [buildout]
    parts = foo
    find-links = %s
    versions =
    
    [versions]
    spam = 1
    eggs = 2.2
    
    [foo]
    recipe = spam
    ''' % join('recipe', 'dist'))
    assert_output(system(buildout), 'Uninstalling foo.\nInstalling foo.\nrecipe v2', N)
    import pkg_resources
    req = pkg_resources.Requirement.parse('setuptools')
    setuptools_version = pkg_resources.working_set.find(req).version
    req = pkg_resources.Requirement.parse('pip')
    pip_version = pkg_resources.working_set.find(req).version
    write('buildout.cfg',
    '''
    [buildout]
    parts = foo
    find-links = %s
    show-picked-versions = true
    
    [versions]
    
    [foo]
    recipe = spam
    ''' % join('recipe', 'dist'))
    assert_output(system(buildout), 'Updating foo.\nrecipe v2\nVersions had to be automatically picked.\nThe following part definition lists the versions picked:\n[versions]\nspam = 2', N)
    write('buildout.cfg',
    '''
    [buildout]
    parts = foo
    find-links = %s
    show-picked-versions = true
    
    [versions]
    pip = %s
    setuptools = %s
    spam = 2
    
    [foo]
    recipe = spam
    ''' % (join('recipe', 'dist'), pip_version, setuptools_version))
    assert_output(system(buildout), 'Updating foo.\nrecipe v2', N)
    write('buildout.cfg',
    '''
    [buildout]
    parts = foo
    find-links = %s
    show-picked-versions = true
    
    [versions]
    pip = %s
    setuptools = %s
    Spam = 2
    
    [foo]
    recipe = spam
    ''' % (join('recipe', 'dist'), pip_version, setuptools_version))
    assert_output(system(buildout), 'Updating foo.\nrecipe v2', N)
    write('my_versions.cfg',
    '''
    [versions]
    pip = %s
    setuptools = %s
    spam = 2
    ''' % (pip_version, setuptools_version))
    write('buildout.cfg',
    '''
    [buildout]
    parts = foo
    extends = my_versions.cfg
    find-links = %s
    show-picked-versions = true
    
    [foo]
    recipe = spam
    ''' % join('recipe', 'dist'))
    assert_output(system(buildout), 'Updating foo.\nrecipe v2', N)
    write('my_versions.cfg',
    '''
    [versions]
    pip = %s
    setuptools = %s
    ''' % (pip_version, setuptools_version))
    write('buildout.cfg',
    '''
    [buildout]
    parts = foo
    extends = my_versions.cfg
    update-versions-file = my_versions.cfg
    find-links = %s
    show-picked-versions = true
    
    [foo]
    recipe = spam
    ''' % join('recipe', 'dist'))
    assert_output(system(buildout), 'Updating foo.\nrecipe v2\nVersions had to be automatically picked.\nThe following part definition lists the versions picked:\n[versions]\nspam = 2\nPicked versions have been written to my_versions.cfg', N)
    with open('my_versions.cfg') as f: print_(f.read())
    # TODO assert: '\n...\n# Added by buildout at YYYY-MM-DD hh:mm:ss.dddddd\nspam '
    _val = ('picked' in system(buildout))
    assert repr(_val) == 'False' or str(_val) == 'False'
    write('my_versions.cfg',
    '''
    [versions]
    pip = %s
    setuptools = %s
    ''' % (pip_version, setuptools_version))
    write('buildout.cfg',
    '''
    [buildout]
    parts = foo
    extends = my_versions.cfg
    update-versions-file = my_versions.cfg
    find-links = %s
    show-picked-versions = false
    
    [foo]
    recipe = spam
    ''' % join('recipe', 'dist'))
    assert_output(system(buildout), 'Updating foo.\nrecipe v2\nPicked versions have been written to my_versions.cfg', N)
    with open('my_versions.cfg') as f: print_(f.read())
    # TODO assert: '\n[versions]\n...\n\n# Added by buildout at YYYY-MM-DD hh:mm:ss.'
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    parts = foo
    extensions = buildout-versions
    
    [foo]
    recipe = spam
    """)
    assert_output(system(buildout), "While:\n  Installing.\n  Loading extensions.\n  Error: Buildout now includes 'buildout-versions'\n  (and part of the older 'buildout.dumppickedversions').\n  Remove the extension from your configuration and look at the\n  'show-picked-versions' option in buildout's documentation.", N)

def test_setup(buildout_env):
    buildout = buildout_env['buildout']
    cd = buildout_env['cd']
    ls = buildout_env['ls']
    mkdir = buildout_env['mkdir']
    print_ = buildout_env['print_']
    system = buildout_env['system']
    write = buildout_env['write']

    mkdir('test')
    cd('test')
    write('setup.py',
    '''
    from distutils.core import setup
    setup(name='sample')
    ''')
    assert_output(system(buildout + ' setup'), "Creating directory '/sample-buildout/test/eggs/v5'.\nError: The setup command requires the path to a setup script or\ndirectory containing a setup script, and its arguments.", N)
    assert_output(system(buildout + ' setup setup.py bdist_egg'), "Running setup script 'setup.py'.\n...", N)
    assert_output(capture_print(ls, 'dist'), '-  sample-0.0.0-py2.5.egg', N)
    assert_output(system(buildout + ' setup . bdist_egg'), "Running setup script './setup.py'.\n...", N)

def test_debugging(buildout_env):
    buildout = buildout_env['buildout']
    mkdir = buildout_env['mkdir']
    print_ = buildout_env['print_']
    sample_buildout = buildout_env['sample_buildout']
    system = buildout_env['system']
    write = buildout_env['write']

    mkdir(sample_buildout, 'recipes')
    write(sample_buildout, 'recipes', 'mkdir.py',
    """
    import os, zc.buildout
    
    class Mkdir:
    
        def __init__(self, buildout, name, options):
            self.name, self.options = name, options
            options['path'] = os.path.join(
                                  buildout['buildout']['directory'],
                                  options['path'],
                                  )
    
        def install(self):
            directory = self.options['directory']
            os.mkdir(directory)
            return directory
    
        def update(self):
            pass
    """)
    write(sample_buildout, 'recipes', 'setup.py',
    """
    from setuptools import setup
    
    setup(name = "recipes",
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
    assert_output(system(buildout, with_exit_code=True), "Develop: '/sample-buildout/recipes'\nInstalling data-dir.\nWhile:\n  Installing data-dir.\nError: Missing option: data-dir:directory\nEXIT CODE: 1", N)
    assert_output(system(buildout + ' -D', 'up\np sorted(self.options.keys())\nq\n', with_exit_code=True), 'Develop: \'/sample-buildout/recipes\'\nInstalling data-dir.\n> /zc/buildout/buildout.py(925)__getitem__()\n-> raise MissingOption("Missing option: %s:%s" % (self.name, key))\n(Pdb) > /sample-buildout/recipes/mkdir.py(14)install()\n-> directory = self.options[\'directory\']\n(Pdb) [\'path\', \'recipe\']\n...While:\n  Installing data-dir.\nTraceback (most recent call last):\n  File "/zc/buildout/buildout.py", line 1352, in main\n...\n  File "/zc/buildout/buildout.py", line 925, in __getitem__\n    raise MissingOption("Missing option: %s:%s" % (self.name, key))\nMissingOption: Missing option: data-dir:directory\n\nStarting pdb:\nEXIT CODE: 1', N)

def test_windows(buildout_env):
    buildout = buildout_env['buildout']
    join = buildout_env['join']
    mkdir = buildout_env['mkdir']
    print_ = buildout_env['print_']
    system = buildout_env['system']
    write = buildout_env['write']

    mkdir('recipe')
    write('recipe', 'recipe.py',
    '''
    import os
    import sys
    print_ = lambda *a: sys.stdout.write(' '.join(map(str, a))+'\\n')
    class Recipe:
        def __init__(self, buildout, name, options):
            self.location = os.path.join(
                 buildout['buildout']['parts-directory'],
                 name)
    
        def install(self):
            print_("can't remove read only files")
            if not os.path.exists (self.location):
                os.makedirs (self.location)
    
            name = os.path.join (self.location, 'readonly.txt')
            with open (name, 'w') as f: f.write ('this is a read only file')
            os.chmod(name, 256)
            return ()
    
        update = install
    ''')
    write('recipe', 'setup.py',
    '''
    from setuptools import setup
    setup(name='spam', version='1', py_modules=['recipe'],
          entry_points={'zc.buildout': ['default = recipe:Recipe']},
          )
    ''')
    write('recipe', 'README', '')
    assert_output(system(buildout + ' setup recipe bdist_egg'), "Running setup script 'recipe/setup.py'.\n...", N)
    write('buildout.cfg',
    '''
    [buildout]
    parts = foo
    find-links = %s
    
    [foo]
    recipe = spam
    ''' % join('recipe', 'dist'))
    assert_output(system(buildout), "Getting distribution for 'spam'.\nGot spam 1.\nInstalling foo.\ncan't remove read only files", N)
