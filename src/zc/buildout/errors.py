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

"""User-facing exception types shared across the package.

Modules import from here so no one needs the Installer stack to raise
a user error.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

import zc.buildout

if TYPE_CHECKING:
    # Type annotations only: with ``from __future__ import annotations``
    # these are never evaluated at runtime, so uv mode never needs
    # pkg_resources for this module. Callers pass pkg_resources objects
    # built by the legacy (pip) code paths, or the behavioral-twin
    # facade objects from zc.buildout._workingset on the uv path.
    import pkg_resources

    from zc.buildout import _workingset


class IncompatibleConstraintError(zc.buildout.UserError):
    """A specified version is incompatible with a given requirement.
    """


IncompatibleVersionError = IncompatibleConstraintError  # Backward compatibility


class VersionConflict(zc.buildout.UserError):

    def __init__(self, err: pkg_resources.VersionConflict | _workingset.VersionConflict, ws: Iterable[pkg_resources.Distribution | _workingset.Distribution]) -> None:
        ws = list(ws)
        ws.sort()
        self.err, self.ws = err, ws

    def __str__(self) -> str:
        result = ["There is a version conflict."]
        if len(self.err.args) == 2:
            existing_dist, req = self.err.args
            result.append(f"We already have: {existing_dist}")
            for dist in self.ws:
                if req in dist.requires():
                    result.append(f"but {dist} requires {str(req)!r}.")
        else:
            # The error argument is already a nice error string.
            result.append(self.err.args[0])
        return '\n'.join(result)


def _uv_detail_suffix(detail: str | None) -> str:
    """The ``  uv: ``-prefixed lines a MissingDistribution appends."""
    if not detail:
        return ''
    return ''.join(f'\n  uv: {line}' for line in detail.splitlines())


class MissingDistribution(zc.buildout.UserError):

    def __init__(self, req: pkg_resources.Requirement | _workingset.Requirement, ws: pkg_resources.WorkingSet | _workingset.AmbientWorkingSet,
                 detail: str | None = None) -> None:
        sorted_dists = list(ws)
        sorted_dists.sort()
        self.data = req, sorted_dists
        # In uv mode, the tail of uv's stderr, so the cause class (not
        # found, unsatisfiable, ...) survives the debug-level demote.
        self.detail = detail
        self._suffix = _uv_detail_suffix(detail)

    def __str__(self) -> str:
        req, _ws = self.data
        return f"Couldn't find a distribution for {str(req)!r}.{self._suffix}"
