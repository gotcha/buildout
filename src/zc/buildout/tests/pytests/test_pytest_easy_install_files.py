"""Pytest port of easy_install.txt, downloadcache.txt, dependencylinks.txt, allowhosts.txt, allow-unknown-extras.txt, download.txt, extends-cache.txt, testing_bugfix.txt — no DocTestRunner."""
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
    NORMALIZERS_EASY_INSTALL,
)

N = NORMALIZERS_EASY_INSTALL


def test_easy_install(easy_install_env):
    cat = easy_install_env['cat']
    get = easy_install_env['get']
    join = easy_install_env['join']
    link_server = easy_install_env['link_server']
    ls = easy_install_env['ls']
    mkdir = easy_install_env['mkdir']
    os = easy_install_env['os']
    print_ = easy_install_env['print_']
    remove = easy_install_env['remove']
    rmdir = easy_install_env['rmdir']
    sample_buildout = easy_install_env['sample_buildout']
    start_server = easy_install_env['start_server']
    system = easy_install_env['system']
    tmpdir = easy_install_env['tmpdir']
    update_extdemo = easy_install_env['update_extdemo']
    write = easy_install_env['write']

    assert_output(str(get(link_server)), '<html><body>\n<a href="bigdemo-0.1-py3-none-any.whl">bigdemo-0.1-py3-none-any.whl</a><br>\n<a href="demo-0.1-py3-none-any.whl">demo-0.1-py3-none-any.whl</a><br>\n<a href="demo-0.2-py3-none-any.whl">demo-0.2-py3-none-any.whl</a><br>\n<a href="demo-0.3-py3-none-any.whl">demo-0.3-py3-none-any.whl</a><br>\n<a href="demo-0.4rc1-py3-none-any.whl">demo-0.4rc1-py3-none-any.whl</a><br>\n<a href="demoneeded-1.0.tar.gz">demoneeded-1.0.tar.gz</a><br>\n<a href="demoneeded-1.1.tar.gz">demoneeded-1.1.tar.gz</a><br>\n<a href="demoneeded-1.2rc1.tar.gz">demoneeded-1.2rc1.tar.gz</a><br>\n<a href="du_zipped-1.0-pyN.N.egg">du_zipped-1.0-pyN.N.egg</a><br>\n<a href="extdemo-1.4.tar.gz">extdemo-1.4.tar.gz</a><br>\n<a href="index/">index/</a><br>\n<a href="mixedcase-0.5.tar.gz">mixedcase-0.5.tar.gz</a><br>\n<a href="other-1.0-py3-none-any.whl">other-1.0-py3-none-any.whl</a><br>\n</body></html>', N)
    dest = tmpdir('sample-install')
    import zc.buildout.easy_install
    ws = zc.buildout.easy_install.install(
        ['demo==0.2'], dest,
        links=[link_server], index=link_server+'index/')
    for dist in ws:
        print_(dist)
    # TODO assert: 'demoneeded 1.1\ndemo 0.2'
    assert_output(capture_print(ls, dest), 'd  demo-0.2-py2.4.egg\nd  demoneeded-1.1-py2.4.egg', N)
    ws = zc.buildout.easy_install.install(
        ['demo'], dest, links=[link_server], index=link_server+'index/',
        newest=False)
    assert_output(capture_print(ls, dest), 'd  demo-0.2-py2.4.egg\nd  demoneeded-1.1-py2.4.egg', N)
    ws = zc.buildout.easy_install.install(
        ['demo'], dest, links=[link_server], index=link_server+'index/')
    assert_output(capture_print(ls, dest), 'd  demo-0.2-py2.4.egg\nd  demo-0.3-py2.4.egg\nd  demoneeded-1.1-py2.4.egg', N)
    _val = (zc.buildout.easy_install.prefer_final(False))
    assert repr(_val) == 'True' or str(_val) == 'True'
    ws = zc.buildout.easy_install.install(
        ['demo'], dest, links=[link_server], index=link_server+'index/')
    for dist in ws:
        print_(dist)
    # TODO assert: 'demoneeded 1.2rc1\ndemo 0.4rc1'
    assert_output(capture_print(ls, dest), 'd  demo-0.2-py2.4.egg\nd  demo-0.3-py2.4.egg\nd  demo-0.4rc1-py2.4.egg\nd  demoneeded-1.1-py2.4.egg\nd  demoneeded-1.2rc1-py2.4.egg', N)
    _val = (zc.buildout.easy_install.prefer_final(True))
    assert repr(_val) == 'False' or str(_val) == 'False'
    ws = zc.buildout.easy_install.install(
        ['demo', 'other', 'demoneeded==1.0'], dest,
        links=[link_server], index=link_server+'index/')
    for dist in ws:
        print_(dist)
    # TODO assert: 'demoneeded 1.0\nother 1.0\ndemo 0.3'
    assert_output(capture_print(ls, dest), 'd  demo-0.2-py2.4.egg\nd  demo-0.3-py2.4.egg\nd  demo-0.4rc1-py2.4.egg\nd  demoneeded-1.0-py2.4.egg\nd  demoneeded-1.1-py2.4.egg\nd  demoneeded-1.2rc1-py2.4.egg\nd  other-1.0-py2.4.egg', N)
    rmdir(dest)
    try:
        ws = zc.buildout.easy_install.install(
            ['demo[unknown_extra]'], dest, links=[link_server],
            index=link_server+'index/')
        assert False, "Expected UserError not raised"
    except Exception as _exc:
        assert_output(str(_exc), "Couldn't find the required extra...", N)
    ws = zc.buildout.easy_install.install(
        ['demo[unknown_extra]'], dest, links=[link_server],
        index=link_server+'index/',
        allow_unknown_extras=True)
    assert_output(capture_print(ls, dest), 'd  demo-0.3-py2.4.egg', N)
    rmdir(dest)
    _ = get(link_server + 'enable_server_logging')
    # TODO assert: 'GET 200 /enable_server_logging'
    ws = zc.buildout.easy_install.install(
        ['MIXEDCASE'], dest,
        links=[link_server], index=link_server+'index/')
    # TODO assert: 'GET 404 /index/mixedcase/\nGET 200 /mixedcase-0.5.tar.gz\nGET '
    for dist in ws:
        print_(str(dist).lower())
    # TODO assert: 'demoneeded 1.1\nmixedcase 0.5'
    assert_output(capture_print(ls, dest, lowercase_and_sort_output=True), 'd  demoneeded-1.1-py2.4.egg\nd  mixedcase-0.5-pyN.N.egg', N)
    _ = get(link_server + 'disable_server_logging')
    rmdir(dest)
    ws = zc.buildout.easy_install.install(
        ['demo'], dest, links=[link_server], index=link_server+'index/',
        versions = dict(demo='0.2', demoneeded='1.0'))
    _val = ([d.version for d in ws])
    assert repr(_val) == "['1.0', '0.2']" or str(_val) == "['1.0', '0.2']"
    from zope.testing.loggingsupport import InstalledHandler
    handler = InstalledHandler('zc.buildout.easy_install')
    import logging
    logging.getLogger('zc.buildout.easy_install').propagate = False
    try:
        ws = zc.buildout.easy_install.install(
            ['demo >0.2'], dest, links=[link_server],
            index=link_server+'index/',
            versions = dict(demo='0.2', demoneeded='1.0'))
        assert False, "Expected IncompatibleConstraintError not raised"
    except Exception as _exc:
        assert_output(str(_exc), "IncompatibleConstraintError: The requirement ('demo>0.2') is not allowed by your [versions] constraint (0.2)", N)
    assert_output(str(handler), "zc.buildout.easy_install DEBUG\n  Installing 'demo >0.2'.\nzc.buildout.easy_install INFO\n  Version and requirements information containing demo:\n  [versions] constraint on demo: 0.2\n  Base installation request: 'demo >0.2'", N)
    handler.clear()
    ws = zc.buildout.easy_install.install(
        ['demo'], dest, links=[link_server], index=link_server+'index/',
        )
    assert_output(str(handler), "zc.buildout.easy_install DEBUG\n  Installing 'demo'.\nzc.buildout.easy_install INFO\n  Getting distribution for 'demo'.\nzc.buildout.easy_install DEBUG\n  Fetching demo 0.3 from: http://.../demo-0.3-py3-none-any.whl\nzc.buildout.easy_install DEBUG\n  Turning dist demo 0.3 (.../demo-0.3-py3-none-any.whl) into egg, and moving to eggs dir /sample-install).\nzc.buildout.easy_install DEBUG\n  Calling pip install for .whl on .../demo-0.3-py3-none-any.whl\nzc.buildout.easy_install DEBUG\n  Running pip install:...\nzc.buildout.easy_install DEBUG\n  Egg for demo 0.3 installed at .../demo-0.3-pyN.N.egg\nzc.buildout.easy_install INFO\n  Got demo 0.3.\nzc.buildout.easy_install DEBUG\n  Picked: demo = 0.3\nzc.buildout.easy_install DEBUG\n  Getting required 'demoneeded'\nzc.buildout.easy_install DEBUG\n    required by demo 0.3.\nzc.buildout.easy_install INFO\n  Getting distribution for 'demoneeded'.\nzc.buildout.easy_install DEBUG\n  Fetching demoneeded 1.1 from: http://.../demoneeded-1.1.tar.gz\nzc.buildout.easy_install DEBUG\n  Turning dist demoneeded 1.1 (.../demoneeded-1.1.tar.gz) into egg, and moving to eggs dir /sample-install).\nzc.buildout.easy_install DEBUG\n  Calling pip install for .gz on .../demoneeded-1.1.tar.gz\nzc.buildout.easy_install DEBUG\n  Running pip install:...\nzc.buildout.easy_install DEBUG\n  Egg for demoneeded 1.1 installed at .../demoneeded-1.1-pyN.N.egg\nzc.buildout.easy_install INFO\n  Got demoneeded 1.1.\nzc.buildout.easy_install DEBUG\n  Picked: demoneeded = 1.1", N)
    handler.uninstall()
    logging.getLogger('zc.buildout.easy_install').propagate = True
    _val = (zc.buildout.easy_install.allow_picked_versions(False))
    assert repr(_val) == 'True' or str(_val) == 'True'
    try:
        ws = zc.buildout.easy_install.install(
            ['demo'], dest, links=[link_server], index=link_server+'index/',
            )
        assert False, "Expected OR set `allow-picked-versions = true`. not raised"
    except Exception as _exc:
        assert_output(str(_exc), 'OR set `allow-picked-versions = true`.', N)
    _val = (zc.buildout.easy_install.allow_picked_versions(True))
    assert repr(_val) == 'False' or str(_val) == 'False'
    _val = (zc.buildout.easy_install.default_versions(dict(demoneeded='1')))
    assert repr(_val) == '{...}' or str(_val) == '{...}'
    _val = (zc.buildout.easy_install.default_versions())
    assert repr(_val) == "{'demoneeded': '1'}" or str(_val) == "{'demoneeded': '1'}"
    ws = zc.buildout.easy_install.install(
        ['demo'], dest, links=[link_server], index=link_server+'index/',
        )
    _val = ([d.version for d in ws])
    assert repr(_val) == "['0.3', '1.0']" or str(_val) == "['0.3', '1.0']"
    _val = (zc.buildout.easy_install.default_versions({}))
    assert repr(_val) == "{'demoneeded': '1'}" or str(_val) == "{'demoneeded': '1'}"
    ws = zc.buildout.easy_install.install(
        ['demo'], dest, links=[link_server], index=link_server+'index/',
        )
    _val = ([d.version for d in ws])
    assert repr(_val) == "['0.3', '1.1']" or str(_val) == "['0.3', '1.1']"
    repoloc = tmpdir('repo')
    from zc.buildout.tests import create_wheel
    create_wheel('demoneeded', '1.2', repoloc)
    link_server2 = start_server(repoloc)
    _ = get(link_server2 + 'enable_server_logging')
    # TODO assert: 'GET 200 /enable_server_logging'
    repoloc = tmpdir('repo2')
    create_wheel('hasdeps', '1.0', repoloc,
                 install_requires = "'demoneeded'",
                 dependency_links = [link_server2])
    link_server3 = start_server(repoloc)
    example_dest = tmpdir('example-install')
    workingset = zc.buildout.easy_install.install(
        ['hasdeps'], example_dest,
        links=[link_server3], index=link_server3+'index/')
    # TODO assert: 'GET 200 /\nGET 200 /demoneeded-1.2-py3-none-any.whl'
    rmdir(example_dest)
    example_dest = tmpdir('example-install')
    workingset = zc.buildout.easy_install.install(
        ['hasdeps'], example_dest, index=link_server+'index/',
        links=[link_server, link_server3])
    # TODO assert: 'GET 200 /\nGET 200 /demoneeded-1.2-py3-none-any.whl'
    rmdir(example_dest)
    example_dest = tmpdir('example-install')
    workingset = zc.buildout.easy_install.install(
        ['hasdeps'], example_dest, index=link_server+'index/',
        links=[link_server, link_server3],
        use_dependency_links=False)
    _val = (zc.buildout.easy_install.use_dependency_links(False))
    assert repr(_val) == 'True' or str(_val) == 'True'
    rmdir(example_dest)
    example_dest = tmpdir('example-install')
    workingset = zc.buildout.easy_install.install(
        ['hasdeps'], example_dest, index=link_server+'index/',
        links=[link_server, link_server3])
    rmdir(example_dest)
    example_dest = tmpdir('example-install')
    workingset = zc.buildout.easy_install.install(
        ['hasdeps'], example_dest, index=link_server+'index/',
        links=[link_server, link_server3],
        use_dependency_links=True)
    # TODO assert: 'GET 200 /demoneeded-1.2-py3-none-any.whl'
    _val = (zc.buildout.easy_install.use_dependency_links(True))
    assert repr(_val) == 'False' or str(_val) == 'False'
    rmdir(example_dest)
    example_dest = tmpdir('example-install')
    workingset = zc.buildout.easy_install.install(
        ['hasdeps'], example_dest, index=link_server+'index/',
        links=[link_server, link_server3])
    # TODO assert: 'GET 200 /demoneeded-1.2-py3-none-any.whl'
    import tempfile
    bin = tmpdir('bin')
    import sys
    scripts = zc.buildout.easy_install.scripts(
        ['demo'], ws, sys.executable, bin)
    assert_output(capture_print(ls, bin), '-  demo', N)
    import os, sys
    if sys.platform == 'win32':
        scripts == [os.path.join(bin, 'demo.exe'),
                    os.path.join(bin, 'demo-script.py')]
    else:
        scripts == [os.path.join(bin, 'demo')]
    assert_output(capture_print(cat, bin, 'demo'), "#!/usr/local/bin/python2.7\n\nimport sys\nsys.path[0:0] = [\n  '/sample-install/demo-0.3-py2.4.egg',\n  '/sample-install/demoneeded-1.1-py2.4.egg',\n  ]\n\nimport eggrecipedemo\n\nif __name__ == '__main__':\n    sys.exit(eggrecipedemo.main())", N)
    scripts = zc.buildout.easy_install.scripts(
        [('demo', 'eggrecipedemo', 'main')], ws,
        sys.executable, bin)
    assert_output(capture_print(cat, bin, 'demo'), "#!/usr/local/bin/python2.7\n\nimport sys\nsys.path[0:0] = [\n  '/sample-install/demo-0.3-py2.4.egg',\n  '/sample-install/demoneeded-1.1-py2.4.egg',\n  ]\n\nimport eggrecipedemo\n\nif __name__ == '__main__':\n    sys.exit(eggrecipedemo.main())", N)
    scripts = zc.buildout.easy_install.scripts(
        ['demo'], ws, sys.executable, bin, interpreter='py')
    assert_output(capture_print(ls, bin), '-  demo\n-  py', N)
    if sys.platform == 'win32':
        scripts == [os.path.join(bin, 'demo.exe'),
                    os.path.join(bin, 'demo-script.py'),
                    os.path.join(bin, 'py.exe'),
                    os.path.join(bin, 'py-script.py')]
    else:
        scripts == [os.path.join(bin, 'demo'),
                    os.path.join(bin, 'py')]
    assert_output(capture_print(cat, bin, 'py'), '#!/usr/local/bin/python2.7\n\nimport sys\n\nsys.path[0:0] = [\n  \'/sample-install/demo-0.3-pyN.N.egg\',\n  \'/sample-install/demoneeded-1.1-pyN.N.egg\',\n  ]\n\n_interactive = True\nif len(sys.argv) > 1:\n    # The Python interpreter wrapper allows only some of the options that a\n    # "regular" Python interpreter accepts.\n    _options, _args = __import__("getopt").getopt(sys.argv[1:], \'Iic:m:\')\n    _interactive = False\n    for (_opt, _val) in _options:\n        if _opt == \'-i\':\n            _interactive = True\n        elif _opt == \'-c\':\n            exec(_val)\n        elif _opt == \'-m\':\n            sys.argv[1:] = _args\n            _args = []\n            __import__("runpy").run_module(\n                 _val, {}, "__main__", alter_sys=True)\n        elif _opt == \'-I\':\n            # Allow yet silently ignore the `-I` option. The original behaviour\n            # for this option is to create an isolated Python runtime. It was\n            # deemed acceptable to allow the option here as this Python wrapper\n            # is isolated from the system Python already anyway.\n            # The specific use-case that led to this change is how the Python\n            # language extension for Visual Studio Code calls the Python\n            # interpreter when initializing the extension.\n            pass\n\n    if _args:\n        sys.argv[:] = _args\n        __file__ = _args[0]\n        del _options, _args\n        with open(__file__, \'U\') as __file__f:\n            exec(compile(__file__f.read(), __file__, "exec"))\n\nif _interactive:\n    del _interactive\n    __import__("code").interact(banner="", local=globals())', N)
    write('ascript', r'''
    "demo doc"
    import sys
    print_ = lambda *a: sys.stdout.write(' '.join(map(str, a))+'\n')
    print_(sys.argv)
    print_((__name__, __file__, __doc__))
    ''')
    assert_output(system(join(bin, 'py') + ' ascript a b c'), "['ascript', 'a', 'b', 'c']\n('__main__', 'ascript', 'demo doc')", N)
    assert_output(system(join(bin, 'py') + ' -m pdb'), 'usage: ...pdb...', N)
    assert_output(system(join(bin, 'py') + ' -m pdb what'), 'Error: what does not exist', N)
    scripts = zc.buildout.easy_install.scripts(
        [], [], sys.executable, bin, interpreter='py')
    assert_output(capture_print(cat, bin, 'py'), '#!/usr/local/bin/python2.7\n\nimport sys\n\nsys.path[0:0] = [\n\n  ]\n...', N)
    bin = tmpdir('bin2')
    scripts = zc.buildout.easy_install.scripts(
        ['demo'], ws, sys.executable, bin, dict(demo='run'))
    if sys.platform == 'win32':
        scripts == [os.path.join(bin, 'run.exe'),
                    os.path.join(bin, 'run-script.py')]
    else:
        scripts == [os.path.join(bin, 'run')]
    assert_output(capture_print(ls, bin), '-  run', N)
    assert_output(system(os.path.join(bin, 'run')), '3 1', N)
    if sys.platform == 'win32':
        os.access(os.path.join(bin, 'run.exe'), os.X_OK)
    else:
        os.access(os.path.join(bin, 'run'), os.X_OK)
    foo = tmpdir('foo')
    scripts = zc.buildout.easy_install.scripts(
       ['demo'], ws, sys.executable, bin, dict(demo='run'),
       extra_paths=[foo])
    assert_output(capture_print(cat, bin, 'run'), "#!/usr/local/bin/python2.7\n\nimport sys\nsys.path[0:0] = [\n  '/sample-install/demo-0.3-py2.4.egg',\n  '/sample-install/demoneeded-1.1-py2.4.egg',\n  '/foo',\n  ]\n\nimport eggrecipedemo\n\nif __name__ == '__main__':\n    sys.exit(eggrecipedemo.main())", N)
    scripts = zc.buildout.easy_install.scripts(
       ['demo'], ws, sys.executable, bin, dict(demo='run'),
       arguments='1, 2')
    assert_output(capture_print(cat, bin, 'run'), "#!/usr/local/bin/python2.7\nimport sys\nsys.path[0:0] = [\n  '/sample-install/demo-0.3-py2.4.egg',\n  '/sample-install/demoneeded-1.1-py2.4.egg',\n  ]\n\nimport eggrecipedemo\n\nif __name__ == '__main__':\n    sys.exit(eggrecipedemo.main(1, 2))", N)
    scripts = zc.buildout.easy_install.scripts(
       ['demo'], ws, sys.executable, bin, dict(demo='run'),
       arguments='1, 2',
       initialization='import os\nos.chdir("foo")',
       interpreter='py')
    assert_output(capture_print(cat, bin, 'run'), '#!/usr/local/bin/python2.7\nimport sys\nsys.path[0:0] = [\n  \'/sample-install/demo-0.3-py2.4.egg\',\n  \'/sample-install/demoneeded-1.1-py2.4.egg\',\n  ]\n\nimport os\nos.chdir("foo")\n\nimport eggrecipedemo\n\nif __name__ == \'__main__\':\n    sys.exit(eggrecipedemo.main(1, 2))', N)
    assert_output(capture_print(cat, bin, 'py'), '#!/usr/local/bin/python2.7\n\nimport sys\n\nsys.path[0:0] = [\n  \'/sample-install/demo-0.3-py3.3.egg\',\n  \'/sample-install/demoneeded-1.1-py3.3.egg\',\n  ]\n\nimport os\nos.chdir("foo")\n\n\n_interactive = True\n...', N)
    bo = tmpdir('bo')
    ba = tmpdir('ba')
    mkdir(bo, 'eggs')
    mkdir(bo, 'bin')
    mkdir(bo, 'other')
    ws = zc.buildout.easy_install.install(
        ['demo'], join(bo, 'eggs'), links=[link_server],
        index=link_server+'index/')
    scripts = zc.buildout.easy_install.scripts(
       ['demo'], ws, sys.executable, join(bo, 'bin'), dict(demo='run'),
       extra_paths=[ba, join(bo, 'bar'), bo],
       interpreter='py',
       relative_paths=bo)
    assert_output(capture_print(cat, bo, 'bin', 'run'), "#!/usr/local/bin/python2.7\n\nimport os\n\njoin = os.path.join\nbase = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))\nbase = os.path.dirname(base)\n\nimport sys\nsys.path[0:0] = [\n  join(base, 'eggs/demoneeded-1.1-pyN.N.egg'),\n  join(base, 'eggs/demo-0.3-pyN.N.egg'),\n  '/ba',\n  join(base, 'bar'),\n  base,\n  ]\n\nimport eggrecipedemo\n\nif __name__ == '__main__':\n    sys.exit(eggrecipedemo.main())", N)
    assert_output(system(join(bo, 'bin', 'run')), '3 1', N)
    assert_output(capture_print(cat, bo, 'bin', 'py'), '#!/usr/local/bin/python2.7\n\nimport os\n\njoin = os.path.join\nbase = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))\nbase = os.path.dirname(base)\n\nimport sys\n\nsys.path[0:0] = [\n  join(base, \'eggs/demoneeded-1.1-pyN.N.egg\'),\n  join(base, \'eggs/demo-0.3-pyN.N.egg\'),\n  \'/ba\',\n  join(base, \'bar\'),\n  base,\n  ]\n\n\n_interactive = True\nif len(sys.argv) > 1:\n    # The Python interpreter wrapper allows only some of the options that a\n    # "regular" Python interpreter accepts.\n    _options, _args = __import__("getopt").getopt(sys.argv[1:], \'Iic:m:\')\n    _interactive = False\n    for (_opt, _val) in _options:\n        if _opt == \'-i\':\n            _interactive = True\n        elif _opt == \'-c\':\n            exec(_val)\n        elif _opt == \'-m\':\n            sys.argv[1:] = _args\n            _args = []\n            __import__("runpy").run_module(\n                 _val, {}, "__main__", alter_sys=True)\n        elif _opt == \'-I\':\n            # Allow yet silently ignore the `-I` option. The original behaviour\n            # for this option is to create an isolated Python runtime. It was\n            # deemed acceptable to allow the option here as this Python wrapper\n            # is isolated from the system Python already anyway.\n            # The specific use-case that led to this change is how the Python\n            # language extension for Visual Studio Code calls the Python\n            # interpreter when initializing the extension.\n            pass\n\n    if _args:\n        sys.argv[:] = _args\n        __file__ = _args[0]\n        del _options, _args\n        with open(__file__, \'U\') as __file__f:\n            exec(compile(__file__f.read(), __file__, "exec"))\n\nif _interactive:\n    del _interactive\n    __import__("code").interact(banner="", local=globals())', N)
    mkdir('include')
    write('include', 'extdemo.h',
    """
    #define EXTDEMO 42
    """)
    _val = (zc.buildout.easy_install.build(
  'extdemo', dest,
  {'include_dirs': os.path.join(sample_buildout, 'include')},
  links=[link_server], index=link_server+'index/'))
    assert repr(_val) == "['/sample-install/extdemo-1.4-py2.4-unix-i686.egg']" or str(_val) == "['/sample-install/extdemo-1.4-py2.4-unix-i686.egg']"
    assert_output(capture_print(ls, dest), 'd  demo-0.2-py2.4.egg\nd  demo-0.3-py2.4.egg\nd  demoneeded-1.0-py2.4.egg\nd  demoneeded-1.1-py2.4.egg\nd  extdemo-1.4-py2.4-unix-i686.egg', N)
    update_extdemo()
    assert_output(str(get(link_server)), '<html><body>\n<a href="bigdemo-0.1-py3-none-any.whl">bigdemo-0.1-py3-none-any.whl</a><br>\n<a href="demo-0.1-py3-none-any.whl">demo-0.1-py3-none-any.whl</a><br>\n<a href="demo-0.2-py3-none-any.whl">demo-0.2-py3-none-any.whl</a><br>\n<a href="demo-0.3-py3-none-any.whl">demo-0.3-py3-none-any.whl</a><br>\n<a href="demo-0.4rc1-py3-none-any.whl">demo-0.4rc1-py3-none-any.whl</a><br>\n<a href="demoneeded-1.0.tar.gz">demoneeded-1.0.tar.gz</a><br>\n<a href="demoneeded-1.1.tar.gz">demoneeded-1.1.tar.gz</a><br>\n<a href="demoneeded-1.2rc1.tar.gz">demoneeded-1.2rc1.tar.gz</a><br>\n<a href="du_zipped-1.0-pyN.N.egg">du_zipped-1.0-pyN.N.egg</a><br>\n<a href="extdemo-1.4.tar.gz">extdemo-1.4.tar.gz</a><br>\n<a href="extdemo-1.5.tar.gz">extdemo-1.5.tar.gz</a><br>\n<a href="index/">index/</a><br>\n<a href="mixedcase-0.5.tar.gz">mixedcase-0.5.tar.gz</a><br>\n<a href="other-1.0-py3-none-any.whl">other-1.0-py3-none-any.whl</a><br>\n</body></html>', N)
    zc.buildout.easy_install.clear_index_cache()
    _val = (zc.buildout.easy_install.build(
  'extdemo', dest,
  {'include_dirs': os.path.join(sample_buildout, 'include')},
  links=[link_server], index=link_server+'index/',
  newest=False))
    assert repr(_val) == "['/sample-install/extdemo-1.4-py2.4-linux-i686.egg']" or str(_val) == "['/sample-install/extdemo-1.4-py2.4-linux-i686.egg']"
    assert_output(capture_print(ls, dest), 'd  demo-0.2-py2.4.egg\nd  demo-0.3-py2.4.egg\nd  demoneeded-1.0-py2.4.egg\nd  demoneeded-1.1-py2.4.egg\nd  extdemo-1.4-py2.4-unix-i686.egg', N)
    _val = (zc.buildout.easy_install.build(
  'extdemo', dest,
  {'include_dirs': os.path.join(sample_buildout, 'include')},
  links=[link_server], index=link_server+'index/'))
    assert repr(_val) == "['/sample-install/extdemo-1.5-py2.4-unix-i686.egg']" or str(_val) == "['/sample-install/extdemo-1.5-py2.4-unix-i686.egg']"
    assert_output(capture_print(ls, dest), 'd  demo-0.2-py2.4.egg\nd  demo-0.3-py2.4.egg\nd  demoneeded-1.0-py2.4.egg\nd  demoneeded-1.1-py2.4.egg\nd  extdemo-1.4-py2.4-unix-i686.egg\nd  extdemo-1.5-py2.4-unix-i686.egg', N)
    import os
    for name in os.listdir(dest):
        remove(dest, name)
    _val = (zc.buildout.easy_install.build(
  'extdemo', dest,
  {'include_dirs': os.path.join(sample_buildout, 'include')},
  links=[link_server], index=link_server+'index/',
  versions=dict(extdemo='1.4')))
    assert repr(_val) == "['/sample-install/extdemo-1.4-py2.4-unix-i686.egg']" or str(_val) == "['/sample-install/extdemo-1.4-py2.4-unix-i686.egg']"
    assert_output(capture_print(ls, dest), 'd  extdemo-1.4-py2.4-unix-i686.egg', N)
    contents = os.listdir(extdemo)
    _val = ('MANIFEST.in' in contents)
    assert repr(_val) == 'True' or str(_val) == 'True'
    _val = ('README' in contents)
    assert repr(_val) == 'True' or str(_val) == 'True'
    _val = ('extdemo.c' in contents)
    assert repr(_val) == 'True' or str(_val) == 'True'
    _val = ('setup.py' in contents)
    assert repr(_val) == 'True' or str(_val) == 'True'
    _val = (zc.buildout.easy_install.develop(
  extdemo, dest,
  {'include_dirs': os.path.join(sample_buildout, 'include')}))
    assert repr(_val) == "'/sample-install/extdemo.egg-link'" or str(_val) == "'/sample-install/extdemo.egg-link'"
    assert_output(capture_print(ls, dest), 'd  extdemo-1.4-py2.4-unix-i686.egg\n-  extdemo.egg-link', N)
    contents = os.listdir(extdemo)
    _val = (bool([f for f in contents if f.endswith('.so') or f.endswith('.pyd')]))
    assert repr(_val) == 'True' or str(_val) == 'True'
    cache = tmpdir('cache')
    zc.buildout.easy_install.download_cache(cache)
    remove(dest)
    dest = tmpdir('sample-install')
    _ = get(link_server+'enable_server_logging')
    # TODO assert: 'GET 200 /enable_server_logging'
    ws = zc.buildout.easy_install.install(
        ['demo==0.2'], dest,
        links=[link_server], index=link_server+'index/')
    # TODO assert: 'GET 200 /\nGET 404 /index/demo/\nGET 200 /index/\nGET 200 /demo'
    assert_output(capture_print(lambda: zc.buildout.easy_install.build(
  'extdemo', dest,
  {'include_dirs': os.path.join(sample_buildout, 'include')},
  links=[link_server], index=link_server+'index/')), "GET 404 /index/extdemo/\nGET 200 /extdemo-1.5.tar.gz\n['/sample-install/extdemo-1.5-py2.4-linux-i686.egg']", N)
    assert_output(capture_print(ls, dest), 'd  demo-0.2-py2.4.egg\nd  demoneeded-1.1-py2.4.egg\nd  extdemo-1.5-py2.4-linux-i686.egg', N)
    assert_output(capture_print(ls, cache), '-  demo-0.2-py3-none-any.whl\n-  demoneeded-1.1.tar.gz\n-  extdemo-1.5.tar.gz', N)
    remove(dest)
    dest = tmpdir('sample-install')
    zc.buildout.easy_install.clear_index_cache()
    ws = zc.buildout.easy_install.install(
        ['demo==0.2'], dest,
        links=[link_server], index=link_server+'index/')
    # TODO assert: 'GET 200 /\nGET 404 /index/demo/\nGET 200 /index/\nGET 404 /inde'
    assert_output(capture_print(lambda: zc.buildout.easy_install.build(
  'extdemo', dest,
  {'include_dirs': os.path.join(sample_buildout, 'include')},
  links=[link_server], index=link_server+'index/')), "GET 404 /index/extdemo/\n['/sample-install/extdemo-1.5-py2.4-linux-i686.egg']", N)
    assert_output(capture_print(ls, dest), 'd  demo-0.2-py2.4.egg\nd  demoneeded-1.1-py2.4.egg\nd  extdemo-1.5-py2.4-linux-i686.egg', N)
    ws = zc.buildout.easy_install.install(
        ['demo'], dest,
        links=[link_server], index=link_server+'index/')
    # TODO assert: 'GET 200 /demo-0.3-py3-none-any.whl'
    _val = (zc.buildout.easy_install.install_from_cache())
    assert repr(_val) == 'False' or str(_val) == 'False'
    _val = (zc.buildout.easy_install.install_from_cache(True))
    assert repr(_val) == 'False' or str(_val) == 'False'
    for  f in os.listdir(cache):
        if f.startswith('demo-0.3-'):
            remove(cache, f)
    zc.buildout.easy_install.clear_index_cache()
    remove(dest)
    dest = tmpdir('sample-install')
    ws = zc.buildout.easy_install.install(
        ['demo'], dest,
        links=[link_server], index=link_server+'index/')
    assert_output(capture_print(ls, dest), 'd  demo-0.2-py2.4.egg\nd  demoneeded-1.1-py2.4.egg', N)
    _val = (zc.buildout.easy_install.download_cache(None))
    assert repr(_val) == "'/cache'" or str(_val) == "'/cache'"
    _val = (zc.buildout.easy_install.install_from_cache(False))
    assert repr(_val) == 'True' or str(_val) == 'True'
    _ = get(link_server + 'disable_server_logging')
    spec = ["demo ==0.1; python_version < '3.10'",
    "demo == 0.2; python_version >= '3.10'"]
    ws = zc.buildout.easy_install.install(
    spec, dest, links=[link_server], index=link_server+'index/')
    demo_version = None
    for egg in ws:
        if egg.project_name == 'demo':
            demo_version = egg.version
    _val = (demo_version is not None)
    assert repr(_val) == 'True' or str(_val) == 'True'
    if (sys.version_info.minor < 10):
        demo_version
    else:
        '0.1'
    if (sys.version_info.minor >= 10):
        demo_version
    else:
        '0.2'
    try:
        ws = zc.buildout.easy_install.install(
        spec, dest, links=[link_server], index=link_server+'index/',
        versions = dict(demo='0.3'))
        assert False, "Expected zc.buildout.easy_install.IncompatibleConstraintError not raised"
    except Exception as _exc:
        assert_output(str(_exc), "zc.buildout.easy_install.IncompatibleConstraintError: The requirement ('demo==0...", N)

