"""Pytest port of update.txt — no DocTestRunner."""
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


def test_update(update_env):
    buildout = update_env['buildout']
    cat = update_env['cat']
    cd = update_env['cd']
    ls = update_env['ls']
    mkdir = update_env['mkdir']
    new_releases = update_env['new_releases']
    print_ = update_env['print_']
    sample_buildout = update_env['sample_buildout']
    system = update_env['system']
    tmpdir = update_env['tmpdir']
    write = update_env['write']

    assert_output(capture_print(ls, new_releases), '...\n-  zc_buildout-91.0-py3-none-any.whl\n-  zc_buildout-NINETYNINE.NINETYNINE-py3-none-any.whl', N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    find-links = %(new_releases)s
    index = %(new_releases)s
    parts = show-versions
    develop = showversions
    
    [show-versions]
    recipe = showversions
    """ % dict(new_releases=new_releases))
    mkdir(sample_buildout, 'showversions')
    write(sample_buildout, 'showversions', 'showversions.py',
    """
    import pkg_resources
    import sys
    print_ = lambda *a: sys.stdout.write(' '.join(map(str, a))+'\\n')
    
    class Recipe:
    
        def __init__(self, buildout, name, options):
            pass
    
        def install(self):
            for project in ['zc.buildout']:
                req = pkg_resources.Requirement.parse(project)
                print_(project, pkg_resources.working_set.find(req).version)
            return ()
        update = install
    """)
    write(sample_buildout, 'showversions', 'setup.py',
    """
    from setuptools import setup
    
    setup(
        name = "showversions",
        entry_points = {'zc.buildout': ['default = showversions:Recipe']},
        )
    """)
    assert_output(system(buildout), 'Develop:...\nInstalling show-versions.\nzc.buildout V.V', N)
    assert_output(system(buildout + ' versions:zc.buildout=91.0'), "Getting distribution for 'zc.buildout==91.0'.\nGot zc.buildout V.V\nUpgraded:\n  zc.buildout V.V\nRestarting.\nGenerated script '/sample-buildout/bin/buildout'.\nDevelop: '/sample-buildout/showversions'\nUpdating show-versions.\nzc.buildout V.V", N)
    assert_output(system(buildout), "Got zc.buildout NINETYNINE.NINETYNINE.\nUpgraded:\n  zc.buildout version NINETYNINE.NINETYNINE;\nRestarting.\nGenerated script '/sample-buildout/bin/buildout'.\nDevelop: '/sample-buildout/showversions'\nUpdating show-versions.\nzc.buildout NINETYNINE.NINETYNINE", N)
    assert_output(capture_print(cat, sample_buildout, 'bin', 'buildout'), "#!/usr/local/bin/python2.7\n\nimport sys\nsys.path[0:0] = [\n  '/sample-buildout/eggs/v5/zc.buildout-NINETYNINE.NINETYNINE-pyN.N.egg',\n...\n  ]\n\nimport zc.buildout.buildout\n\nif __name__ == '__main__':\n    sys.exit(zc.buildout.buildout.main())", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    find-links = %(new_releases)s
    index = %(new_releases)s
    parts = show-versions
    develop = showversions
    
    [versions]
    zc.buildout = < 99
    
    [show-versions]
    recipe = showversions
    """ % dict(new_releases=new_releases))
    assert_output(system(buildout), "Upgraded:\n  zc.buildout V.V\nRestarting.\nGenerated script '/sample-buildout/bin/buildout'.\nDevelop: '/sample-buildout/showversions'\nUpdating show-versions.\nzc.buildout V.V", N)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    find-links = %(new_releases)s
    index = %(new_releases)s
    parts = show-versions
    develop = showversions
    
    [show-versions]
    recipe = showversions
    """ % dict(new_releases=new_releases))
    assert_output(system(buildout + ' -o'), "Develop: '/sample-buildout/showversions'\nUpdating show-versions.\nzc.buildout 1.0.0", N)
    assert_output(system(buildout + ' -N'), "Develop: '/sample-buildout/showversions'\nUpdating show-versions.\nzc.buildout 1.0.0", N)
    sample_buildout2 = tmpdir('sample_buildout2')
    write(sample_buildout2, 'buildout.cfg',
    """
    [buildout]
    find-links = %(new_releases)s
    index = %(new_releases)s
    parts =
    
    [versions]
    zc.buildout = 99.99
    """ % dict(new_releases=new_releases))
    cd(sample_buildout2)
    assert_output(system(buildout), "Creating directory '/sample_buildout2/eggs/v5'.\nCreating directory '/sample_buildout2/bin'.\nCreating directory '/sample_buildout2/parts'.\nCreating directory '/sample_buildout2/develop-eggs'.\nGetting distribution for 'zc.buildout==NINETYNINE.NINETYNINE'.\nGot zc.buildout NINETYNINE.NINETYNINE.\nNot upgrading because not running a local buildout command.", N)
    ls('bin')
    cd(sample_buildout)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    find-links = %(new_releases)s
    index = %(new_releases)s
    parts = show-versions
    develop = showversions
    relative-paths = true
    
    [show-versions]
    recipe = showversions
    """ % dict(new_releases=new_releases))
    assert_output(system(buildout), "Upgraded:\n  zc.buildout version NINETYNINE.NINETYNINE;\nRestarting.\nGenerated script '/sample-buildout/bin/buildout'.\nDevelop: '/sample-buildout/showversions'\nSection `buildout` contains unused option(s): 'relative-paths'.\nThis may be an indication for either a typo in the option's name or a bug in the used recipe.\nUpdating show-versions.\nzc.buildout NINETYNINE.NINETYNINE", N)
    assert_output(capture_print(cat, 'bin', 'buildout'), "#!/usr/local/bin/python2.7\n\nimport os\n\njoin = os.path.join\nbase = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))\nbase = os.path.dirname(base)\n\nimport sys\nsys.path[0:0] = [\n  join(base, 'eggs/v5/zc.buildout-NINETYNINE.NINETYNINE-pyN.N.egg'),\n...\n  ]\n\nimport zc.buildout.buildout\n\nif __name__ == '__main__':\n    sys.exit(zc.buildout.buildout.main())", N)
    mkdir(sample_buildout, 'failrecipe')
    write(sample_buildout, 'failrecipe', 'failrecipe.py',
    """
    import pkg_resources
    import sys
    print_ = lambda *a: sys.stdout.write(' '.join(map(str, a))+'\\n')
    
    class Recipe:
    
        def __init__(self, buildout, name, options):
            sys.exit('recipe sys-exits')
    
        def install(self):
            pass
    
        update = install
    """)
    write(sample_buildout, 'failrecipe', 'setup.py',
    """
    from setuptools import setup
    
    setup(
        name = "failrecipe",
        entry_points = {'zc.buildout': ['default = failrecipe:Recipe']},
        )
    """)
    write(sample_buildout, 'buildout.cfg',
    """
    [buildout]
    find-links = %(new_releases)s
    index = %(new_releases)s
    parts = fail
    develop = failrecipe
    
    [versions]
    zc.buildout = < 99
    
    [fail]
    recipe = failrecipe
    """ % dict(new_releases=new_releases))
    assert_output(system(buildout, with_exit_code=True), "Upgraded:\n  zc.buildout V.V\nRestarting.\nGenerated script '/sample-buildout/bin/buildout'.\nDevelop: '/sample-buildout/failrecipe'\nrecipe sys-exits\nEXIT CODE: 1", N)
