##############################################################################
#
# Copyright (c) 2005-2009 Zope Foundation and Contributors.
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
"""Install and update part lifecycle.

Everything here moved out of ``zc.buildout.buildout`` unchanged; that
module re-exports these names so existing import paths keep working.
The ``_spacey_nl`` regex and ``_quote_spacey_nl`` helper move with
their only consumer, ``_save_option``; ``_spacey_defaults`` stays,
consumed by ``Buildout``.  ``Options`` resolves under TYPE_CHECKING
only, so the module keeps no runtime edge back to
``zc.buildout.buildout``.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Protocol, TextIO, Union, cast

import pkg_resources
from packaging import utils as packaging_utils

import zc.buildout.easy_install
from zc.buildout.easy_install import realpath
from zc.buildout.utils import bool_option, print_

if TYPE_CHECKING:
    from zc.buildout.buildout import Options


class _InstallOnly(Protocol):
    def install(self) -> None | str | Sequence[str]: ...


class _Updatable(Protocol):
    def update(self) -> None | str | Sequence[str]: ...


# The recipe contract: constructed with ``(buildout, name, options)``;
# ``install()`` and/or ``update()`` take no arguments and return
# ``None``, a path, or a sequence of paths.  Entry-point-loaded recipes
# may carry either or both methods, so the seam types the union.
# typing.Union because the 3.9 runtime cannot evaluate ``X | Y`` on
# classes at module level.
Recipe = Union[_InstallOnly, _Updatable]


class _UpdateInstalled(Protocol):
    """The ``Buildout._update_installed`` seam: str-valued keyword
    options (``parts=...``, ``installed_develop_eggs=...``)."""

    def __call__(self, **buildout_options: str) -> None: ...


_spacey_nl = re.compile('[ \t\r\f\v]*\n[ \t\r\f\v\n]*'
                        '|'
                        '^[ \t\r\f\v]+'
                        '|'
                        '[ \t\r\f\v]+$'
                        )


def _quote_spacey_nl(match: re.Match) -> str:
    match = match.group(0).split('\n', 1)
    result = '\n\t'.join(
        [(s
          .replace(' ', '%(__buildout_space__)s')
          .replace('\r', '%(__buildout_space_r__)s')
          .replace('\f', '%(__buildout_space_f__)s')
          .replace('\v', '%(__buildout_space_v__)s')
          .replace('\n', '%(__buildout_space_n__)s')
          )
         for s in match]
        )
    return result

def _save_option(option: str, value: str, f: TextIO) -> None:
    value = _spacey_nl.sub(_quote_spacey_nl, value)
    if value.startswith('\n\t'):
        value = '%(__buildout_space_n__)s' + value[2:]
    if value.endswith('\n\t'):
        value = value[:-2] + '%(__buildout_space_n__)s'
    print_(option, '=', value, file=f)

def _save_options(section: str, options: Options | dict[str, str], f: TextIO) -> None:
    print_(f'[{section}]', file=f)
    items = list(options.items())
    items.sort()
    for option, value in items:
        _save_option(option, value, f)


def _print_configuration_data(
        data: Mapping[str, Options | dict[str, str]],
        get_options: Callable[[str], Options | dict[str, str]],
        ) -> None:
    """Print the full configuration data (quiet log levels only)."""
    print_()
    print_('Configuration data:')
    for section in sorted(data):
        _save_options(section, get_options(section), sys.stdout)
    print_()


def _part_is_up_to_date(
        old_options: Mapping[str, str],
        installed_files: str,
        new_options: Mapping[str, str],
        buildout_path: Callable[[str], str],
        ) -> bool:
    """Decide whether an installed part can be kept as-is.

    A part is up to date when its options are unchanged and every file
    it installed still exists.
    """
    if old_options != new_options:
        return False
    # The options are the same, but are all of the installed files still
    # there?  If not, we should reinstall.
    if not installed_files:
        return True
    for f in installed_files.split('\n'):
        if not os.path.exists(buildout_path(f)):
            return False
    return True


def _log_part_option_changes(
        logger: logging.Logger,
        part: str,
        old_options: Mapping[str, str],
        new_options: Mapping[str, str],
        ) -> None:
    """Log the dropped, changed and new options of a part being
    reinstalled."""
    for k in old_options:
        if k not in new_options:
            logger.debug("Part %s, dropped option %s.", part, k)
        elif old_options[k] != new_options[k]:
            logger.debug(
                "Part %s, option %s changed:\n%r != %r",
                part, k, new_options[k], old_options[k],
                )
    for k in new_options:
        if k not in old_options:
            logger.debug("Part %s, new option %s.", part, k)


def _uninstall_stale_parts(
        install_parts: Sequence[str],
        installed_parts: list[str],
        installed_part_options: dict[str, Options | dict[str, str]],
        uninstall_missing: bool,
        installed_exists: bool,
        get_options: Callable[[str], Mapping[str, str] | None],
        buildout_path: Callable[[str], str],
        logger: logging.Logger,
        uninstall_part: Callable[
            [str, dict[str, Options | dict[str, str]]], None],
        update_installed: _UpdateInstalled,
        ) -> list[str]:
    """Uninstall the parts that are no longer used or whose configuration
    changed; return the updated list of installed parts."""
    for part in reversed(installed_parts):
        if part in install_parts:
            old_options = installed_part_options[part].copy()
            installed_files = old_options.pop('__buildout_installed__')
            new_options = get_options(part)
            # part is in install_parts, whose sections were all loaded
            # above, so the section exists.
            assert new_options is not None
            if _part_is_up_to_date(
                    old_options, installed_files, new_options,
                    buildout_path):
                continue

            # output debugging info
            if logger.getEffectiveLevel() < logging.DEBUG:
                _log_part_option_changes(
                    logger, part, old_options, new_options)

        elif not uninstall_missing:
            continue

        uninstall_part(part, installed_part_options)
        installed_parts = [p for p in installed_parts if p != part]

        if installed_exists:
            update_installed(parts=' '.join(installed_parts))
    return installed_parts


def _update_recipe_callable(
        recipe: Recipe,
        part: str,
        logger: logging.Logger,
        ) -> Callable[[], None | str | Sequence[str]]:
    """Return the recipe's update callable, falling back to its install
    callable (with a warning) when it doesn't define one.

    Each ``cast`` names the arm of the ``Recipe`` union the runtime
    probes for; the ``except`` covers a recipe that has neither the
    probe's method nor, in a broken plugin, the fallback's."""
    try:
        update = cast(_Updatable, recipe).update
    except AttributeError:
        update = cast(_InstallOnly, recipe).install
        logger.warning(
            "The recipe for %s doesn't define an update "
            "method. Using its install method.",
            part)
    return update


def _merged_updated_files(
        installed_files: tuple[str, ...] | str | list[str] | None,
        old_installed_files: str,
        ) -> tuple[list[str], list[str]]:
    """Merge an update result with the previously installed files.

    Return ``(installed_files, new_files)``: a ``None`` update result
    keeps the previous files; otherwise the result is normalized to a
    list and any new files are appended to the previous ones.
    """
    previous = old_installed_files.split('\n')
    if installed_files is None:
        return previous, []
    if isinstance(installed_files, str):
        files = [installed_files]
    else:
        files = list(installed_files)
    new_files = [p for p in files if p not in previous]
    if new_files:
        files = previous + new_files
    return files, new_files


def _update_part(
        part: str,
        recipe: Recipe,
        call: Callable[
            [Callable], tuple[str, ...] | str | list[str] | None],
        installed_part_options: dict[str, Options | dict[str, str]],
        installed_parts: list[str],
        installed_exists: bool,
        logger: logging.Logger,
        uninstall: Callable[[str], None],
        update_installed: _UpdateInstalled,
        ) -> tuple[list[str], list[str]]:
    """Run a part's update recipe, rolling the part back on failure.

    Return ``(installed_files, new_files)`` as merged by
    ``_merged_updated_files``.
    """
    logger.info('Updating %s.', part)
    old_options = installed_part_options[part]
    old_installed_files = old_options['__buildout_installed__']
    update = _update_recipe_callable(recipe, part, logger)
    try:
        installed_files = call(update)
    except Exception:
        installed_parts.remove(part)
        uninstall(old_installed_files)
        if installed_exists:
            update_installed(parts=' '.join(installed_parts))
        raise
    return _merged_updated_files(installed_files, old_installed_files)


def _normalize_installed_files(
        installed_files: tuple[str, ...] | str | list[str] | None,
        part: str,
        logger: logging.Logger,
        ) -> list[str] | tuple[str, ...]:
    """Normalize a recipe install result to a list of paths.

    A ``None`` result is a recipe bug: warn and use the empty tuple,
    exactly as ``Buildout.install`` always has.
    """
    if installed_files is None:
        logger.warning(
            "The %s install returned None.  A path or "
            "iterable os paths should be returned.",
            part)
        return ()
    if isinstance(installed_files, str):
        return [installed_files]
    return list(installed_files)


def _record_installed_part(
        part: str,
        signature: str,
        saved_options: dict[str, str],
        installed_files: list[str] | tuple[str, ...],
        installed_parts: list[str],
        installed_part_options: dict[str, Options | dict[str, str]],
        ) -> list[str]:
    """Record the part's final options and move it to the end of the
    installed parts list; return the updated list."""
    installed_part_options[part] = saved_options
    saved_options['__buildout_installed__'] = '\n'.join(installed_files)
    saved_options['__buildout_signature__'] = signature

    installed_parts = [p for p in installed_parts if p != part]
    installed_parts.append(part)
    return installed_parts


def _save_or_update_installed(
        need_to_save_installed: bool | list[str],
        installed_exists: bool,
        installed_parts: list[str],
        installed_part_options: dict[str, Options | dict[str, str]],
        save_installed_options: Callable[
            [Mapping[str, Options | dict[str, str]]], None],
        update_installed: _UpdateInstalled,
        ) -> bool:
    """Persist the installed options after a part install/update;
    return the new ``installed_exists`` flag."""
    if need_to_save_installed:
        installed_part_options['buildout']['parts'] = (
            ' '.join(installed_parts))
        save_installed_options(installed_part_options)
        return True
    assert installed_exists
    update_installed(parts=' '.join(installed_parts))
    return installed_exists


def _finalize_installed_options(
        installed_develop_eggs: str,
        installed_exists: bool,
        installed_parts: list[str],
        installed_part_options: dict[str, Options | dict[str, str]],
        buildout_options: Options | dict[str, str],
        save_installed_options: Callable[
            [Mapping[str, Options | dict[str, str]]], None],
        ) -> None:
    """Persist the installed options when only develop eggs changed, or
    drop the installed file when no parts remain."""
    if installed_develop_eggs:
        if not installed_exists:
            save_installed_options(installed_part_options)
    elif (not installed_parts) and installed_exists:
        os.remove(buildout_options['installed'])


def _find_upgraded_dists(
        projects: tuple[str, ...],
        ws: pkg_resources.WorkingSet,
        logger: logging.Logger,
        ) -> list[pkg_resources.Distribution]:
    """Return the dists in ``ws`` for ``projects`` whose loaded module
    lives outside the dist location (i.e. the dist upgrades the active
    version)."""
    upgraded = []
    for project in projects:
        canonicalized_name = packaging_utils.canonicalize_name(project)
        req = pkg_resources.Requirement.parse(canonicalized_name)
        dist = ws.find(req)
        if dist is None and canonicalized_name != project:
            # Try with the original project name.  Depending on which setuptools
            # version is used, this is either useless or a life saver.
            req = pkg_resources.Requirement.parse(project)
            dist = ws.find(req)
        importlib.import_module(project)
        if dist is None:
            # This is unexpected.  This must be some problem with how we use
            # setuptools/pkg_resources.  But since the import worked, it feels
            # safe to ignore.
            logger.warning(
                "Could not find %s in working set during upgrade check. Ignoring.",
                project,
            )
            continue
        if not inspect.getfile(sys.modules[project]).startswith(
                zc.buildout.easy_install._dist_location(dist)):
            upgraded.append(dist)
    return upgraded


def _upgrade_and_restart(
        options: Options | dict[str, str],
        ws: pkg_resources.WorkingSet,
        upgraded: list[pkg_resources.Distribution],
        logger: logging.Logger,
        ) -> None:
    """Regenerate the buildout scripts for the ``upgraded`` dists and
    restart the buildout process; skip with a warning when not running
    a local buildout command."""
    should_run = realpath(
        os.path.join(os.path.abspath(options['bin-directory']),
                     'buildout')
        )
    if sys.platform == 'win32':
        should_run += '-script.py'

    if (realpath(os.path.abspath(sys.argv[0])) != should_run):
        logger.debug("Running %r.", realpath(sys.argv[0]))
        logger.debug("Local buildout is %r.", should_run)
        logger.warning("Not upgrading because not running a local "
                       "buildout command.")
        return

    logger.info("Upgraded:\n  %s;\nRestarting.",
                ",\n  ".join([(f"{dist.project_name} version {dist.version}"
                               )
                              for dist in upgraded
                              ]
                             ),
                )

    # the new dist is different, so we've upgraded.
    # Update the scripts and return True
    eggs_dir = options['eggs-directory']
    develop_eggs_dir = options['develop-eggs-directory']
    ws = zc.buildout.easy_install.sort_working_set(
            ws,
            eggs_dir=eggs_dir,
            develop_eggs_dir=develop_eggs_dir
            )
    zc.buildout.easy_install.scripts(
        ['zc.buildout'], ws, sys.executable,
        options['bin-directory'],
        relative_paths = (
            bool_option(options, 'relative-paths', False)
            and options['directory']
            or ''),
        )

    # Restart
    args = sys.argv[:]
    if not __debug__:
        args.insert(0, '-O')
    args.insert(0, sys.executable)
    env=dict(os.environ, BUILDOUT_RESTART_AFTER_UPGRADE='1')
    sys.exit(subprocess.call(args, env=env))
