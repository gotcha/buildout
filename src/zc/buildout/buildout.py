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
"""Buildout main script
"""

from __future__ import annotations

import copy
import datetime
import distutils.errors  # ty: ignore[unresolved-import]  # runtime: setuptools distutils-precedence hook
import glob
import importlib
import inspect
import itertools
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping, MutableMapping, Sequence
from collections.abc import MutableMapping as DictMixin
from functools import partial
from hashlib import md5 as md5_original
from typing import Any, ClassVar, NoReturn, TypeVar, overload

import pkg_resources
from packaging import utils as packaging_utils

import zc.buildout
import zc.buildout.configparser
import zc.buildout.download
import zc.buildout.easy_install
from zc.buildout import _activity
from zc.buildout.annotations import (
    ConfigData,
    HistoryItem,
    SectionKey,
    _annotate,
    _annotate_section,
    _buildout_default_options,
    _format_picked_versions,
    _print_annotate,
    _unannotate,
    _unannotate_section,
)
from zc.buildout.cli import (
    _apply_letter_flag,
    _consume_letter_flags,
    _handle_buildout_error,
    _help,
    _long_option,
    _option_assignment,
    _pop_command,
    _usage,
    _valued_option,
    _version,
)
from zc.buildout.configfiles import (
    _extends_results,
    _filename_for_logging,
    _isurl,
    _merge_config_data,
    _open,
    _open_config_file,
    _optional_extends_results,
    _parse_config_file,
    _resolve_config_location,
    _update,
    _update_section,
    _update_verbose,
    _validated_extends_cache,
    variable_template_split,
)
from zc.buildout.configsetup import (
    _absolutize_cache_dirs,
    _absolutize_standard_dirs,
    _apply_cl_extends,
    _check_allow_hosts_with_uv,
    _check_install_from_cache,
    _cloptions_dict,
    _create_cache_dirs,
    _default_versions,
    _develop_source_dir,
    _get_user_config,
    _links_and_hosts,
    _load_config,
    _load_user_defaults,
    _new_develop_eggs,
    _pin_buildout_version,
    _previous_develop_links,
    _resolve_config_file,
    _setup_download_cache,
    _split_parts,
    _use_default_options,
    _version_eggs_directory,
)
from zc.buildout.parts import (
    _finalize_installed_options,
    _find_upgraded_dists,
    _log_part_option_changes,
    _merged_updated_files,
    _normalize_installed_files,
    _part_is_up_to_date,
    _print_configuration_data,
    _quote_spacey_nl,
    _record_installed_part,
    _save_option,
    _save_options,
    _save_or_update_installed,
    _spacey_nl,
    _uninstall_stale_parts,
    _update_part,
    _update_recipe_callable,
    _upgrade_and_restart,
)
from zc.buildout.rmtree import rmtree
from zc.buildout.utils import _bool_names, _print_options, bool_option, print_

try:
    hashed = md5_original(b'test')
    md5 = md5_original
except ValueError:
    md5 = partial(md5_original, usedforsecurity=False)


def command(method: Callable) -> Callable:
    # The marker attribute is created dynamically at runtime.
    setattr(method, 'buildout_command', True)  # noqa: B010 - dynamic marker
    return method


def commands(cls: type[Buildout]) -> type[Buildout]:
    for name, method in cls.__dict__.items():
        if hasattr(method, "buildout_command"):
            cls.COMMANDS.add(name)
    return cls


realpath = zc.buildout.easy_install.realpath

class MissingOption(zc.buildout.UserError, KeyError):
    """A required option was missing.
    """

class MissingSection(zc.buildout.UserError, KeyError):
    """A required section is missing.
    """

    def __str__(self) -> str:
        return f"The referenced section, {self.args[0]!r}, was not defined."


def _split_query_option(arg: str) -> tuple[str, str]:
    """Split a ``section:option`` query argument, defaulting the section
    to ``buildout`` and rejecting malformed arguments."""
    option = arg.split(':')
    if len(option) == 1:
        option = 'buildout', option[0]
    elif len(option) != 2:
        _error(f"Invalid query argument: {arg!r} (expected section:option)")
    section, option = option
    if not section or not option:
        _error(f"Invalid query argument: {arg!r} (expected section:option)")
    return section, option


def _parse_query_args(args: list[str] | None) -> tuple[str, str, bool]:
    """Parse the query command arguments into ``(section, option,
    interpolated)``."""
    interpolated = bool(args) and '--interpolated' in args
    if interpolated:
        args = [arg for arg in args if arg != '--interpolated']
    if args is None or len(args) != 1:
        _error('The query command requires a single argument.')
    section, option = _split_query_option(args[0])
    return section, option, interpolated


def _raw_query_value(
        raw: dict[str, dict[str, str]], section: str, option: str,
        ) -> str:
    """Return the raw value of ``section:option``, reporting the missing
    section or key."""
    try:
        return raw[section][option]
    except KeyError:
        if section in raw:
            _error('Key not found:', option)
        else:
            _error('Section not found:', section)