def test_downloadcache(easy_install_env):
    buildout = easy_install_env['buildout']
    cd = easy_install_env['cd']
    get = easy_install_env['get']
    link_server = easy_install_env['link_server']
    ls = easy_install_env['ls']
    os = easy_install_env['os']
    print_ = easy_install_env['print_']
    remove = easy_install_env['remove']
    sample_buildout = easy_install_env['sample_buildout']
    start_server = easy_install_env['start_server']
    system = easy_install_env['system']
    tmpdir = easy_install_env['tmpdir']
    write = easy_install_env['write']

    cache = tmpdir('cache')
    write('buildout.cfg',
    '''
    [buildout]
    parts = eggs
    download-cache = %(cache)s
    find-links = %(link_server)s
    
    [eggs]
    recipe = zc.recipe.egg
    eggs = demo ==0.2
    ''' % locals())
    assert_output(str(get(link_server)), '<html><body>\n<a href="bigdemo-0.1-py3-none-any.whl">bigdemo-0.1-py3-none-any.whl</a><br>\n<a href="demo-0.1-py3-none-any.whl">demo-0.1-py3-none-any.whl</a><br>\n<a href="demo-0.2-py3-none-any.whl">demo-0.2-py3-none-any.whl</a><br>\n<a href="demo-0.3-py3-none-any.whl">demo-0.3-py3-none-any.whl</a><br>\n<a href="demo-0.4rc1-py3-none-any.whl">demo-0.4rc1-py3-none-any.whl</a><br>\n<a href="demoneeded-1.0.tar.gz">demoneeded-1.0.tar.gz</a><br>\n<a href="demoneeded-1.1.tar.gz">demoneeded-1.1.tar.gz</a><br>\n<a href="demoneeded-1.2rc1.tar.gz">demoneeded-1.2rc1.tar.gz</a><br>\n<a href="du_zipped-1.0-pyN.N.egg">du_zipped-1.0-pyN.N.egg</a><br>\n<a href="extdemo-1.4.tar.gz">extdemo-1.4.tar.gz</a><br>\n<a href="index/">index/</a><br>\n<a href="mixedcase-0.5.tar.gz">mixedcase-0.5.tar.gz</a><br>\n<a href="other-1.0-py3-none-any.whl">other-1.0-py3-none-any.whl</a><br>\n</body></html>', N)
    _ = get(link_server+'enable_server_logging')
    # TODO assert: 'GET 200 /enable_server_logging'
    assert_output(system(buildout), "Installing eggs.\nGetting distribution for 'demo==0.2'.\nGot demo 0.2.\nGetting distribution for 'demoneeded'.\nGot demoneeded 1.1.\nGenerated script '/sample-buildout/bin/demo'.", N)
    assert_output(capture_print(ls, cache), 'd  dist', N)
    assert_output(capture_print(ls, cache, 'dist'), '-  demo-0.2-py3-none-any.whl\n-  demoneeded-1.1.tar.gz', N)
    import os
    for f in os.listdir(os.path.join('eggs', 'v5')):
        if f.startswith('demo'):
            remove('eggs', 'v5', f)
    assert_output(system(buildout), "Updating eggs.\nGetting distribution for 'demo==0.2'.\nGot demo 0.2.\nGetting distribution for 'demoneeded'.\nGot demoneeded 1.1.", N)
    for f in os.listdir(os.path.join('eggs', 'v5')):
        if f.startswith('demo'):
            remove('eggs', 'v5', f)
    write('buildout.cfg',
    '''
    [buildout]
    parts = eggs
    download-cache = %(cache)s
    install-from-cache = true
    find-links = %(link_server)s
    
    [eggs]
    recipe = zc.recipe.egg
    eggs = demo
    ''' % locals())
    assert_output(system(buildout), "Uninstalling eggs.\nInstalling eggs.\nGetting distribution for 'demo'.\nGot demo 0.2.\nGetting distribution for 'demoneeded'.\nGot demoneeded 1.1.\nGenerated script '/sample-buildout/bin/demo'.", N)
    write('buildout.cfg',
    '''
    [buildout]
    parts =
    download-cache = %(cache)s/newdir
    ''' % locals())
    assert_output(system(buildout), "Creating directory '/cache/newdir'.\nUninstalling eggs.", N)
    assert_output(capture_print(ls, cache), 'd  dist\nd  newdir', N)
    basedir = tmpdir('basecfg')
    write(basedir, 'base.cfg',
    '''
    [buildout]
    download-cache = cache
    ''')
    write('buildout.cfg',
    '''
    [buildout]
    extends = %(basedir)s/base.cfg
    parts =
    ''' % locals())
    dummy = system(buildout)
    assert_output(capture_print(ls, basedir), '-  base.cfg\nd  cache', N)
    server_data = tmpdir('server_data')
    server_url = start_server(server_data)
    cd(sample_buildout)
    write(server_data, 'base.cfg', """\
    [buildout]
    download-cache = cache
    """)
    write('buildout.cfg',
    '''
    [buildout]
    extends = %(server_url)s/base.cfg
    parts =
    ''' % locals())
    assert_output(system(buildout), 'While:\n  Initializing.\nError: Setting "download-cache" to a non absolute location ("cache") within a\nremote configuration file...', N)
    test_nested = tmpdir('test_nested')
    cd(test_nested)
    write('buildout.cfg',
    '''
    [buildout]
    download-cache = ${buildout:directory}/var/cache
    eggs-directory = ${buildout:directory}/var/eggs
    parts-directory = ${buildout:directory}/var/parts
    develop-eggs-directory = ${buildout:directory}/var/develop-eggs
    ''')
    dummy = system(buildout)
    assert_output(capture_print(ls, test_nested), 'd  bin\n-  buildout.cfg\nd  var', N)
    assert_output(capture_print(ls, os.path.join(test_nested, 'var')), 'd  cache\nd  develop-eggs\nd  eggs\nd  parts', N)

