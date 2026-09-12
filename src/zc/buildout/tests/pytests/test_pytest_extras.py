"""Pytest port of test_extras.py — no DocTestRunner."""
import zc.buildout.easy_install


def test_install_extras_with_greater_than_constrains(easy_install_env):
    sample_eggs = easy_install_env['sample_eggs']
    tmpdir = easy_install_env['tmpdir']
    cd = easy_install_env['cd']
    mkdir = easy_install_env['mkdir']
    sdist = easy_install_env['sdist']

    # There was a bug that caused extras in requirements to be lost.
    working = tmpdir('working')
    cd(working)
    mkdir('dependency')
    cd('dependency')
    with open('setup.py', 'w') as f:
        _ = f.write('''
from setuptools import setup
setup(name='dependency', version='1.0',
      url='x', author='x', author_email='x',
      py_modules=['t'])
''')
    open('README', 'w').close()
    open('t.py', 'w').close()

    sdist('.', sample_eggs)
    cd(working)
    mkdir('extras')
    cd('extras')
    with open('setup.py', 'w') as f:
        _ = f.write('''
from setuptools import setup
setup(name='extraversiondemo', version='1.0',
      url='x', author='x', author_email='x',
      extras_require=dict(foo=['dependency']), py_modules=['t'])
''')
    open('README', 'w').close()
    open('t.py', 'w').close()

    sdist('.', sample_eggs)
    mkdir('dest')
    ws = zc.buildout.easy_install.install(
        ['extraversiondemo[foo]'], 'dest', links=[sample_eggs],
        versions=dict(extraversiondemo='1.0', dependency='>0.9')
    )
    assert sorted(dist.key for dist in ws) == ['dependency', 'extraversiondemo']