@commands
class Buildout(DictMixin):

    COMMANDS: ClassVar[set] = set()
    # Bound further below, where the Options class is defined
    # (``Buildout.Options = Options``).
    Options: ClassVar[type[Options]]

    def __init__(self, config_file: str | None, cloptions: list[tuple[str, str, str]],
                 use_user_defaults: bool=True,
                 command: str | None=None, args: tuple[str, ...] | list[str]=()) -> None:

        with _activity('Initializing.'):

            # default options
            _buildout_default_options_copy = copy.deepcopy(
                _buildout_default_options)
            data: ConfigData = {'buildout': _buildout_default_options_copy}
            self._buildout_dir = os.getcwd()

            config_file, directory = _resolve_config_file(
                config_file, command, args, self._init_config)
            if directory is not None:
                data['buildout']['directory'] = directory

            cloptions_dict: ConfigData = _cloptions_dict(cloptions)
            override = copy.deepcopy(cloptions_dict.get('buildout', {}))

            # load user defaults, which override defaults
            user_defaults, for_download_options = _load_user_defaults(
                use_user_defaults, data, override)

            # load configuration files
            if config_file:
                data = _load_config(
                    data, os.path.dirname(config_file), config_file,
                    for_download_options, override, user_defaults)

            # extends from command-line
            data = _apply_cl_extends(
                data, cloptions_dict, for_download_options,
                override, user_defaults)

            # apply command-line options
            data = _update(data, cloptions_dict)

            versions_section_name, versions = _default_versions(data)

            _absolutize_cache_dirs(data, self._buildout_dir)

            self._annotated = copy.deepcopy(data)
            self._raw = _unannotate(data)
            self._data = {}
            self._parts = []

            # provide some defaults before options are parsed
            # because while parsing options those attributes might be
            # used already (Gottfried Ganssauge)
            buildout_section = self._raw['buildout']

            # Try to make sure we have absolute paths for standard
            # directories. We do this before doing substitutions, in case
            # a one of these gets read by another section.  If any
            # variable references are used though, we leave it as is in
            # _buildout_path.
            if 'directory' in buildout_section:
                self._buildout_dir = buildout_section['directory']
                _absolutize_standard_dirs(buildout_section, self._buildout_path)

            # Attributes on this buildout object shouldn't be used by
            # recipes in their __init__.  It can cause bugs, because the
            # recipes will be instantiated below (``options = self['buildout']``)
            # before this has completed initializing.  These attributes are
            # left behind for legacy support but recipe authors should
            # beware of using them.  A better practice is for a recipe to
            # use the buildout['buildout'] options.
            self._links, self._allow_hosts = _links_and_hosts(
                buildout_section['find-links'], buildout_section['allow-hosts'])
            self._logger = logging.getLogger('zc.buildout')
            self.offline = bool_option(buildout_section, 'offline')
            zc.buildout.easy_install.offline(self.offline)
            self.newest = ((not self.offline) and
                           bool_option(buildout_section, 'newest')
                           )

            ##################################################################
            ## WARNING!!!
            ## ALL ATTRIBUTES MUST HAVE REASONABLE DEFAULTS AT THIS POINT
            ## OTHERWISE ATTRIBUTEERRORS MIGHT HAPPEN ANY TIME FROM RECIPES.
            ## RECIPES SHOULD GENERALLY USE buildout['buildout'] OPTIONS, NOT
            ## BUILDOUT ATTRIBUTES.
            ##################################################################
            # initialize some attrs and buildout directories.
            options = self['buildout']

            # now reinitialize
            self._links, self._allow_hosts = _links_and_hosts(
                options.get('find-links', ''), options['allow-hosts'])

            self._buildout_dir = options['directory']

            # Make sure we have absolute paths for standard directories.  We do this
            # a second time here in case someone overrode these in their configs.
            _absolutize_standard_dirs(options, self._buildout_path)

            if options['installed']:
                options['installed'] = os.path.join(options['directory'],
                                                    options['installed'])

            self._setup_logging()
            self._setup_socket_timeout()

            # finish w versions
            if versions_section_name:
                # refetching section name just to avoid a warning
                versions = self[versions_section_name]
            else:
                # remove annotations
                versions = {k: v.value for (k, v) in versions.items()}
            options['versions'] # refetching section name just to avoid a warning
            self.versions = versions
            zc.buildout.easy_install.default_versions(versions)

            zc.buildout.easy_install.prefer_final(
                bool_option(options, 'prefer-final'))
            zc.buildout.easy_install.use_dependency_links(
                bool_option(options, 'use-dependency-links'))
            zc.buildout.easy_install.index_url(options.get('index', '').strip())
            installer_option = options.get('installer', '').strip()
            if installer_option:
                zc.buildout.easy_install.installer(installer_option)
            zc.buildout.easy_install.allow_picked_versions(
                    bool_option(options, 'allow-picked-versions'))
            self.show_picked_versions = bool_option(options,
                                                    'show-picked-versions')
            self.update_versions_file = options['update-versions-file']
            zc.buildout.easy_install.store_required_by(self.show_picked_versions or
                                                       self.update_versions_file)

            download_cache = options.get('download-cache')
            extends_cache = options.get('extends-cache')

            _version_eggs_directory(options)

            eggs_cache = options.get('eggs-directory')

            _create_cache_dirs(
                options['directory'],
                [download_cache, extends_cache, eggs_cache],
                self._logger)

            _setup_download_cache(download_cache)

            _check_install_from_cache(options, self.offline)

            _check_allow_hosts_with_uv(self._allow_hosts, self._logger)

            _use_default_options(options)

            os.chdir(options['directory'])

    def _buildout_path(self, name: str) -> str:
        if '${' in name:
            return name
        return os.path.join(self._buildout_dir, name)

    @command
    def bootstrap(self, args: list[str] | tuple[str, ...]) -> None:
        with _activity('Bootstrapping.'):

            if os.path.exists(self['buildout']['develop-eggs-directory']) and os.path.isdir(
                    self['buildout']['develop-eggs-directory']):
                rmtree(self['buildout']['develop-eggs-directory'])
                self._logger.debug(
                    "Removed existing develop-eggs directory")

            self._setup_directories()

            # Now copy buildout and setuptools eggs, and record destination eggs:
            entries = []
            for dist in zc.buildout.easy_install.buildout_and_setuptools_dists:
                # These are the dists running the current buildout, so they
                # always live on disk.
                location = zc.buildout.easy_install._dist_location(dist)
                if dist.precedence == pkg_resources.DEVELOP_DIST:
                    dest = os.path.join(self['buildout']['develop-eggs-directory'],
                                        dist.key + '.egg-link')
                    with open(dest, 'w') as fh:
                        fh.write(location)
                    entries.append(location)
                else:
                    dest = os.path.join(self['buildout']['eggs-directory'],
                                        os.path.basename(location))
                    entries.append(dest)
                    if not os.path.exists(dest):
                        if os.path.isdir(location):
                            shutil.copytree(location, dest)
                        else:
                            shutil.copy2(location, dest)

            # Create buildout script
            ws = pkg_resources.WorkingSet(entries)
            ws.require('zc.buildout')
            options = self['buildout']
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

    def _init_config(self, config_file: str, args: tuple[str, ...] | list[str]) -> None:
        print_(f'Creating {config_file!r}.')
        sep = re.compile(r'[\\/]')
        with open(config_file, 'w') as f:
            if args:
                eggs = '\n  '.join(a for a in args if not sep.search(a))
                sepsub = os.path.sep == '/' and '/' or re.escape(os.path.sep)
                paths = '\n  '.join(
                    sep.sub(sepsub, a)
                    for a in args if sep.search(a))
                f.write('[buildout]\n'
                        'parts = py\n'
                        '\n'
                        '[py]\n'
                        'recipe = zc.recipe.egg\n'
                        'interpreter = py\n'
                        'eggs =\n'
                        )
                if eggs:
                    f.write(f'  {eggs}\n')
                if paths:
                    f.write(f'extra-paths =\n  {paths}\n')
                    for p in [a for a in args if sep.search(a)]:
                        if not os.path.exists(p):
                            os.mkdir(p)

            else:
                f.write('[buildout]\nparts =\n')

    @command
    def init(self, args: list[str]) -> None:
        self.bootstrap(())
        if args:
            self.install(())

    @command
    def install(self, install_args: list[str] | tuple[str, ...]) -> None:
        with _activity('Installing.'):

            self._load_extensions()
            self._setup_directories()

            # Add develop-eggs directory to path so that it gets searched
            # for eggs:
            sys.path.insert(0, self['buildout']['develop-eggs-directory'])

            # Check for updates. This could cause the process to be restarted
            self._maybe_upgrade()

            # load installed data
            (installed_part_options, installed_exists
             )= self._read_installed_part_options()

            # Build develop eggs, reusing the egg-links of sources whose
            # packaging metadata is unchanged, and removing the egg-links
            # of sources no longer being developed.
            installed_develop_eggs = self._develop(
                installed_part_options['buildout'].get(
                    'installed_develop_eggs', '')
                )
            installed_part_options['buildout']['installed_develop_eggs'
                                               ] = installed_develop_eggs

            if installed_exists:
                self._update_installed(
                    installed_develop_eggs=installed_develop_eggs)

            # get configured and installed part lists
            conf_parts = _split_parts(self['buildout']['parts'])
            installed_parts = _split_parts(
                installed_part_options['buildout']['parts'])

            if install_args:
                install_parts = install_args
                uninstall_missing = False
            else:
                install_parts = conf_parts
                uninstall_missing = True

            # load and initialize recipes
            [self[part]['recipe'] for part in install_parts]
            if not install_args:
                install_parts = self._parts

            if self._log_level < logging.DEBUG:
                # Quirk preserved: the sorted sections list is unused.
                sections = list(self)
                sections.sort()
                _print_configuration_data(self._data, self.__getitem__)

            # compute new part recipe signatures
            self._compute_part_signatures(install_parts)

            # uninstall parts that are no-longer used or who's configs
            # have changed
            installed_parts = _uninstall_stale_parts(
                install_parts, installed_parts, installed_part_options,
                uninstall_missing, installed_exists,
                self.get, self._buildout_path, self._logger,
                self._uninstall_part, self._update_installed)

            # Check for unused buildout options:
            _check_for_unused_options_in_section(self, 'buildout')

        # install new parts
        for part in install_parts:
            signature = self[part].pop('__buildout_signature__')
            saved_options = self[part].copy()
            recipe = self[part].recipe
            if part in installed_parts: # update
                with _activity('Updating %s.', part):
                    (installed_files, need_to_save_installed
                     ) = _update_part(
                        part, recipe, self[part]._call,
                        installed_part_options, installed_parts,
                        installed_exists, self._logger,
                        self._uninstall, self._update_installed)

            else: # install
                need_to_save_installed = True
                with _activity('Installing %s.', part):
                    self._logger.info('Installing %s.', part)
                    installed_files = _normalize_installed_files(
                        self[part]._call(recipe.install), part, self._logger)

            installed_parts = _record_installed_part(
                part, signature, saved_options, installed_files,
                installed_parts, installed_part_options)
            _check_for_unused_options_in_section(self, part)
            installed_exists = _save_or_update_installed(
                need_to_save_installed, installed_exists,
                installed_parts, installed_part_options,
                self._save_installed_options, self._update_installed)

        _finalize_installed_options(
            installed_develop_eggs, installed_exists, installed_parts,
            installed_part_options, self['buildout'],
            self._save_installed_options)

        if self.show_picked_versions or self.update_versions_file:
            self._print_picked_versions()
        self._print_namespace_packages()
        self._unload_extensions()

    def _update_installed(self, **buildout_options: str) -> None:
        installed = self['buildout']['installed']
        with open(installed, 'a') as f:
            f.write('\n[buildout]\n')
            for option, value in list(buildout_options.items()):
                _save_option(option, value, f)

    def _uninstall_part(self, part: str, installed_part_options: dict[str, Options | dict[str, str]]) -> None:
        # uninstall part
        with _activity('Uninstalling %s.', part):
            self._logger.info('Uninstalling %s.', part)

            # run uninstall recipe
            recipe, entry = _recipe(installed_part_options[part])
            try:
                uninstaller = _install_and_load(
                    recipe, 'zc.buildout.uninstall', entry, self)
                self._logger.info('Running uninstall recipe.')
                uninstaller(part, installed_part_options[part])
            except (ImportError, pkg_resources.DistributionNotFound):
                pass

            # remove created files and directories
            self._uninstall(
                installed_part_options[part]['__buildout_installed__'])

    def _setup_directories(self) -> None:
        with _activity('Setting up buildout directories'):

            # Create buildout directories
            for name in ('bin', 'parts', 'develop-eggs'):
                d = self['buildout'][name+'-directory']
                if not os.path.exists(d):
                    self._logger.info('Creating directory %r.', d)
                    os.mkdir(d)

    def _develop(self, previously_installed: str='') -> str:
        """Install sources by running in editable mode.

        Traditionally: run `setup.py develop` on them.
        Nowadays: run `pip install -e` on them, as there may not be a `setup.py`,
        but `pyproject.toml` instead, using for example `hatchling`.

        Reinstalling an editable install is only needed when its packaging
        metadata may have changed: an editable install does not copy any
        code, so changes in the source code itself are picked up without
        reinstalling.  Running `pip install -e` costs about a second per
        source per run, so we skip it for sources whose packaging metadata
        (``setup.py``, ``setup.cfg``, ``pyproject.toml``) has not changed
        since their egg-link was created, and reuse the existing egg-link.

        ``previously_installed`` is the newline-separated list of files
        created by the previous run (as returned by this method), used to
        find reusable egg-links and to remove egg-links of sources that are
        no longer listed in the ``develop`` option.
        """
        with _activity('Processing directories listed in the develop option'):

            develop = self['buildout'].get('develop')
            if not develop:
                self._uninstall(previously_installed)
                return ''

            dest = self['buildout']['develop-eggs-directory']
            old_files = os.listdir(dest)

            # Map the previously installed egg-links to the source directory
            # they point at, so we can tell which ones are still current.
            previous_links = _previous_develop_links(
                previously_installed, self._buildout_path)

            here = os.getcwd()
        try:
            try:
                installed = []
                for setup in develop.split():
                    setup = self._buildout_path(setup)
                    files = glob.glob(setup)
                    if not files:
                        self._logger.warning("Couldn't develop %r (not found)",
                                             setup)
                    else:
                        files.sort()
                    for setup in files:
                        self._logger.info("Develop: %r", setup)
                        with _activity('Processing develop directory %r.',
                                       setup):
                            directory = os.path.realpath(
                                os.path.expanduser(setup))
                            existing = previous_links.pop(directory, None)
                            if existing is not None and os.path.dirname(
                                    existing) != os.path.realpath(dest):
                                # The develop-eggs directory changed since the
                                # previous run: the old egg-link cannot be
                                # reused in the new directory.
                                self._uninstall(existing)
                                existing = None
                            if existing is not None:
                                if self._develop_link_fresh(existing, directory):
                                    self._logger.debug(
                                        "Keeping editable install of %s: "
                                        "its packaging metadata (setup.py, "
                                        "setup.cfg, pyproject.toml) is "
                                        "unchanged since the previous run",
                                        setup)
                                    self._logger.debug(
                                        "Reusing editable install: %s",
                                        existing)
                                    installed.append(os.path.join(
                                        dest, os.path.basename(existing)))
                                    continue
                                # Stale egg-link: reinstall from scratch.
                                self._uninstall(existing)
                            link = zc.buildout.easy_install.develop(setup, dest)
                            if link:
                                installed.append(os.path.join(
                                    dest, os.path.basename(link)))
            except Exception:
                # if we had an error, we need to roll back changes, by
                # removing any files we created.
                self._sanity_check_develop_eggs_files(dest, old_files)
                self._uninstall(_new_develop_eggs(dest, old_files))
                raise

            else:
                # Remove egg-links of sources no longer being developed.
                self._uninstall('\n'.join(previous_links.values()))
                self._sanity_check_develop_eggs_files(dest, old_files)
                return '\n'.join(dict.fromkeys(installed))

        finally:
            os.chdir(here)

    @staticmethod
    def _develop_link_fresh(link: str, directory: str) -> bool:
        """Can the existing egg-link be kept for this source directory?

        True when the packaging metadata files (``setup.py``,
        ``setup.cfg``, ``pyproject.toml``) are all older than the
        egg-link, and the egg-info generated by the previous editable
        install is still present in the source tree.
        """
        try:
            link_mtime = os.path.getmtime(link)
        except OSError:
            return False
        for name in ('setup.py', 'setup.cfg', 'pyproject.toml'):
            path = os.path.join(directory, name)
            if os.path.isfile(path) and os.path.getmtime(path) >= link_mtime:
                return False
        for pattern in ('*.egg-info', os.path.join('src', '*.egg-info')):
            if glob.glob(os.path.join(directory, pattern)):
                return True
        # No egg-info left in the source tree: the previous editable
        # install is incomplete, so it must be redone.
        return False


    def _sanity_check_develop_eggs_files(self, dest: str, old_files: list[str]) -> None:
        for f in os.listdir(dest):
            if f in old_files:
                continue
            if not (os.path.isfile(os.path.join(dest, f))
                    and f.endswith('.egg-link')):
                self._logger.warning(
                    "Unexpected entry, %r, in develop-eggs directory.", f)

    def _compute_part_signatures(self, parts: Sequence[str]) -> None:
        # Compute recipe signature and add to options
        for part in parts:
            options = self.get(part)
            if options is None:
                options = self[part] = {}
            recipe, _entry = _recipe(options)
            req = pkg_resources.Requirement.parse(recipe)
            sig = _dists_sig(pkg_resources.working_set.resolve([req]))
            options['__buildout_signature__'] = ' '.join(sig)

    def _read_installed_part_options(self) -> tuple[dict[str, Options | dict[str, str]], bool]:
        old = self['buildout']['installed']
        if old and os.path.isfile(old):
            with open(old) as fp:
                sections = zc.buildout.configparser.parse(fp, old)
            result: dict[str, Options | dict[str, str]] = {}
            for section, options in sections.items():
                for option, value in options.items():
                    if '%(' in value:
                        for k, v in _spacey_defaults:
                            value = value.replace(k, v)
                        options[option] = value
                result[section] = self.Options(self, section, options)

            return result, True
        else:
            return ({'buildout': self.Options(self, 'buildout', {'parts': ''})},
                    False,
                    )

    def _uninstall(self, installed: str) -> None:
        for f in installed.split('\n'):
            if not f:
                continue
            f = self._buildout_path(f)
            if os.path.isdir(f):
                rmtree(f)
            elif os.path.isfile(f):
                try:
                    os.remove(f)
                except OSError:
                    if not (
                        sys.platform == 'win32' and
                        (realpath(os.path.join(os.path.dirname(sys.argv[0]),
                                               'buildout.exe'))
                         ==
                         realpath(f)
                         )
                        # Sigh. This is the executable used to run the buildout
                        # and, of course, it's in use. Leave it.
                        ):
                        raise

    def _install(self, part: str) -> str:
        options = self[part]
        recipe, entry = _recipe(options)
        recipe_class = pkg_resources.load_entry_point(
            recipe, 'zc.buildout', entry)
        installed = recipe_class(self, part, options).install()
        if installed is None:
            installed = []
        elif isinstance(installed, str):
            installed = [installed]
        base = self._buildout_path('')
        installed = [d.startswith(base) and d[len(base):] or d
                     for d in installed]
        return ' '.join(installed)


    def _save_installed_options(self, installed_options: Mapping[str, Options | dict[str, str]]) -> None:
        installed = self['buildout']['installed']
        if not installed:
            return
        with open(installed, 'w') as f:
            _save_options('buildout', installed_options['buildout'], f)
            for part in installed_options['buildout']['parts'].split():
                print_(file=f)
                _save_options(part, installed_options[part], f)

    def _error(self, message: str, *args: object) -> NoReturn:
        raise zc.buildout.UserError(message % args)

    def _setup_socket_timeout(self) -> None:
        timeout = self['buildout']['socket-timeout']
        if timeout != '':
            try:
                timeout = int(timeout)
                import socket
                self._logger.info(
                    'Setting socket time out to %d seconds.', timeout)
                socket.setdefaulttimeout(timeout)
            except ValueError:
                self._logger.warning("Default socket timeout is used !\n"
                    "Value in configuration is not numeric: [%s].\n",
                    timeout)

    def _setup_logging(self) -> None:
        root_logger = logging.getLogger()
        self._logger = logging.getLogger('zc.buildout')
        handler = logging.StreamHandler(sys.stdout)
        log_format = self['buildout']['log-format']
        if not log_format:
            # No format specified. Use different formatter for buildout
            # and other modules, showing logger name except for buildout
            log_format = '%(name)s: %(message)s'
            buildout_handler = logging.StreamHandler(sys.stdout)
            buildout_handler.setFormatter(logging.Formatter('%(message)s'))
            self._logger.propagate = False
            self._logger.addHandler(buildout_handler)

        handler.setFormatter(logging.Formatter(log_format))
        root_logger.addHandler(handler)

        level = self['buildout']['log-level']
        if level in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
            level = getattr(logging, level)
        else:
            try:
                level = int(level)
            except ValueError:
                self._error("Invalid logging level %s", level)
        verbosity = self['buildout'].get('verbosity', 0)
        try:
            verbosity = int(verbosity)
        except ValueError:
            self._error("Invalid verbosity %s", verbosity)

        level -= verbosity
        root_logger.setLevel(level)
        self._log_level = level

    def _maybe_upgrade(self) -> None:
        # See if buildout or setuptools or other dependencies need to be upgraded.
        # If they do, do the upgrade and restart the buildout process.
        with _activity('Checking for upgrades.'):

            if 'BUILDOUT_RESTART_AFTER_UPGRADE' in os.environ:
                return

            if not self.newest:
                return

            # We must install `wheel` before `setuptools`` to avoid confusion between
            # the true `wheel` package and the one vendorized by `setuptools`.
            # See https://github.com/buildout/buildout/issues/691
            projects = ('zc.buildout', 'wheel', 'pip', 'setuptools')
            ws = zc.buildout.easy_install.install(
                projects,
                self['buildout']['eggs-directory'],
                links = self['buildout'].get('find-links', '').split(),
                index = self['buildout'].get('index'),
                path = [self['buildout']['develop-eggs-directory']],
                allow_hosts = self._allow_hosts
                )

            upgraded = _find_upgraded_dists(projects, ws, self._logger)

            if not upgraded:
                return

            with _activity('Upgrading.'):
                _upgrade_and_restart(
                    self['buildout'], ws, upgraded, self._logger)

    def _load_extensions(self) -> None:
        with _activity('Loading extensions.'):
            specs = self['buildout'].get('extensions', '').split()
            for superceded_extension in ['buildout-versions',
                                         'buildout.dumppickedversions']:
                if superceded_extension in specs:
                    msg = ("Buildout now includes 'buildout-versions' (and part "
                           "of the older 'buildout.dumppickedversions').\n"
                           "Remove the extension from your configuration and "
                           "look at the 'show-picked-versions' option in "
                           "buildout's documentation.")
                    raise zc.buildout.UserError(msg)
            if specs:
                path = [self['buildout']['develop-eggs-directory']]
                if self.offline:
                    dest = None
                    path.append(self['buildout']['eggs-directory'])
                else:
                    dest = self['buildout']['eggs-directory']

                zc.buildout.easy_install.install(
                    specs, dest, path=path,
                    working_set=pkg_resources.working_set,
                    links = self['buildout'].get('find-links', '').split(),
                    index = self['buildout'].get('index'),
                    newest=self.newest, allow_hosts=self._allow_hosts)

                # Clear cache because extensions might now let us read pages we
                # couldn't read before.
                zc.buildout.easy_install.clear_index_cache()

                for ep in pkg_resources.iter_entry_points('zc.buildout.extension'):
                    ep.load()(self)

    def _unload_extensions(self) -> None:
        with _activity('Unloading extensions.'):
            specs = self['buildout'].get('extensions', '').split()
            if specs:
                for ep in pkg_resources.iter_entry_points(
                    'zc.buildout.unloadextension'):
                    ep.load()(self)

    def _print_picked_versions(self) -> None:
        picked_versions, required_by = (zc.buildout.easy_install
                                        .get_picked_versions())
        if not picked_versions:
            # Don't print empty output.
            return

        output = _format_picked_versions(picked_versions, required_by)

        if self.show_picked_versions:
            print_("Versions had to be automatically picked.")
            print_("The following part definition lists the versions picked:")
            print_('\n'.join(output))

        if self.update_versions_file:
            # Write to the versions file.
            if os.path.exists(self.update_versions_file):
                output[:1] = [
                    '',
                    f'# Added by buildout at {datetime.datetime.now()}'  # noqa: DTZ005 - naive local time is the pinned format
                ]
            output.append('')
            with open(self.update_versions_file, 'a') as f:
                f.write('\n'.join(output))
            print_("Picked versions have been written to " +
                   self.update_versions_file)

    def _print_namespace_packages(self) -> None:
        namespace_packages = zc.buildout.easy_install.get_namespace_packages()
        if not namespace_packages:
            # Don't print empty output.
            return
        print("""
** WARNING **
Some development packages are using old style namespace packages.
You should switch to native namespaces (PEP 420).
If you get a ModuleNotFound or an ImportError when importing a package
from one of these namespaces, you can try this as a temporary workaround:

    pip install horse-with-no-namespace

Note: installing horse-with-no-namespace with buildout will not work.
You must install it into the virtualenv with pip (or uv) before running the buildout.

The following list shows the affected packages and their namespaces:
"""
)
        for key, value in namespace_packages:
            print(f"* {key}: {', '.join(value.splitlines())}")

    @command
    def setup(self, args: list[str]) -> None:
        if not args:
            raise zc.buildout.UserError(
                "The setup command requires the path to a setup script or \n"
                "directory containing a setup script, and its arguments."
                )
        setup = args.pop(0)
        if os.path.isdir(setup):
            setup = os.path.join(setup, 'setup.py')

        self._logger.info("Running setup script %r.", setup)
        setup = os.path.abspath(setup)

        fd, tsetup = tempfile.mkstemp()
        try:
            os.write(fd, (zc.buildout.easy_install.runsetup_template % {
                'setupdir': os.path.dirname(setup),
                'setup': setup,
                '__file__': setup,
                'extra': "",
                }).encode())
            args = [sys.executable, tsetup] + args
            zc.buildout.easy_install.call_subprocess(args)
        finally:
            os.close(fd)
            os.remove(tsetup)

    @command
    def runsetup(self, args: list[str]) -> None:
        self.setup(args)

    @command
    def query(self, args: list[str] | None=None) -> None:
        section, option, interpolated = _parse_query_args(args)
        verbose = self['buildout'].get('verbosity', 0) != 0
        if verbose:
            print_(f'${{{section}:{option}}}')
        value = _raw_query_value(self._raw, section, option)
        if interpolated:
            value = self[section].get(option)
        print_(value)

    @command
    def annotate(self, args: list[str] | None=None) -> None:
        verbose = self['buildout'].get('verbosity', 0) != 0
        if args is None:
            sections = []
        else:
            sections = args
        interpolated = '--interpolated' in sections
        if interpolated:
            sections = [s for s in sections if s != '--interpolated']
            data = self._interpolated_annotated()
        else:
            data = self._annotated
        _print_annotate(data, verbose, sections, self._buildout_dir)

    def _interpolated_annotated(self) -> dict[str, dict[str, SectionKey]]:
        data = copy.deepcopy(self._annotated)
        for section_name, section in data.items():
            options = self[section_name]
            for key, sectionkey in section.items():
                value = options.get(key)
                if value is not None:
                    sectionkey.value = value
        return data

    def print_options(self, base_path: str | None=None) -> None:
        for section in sorted(self._data):
            if section == 'buildout' or section == self['buildout']['versions']:
                continue
            print_('['+section+']')
            for k, v in sorted(self._data[section].items()):
                if '\n' in v:
                    v = '\n  ' + v.replace('\n', '\n  ')
                else:
                    v = ' '+v

                if base_path:
                    v = v.replace(os.getcwd(), base_path)
                print_(f"{k} ={v}")

    def __getitem__(self, section: str) -> Options:
        with _activity('Getting section %s.', section):
            try:
                return self._data[section]
            except KeyError:
                pass

            try:
                data = self._raw[section]
            except KeyError:
                raise MissingSection(section)

            options = self.Options(self, section, data)
            self._data[section] = options
            options._initialize()
            return options

    def __setitem__(self, name: str, data: dict[str, object]) -> None:  # values str()-ified
        if name in self._raw:
            raise KeyError("Section already exists", name)
        self._raw[name] = {k: str(v) for (k, v) in data.items()}
        self[name] # Add to parts

    def parse(self, data: str) -> None:
        import textwrap
        from io import StringIO

        sections = zc.buildout.configparser.parse(
            StringIO(textwrap.dedent(data)), '', _default_globals)
        for name in sections:
            if name in self._raw:
                raise KeyError("Section already exists", name)
            self._raw[name] = {k: str(v)
                                   for (k, v) in sections[name].items()}

        for name in sections:
            self[name] # Add to parts

    def __delitem__(self, key: str) -> None:
        raise NotImplementedError('__delitem__')

    # Legacy API: returns a real list, not a KeysView as Mapping.keys does.
    def keys(self) -> list[str]:  # ty: ignore[invalid-method-override]
        return list(self._raw.keys())

    def __iter__(self) -> Iterator[str]:
        return iter(self._raw)

    def __len__(self) -> int:
        return len(self._raw)