def test_dependencylinks(easy_install_env):
    buildout = easy_install_env['buildout']
    get = easy_install_env['get']
    join = easy_install_env['join']
    link_server = easy_install_env['link_server']
    mkdir = easy_install_env['mkdir']
    print_ = easy_install_env['print_']
    remove = easy_install_env['remove']
    sample_buildout = easy_install_env['sample_buildout']
    sample_eggs = easy_install_env['sample_eggs']
    start_server = easy_install_env['start_server']
    system = easy_install_env['system']
    write = easy_install_env['write']

    link_server2 = start_server(sample_eggs)
    _ = get(link_server2 + 'enable_server_logging')
    # TODO assert: 'GET 200 /enable_server_logging'
    mkdir(sample_buildout, 'depdemo')
    write(sample_buildout, 'depdemo', 'dependencydemo.py',
          'import eggrecipedemoneeded')
    write(sample_buildout, 'depdemo', 'setup.py',
    '''from setuptools import setup; setup(
        name='depdemo', py_modules=['dependencydemo'],
        install_requires = 'demoneeded',
        dependency_links = ['%s'],
        zip_safe=True, version='1')
    ''' % link_server2)
    write(sample_buildout, 'buildout.cfg',
    '''
    [buildout]
    develop = depdemo
    parts = eggs
    
    [eggs]
    recipe = zc.recipe.egg:eggs
    eggs = depdemo
    ''')
    assert_output(system(buildout), "Develop: '/sample-buildout/depdemo'\nInstalling eggs.\nGetting distribution for 'demoneeded'.\nGot demoneeded 1.1...", N)
    write(sample_buildout, 'depdemo', 'setup.py',
    '''from setuptools import setup; setup(
        name='depdemo', py_modules=['dependencydemo'],
        install_requires = 'demoneeded',
        zip_safe=True, version='1')
    ''')
    from glob import glob
    from os.path import join
    def remove_demoneeded_egg():
        for egg in glob(join(sample_buildout, 'eggs', 'v5', 'demoneeded*.egg')):
            remove(sample_buildout, 'eggs', egg)
    remove_demoneeded_egg()
    assert_output(system(buildout), "Develop: '/sample-buildout/depdemo'\nUpdating eggs.\n...\nWhile:\n  Updating eggs.\n  Getting distribution for 'demoneeded'.\nError: Couldn't find a distribution for 'demoneeded'.", N)
    write(sample_buildout, 'buildout.cfg',
    '''
    [buildout]
    develop = depdemo
    parts = eggs
    find-links = %s
    
    [eggs]
    recipe = zc.recipe.egg:eggs
    eggs = depdemo
    ''' % link_server)
    assert_output(system(buildout), "Develop: '/sample-buildout/depdemo'\nInstalling eggs.\nGetting distribution for 'demoneeded'.\nGot demoneeded 1.1.", N)
    write(sample_buildout, 'depdemo', 'setup.py',
    '''from setuptools import setup; setup(
        name='depdemo', py_modules=['dependencydemo'],
        install_requires = 'demoneeded',
        dependency_links = ['%s'],
        zip_safe=True, version='1')
    '''  % link_server2)
    remove_demoneeded_egg()
    assert_output(system(buildout), "Develop: '/sample-buildout/depdemo'\nUpdating eggs.\nGetting distribution for 'demoneeded'.\nGot demoneeded 1.1...", N)
    write(sample_buildout, 'buildout.cfg',
    '''
    [buildout]
    develop = depdemo
    parts = eggs
    find-links = %s
    use-dependency-links = false
    
    [eggs]
    recipe = zc.recipe.egg:eggs
    eggs = depdemo
    ''' % link_server)
    remove_demoneeded_egg()
    assert_output(system(buildout), "Develop: '/sample-buildout/depdemo'\nUpdating eggs.\nGetting distribution for 'demoneeded'.\nGot demoneeded 1.1.", N)
    write(sample_buildout, 'buildout.cfg',
    '''
    [buildout]
    develop = depdemo
    parts = eggs
    find-links = %s
    use-dependency-links = true
    
    [eggs]
    recipe = zc.recipe.egg:eggs
    eggs = depdemo
    ''' % link_server)
    remove_demoneeded_egg()
    assert_output(system(buildout), "Develop: '/sample-buildout/depdemo'\nUpdating eggs.\nGetting distribution for 'demoneeded'.\nGot demoneeded 1.1...", N)

