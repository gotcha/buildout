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

    # Running setup scripts
    # =====================
    #
    # Buildouts are often used to work on packages that will be distributed
    # as eggs. During development, we use develop eggs.  When you've
    # completed a development cycle, you'll need to run your setup script to
    # generate a distribution and, perhaps, uploaded it to the Python
    # package index.  If your script uses setuptools, you'll need setuptools
    # in your Python path, which may be an issue if you haven't installed
    # setuptools into your Python installation.
    #
    # The buildout setup command is helpful in a situation like this.  It
    # can be used to run a setup script and it does so with the setuptools
    # egg in the Python path and with setuptools already imported.  The fact
    # that setuptools is imported means that you can use setuptools-based
    # commands, like bdist_egg even with packages that don't use setuptools.
    # To illustrate this, we'll create a package in a sample buildout:
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
    # We can use the buildout command to generate the hello egg:
    assert_output(system(buildout + ' setup hello -q bdist_egg'), """
Running setup script 'hello/setup.py'.
zip_safe flag not set; analyzing archive contents...
""", N)
    # The hello directory now has a hello egg in it's dist directory:
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

    # Repeatable buildouts: controlling eggs used
    # ===========================================
    #
    # One of the goals of zc.buildout is to provide enough control to make
    # buildouts repeatable.  It should be possible to check the buildout
    # configuration files for a project into a version control system and
    # later use the checked in files to get the same buildout, subject to
    # changes in the environment outside the buildout.
    #
    # An advantage of using Python eggs is that dependencies of eggs used are
    # automatically determined and used.  The automatic inclusion of
    # dependent distributions is at odds with the goal of repeatable
    # buildouts.
    #
    # To support repeatable buildouts, a versions section can be created
    # with options for each distribution name who's version is to be fixed.
    # The section can then be specified via the buildout versions option.
    #
    # To see how this works, we'll create two versions of a recipe egg:
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
    assert_output(system(buildout + ' setup recipe bdist_egg'), """
Running setup script 'recipe/setup.py'.
...
""", N)
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
    assert_output(system(buildout + ' setup recipe bdist_egg'), """
Running setup script 'recipe/setup.py'.
...
""", N)
    # and we'll configure a buildout to use it:
    write('buildout.cfg',
    '''
    [buildout]
    parts = foo
    find-links = %s
    
    [foo]
    recipe = spam
    ''' % join('recipe', 'dist'))
    # If we run the buildout, it will use version 2:
    assert_output(system(buildout), """
Getting distribution for 'spam'.
Got spam 2.
Installing foo.
recipe v2
""", N)
    # We can specify a versions section that lists our recipe and name it in
    # the buildout section:
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
    # Here we created a versions section listing the version 1 for the spam
    # distribution.  We told the buildout to use it by specifying release-1
    # as in the versions option.
    #
    # Now, if we run the buildout, we'll use version 1 of the spam recipe:
    assert_output(system(buildout), """
Getting distribution for 'spam==1'.
Got spam 1.
Uninstalling foo.
Installing foo.
recipe v1
""", N)
    # Running the buildout in verbose mode will help us get information
    # about versions used. If we run the buildout in verbose mode without
    # specifying a versions section:
    assert_output(system(buildout + ' buildout:versions= -v'), """
Installing 'zc.buildout', 'wheel', 'pip', 'setuptools'.
...
Installing 'spam'.
We have the best distribution that satisfies 'spam'.
Picked: spam = 2.
Uninstalling foo.
Installing foo.
recipe v2
""", N)
    # We'll get output that includes lines that tell us what versions
    # buildout chose a for us, like::
    #
    #     zc.buildout.easy_install.picked: spam = 2
    #
    # This allows us to discover versions that are picked dynamically, so
    # that we can fix them in a versions section.
    #
    # If we run the buildout with the versions section:
    assert_output(system(buildout + ' -v'), """
Installing 'zc.buildout', 'wheel', 'pip', 'setuptools'.
...
Installing 'spam'.
We have the distribution that satisfies 'spam==1'.
Uninstalling foo.
Installing foo.
recipe v1
""", N)
    # We won't get output for the spam distribution, which we didn't pick,
    # but we will get output for setuptools, which we didn't specify
    # versions for.
    #
    # .. Edge case: version applied to range requirement:
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
    assert_output(system(buildout + ' -v'), """
Installing 'zc.buildout', 'wheel', 'pip', 'setuptools'.
...
Installing 'spam >0'.
We have the distribution that satisfies 'spam==1'.
Uninstalling foo.
Installing foo.
recipe v1
""", N)
    # Edge case (issue #577) where a substitution inside the buildout section
    # which comes from a section with a recipe, then the versions versions
    # specifications were ignored, and the latest version installed, even if
    # allow-picked-versions is false.
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
    assert_output(system(buildout), """
Uninstalling foo.
Section `buildout` contains unused option(s): 'test'.
...
Installing foo.
recipe v1
""", N)
    # You can request buildout to generate an error if it picks any
    # versions:
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
    assert_output(system(buildout), """
While:
  Installing.
  Getting section foo.
  Initializing section foo.
  Installing recipe spam.
  Getting distribution for 'spam'.
Error: Picked: spam = 2
...
""", N)
    # We can name a version something else, if we wish, using the versions option:
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
    assert_output(system(buildout), """
Uninstalling foo.
Installing foo.
recipe v1
""", N)
    # We can also disable checking versions:
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
    assert_output(system(buildout), """
Uninstalling foo.
Installing foo.
recipe v2
""", N)
    # Easier reporting and managing of versions (new in buildout 2.0)
    # ---------------------------------------------------------------
    #
    # Since buildout 2.0, the functionality of the `buildout-versions
    # <http://packages.python.org/buildout-versions/>`_ extension is part of
    # buildout itself. This makes reporting and managing versions easier.
    #
    # Buildout picks versions for pip and setuptools and for the tests, we need to grab the
    # version number:
    import pkg_resources
    req = pkg_resources.Requirement.parse('setuptools')
    _dist = pkg_resources.working_set.find(req)
    assert _dist is not None
    setuptools_version = _dist.version
    req = pkg_resources.Requirement.parse('pip')
    _dist = pkg_resources.working_set.find(req)
    assert _dist is not None
    pip_version = _dist.version
    # If you set the ``show-picked-versions`` option, buildout will print
    # versions it picked at the end of its run:
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
    assert_output(system(buildout), """
Updating foo.
recipe v2
Versions had to be automatically picked.
The following part definition lists the versions picked:
[versions]
spam = 2
""", N)
    # When everything is pinned, no output is generated:
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
    assert_output(system(buildout), """
Updating foo.
recipe v2
""", N)
    # The Python package index is case-insensitive. Both
    # https://pypi.org/simple/Django/ and
    # https://pypi.org/simple/dJaNgO/ work. And distributions aren't always
    # naming themselves consistently case-wise. So all version names are normalized
    # and case differences won't impact the pinning:
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
    assert_output(system(buildout), """
Updating foo.
recipe v2
""", N)
    # Sometimes it is handy to have a separate file with versions. This is a regular
    # buildout file with a single ``[versions]`` section. You include it by
    # extending from that versions file:
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
    assert_output(system(buildout), """
Updating foo.
recipe v2
""", N)
    # If not everything is pinned and buildout has to pick versions, you can tell
    # buildout to append the versions to your versions file. It simply appends them
    # at the end.
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
    assert_output(system(buildout), """
Updating foo.
recipe v2
Versions had to be automatically picked.
The following part definition lists the versions picked:
[versions]
spam = 2
Picked versions have been written to my_versions.cfg
""", N)
    # The versions file now contains the extra pin:
    with open('my_versions.cfg') as f: print_(f.read())
    # TODO assert: '\n...\n# Added by buildout at YYYY-MM-DD hh:mm:ss.dddddd\nspam '
    # And re-running buildout doesn't report any picked versions anymore:
    _val = ('picked' in system(buildout))
    assert repr(_val) == 'False' or str(_val) == 'False'
    # If you've enabled ``update-versions-file`` but not ``show-picked-versions``,
    # buildout will append the versions to your versions file anyway (without
    # printing them to the console):
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
    assert_output(system(buildout), """
Updating foo.
recipe v2
Picked versions have been written to my_versions.cfg
""", N)
    # The versions file contains the extra pin:
    with open('my_versions.cfg') as f: print_(f.read())
    # TODO assert: '\n[versions]\n...\n\n# Added by buildout at YYYY-MM-DD hh:mm:ss.'
    # Because buildout now includes buildout-versions' (and part of the older
    # buildout.dumppickedversions') functionality, it warns if these extensions are
    # configured.
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    parts = foo
    extensions = buildout-versions
    
    [foo]
    recipe = spam
    """)
    assert_output(system(buildout), """