def _install_and_load(spec: str, group: str, entry: str, buildout: Buildout) -> Callable:
    try:
        with _activity('Loading recipe %r.', spec):
            req = pkg_resources.Requirement.parse(spec)

            buildout_options = buildout['buildout']
            installed = pkg_resources.working_set.find(req)
        if installed is None:
            with _activity('Installing recipe %s.', spec):
                if buildout.offline:
                    dest = None
                    path = [buildout_options['develop-eggs-directory'],
                            buildout_options['eggs-directory'],
                            ]
                else:
                    dest = buildout_options['eggs-directory']
                    path = [buildout_options['develop-eggs-directory']]

                # Pin versions when processing the buildout section
                versions_section_name = buildout['buildout'].get('versions', 'versions')
                versions = buildout.get(versions_section_name, {})
                zc.buildout.easy_install.allow_picked_versions(
                    bool_option(buildout['buildout'], 'allow-picked-versions')
                    )
                zc.buildout.easy_install.install(
                    [spec], dest,
                    links=buildout._links,
                    index=buildout_options.get('index'),
                    path=path,
                    working_set=pkg_resources.working_set,
                    newest=buildout.newest,
                    allow_hosts=buildout._allow_hosts,
                    versions=versions,
                    )

        with _activity('Loading %s recipe entry %s:%s.', group, spec, entry):
            return pkg_resources.load_entry_point(
                req.project_name, group, entry)

    except Exception:
        v = sys.exc_info()[1]
        buildout._logger.log(
            1,
            "Couldn't load %s entry point %s\nfrom %s:\n%s.",
            group, entry, spec, v)
        raise