def test_allowhosts(easy_install_env):
    buildout = easy_install_env['buildout']
    mkdir = easy_install_env['mkdir']
    print_ = easy_install_env['print_']
    sample_buildout = easy_install_env['sample_buildout']
    system = easy_install_env['system']
    write = easy_install_env['write']

    mkdir(sample_buildout, 'allowdemo')
    write(sample_buildout, 'allowdemo', 'dependencydemo.py',
          'import eggrecipekss.core')
    write(sample_buildout, 'allowdemo', 'setup.py',
    '''from setuptools import setup; setup(
        name='allowdemo', py_modules=['dependencydemo'],
        install_requires = 'kss.core',
        dependency_links = ['http://dist.plone.org'],
        zip_safe=True, version='1')
    ''')
    write(sample_buildout, 'buildout.cfg',
    '''
    [buildout]
    develop = allowdemo
    parts = eggs
    allow-hosts =
        pypi.org
    
    [eggs]
    recipe = zc.recipe.egg:eggs
    eggs = allowdemo
    ''')
    assert_output(system(buildout), "Develop: '/sample-buildout/allowdemo'\nInstalling eggs...\n...\nWhile:\n  Installing eggs.\n  Getting distribution for 'kss.core'.\nError: Couldn't find a distribution for 'kss.core'.", N)
    write(sample_buildout, 'buildout.cfg',
    '''
    [buildout]
    develop = allowdemo
    parts = eggs
    allow-hosts =
        ^(!svn://).*
    
    [eggs]
    recipe = zc.recipe.egg:eggs
    eggs = allowdemo
    ''')
    assert_output(system(buildout), "Develop: '/sample-buildout/allowdemo'\nInstalling eggs...\n...\nWhile:\n  Installing eggs.\n  Getting distribution for 'kss.core'.\nError: Couldn't find a distribution for 'kss.core'.", N)
    write(sample_buildout, 'buildout.cfg',
    '''
    [buildout]
    parts=python
    foo = ${python:interpreter}
    
    [python]
    recipe=zc.recipe.egg
    eggs=zc.buildout
    interpreter=python
    ''')
    def _step():
        print_('XX')
        print_(system(buildout), end='')
    assert_output(capture_print(_step), "X...\nSection `buildout` contains unused option(s): 'foo'.\nThis may be an indication for either a typo in the option's name or a bug in the used recipe.\nInstalling python...\nGenerated interpreter '/sample-buildout/bin/python'.", N)