While:
  Installing.
  Loading extensions.
  Error: Buildout now includes 'buildout-versions' (and part of the older 'buildout.dumppickedversions').
  Remove the extension from your configuration and look at the 'show-picked-versions' option in buildout's documentation.
""", N)

def test_setup(buildout_env):
    buildout = buildout_env['buildout']
    cd = buildout_env['cd']
    ls = buildout_env['ls']
    mkdir = buildout_env['mkdir']
    print_ = buildout_env['print_']
    system = buildout_env['system']
    write = buildout_env['write']

    # Using zc.buildout to run setup scripts
    # ======================================
    #
    # zc buildout has a convenience command for running setup scripts.  Why?
    # There are two reasons.  If a setup script doesn't import setuptools,
    # you can't use any setuptools-provided commands, like bdist_egg.  When
    # buildout runs a setup script, it arranges to import setuptools before
    # running the script so setuptools-provided commands are available.
    #
    # If you use a squeaky-clean Python to do your development, the setup
    # script that would import setuptools because setuptools isn't in the
    # path.  Because buildout requires setuptools and knows where it has
    # installed a setuptools egg, it adds the setuptools egg to the Python
    # path before running the script.  To run a setup script, use the
    # buildout setup command, passing the name of a script or a directory
    # containing a setup script and arguments to the script.  Let's look at
    # an example:
    mkdir('test')
    cd('test')
    write('setup.py',
    '''
    from distutils.core import setup
    setup(name='sample')
    ''')
    # We've created a super simple (stupid) setup script.  Note that it
    # doesn't import setuptools.  Let's try running it to create an egg.
    # We'll use the buildout script from our sample buildout:
    assert_output(system(buildout + ' setup'), """
