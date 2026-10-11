##############################################################################
#
# Copyright (c) 2006-2009 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
name = "zc.buildout"
version = "5.3.0a3.dev0"

import os

from setuptools import setup


def read(*rnames):
    with open(os.path.join(os.path.dirname(__file__), *rnames)) as f:
        return f.read()

long_description= read('README.rst') + '\n' + read('CHANGES.rst')

entry_points = f"""
[console_scripts]
buildout = {name}.buildout:main

[zc.buildout]
debug = {name}.testrecipes:Debug

"""

setup(
    name = name,
    version = version,
    author = "Jim Fulton",
    author_email = "jim@zope.com",
    description = "System for managing development buildouts",
    long_description=long_description,
    license = "ZPL-2.1",
    keywords = "development build",
    url='http://buildout.org',
    packages = [
        'zc',
        'zc.buildout',
        'zc.buildout._vendor',
        'zc.buildout._vendor.pkg_resources',
    ],
    package_dir = {'': 'src'},
    python_requires = '>=3.10',
    install_requires = [
        # setuptools ships on win32 only: uv-mode Windows script and
        # interpreter generation still imports it (scripts.py calls
        # easy_install.get_win_launcher, which resolves
        # setuptools._scripts) until the Phase-4 launcher decision
        # lands.  On POSIX every setuptools import is pip-mode or
        # legacy-source-build gated, so there it comes from the
        # 'zc.buildout[pip]' extra below.
        'setuptools>=75.8.2; sys_platform == "win32"',
        'packaging>=23.2',
        # pip is NOT a dependency: the uv installer never touches it,
        # the legacy pip installer requires it via the
        # 'zc.buildout[pip]' extra below, and pip mode raises a clear
        # error when pip is missing (guard in
        # easy_install._compute_toolchain).
        # platformdirs stays: the vendored pkg_resources copy
        # hard-imports it (see src/zc/buildout/_vendor/README.rst) and
        # the bootstrap command reaches pkg_resources in both
        # installer modes (buildout.Buildout.bootstrap).
        'platformdirs',
        # wheel is gone: nothing imports it; only the self-upgrade
        # check still resolves it by name (buildout._maybe_upgrade),
        # to be installed on demand by the active installer.
        # 0.12.11 is the floor: earlier 0.12.x serve their own cache on
        # --offline resolves, breaking install-from-cache isolation
        # (easy_install.txt and downloadcache.txt pin that contract).
        'uv>=0.12.11',
        'tomli; python_version < "3.11"',
    ],
    include_package_data = True,
    entry_points = entry_points,
    extras_require = {
        "test": ['zope.testing', 'manuel',
              'bobo ==2.3.0', 'zdaemon', 'zc.zdaemonrecipe',
              'zc.recipe.deployment'],
        "pip": ["pip>=25.0", "setuptools>=75.8.2"]},
    zip_safe=False,
    classifiers = [
       'Development Status :: 6 - Mature',
       'Intended Audience :: Developers',
       'Programming Language :: Python',
       'Programming Language :: Python :: 3.10',
       'Programming Language :: Python :: 3.11',
       'Programming Language :: Python :: 3.12',
       'Programming Language :: Python :: 3.13',
       'Programming Language :: Python :: 3.14',
       'Topic :: Software Development :: Build Tools',
       'Topic :: Software Development :: Libraries :: Python Modules',
       ],
    )