_T = TypeVar('_T')


class Options(DictMixin):

    def __init__(self, buildout: Buildout, section: str, data: dict[str, str]) -> None:
        self.buildout = buildout
        self.name = section
        self._raw = data
        self._cooked = {}
        self._data = {}
        # Only holds a value while a recipe is installing (see _call);
        # declared here so its type is known in created().
        self._created: list[str] | None

    def _initialize(self) -> None:
        name = self.name
        with _activity('Initializing section %s.', name):

            if '<' in self._raw:
                self._raw = self._do_extend_raw(name, self._raw, [])

            # force substitutions
            for k, v in sorted(self._raw.items()):
                if '${' in v:
                    self._dosub(k, v)

            if name == 'buildout':
                return # buildout section can never be a part

            for dname in self.get('<part-dependencies>', '').split():
                # force use of dependencies in buildout:
                self.buildout[dname]

            if self.get('recipe'):
                self.initialize()
                self.buildout._parts.append(name)

    def initialize(self) -> None:
        reqs, entry = _recipe(self._data)
        buildout = self.buildout
        recipe_class = _install_and_load(reqs, 'zc.buildout', entry, buildout)

        name = self.name
        self.recipe = recipe_class(buildout, name, self)

    def _do_extend_raw(self, name: str, data: dict[str, str], doing: list[str]) -> dict[str, str]:
        if name == 'buildout':
            return data
        if name in doing:
            raise zc.buildout.UserError(f"Infinite extending loop {name!r}")
        doing.append(name)
        try:
            to_do = data.get('<', None)
            if to_do is None:
                return data
            with _activity('Loading input sections for %r', name):

                result = {}
                for iname in to_do.split('\n'):
                    iname = iname.strip()
                    if not iname:
                        continue
                    raw = self.buildout._raw.get(iname)
                    if raw is None:
                        raise zc.buildout.UserError(f"No section named {iname!r}")
                    result.update(self._do_extend_raw(iname, raw, doing))

                annotated_result = _annotate_section(result, "")
                annotated_data = _annotate_section(copy.deepcopy(data), "")
                result = _unannotate_section(
                    _update_section(annotated_result, annotated_data))
                result.pop('<', None)
                return result
        finally:
            assert doing.pop() == name

    def _dosub(self, option: str, v: str) -> None:
        with _activity('Getting option %s:%s.', self.name, option):
            seen = [(self.name, option)]
            v = '$$'.join([self._sub(s, seen) for s in v.split('$$')])
            self._cooked[option] = v

    # Option values are always strings; a non-string ``default`` is
    # returned as is, so its type shows up in the overloads.  The key
    # parameter is typed ``Any`` to stay compatible with ``Mapping.get``,
    # whose key type is not narrowed by this class.
    @overload
    def get(self, key: Any) -> str | None: ...  # type: ignore[explicit-any]  # Mapping.get compatibility, see comment above
    @overload
    def get(self, key: Any, default: _T, seen: list[tuple[str, str]] | None=None) -> str | _T: ...  # type: ignore[explicit-any]  # Mapping.get compatibility, see comment above
    def get(self, key: Any, default: str | int | bool | None=None, seen: list[tuple[str, str]] | None=None) -> str | int | bool | None:  # type: ignore[explicit-any]  # Mapping.get compatibility, see comment above
        try:
            return self._data[key]
        except KeyError:
            pass

        v = self._cooked.get(key)
        if v is None:
            v = self._raw.get(key)
            if v is None:
                return default

        with _activity('Getting option %s:%s.', self.name, key):

            if '${' in v:
                seen_key = self.name, key
                if seen is None:
                    seen = [seen_key]
                elif seen_key in seen:
                    raise zc.buildout.UserError(
                        "Circular reference in substitutions.\n"
                        )
                else:
                    seen.append(seen_key)
                v = '$$'.join([self._sub(s, seen) for s in v.split('$$')])
                seen.pop()

            self._data[key] = v
            return v

    _template_split = re.compile('([$]{[^}]*})').split
    _simple = re.compile('[-a-zA-Z0-9 ._]+$').match
    _valid = re.compile(r'\${[-a-zA-Z0-9 ._]*:[-a-zA-Z0-9 ._]+}$').match
    def _sub(self, template: str, seen: list[tuple[str, str]]) -> str:
        value = self._template_split(template)
        subs = []
        for ref in value[1::2]:
            s = tuple(ref[2:-1].split(':'))
            if not self._valid(ref):
                if len(s) < 2:
                    raise zc.buildout.UserError(f"The substitution, {ref},\n"
                                                "doesn't contain a colon.")
                if len(s) > 2:
                    raise zc.buildout.UserError(f"The substitution, {ref},\n"
                                                "has too many colons.")
                if not self._simple(s[0]):
                    raise zc.buildout.UserError(
                        f"The section name in substitution, {ref},\n"
                        "has invalid characters.")
                if not self._simple(s[1]):
                    raise zc.buildout.UserError(
                        f"The option name in substitution, {ref},\n"
                        "has invalid characters.")

            section, option = s
            if not section:
                section = self.name
            v = self.buildout[section].get(option, None, seen)
            if v is None:
                if option == '_buildout_section_name_':
                    v = self.name
                else:
                    raise MissingOption("Referenced option does not exist:",
                                        section, option)
            subs.append(v)
        subs.append('')

        return ''.join([''.join(v) for v in zip(value[::2], subs)])

    def __getitem__(self, key: str) -> str:
        try:
            return self._data[key]
        except KeyError:
            pass

        v = self.get(key)
        if v is None:
            raise MissingOption(f"Missing option: {self.name}:{key}")
        return v

    def __setitem__(self, option: str, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError('Option values must be strings', value)
        self._data[option] = value

    def __delitem__(self, key: str) -> None:
        if key in self._raw:
            del self._raw[key]
            if key in self._data:
                del self._data[key]
            if key in self._cooked:
                del self._cooked[key]
        elif key in self._data:
            del self._data[key]
        else:
            raise KeyError(key)

    # Legacy API: returns a real list, not a KeysView as Mapping.keys does.
    def keys(self) -> list[str]:  # ty: ignore[invalid-method-override]
        raw = self._raw
        return list(self._raw) + [k for k in self._data if k not in raw]

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    def __len__(self) -> int:
        return len(self.keys())

    def copy(self) -> dict[str, str]:
        result = copy.deepcopy(self._raw)
        result.update(self._cooked)
        result.update(self._data)
        return result

    def _call(self, f: Callable) -> tuple[str, ...] | str | list[str] | None:
        buildout_directory = self.buildout['buildout']['directory']
        self._created = []
        try:
            try:
                os.chdir(buildout_directory)
                return f()
            except Exception:
                for p in self._created:
                    if os.path.isdir(p):
                        rmtree(p)
                    elif os.path.isfile(p):
                        os.remove(p)
                    else:
                        self.buildout._logger.warning("Couldn't clean up %r.", p)
                raise
        finally:
            self._created = None
            os.chdir(buildout_directory)

    def created(self, *paths: str) -> list[str]:
        try:
            created = self._created
        except AttributeError:
            raise TypeError(
                "Attempt to register a created path while not installing",
                self.name)
        if created is None:
            raise TypeError(
                "Attempt to register a created path while not installing",
                self.name)
        created.extend(paths)
        return created

    def __repr__(self) -> str:
        return repr(dict(self))

Buildout.Options = Options

_spacey_defaults = [
    ('%(__buildout_space__)s',   ' '),
    ('%(__buildout_space_n__)s', '\n'),
    ('%(__buildout_space_r__)s', '\r'),
    ('%(__buildout_space_f__)s', '\f'),
    ('%(__buildout_space_v__)s', '\v'),
    ]

def _default_globals() -> dict[str, Any]:  # type: ignore[explicit-any]  # eval globals for interpolation hold arbitrary values
    """Return a mapping of default and precomputed expressions.
    These default expressions are convenience defaults available when eveluating
    section headers expressions.
    NB: this is wrapped in a function so that the computing of these expressions
    is lazy and done only if needed (ie if there is at least one section with
    an expression) because the computing of some of these expressions can be
    expensive.
    """
    # partially derived or inspired from its.py
    # Copyright (c) 2012, Kenneth Reitz All rights reserved.
    # Redistribution and use in source and binary forms, with or without modification,
    # are permitted provided that the following conditions are met:
    # Redistributions of source code must retain the above copyright notice, this list
    # of conditions and the following disclaimer. Redistributions in binary form must
    # reproduce the above copyright notice, this list of conditions and the following
    # disclaimer in the documentation and/or other materials provided with the
    # distribution. THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
    # CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
    # LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
    # PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
    # CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
    # OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
    # SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
    # INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
    # CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING
    # IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY
    # OF SUCH DAMAGE.

    # default available modules, explicitly re-imported locally here on purpose
    import os
    import platform
    import re
    import sys

    globals_defs = {'sys': sys, 'os': os, 'platform': platform, 're': re,}

    # major python major_python_versions as python2 and python3
    major_python_versions = tuple(map(str, platform.python_version_tuple()))
    globals_defs.update({'python2': major_python_versions[0] == '2',
                         'python3': major_python_versions[0] == '3'})

    # minor python major_python_versions as python24, python25 ... python39
    minor_python_versions = ('24', '25', '26', '27',
                             '30', '31', '32', '33', '34', '35', '36', '37', '38', '39',
                             '310', '311', '312', '313', '314', '315')
    for v in minor_python_versions:
        globals_defs['python' + v] = ''.join(major_python_versions[:2]) == v

    # interpreter type
    sys_version = sys.version.lower()
    pypy = 'pypy' in sys_version
    jython = 'java' in sys_version
    ironpython ='iron' in sys_version
    # assume CPython, if nothing else.
    cpython = not any((pypy, jython, ironpython,))
    globals_defs.update({'cpython': cpython,
                         'pypy': pypy,
                         'jython': jython,
                         'ironpython': ironpython})

    # operating system
    sys_platform = str(sys.platform).lower()
    globals_defs.update({'linux': 'linux' in sys_platform,
                         'windows': 'win32' in sys_platform,
                         'cygwin': 'cygwin' in sys_platform,
                         'solaris': 'sunos' in sys_platform,
                         'macosx': 'darwin' in sys_platform,
                         'posix': 'posix' in os.name.lower()})

    #bits and endianness
    import struct
    void_ptr_size = struct.calcsize('P') * 8
    globals_defs.update({'bits32': void_ptr_size == 32,
                         'bits64': void_ptr_size == 64,
                         'little_endian': sys.byteorder == 'little',
                         'big_endian': sys.byteorder == 'big'})

    return globals_defs

ignore_directories = '.svn', 'CVS', '__pycache__', '.git'
_dir_hashes = {}
def _dir_hash_file_ignored(name: str) -> bool:
    """Files _dir_hash must not see.

    pyc/pyo are interpreter caches. SOURCES.txt is setuptools' sdist
    manifest: any packaging run on the source tree (python -m build,
    setup.py sdist) regenerates it with varying content while the
    installed dist is unchanged, so hashing it flips develop-dist
    signatures and forces spurious part reinstalls.
    """
    return name.endswith(('pyc', 'pyo')) or name == 'SOURCES.txt'


def _dir_hash(dir: str) -> str:
    dir_hash = _dir_hashes.get(dir, None)
    if dir_hash is not None:
        return dir_hash
    hash = md5()
    for (dirpath, dirnames, filenames) in os.walk(dir):
        dirnames[:] = sorted(n for n in dirnames if n not in ignore_directories)
        filenames[:] = sorted(f for f in filenames
                              if (not _dir_hash_file_ignored(f)
                                  and os.path.exists(os.path.join(dirpath, f)))
                          )
        for_hash = ' '.join(dirnames + filenames)
        if isinstance(for_hash, str):
            for_hash = for_hash.encode()
        hash.update(for_hash)
        for name in filenames:
            path = os.path.join(dirpath, name)
            if name == 'entry_points.txt':
                # Entry points aren't written in stable order. :(
                try:
                    with open(path) as f:
                        sections = zc.buildout.configparser.parse(f, path)
                except Exception:  # noqa: BLE001 - any parse failure falls
                    # back to hashing the raw bytes
                    with open(path, 'rb') as f:
                        data = f.read()
                else:
                    data = repr([(sname, sorted(sections[sname].items()))
                                 for sname in sorted(sections)]).encode('utf-8')
            else:
                with open(path, 'rb') as f:
                    data = f.read()
            hash.update(data)
    _dir_hashes[dir] = dir_hash = hash.hexdigest()
    return dir_hash

def _dists_sig(dists: list[pkg_resources.Distribution]) -> list[str]:
    seen = set()
    result = []
    for dist in sorted(dists):
        if dist in seen:
            continue
        seen.add(dist)
        location = zc.buildout.easy_install._dist_location(dist)
        if dist.precedence == pkg_resources.DEVELOP_DIST:
            result.append(dist.project_name + '-' + _dir_hash(location))
        else:
            result.append(os.path.basename(location))
    return result


def _recipe(options: Options | dict[str, str]) -> tuple[str, str]:
    recipe = options['recipe']
    if ':' in recipe:
        recipe, entry = recipe.split(':')
    else:
        entry = 'default'

    return recipe, entry

def _doing() -> None:
    # Activities are attached to the exception objects by _activity.
    # Walk the re-raise chain too: easy_install re-wraps lower-level
    # errors (e.g. pkg_resources.VersionConflict) into fresh
    # exceptions, so activities recorded before the re-wrap sit on the
    # __context__, not on the exception main() catches.
    _, v, _ = sys.exc_info()
    doing = []
    seen = set()
    while v is not None and id(v) not in seen:
        seen.add(id(v))
        doing.extend(reversed(getattr(v, '_zc_doing', [])))
        v = v.__cause__ if v.__cause__ is not None else v.__context__
    if doing:
        sys.stderr.write('While:\n')
        for message, args in doing:
            if args:
                message = message % args
            sys.stderr.write(f'  {message}\n')

def _error(*message: Any) -> NoReturn:  # type: ignore[explicit-any]  # arbitrary parts; join raising TypeError on non-str is a preserved quirk (cli.py:244)
    sys.stderr.write('Error: ' + ' '.join(message) +'\n')
    sys.exit(1)

_internal_error_template = """
An internal error occurred due to a bug in either zc.buildout or in a
recipe being used:
"""

def _check_for_unused_options_in_section(buildout: Buildout, section: str) -> None:
    options = buildout[section]
    unused = [option for option in sorted(options._raw)
              if option not in options._data]
    if unused:
        buildout._logger.warning(
            "Section `%s` contains unused option(s): %s.\n"
            "This may be an indication for either a typo in the option's name "
            "or a bug in the used recipe.",
            section, ' '.join(map(repr, unused))
        )


def main(args: list[str] | None=None) -> None:
    if args is None:
        args = sys.argv[1:]

    config_file = 'buildout.cfg'
    verbosity = 0
    options: list[tuple[str, str, str]] = []
    use_user_defaults = True
    debug = False
    while args:
        if args[0][0] == '-':
            op = orig_op = args.pop(0)
            (op, verbosity, use_user_defaults, debug
             ) = _consume_letter_flags(
                op[1:], verbosity, use_user_defaults, debug, options)

            if op[:1] in  ('c', 't'):
                config_file = _valued_option(
                    op, orig_op, config_file, args, options)
            elif op:
                _long_option(orig_op, op)
        elif '=' in args[0]:
            options.append(_option_assignment(args.pop(0)))
        else:
            # We've run out of command-line options and option assignments
            # The rest should be commands, so we'll stop here
            break

    if verbosity:
        options.append(('buildout', 'verbosity', str(verbosity)))

    command = _pop_command(args)

    try:
        try:
            buildout = Buildout(config_file, options,
                                use_user_defaults, command, args)
            getattr(buildout, command)(args)
        except SystemExit:
            logging.shutdown()
            # Make sure we properly propagate an exit code from a restarted
            # buildout process.
            raise
        except Exception:  # noqa: BLE001 - top-level error funnel: every
            # buildout failure is reported through _handle_buildout_error
            _handle_buildout_error(debug)

    finally:
        logging.shutdown()