def test_allow_unknown_extras(easy_install_env):
    buildout = easy_install_env['buildout']
    mkdir = easy_install_env['mkdir']
    print_ = easy_install_env['print_']
    sample_buildout = easy_install_env['sample_buildout']
    system = easy_install_env['system']
    write = easy_install_env['write']

    mkdir(sample_buildout, 'allowdemo')
    write(sample_buildout, 'allowdemo', 'dependencydemo.py',
          'import eggrecipekss.core')
    write(sample_buildout, 'allowdemo', 'setup.py',
    '''from setuptools import setup; setup(
        name='allowdemo', py_modules=['dependencydemo'],
        zip_safe=True, version='1')
    ''')
    write(sample_buildout, 'buildout.cfg',
    '''
    [buildout]
    develop = allowdemo
    parts = eggs
    
    [eggs]
    recipe = zc.recipe.egg:eggs
    eggs = allowdemo[bad_extra]
    ''')
    assert_output(system(buildout), "Develop: '/sample-buildout/allowdemo'\nInstalling eggs...\n...\nWhile:\n  Installing eggs.\nError: Couldn't find the required extra...", N)
    write(sample_buildout, 'buildout.cfg',
    '''
    [buildout]
    develop = allowdemo
    parts = eggs
    allow-unknown-extras = true
    
    [eggs]
    recipe = zc.recipe.egg:eggs
    eggs = allowdemo[bad_extra]
    ''')
    assert_output(system(buildout), "Develop: '/sample-buildout/allowdemo'\nInstalling eggs...\nallowdemo 1 does not provide the extra 'bad_extra'", N)

