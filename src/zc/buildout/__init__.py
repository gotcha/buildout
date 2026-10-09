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
from __future__ import annotations

# do not change the import order
# deleting the spec_for_pip hack needs to be done before importing pip
# see https://github.com/pypa/pip/issues/8761 to understand
# the reason for the hack.
# I think it is reasonable to assume we will not run into the race.
# pip itself is no longer imported here: it is not a dependency of
# zc.buildout anymore — only the legacy pip installer needs it, and it
# provisions it on demand (see install_backend._provision_pip).  The
# hack deletion stays unconditional so a later pip import in pip mode
# is always safe.

try:
    from _distutils_hack import DistutilsMetaFinder
    if hasattr(DistutilsMetaFinder, 'spec_for_pip'):
        del DistutilsMetaFinder.spec_for_pip
except ImportError:
    pass

import sys

# zc.buildout ships its own copy of pkg_resources, taken from setuptools
# 81.0.0 (the last release that contained it).  `import pkg_resources` by
# anyone — buildout's own modules, recipes, extensions running inside the
# buildout process — must resolve to that copy, with full module identity
# (the same object under both names in sys.modules).  The mapping happens
# on demand via the meta_path bridge below: importing zc.buildout itself
# loads no pkg_resources at all, so a uv-mode run that never resolves
# distributions never pays for it.  If other code already imported a real
# pkg_resources before the bridge fires (only possible with
# setuptools < 82), that copy keeps its place: the import then resolves
# straight from sys.modules and finders are never consulted.
# See src/zc/buildout/_vendor/README.rst and
# https://github.com/buildout/buildout/issues/685

import importlib.abc
import importlib.machinery
import warnings
from collections.abc import Sequence
from types import ModuleType


def _install_pkg_resources_warning_filters(
        pkg_resources_module: ModuleType) -> None:
    """Silence the pkg_resources copy's own deprecation noise.

    Runs when a pkg_resources copy becomes the live one: from the
    bridge below for the vendored copy, or at package init (end of this
    block) for a copy some other code pre-imported (setuptools < 82).
    """
    warnings.filterwarnings(
        'ignore', category=pkg_resources_module.PkgResourcesDeprecationWarning)
    warnings.filterwarnings(
        'ignore', message='Setuptools is replacing distutils.')


class _VendoredPkgResourcesLoader(importlib.abc.Loader):
    """Load `pkg_resources` as an alias of the vendored copy.

    The import machinery registers a fresh module before calling
    exec_module and takes whatever sits in sys.modules afterwards as
    the result; swapping the entry here makes `import pkg_resources`
    return the vendored copy, so both names hold the same object.
    """

    def exec_module(self, module: ModuleType) -> None:
        from zc.buildout._vendor import pkg_resources as vendored
        _install_pkg_resources_warning_filters(vendored)
        sys.modules['pkg_resources'] = vendored
        # The patches land before any pkg_resources object is used, as
        # they did when the alias was installed eagerly.  patches is
        # long imported by the time this bridge can fire (nothing in the
        # zc.buildout import chain loads pkg_resources; the hermetic
        # import contract test pins that).
        from zc.buildout import patches
        patches.apply_patches()


class _VendoredPkgResourcesFinder(importlib.abc.MetaPathFinder):
    """Map `pkg_resources` imports onto the vendored copy.

    Finders are consulted only for modules absent from sys.modules, so
    a pre-imported copy — real or vendored — always keeps its place.
    """

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if fullname != 'pkg_resources':
            return None
        return importlib.machinery.ModuleSpec(
            fullname, _VendoredPkgResourcesLoader())


sys.meta_path.insert(0, _VendoredPkgResourcesFinder())

# A pkg_resources loaded before zc.buildout (setuptools < 82) keeps its
# place — the bridge never fires for it — but the filters silencing its
# own deprecation noise still install at package init, as before.
if 'pkg_resources' in sys.modules:
    _install_pkg_resources_warning_filters(sys.modules['pkg_resources'])

import contextlib
from collections.abc import Iterator

import zc.buildout.patches

WINDOWS = sys.platform.startswith('win')


class UserError(Exception):
    """Errors made by a user
    """

    def __str__(self) -> str:
        return " ".join(map(str, self.args))


@contextlib.contextmanager
def _activity(message: str, *args: object) -> Iterator[None]:
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
        # Dynamic marker attribute on foreign exception objects;
        # setattr keeps it invisible to the type checker.
        setattr(e, '_zc_doing',  # noqa: B010
                getattr(e, '_zc_doing', []) + [(message, args)])
        raise
