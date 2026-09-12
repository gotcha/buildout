##############################################################################
#
# Copyright (c) 2006 Zope Foundation and Contributors.
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
"""Buildout package
"""
# do not change the import order
# deleting the spec_for_pip hack needs to be done before importing pip
# see https://github.com/pypa/pip/issues/8761 to understand
# the reason for the hack.
# I think it is reasonable to assume we will not run into the race.
import setuptools

try:
    from _distutils_hack import DistutilsMetaFinder
    if hasattr(DistutilsMetaFinder, 'spec_for_pip'):
        del DistutilsMetaFinder.spec_for_pip
except ImportError:
    pass

import pip  # NOQA

import warnings
from pkg_resources import PkgResourcesDeprecationWarning
warnings.filterwarnings('ignore', category=PkgResourcesDeprecationWarning)
warnings.filterwarnings('ignore', message='Setuptools is replacing distutils.')

import sys
import contextlib
from typing import Any, Iterator
import zc.buildout.patches  # NOQA


WINDOWS = sys.platform.startswith('win')


class UserError(Exception):
    """Errors made by a user
    """

    def __str__(self) -> str:
        return " ".join(map(str, self.args))


@contextlib.contextmanager
def _activity(message: str, *args: Any) -> Iterator[None]:
    """Record what buildout was doing, for error reporting.

    Attaches the activity to a propagating exception: a context
    manager's own state unwinds with the stack, but the exception
    object travels to the handler in ``main()`` that prints it
    (``While:`` lines). Lives in the package root so both buildout.py
    and easy_install.py can use it without an import cycle.
    """
    try:
        yield
    except BaseException as e:
        setattr(e, '_zc_doing',
                getattr(e, '_zc_doing', []) + [(message, args)])
        raise