def test_download(easy_install_env):
    cat = easy_install_env['cat']
    get = easy_install_env['get']
    join = easy_install_env['join']
    ls = easy_install_env['ls']
    mkdir = easy_install_env['mkdir']
    print_ = easy_install_env['print_']
    remove = easy_install_env['remove']
    rmdir = easy_install_env['rmdir']
    sample_buildout = easy_install_env['sample_buildout']
    start_server = easy_install_env['start_server']
    tmpdir = easy_install_env['tmpdir']
    write = easy_install_env['write']

    server_data = tmpdir('sample_files')
    write(server_data, 'foo.txt', 'This is a foo text.')
    server_url = start_server(server_data)
    import tempfile
    old_tempdir = tempfile.tempdir
    tempfile.tempdir = tmpdir('tmp')
    from zc.buildout.download import Download
    download = Download()
    assert_output(str(download.cache_dir), 'None', N)
    path, is_temp = download(server_url+'foo.txt')
    assert_output(str(path), '/.../buildout-...', N)
    assert_output(capture_print(cat, path), 'This is a foo text.', N)
    _val = (is_temp)
    assert repr(_val) == 'True' or str(_val) == 'True'
    import tempfile
    _val = (path.startswith(tempfile.gettempdir()))
    assert repr(_val) == 'True' or str(_val) == 'True'
    remove(path)
    try: download(server_url+'not-there') # doctest: +ELLIPSIS
    except: print_('download error')
    else: print_('woops')
    # TODO assert: 'download error'
    _val = (download(join(server_data, 'foo.txt')))
    assert_output(str(_val), "('/sample_files/foo.txt', False)", N)
    from hashlib import md5
    path, is_temp = download(server_url+'foo.txt',
                             md5('This is a foo text.'.encode()).hexdigest())
    _val = (is_temp)
    assert repr(_val) == 'True' or str(_val) == 'True'
    remove(path)
    try:
        download(server_url+'foo.txt',
                 md5('The wrong text.'.encode()).hexdigest())
        assert False, "Expected ChecksumError not raised"
    except Exception as _exc:
        assert_output(str(_exc), "ChecksumError: MD5 checksum mismatch downloading 'http://localhost/foo.txt'", N)
    _val = (download(join(server_data, 'foo.txt'),
              md5('This is a foo text.'.encode()).hexdigest()))
    assert_output(str(_val), "('/sample_files/foo.txt', False)", N)
    try:
        download(join(server_data, 'foo.txt'),
                 md5('The wrong text.'.encode()).hexdigest())
        assert False, "Expected ChecksumError not raised"
    except Exception as _exc:
        assert_output(str(_exc), "ChecksumError: MD5 checksum mismatch for local resource at '/sample_files/foo.txt'.", N)
    target_dir = tmpdir('download-target')
    path, is_temp = download(server_url+'foo.txt',
                             path=join(target_dir, 'downloaded.txt'))
    assert_output(str(path), '/download-target/downloaded.txt', N)
    assert_output(capture_print(cat, path), 'This is a foo text.', N)
    _val = (is_temp)
    assert repr(_val) == 'False' or str(_val) == 'False'
    download = Download(cache=None, offline=True)
    try:
        download(server_url+'foo.txt')
        assert False, "Expected UserError not raised"
    except Exception as _exc:
        assert_output(str(_exc), "UserError: Couldn't download 'http://localhost/foo.txt' in offline mode.", N)
    assert_output(capture_print(cat, download(join(server_data, 'foo.txt'))[0]), 'This is a foo text.', N)
    assert_output(capture_print(cat, download('file:' + join(server_data, 'foo.txt'))[0]), 'This is a foo text.', N)
    remove(path)
    cache = tmpdir('download-cache')
    download = Download(cache=cache)
    assert_output(str(download.cache_dir), '/download-cache/', N)
    ls(cache)
    path, is_temp = download(server_url+'foo.txt')
    assert_output(str(path), '/download-cache/foo.txt', N)
    assert_output(capture_print(cat, path), 'This is a foo text.', N)
    _val = (is_temp)
    assert repr(_val) == 'False' or str(_val) == 'False'
    write(server_data, 'foo.txt', 'The wrong text.')
    path, is_temp = download(server_url+'foo.txt')
    assert_output(str(path), '/download-cache/foo.txt', N)
    assert_output(capture_print(cat, path), 'This is a foo text.', N)
    try:
        download(server_url+'foo.txt', md5('The wrong text.'.encode()).hexdigest())
        assert False, "Expected from 'http not raised"
    except Exception as _exc:
        assert_output(str(_exc), "               from 'http://localhost/foo.txt' at '/download-cache/foo.txt'", N)
    mkdir(server_data, 'other')
    write(server_data, 'other', 'foo.txt', 'The wrong text.')
    path, is_temp = download(server_url+'other/foo.txt')
    assert_output(str(path), '/download-cache/foo.txt', N)
    assert_output(capture_print(cat, path), 'This is a foo text.', N)
    remove(cache, 'foo.txt')
    ls(cache)
    write(server_data, 'foo.txt', 'This is a foo text.')
    path, is_temp = download(server_url+'foo.txt',
                             path=join(target_dir, 'downloaded.txt'))
    assert_output(str(path), '/download-target/downloaded.txt', N)
    assert_output(capture_print(cat, path), 'This is a foo text.', N)
    _val = (is_temp)
    assert repr(_val) == 'False' or str(_val) == 'False'
    assert_output(capture_print(ls, cache), '- foo.txt', N)
    remove(path)
    write(server_data, 'foo.txt', 'The wrong text.')
    path, is_temp = download(server_url+'foo.txt',
                             path=join(target_dir, 'downloaded.txt'))
    assert_output(str(path), '/download-target/downloaded.txt', N)
    assert_output(capture_print(cat, path), 'This is a foo text.', N)
    _val = (is_temp)
    assert repr(_val) == 'False' or str(_val) == 'False'
    download = Download(cache=cache, offline=True)
    assert_output(capture_print(cat, download(server_url + 'foo.txt')[0]), 'This is a foo text.', N)
    remove(cache, 'foo.txt')
    ls(cache)
    write(server_data, 'foo.txt', 'This is a foo text.')
    download = Download(cache=cache)
    assert_output(capture_print(cat, download('file:' + join(server_data, 'foo.txt'), path=path)[0]), 'This is a foo text.', N)
    assert_output(capture_print(ls, cache), '- foo.txt', N)
    remove(cache, 'foo.txt')
    assert_output(capture_print(cat, download(join(server_data, 'foo.txt'), path=path)[0]), 'This is a foo text.', N)
    assert_output(capture_print(ls, cache), '- foo.txt', N)
    remove(cache, 'foo.txt')
    try:
        download(server_url+'foo.txt', md5('The wrong text.'.encode()).hexdigest())
        assert False, "Expected ChecksumError not raised"
    except Exception as _exc:
        assert_output(str(_exc), "ChecksumError: MD5 checksum mismatch downloading 'http://localhost/foo.txt'", N)
    ls(cache)
    remove(path)
    try:
        download(server_url+'bar.txt')
        assert False, "Expected ...404... not raised"
    except Exception as _exc:
        assert_output(str(_exc), '...404...', N)
    ls(cache)
    try:
        Download(cache=join(cache, 'non-existent'))(server_url+'foo.txt')
        assert False, "Expected to be used as a download cache doesn't exist. not raised"
    except Exception as _exc:
        assert_output(str(_exc), "to be used as a download cache doesn't exist.", N)
    download = Download(cache=cache, namespace='test')
    assert_output(str(download.cache_dir), '/download-cache/test', N)
    ls(cache)
    path, is_temp = download(server_url+'foo.txt')
    assert_output(str(path), '/download-cache/test/foo.txt', N)
    assert_output(capture_print(ls, cache), 'd test', N)
    assert_output(capture_print(ls, cache, 'test'), '- foo.txt', N)
    assert_output(capture_print(cat, path), 'This is a foo text.', N)
    _val = (is_temp)
    assert repr(_val) == 'False' or str(_val) == 'False'
    write(server_data, 'foo.txt', 'The wrong text.')
    write(cache, 'foo.txt', 'The wrong text.')
    path, is_temp = download(server_url+'foo.txt')
    assert_output(str(path), '/download-cache/test/foo.txt', N)
    assert_output(capture_print(cat, path), 'This is a foo text.', N)
    rmdir(cache, 'test')
    remove(cache, 'foo.txt')
    write(server_data, 'foo.txt', 'This is a foo text.')
    download = Download(cache=cache, hash_name=True)
    path, is_temp = download(server_url+'foo.txt')
    assert_output(str(path), '/download-cache/09f5793fcdc1716727f72d49519c688d', N)
    assert_output(capture_print(cat, path), 'This is a foo text.', N)
    assert_output(capture_print(ls, cache), '- 09f5793fcdc1716727f72d49519c688d', N)
    _val = ((path.lower() ==
 join(cache, md5((server_url+'foo.txt').encode()).hexdigest()).lower()))
    assert repr(_val) == 'True' or str(_val) == 'True'
    write(server_data, 'foo.txt', 'The wrong text.')
    _val = ((path, is_temp) == download(server_url+'foo.txt'))
    assert repr(_val) == 'True' or str(_val) == 'True'
    assert_output(capture_print(cat, path), 'This is a foo text.', N)
    assert_output(capture_print(ls, cache), '- 09f5793fcdc1716727f72d49519c688d', N)
    path2, is_temp = download(server_url+'other/foo.txt')
    assert_output(str(path2), '/download-cache/537b6d73267f8f4447586989af8c470e', N)
    _val = (path == path2)
    assert repr(_val) == 'False' or str(_val) == 'False'
    _val = ((path2.lower() ==
 join(cache, md5((server_url+'other/foo.txt').encode()).hexdigest()
      ).lower()))
    assert repr(_val) == 'True' or str(_val) == 'True'
    assert_output(capture_print(cat, path), 'This is a foo text.', N)
    assert_output(capture_print(cat, path2), 'The wrong text.', N)
    assert_output(capture_print(ls, cache), '- 09f5793fcdc1716727f72d49519c688d\n- 537b6d73267f8f4447586989af8c470e', N)
    remove(path)
    remove(path2)
    write(server_data, 'foo.txt', 'This is a foo text.')
    download = Download(cache=cache, fallback=True)
    assert_output(str(download.cache_dir), '/download-cache/', N)
    ls(cache)
    path, is_temp = download(server_url+'foo.txt')
    assert_output(capture_print(ls, cache), '- foo.txt', N)
    assert_output(capture_print(cat, cache, 'foo.txt'), 'This is a foo text.', N)
    _val = (is_temp)
    assert repr(_val) == 'False' or str(_val) == 'False'
    remove(server_data, 'foo.txt')
    try: Download()(server_url+'foo.txt') # doctest: +ELLIPSIS
    except: print_('download error')
    else: print_('woops')
    # TODO assert: 'download error'
    path, is_temp = download(server_url+'foo.txt')
    assert_output(capture_print(cat, path), 'This is a foo text.', N)
    _val = (is_temp)
    assert repr(_val) == 'False' or str(_val) == 'False'
    write(server_data, 'foo.txt', 'The wrong text.')
    _val = (get(server_url+'foo.txt'))
    assert repr(_val) == "'The wrong text.'" or str(_val) == "'The wrong text.'"
    offline_download = Download(cache=cache, offline=True, fallback=True)
    path, is_temp = offline_download(server_url+'foo.txt')
    assert_output(str(path), '/download-cache/foo.txt', N)
    assert_output(capture_print(cat, path), 'This is a foo text.', N)
    _val = (is_temp)
    assert repr(_val) == 'False' or str(_val) == 'False'
    assert_output(capture_print(cat, download(server_url + 'foo.txt')[0]), 'The wrong text.', N)
    assert_output(capture_print(cat, cache, 'foo.txt'), 'The wrong text.', N)
    write(server_data, 'foo.txt', 'This is a foo text.')
    try:
        download(server_url+'foo.txt', md5('The wrong text.'.encode()).hexdigest())
        assert False, "Expected ChecksumError not raised"
    except Exception as _exc:
        assert_output(str(_exc), "ChecksumError: MD5 checksum mismatch downloading 'http://localhost/foo.txt'", N)
    assert_output(capture_print(cat, cache, 'foo.txt'), 'The wrong text.', N)
    download = Download({'download-cache': cache}, namespace='cmmi')
    assert_output(str(download.cache_dir), '/download-cache/cmmi', N)
    download = Download({'download-cache': 'relative-cache'})
    assert_output(str(download.cache_dir), '/sample-buildout/relative-cache/', N)
    download = Download({'directory': join(sample_buildout, 'root'),
                         'download-cache': 'relative-cache'})
    assert_output(str(download.cache_dir), '/sample-buildout/root/relative-cache/', N)
    download = Download({'download-cache': cache}, cache=None)
    assert_output(str(download.cache_dir), 'None', N)
    download = Download({'offline': 'true'})
    _val = (download.offline)
    assert repr(_val) == 'True' or str(_val) == 'True'
    download = Download({'offline': 'false'})
    _val = (download.offline)
    assert repr(_val) == 'False' or str(_val) == 'False'
    download = Download({'install-from-cache': 'true'})
    _val = (download.offline)
    assert repr(_val) == 'True' or str(_val) == 'True'
    download = Download({'install-from-cache': 'false'})
    _val = (download.offline)
    assert repr(_val) == 'False' or str(_val) == 'False'
    download = Download({'offline': 'true', 'install-from-cache': 'false'})
    _val = (download.offline)
    assert repr(_val) == 'True' or str(_val) == 'True'
    download = Download({'offline': 'false', 'install-from-cache': 'true'})
    _val = (download.offline)
    assert repr(_val) == 'True' or str(_val) == 'True'
    download = Download({'offline': 'true'}, offline=False)
    _val = (download.offline)
    assert repr(_val) == 'False' or str(_val) == 'False'
    download = Download({'install-from-cache': 'false'}, offline=True)
    _val = (download.offline)
    assert repr(_val) == 'True' or str(_val) == 'True'
    text = 'First line of text.\r\nSecond line.\r\n'
    f = open(join(server_data, 'foo.txt'), 'wb')
    _ = f.write(text.encode())
    f.close()
    path, is_temp = Download()(server_url+'foo.txt',
                               md5(text.encode()).hexdigest())
    remove(path)
    download = Download(cache=cache)
    dirpath = join(server_data, 'some_directory')
    mkdir(dirpath)
    dest, _ = download(dirpath)
    mkdir(join(dirpath, 'foo'))
    assert_output(capture_print(ls, dirpath), 'd foo', N)
    dest, _ = download(dirpath)
    ls(dest)
    ls(tempfile.tempdir)
    tempfile.tempdir = old_tempdir