Creating directory '/sample-buildout/test/eggs/v5'.
Error: The setup command requires the path to a setup script or
directory containing a setup script, and its arguments.
""", N)
    # Oops, we forgot to give the name of the setup script:
    assert_output(system(buildout + ' setup setup.py bdist_egg'), """
Running setup script 'setup.py'.
...
""", N)
    assert_output(capture_print(ls, 'dist'), '-  sample-0.0.0-py2.5.egg', N)
    # Note that we can specify a directory name.  This is often shorter and
    # preferred by the lazy :)
    assert_output(system(buildout + ' setup . bdist_egg'), """
Running setup script './setup.py'.
...
""", N)

def test_debugging(buildout_env):
    buildout = buildout_env['buildout']
    mkdir = buildout_env['mkdir']
    print_ = buildout_env['print_']
    sample_buildout = buildout_env['sample_buildout']
    system = buildout_env['system']
    write = buildout_env['write']

    # Debugging buildouts
    # ===================
    #
    # Buildouts can be pretty complex.  When things go wrong, it isn't
    # always obvious why.  Errors can occur due to problems in user input or
    # due to bugs in zc.buildout or recipes.  When an error occurs, Python's
    # post-mortem debugger can be used to inspect the state of the buildout
    # or recipe code were there error occurred.  To enable this, use the -D
    # option to the buildout.  Let's create a recipe that has a bug:
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
    # And create a buildout that uses it:
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    develop = recipes
    parts = data-dir
    
    [data-dir]
    recipe = recipes:mkdir
    path = mystuff
    """)
    # If we run the buildout, we'll get an error:
    assert_output(system(buildout, with_exit_code=True), """
Develop: '/sample-buildout/recipes'
Installing data-dir.
While:
  Installing data-dir.
Error: Missing option: data-dir:directory
EXIT CODE: 1
""", N)
    # If we want to debug the error, we can add the -D option. Here's we'll
    # supply some input:
    assert_output(system(buildout + ' -D', 'up\np sorted(self.options.keys())\nq\n', with_exit_code=True), """
Develop: '/sample-buildout/recipes'
Installing data-dir.
> /zc/buildout/buildout.py(925)__getitem__()
-> raise MissingOption("Missing option: %s:%s" % (self.name, key))
(Pdb) > /sample-buildout/recipes/mkdir.py(14)install()
-> directory = self.options['directory']
(Pdb) ['path', 'recipe']
...While:
  Installing data-dir.
Traceback (most recent call last):
  File "/zc/buildout/buildout.py", line 1352, in main
...
  File "/zc/buildout/buildout.py", line 925, in __getitem__
    raise MissingOption("Missing option: %s:%s" % (self.name, key))
MissingOption: Missing option: data-dir:directory

Starting pdb:
EXIT CODE: 1
""", N)

def test_windows(buildout_env):
    buildout = buildout_env['buildout']
    join = buildout_env['join']
    mkdir = buildout_env['mkdir']
    print_ = buildout_env['print_']
    system = buildout_env['system']
    write = buildout_env['write']

    # zc.buildout on MS-Windows
    # =========================
    #
    # Certain aspects of every software project are dependent on the
    # operating system used.
    # The same - of course - applies to zc.buildout.
    #
    # To test that Windows doesn't get in the way, we'll test some system
    # dependent aspects.
    # The following recipe will create a read-only file which shutil.rmtree
    # can't delete.
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
    assert_output(system(buildout + ' setup recipe bdist_egg'), """
Running setup script 'recipe/setup.py'.
...
""", N)
    # and we'll configure a buildout to use it:
    write('buildout.cfg',
    '''
    [buildout]
    parts = foo
    find-links = %s
    
    [foo]
    recipe = spam
    ''' % join('recipe', 'dist'))
    assert_output(system(buildout), """
Getting distribution for 'spam'.
Got spam 1.
Installing foo.
can't remove read only files
""", N)