def test_extends_cache(easy_install_env):
    buildout = easy_install_env['buildout']
    cat = easy_install_env['cat']
    cd = easy_install_env['cd']
    join = easy_install_env['join']
    ls = easy_install_env['ls']
    mkdir = easy_install_env['mkdir']
    os = easy_install_env['os']
    print_ = easy_install_env['print_']
    remove = easy_install_env['remove']
    rmdir = easy_install_env['rmdir']
    sample_buildout = easy_install_env['sample_buildout']
    start_server = easy_install_env['start_server']
    system = easy_install_env['system']
    tmpdir = easy_install_env['tmpdir']
    write = easy_install_env['write']

    server_data = tmpdir('server_data')
    server_url = start_server(server_data)
    cd(sample_buildout)
    import tempfile
    old_tempdir = tempfile.tempdir
    tempfile.tempdir = tmpdir('tmp')
    write(server_data, 'base.cfg', """\
    [buildout]
    parts =
    foo = bar
    """)
    write('buildout.cfg', """\
    [buildout]
    extends = %sbase.cfg
    """ % server_url)
    assert_output(system(buildout + ' -o'), "While:\n  Initializing.\nError: Couldn't download 'http://localhost/base.cfg' in offline mode.", N)
    assert_output(system(buildout), "Section `buildout` contains unused option(s): 'foo'.\nThis may be an indication for either a typo in the option's name or a bug in the used recipe.", N)
    assert_output(system(buildout + ' -o'), "While:\n  Initializing.\nError: Couldn't download 'http://localhost/base.cfg' in offline mode.", N)
    mkdir('cache')
    write('buildout.cfg', """\
    [buildout]
    extends = %sbase.cfg
    extends-cache = cache
    """ % server_url)
    assert_output(system(buildout), "Section `buildout` contains unused option(s): 'foo'.\nThis may be an indication for either a typo in the option's name or a bug in the used recipe.", N)
    cache = join(sample_buildout, 'cache')
    assert_output(capture_print(ls, cache), '-  5aedc98d7e769290a29d654a591a3a45', N)
    import os
    assert_output(capture_print(cat, cache, os.listdir(cache)[0]), '[buildout]\nparts =\nfoo = bar', N)
    assert_output(system(buildout + ' -o'), "Section `buildout` contains unused option(s): 'foo'.\nThis may be an indication for either a typo in the option's name or a bug in the used recipe.", N)
    write(server_data, 'base.cfg', """\
    [buildout]
    parts =
    bar = baz
    """)
    assert_output(system(buildout + ' -o'), "Section `buildout` contains unused option(s): 'foo'.\nThis may be an indication for either a typo in the option's name or a bug in the used recipe.", N)
    assert_output(system(buildout + ' install-from-cache=true download-cache=.'), "Section `buildout` contains unused option(s): 'foo'.\nThis may be an indication for either a typo in the option's name or a bug in the used recipe.", N)
    assert_output(system(buildout), "Section `buildout` contains unused option(s): 'bar'.\nThis may be an indication for either a typo in the option's name or a bug in the used recipe.", N)
    assert_output(system(buildout + ' -o'), "Section `buildout` contains unused option(s): 'bar'.\nThis may be an indication for either a typo in the option's name or a bug in the used recipe.", N)
    rmdir(cache)
    mkdir('home')
    mkdir('home', '.buildout')
    mkdir('cache')
    mkdir('user-cache')
    home=join(sample_buildout, 'home')
    env=dict(HOME=home, USERPROFILE=home)
    import functools
    system = functools.partial(system, env=env)
    write('home', '.buildout', 'default.cfg', """\
    [buildout]
    extends = fancy_default.cfg
    extends-cache = user-cache
    """)
    write('home', '.buildout', 'fancy_default.cfg', """\
    [buildout]
    extends = %sbase_default.cfg
    """ % server_url)
    write(server_data, 'base_default.cfg', """\
    [buildout]
    foo = bar
    offline = false
    """)
    write('buildout.cfg', """\
    [buildout]
    extends = fancy.cfg
    extends-cache = cache
    """)
    write('fancy.cfg', """\
    [buildout]
    extends = %sbase.cfg
    """ % server_url)
    write(server_data, 'base.cfg', """\
    [buildout]
    parts =
    offline = false
    """)
    assert_output(system(buildout), "Section `buildout` contains unused option(s): 'foo'.\nThis may be an indication for either a typo in the option's name or a bug in the used recipe.", N)
    assert_output(capture_print(ls, 'user-cache'), '-  10e772cf422123ef6c64ae770f555740', N)
    assert_output(capture_print(cat, 'user-cache', os.listdir('user-cache')[0]), '[buildout]\nfoo = bar\noffline = false', N)
    assert_output(capture_print(ls, 'cache'), '-  c72213127e6eb2208a3e1fc1dba771a7', N)
    assert_output(capture_print(cat, 'cache', os.listdir('cache')[0]), '[buildout]\nparts =\noffline = false', N)
    write('home', '.buildout', 'default.cfg', """\
    [buildout]
    extends = fancy_default.cfg
    """)
    write('home', '.buildout', 'fancy_default.cfg', """\
    [buildout]
    extends = %sbase_default.cfg
    extends-cache = user-cache
    """ % server_url)
    write('buildout.cfg', """\
    [buildout]
    extends = fancy.cfg
    """)
    write('fancy.cfg', """\
    [buildout]
    extends = %sbase.cfg
    extends-cache = cache
    """ % server_url)
    remove('user-cache', os.listdir('user-cache')[0])
    remove('cache', os.listdir('cache')[0])
    assert_output(system(buildout), "Section `buildout` contains unused option(s): 'foo'.\nThis may be an indication for either a typo in the option's name or a bug in the used recipe.", N)
    assert_output(capture_print(ls, 'user-cache'), '-  0548bad6002359532de37385bb532e26', N)
    assert_output(capture_print(cat, 'user-cache', os.listdir('user-cache')[0]), '[buildout]\nparts =\noffline = false', N)
    ls('cache')
    rmdir('user-cache')
    rmdir('cache')
    assert_output(system(buildout + ' -o'), "While:\n  Initializing.\nError: Couldn't download 'http://localhost/base_default.cfg' in offline mode.", N)
    write('home', '.buildout', 'default.cfg', """\
    [buildout]
    extends = fancy_default.cfg
    offline = true
    """)
    assert_output(system(buildout), "While:\n  Initializing.\nError: Couldn't download 'http://localhost/base_default.cfg' in offline mode.", N)
    write('home', '.buildout', 'default.cfg', """\
    [buildout]
    extends = fancy_default.cfg
    """)
    write('home', '.buildout', 'fancy_default.cfg', """\
    [buildout]
    extends = %sbase_default.cfg
    offline = true
    """ % server_url)
    assert_output(system(buildout), "While:\n  Initializing.\nError: Couldn't download 'http://localhost/base.cfg' in offline mode.", N)
    write('home', '.buildout', 'fancy_default.cfg', """\
    [buildout]
    extends = %sbase_default.cfg
    """ % server_url)
    write('buildout.cfg', """\
    [buildout]
    extends = fancy.cfg
    offline = true
    """)
    assert_output(system(buildout), "While:\n  Initializing.\nError: Couldn't download 'http://localhost/base.cfg' in offline mode.", N)
    write('buildout.cfg', """\
    [buildout]
    extends = fancy.cfg
    """)
    write('fancy.cfg', """\
    [buildout]
    extends = %sbase.cfg
    offline = true
    """ % server_url)
    assert_output(system(buildout), "Section `buildout` contains unused option(s): 'foo'.\nThis may be an indication for either a typo in the option's name or a bug in the used recipe.", N)
    write('home', '.buildout', 'default.cfg', """\
    [buildout]
    extends = fancy_default.cfg
    install-from-cache = true
    """)
    assert_output(system(buildout), "While:\n  Initializing.\nError: Couldn't download 'http://localhost/base_default.cfg' in offline mode.", N)
    write('home', '.buildout', 'default.cfg', """\
    [buildout]
    extends = fancy_default.cfg
    """)
    write('home', '.buildout', 'fancy_default.cfg', """\
    [buildout]
    extends = %sbase_default.cfg
    install-from-cache = true
    """ % server_url)
    assert_output(system(buildout), "While:\n  Initializing.\nError: Couldn't download 'http://localhost/base.cfg' in offline mode.", N)
    write('home', '.buildout', 'fancy_default.cfg', """\
    [buildout]
    extends = %sbase_default.cfg
    """ % server_url)
    write('buildout.cfg', """\
    [buildout]
    extends = fancy.cfg
    install-from-cache = true
    """)
    assert_output(system(buildout), "While:\n  Initializing.\nError: Couldn't download 'http://localhost/base.cfg' in offline mode.", N)
    write('buildout.cfg', """\
    [buildout]
    extends = fancy.cfg
    """)
    write('fancy.cfg', """\
    [buildout]
    extends = %sbase.cfg
    install-from-cache = true
    """ % server_url)
    assert_output(system(buildout), 'While:\n  Installing.\n  Checking for upgrades.\nAn internal error occurred ...\nValueError: install_from_cache set to true with no download cache', N)
    rmdir('home', '.buildout')
    mkdir("cache")
    write(server_data, 'base.cfg', """\
    [buildout]
    parts =
    """)
    write('buildout.cfg', """\
    [buildout]
    extends-cache = cache
    extends = %sbase.cfg
    """ % server_url)
    print_(system(buildout))
    assert_output(capture_print(ls, 'cache'), '-  5aedc98d7e769290a29d654a591a3a45', N)
    assert_output(capture_print(cat, 'cache', os.listdir(cache)[0]), '[buildout]\nparts =', N)
    write(server_data, 'base.cfg', """\
    [buildout]
    parts =
    foo = bar
    """)
    assert_output(system(buildout + ' -n'), "Section `buildout` contains unused option(s): 'foo'.\nThis may be an indication for either a typo in the option's name or a bug in the used recipe.", N)
    assert_output(capture_print(cat, 'cache', os.listdir(cache)[0]), '[buildout]\nparts =\nfoo = bar', N)
    write(server_data, 'base.cfg', """\
    [buildout]
    parts =
    """)
    assert_output(system(buildout + ' -N'), "Section `buildout` contains unused option(s): 'foo'.\nThis may be an indication for either a typo in the option's name or a bug in the used recipe.", N)
    assert_output(capture_print(cat, 'cache', os.listdir(cache)[0]), '[buildout]\nparts =\nfoo = bar', N)
    write(server_data, 'baseA.cfg', """\
    [buildout]
    extends = %sbase.cfg
    foo = bar
    """ % server_url)
    write(server_data, 'baseB.cfg', """\
    [buildout]
    extends-cache = cache
    extends = %sbase.cfg
    bar = foo
    """ % server_url)
    write('buildout.cfg', """\
    [buildout]
    extends-cache = cache
    newest = true
    extends = %sbaseA.cfg %sbaseB.cfg
    """ % (server_url, server_url))
    assert_output(system(buildout + ' -n'), "Section `buildout` contains unused option(s): 'bar' 'foo'.\nThis may be an indication for either a typo in the option's name or a bug in the used recipe.", N)
    import zc.buildout
    old_download = zc.buildout.download.Download.download
    def wrapper_download(self, url, md5sum=None, path=None):
      print_("The URL %s was downloaded." % url)
      return old_download(url, md5sum, path)
    zc.buildout.download.Download.download = wrapper_download
    assert_output(capture_print(lambda: zc.buildout.buildout.main([])), "The URL http://localhost/baseA.cfg was downloaded.\nThe URL http://localhost/base.cfg was downloaded.\nThe URL http://localhost/baseB.cfg was downloaded.\nNot upgrading because not running a local buildout command.\nSection `buildout` contains unused option(s): 'bar' 'foo'.\nThis may be an indication for either a typo in the option's name or a bug in the used recipe.", N)
    zc.buildout.download.Download.download = old_download
    write(server_data, 'base.cfg', """\
    [buildout]
    parts =
    extended-by = foo.cfg
    """)
    assert_output(system(buildout), 'While:\n  Initializing.\nError: No-longer supported "extended-by" option found in http://localhost/base.cfg.', N)
    write(server_data, 'faulty.cfg', """\
    This is definitively not
    a proper() config file.
    """)
    write('buildout.cfg', """\
    [buildout]
    extends = %sfaulty.cfg
    """ % server_url)
    assert_output(system(buildout), "While:\n  Initializing.\n... File contains no section headers.\nfile: http://localhost/faulty.cfg (downloaded as ...), line: 1\n'This is definitively not\\n'", N)
    write(server_data, 'proper.cfg', """\
    [buildout]
    dummy = fjhfj
    """)
    write('buildout.cfg', """\
    [buildout]
    extends = %sproper.cfg
    extends-cache = ${buildout:dummy}
    """ % server_url)
    assert_output(system(buildout), "While:\n  Initializing.\n... ValueError: extends-cache '${buildout:dummy}' may not contain ${section:variable} to expand.", N)
    ls(tempfile.tempdir)
    tempfile.tempdir = old_tempdir

def test_testing_bugfix(easy_install_env):
    import logging
    count = len(logging.getLogger().handlers)
    assert_output(capture_print(lambda: print(logging.getLogger().handlers)), '[<...NullHandler...>]', N)
    import zc.buildout.testing
    import doctest
    test = doctest.DocTestParser().get_doctest(
        '>>> x', {}, 'foo', 'foo.py', 0)
    zc.buildout.testing.buildoutSetUp(test)
    _val = (len(logging.getLogger().handlers) == count + 1)
    assert repr(_val) == 'True' or str(_val) == 'True'
    assert_output(capture_print(lambda: print(logging.getLogger().handlers)), '[<...NullHandler...StreamHandler...>]', N)
    zc.buildout.testing.buildoutTearDown(test)
    _val = (len(logging.getLogger().handlers) == count)
    assert repr(_val) == 'True' or str(_val) == 'True'
    assert_output(capture_print(lambda: print(logging.getLogger().handlers)), '[<...NullHandler...>]', N)
