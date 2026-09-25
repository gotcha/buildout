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
"""Configuration resolution and defaults pipeline.

Everything here moved out of ``zc.buildout.buildout`` unchanged; that
module re-exports these names so existing import paths keep working.
The logger name stays the historical ``zc.buildout`` so doctest
transcripts that assert it keep matching.  ``Options`` resolves under
TYPE_CHECKING only, so the module keeps no runtime edge back to
``zc.buildout.buildout``.
"""

from __future__ import annotations

import copy
import itertools
import logging
import os
from collections.abc import Callable, Mapping, MutableMapping
from typing import TYPE_CHECKING

import pkg_resources

import zc.buildout
import zc.buildout.easy_install
from zc.buildout.annotations import (
    AnnotatedSection,
    ConfigData,
    SectionKey,
    _buildout_default_options,
)
from zc.buildout.configfiles import _isurl, _open, _update
from zc.buildout.utils import bool_option

if TYPE_CHECKING:
    from zc.buildout.buildout import Options

logger = logging.getLogger('zc.buildout')

def _get_user_config() -> str:
    buildout_home = os.path.join(os.path.expanduser('~'), '.buildout')
    buildout_home = os.environ.get('BUILDOUT_HOME', buildout_home)
    return os.path.join(buildout_home, 'default.cfg')


def _develop_source_dir(egg_path: str) -> str:
    """Return the source directory for an egg-link target path.

    The egg path is the source directory itself or, for src-layouts, its
    'src' subdirectory.  Note that the source directory itself may also be
    named 'src' (a flat layout in a directory called src), so check which
    of the candidates holds the packaging metadata.
    """
    source = egg_path
    if os.path.basename(egg_path) == 'src':
        parent = os.path.dirname(egg_path)
        metadata = ('setup.py', 'setup.cfg', 'pyproject.toml')
        if (any(os.path.isfile(os.path.join(parent, name))
                for name in metadata)
                and not any(os.path.isfile(os.path.join(egg_path, name))
                            for name in metadata)):
            source = parent
    return source


def _previous_develop_links(
        previously_installed: str,
        buildout_path: Callable[[str], str]) -> dict[str, str]:
    """Map develop source directories to their existing egg-link files.

    ``previously_installed`` is the newline-separated list of files created
    by the previous run; ``buildout_path`` resolves buildout-relative paths.
    Keys are realpaths of the source directories.
    """
    previous_links = {}
    for f in previously_installed.split('\n'):
        if not f:
            continue
        f = buildout_path(f)
        if not f.endswith('.egg-link') or not os.path.isfile(f):
            continue
        with open(f) as fp:
            egg_path = fp.readline().strip()
        previous_links[os.path.realpath(_develop_source_dir(egg_path))] = f
    return previous_links


def _new_develop_eggs(dest: str, old_files: list[str]) -> str:
    """Return newline-joined paths of entries created in ``dest`` since
    ``old_files`` was listed."""
    return '\n'.join(
        [os.path.join(dest, f)
         for f in os.listdir(dest)
         if f not in old_files
         ])


def _resolve_config_file(
        config_file: str | None,
        command: str | None,
        args: tuple[str, ...] | list[str],
        init_config: Callable[[str, tuple[str, ...] | list[str]], None],
        ) -> tuple[str | None, SectionKey | None]:
    """Resolve a local ``config_file`` path for opening.

    Return the possibly rewritten ``config_file`` along with the
    computed ``directory`` setting; ``None`` for the latter means the
    default directory stays.  A missing file is created by
    ``init_config`` for the ``init`` command, and turns a ``setup``
    command into a directory-less run rooted at the current directory.
    """
    directory = None
    if config_file and not _isurl(config_file):
        config_file = os.path.abspath(config_file)
        if not os.path.exists(config_file):
            if command == 'init':
                init_config(config_file, args)
            elif command == 'setup':
                # Sigh. This model of a buildout instance
                # with methods is breaking down. :(
                config_file = None
                directory = SectionKey('.', 'COMPUTED_VALUE')
            else:
                raise zc.buildout.UserError(
                    f"Couldn't open {config_file}")
        elif command == 'init':
            raise zc.buildout.UserError(
                f"{config_file!r} already exists.")

        if config_file:
            directory = SectionKey(
                os.path.dirname(config_file), 'COMPUTED_VALUE')
    return config_file, directory


def _cloptions_dict(cloptions: list[tuple[str, str, str]]) -> ConfigData:
    """Group command-line options into config data, keyed by section."""
    return {
        section: {option: SectionKey(value, 'COMMAND_LINE_VALUE')
                       for (_, option, value) in v}
        for (section, v) in itertools.groupby(sorted(cloptions),
                                              lambda v: v[0])
        }


def _load_user_defaults(
        use_user_defaults: bool,
        data: ConfigData,
        override: dict[str, SectionKey],
        ) -> tuple[ConfigData, ConfigData]:
    """Load the user defaults, which override defaults.

    Return ``(user_defaults, for_download_options)``: both empty resp.
    a deep copy of ``data`` when the user config is absent or disabled.
    """
    user_config = _get_user_config()
    if use_user_defaults and os.path.exists(user_config):
        download_options = data['buildout']
        user_defaults, _ = _open(
            os.path.dirname(user_config),
            user_config, [], download_options,
            override, set(), {}
        )
        # A top-level _open call returns the dict form.
        assert isinstance(user_defaults, dict)
        return user_defaults, _update(data, user_defaults)
    return {}, copy.deepcopy(data)


def _load_config(
        data: ConfigData,
        base: str,
        filename: str,
        for_download_options: ConfigData,
        override: dict[str, SectionKey],
        user_defaults: ConfigData,
        ) -> ConfigData:
    """Open the config file ``filename`` (relative to ``base``) and
    update ``data`` with it."""
    download_options = for_download_options['buildout']
    cfg_data, _ = _open(
        base, filename, [], download_options,
        override, set(), user_defaults
    )
    # A top-level _open call returns the dict form.
    assert isinstance(cfg_data, dict)
    return _update(data, cfg_data)


def _apply_cl_extends(
        data: ConfigData,
        cloptions_dict: ConfigData,
        for_download_options: ConfigData,
        override: dict[str, SectionKey],
        user_defaults: ConfigData,
        ) -> ConfigData:
    """Apply command-line ``buildout:extends`` files to ``data``.

    Pops ``extends`` from the command-line buildout section, so it is
    not applied again later as a plain option.
    """
    if 'buildout' in cloptions_dict:
        cl_extends = cloptions_dict['buildout'].pop('extends', None)
        if cl_extends:
            for extends in cl_extends.value.split():
                data = _load_config(
                    data,
                    os.path.dirname(extends),
                    os.path.basename(extends),
                    for_download_options, override, user_defaults
                )
    return data


def _pin_buildout_version(versions: dict[str, SectionKey]) -> None:
    """Pin ``zc.buildout`` to at least the running version."""
    # Prevent downgrading of zc.buildout itself due to prefer-final.
    ws = pkg_resources.working_set
    dist = ws.find(
        pkg_resources.Requirement.parse('zc-buildout')
    )
    if dist is None:
        # older setuptools
        dist = ws.find(
            pkg_resources.Requirement.parse('zc.buildout')
        )
        if dist is None:
            # This would be really strange, but I prefer an explicit
            # failure here over an unclear error later.
            raise ValueError(
                "Could not find distribution for zc.buildout in working set."
            )
    minimum = dist.version
    versions['zc.buildout'] = SectionKey(f'>={minimum}', 'DEFAULT_VALUE')


def _default_versions(
        data: ConfigData,
        ) -> tuple[str, AnnotatedSection]:
    """Ensure ``data`` has a versions section with default pins.

    Return the versions section name and the versions mapping.
    """
    # Set up versions section, if necessary
    if 'versions' not in data['buildout']:
        data['buildout']['versions'] = SectionKey(
            'versions', 'DEFAULT_VALUE')
        if 'versions' not in data:
            data['versions'] = {}

    # Default versions:
    versions_section_name = data['buildout']['versions'].value
    versions: AnnotatedSection
    if versions_section_name:
        versions = data[versions_section_name]
    else:
        versions = {}
    if 'zc.buildout' not in versions:
        _pin_buildout_version(versions)
    if 'zc.recipe.egg' not in versions:
        # zc.buildout and zc.recipe egg are closely linked, but zc.buildout
        # does NOT depend on it: we do not want to add it to our
        # install_requires.  (One could debate why, although one answer
        # would be to avoid a circular dependency.  Maybe we could merge them,
        # as I see no use case for Buildout without recipes.  But we would
        # need to update the zc.recipe.egg test setup first.)
        #
        # Anyway: we use a different way to set a minimum version.
        # Originally (in 2013, zc.buildout 2.0.0b1) we made sure
        # zc.recipe.egg>=2.0.0a3 was pinned, mostly to avoid problems
        # when prefer-final is true.
        # Later (in 2018, zc.buildout 2.12.1) we updated the minimum version
        # to 2.0.6, to avoid a KeyError: 'allow-unknown-extras'.
        # See https://github.com/buildout/buildout/pull/461
        # I wonder if we really need a minimum version, as older versions
        # are unlikely to even be installable by supported Python versions.
        # But if we ever really need a more recent minimum version,
        # it is easy to update a version here.
        versions['zc.recipe.egg'] = SectionKey('>=2.0.6', 'DEFAULT_VALUE')
    return versions_section_name, versions


def _absolutize_cache_dirs(data: ConfigData, buildout_dir: str) -> None:
    """Absolutize the download-cache, eggs-directory and extends-cache
    settings in place.

    Handles also the ~/foo form, and considers the location of the
    configuration file that generated the setting as the base path,
    falling back to the main configuration file location.
    """
    for name in ('download-cache', 'eggs-directory', 'extends-cache'):
        if name in data['buildout']:
            sectionkey = data['buildout'][name]
            origdir = sectionkey.value
            src = sectionkey.source
            if '${' in origdir:
                continue
            if not os.path.isabs(origdir):
                if src in ('DEFAULT_VALUE',
                           'COMPUTED_VALUE',
                           'COMMAND_LINE_VALUE'):
                    if 'directory' in data['buildout']:
                        basedir = data['buildout']['directory'].value
                    else:
                        basedir = buildout_dir
                else:
                    if _isurl(src):
                        raise zc.buildout.UserError(
                            f'Setting "{name}" to a non absolute location ("{origdir}") '
                            'within a\n'
                            f'remote configuration file ("{src}") is ambiguous.')
                    basedir = os.path.dirname(src)
                absdir = os.path.expanduser(origdir)
                if not os.path.isabs(absdir):
                    absdir = os.path.join(basedir, absdir)
                absdir = os.path.abspath(absdir)
                sectionkey.setDirectory(absdir)


def _links_and_hosts(
        links: str,
        allow_hosts: str,
        ) -> tuple[list[str] | tuple[str, ...], tuple[str, ...]]:
    """Compute the legacy ``_links`` and ``_allow_hosts`` attribute
    values from the ``find-links`` and ``allow-hosts`` settings."""
    # ty over-widens the and/or idiom with an impossible falsy-str case.
    return (links and links.split() or (),  # ty: ignore[invalid-return-type]
            tuple([host.strip() for host in allow_hosts.split('\n')
                   if host.strip() != ''])
            )


def _absolutize_standard_dirs(
        section: MutableMapping[str, str],
        buildout_path: Callable[[str], str],
        ) -> None:
    """Absolutize the bin/parts/eggs/develop-eggs directory settings
    of ``section`` through ``buildout_path``, in place."""
    for name in ('bin', 'parts', 'eggs', 'develop-eggs'):
        d = buildout_path(section[name+'-directory'])
        section[name+'-directory'] = d


def _version_eggs_directory(options: Options | dict[str, str]) -> None:
    """Join the eggs-directory version and ABI tag into
    ``options['eggs-directory']``, in place."""
    # Since zc.buildout version 5 we maintain separate directories for each
    # buildout eggs format version.  Current idea: we use v5 from zc.buildout
    # 5.x onwards.  Later versions will likely also use v5, as the current
    # expectation is that they will be compatible, just like zc.buildout
    # 1.x through 4.x are compatible.
    # If you know what you are doing, you can set eggs-directory-version to
    # an empty string.  This can be fine if you don't have any previous eggs
    # and only use zc.buildout 5 or later.  It should also be fine in case
    # you don't use any namespace packages; but you would be wrong, because
    # you are using zc.buildout and probably zc.recipe.egg, so you use the
    # zc namespace.  Still, if those are the only two packages, it might
    # possibly work.
    if options['eggs-directory-version']:
        options['eggs-directory'] = os.path.join(
            options['eggs-directory'], options['eggs-directory-version'])

    if bool_option(options, 'abi-tag-eggs', 'false'):
        from zc.buildout.pep425tags import get_abi_tag
        abi_tag = get_abi_tag()
        # get_abi_tag() only returns None on platforms without a known
        # ABI tag, where joining it into a path would fail anyway.
        assert abi_tag is not None
        options['eggs-directory'] = os.path.join(
            options['eggs-directory'], abi_tag)


def _create_cache_dirs(
        directory: str,
        caches: list[str | None],
        logger: logging.Logger,
        ) -> None:
    """Create each cache directory (relative to ``directory``) if missing."""
    for cache in caches:
        if cache:
            cache = os.path.join(directory, cache)
            if not os.path.exists(cache):
                logger.info('Creating directory %r.', cache)
                os.makedirs(cache)


def _setup_download_cache(download_cache: str | None) -> None:
    """Create the download cache and point easy_install at it."""
    if download_cache:
        # Actually, we want to use a subdirectory in there called 'dist'.
        download_cache = os.path.join(download_cache, 'dist')
        if not os.path.exists(download_cache):
            os.mkdir(download_cache)
        zc.buildout.easy_install.download_cache(download_cache)


def _check_install_from_cache(
        options: Options | dict[str, str],
        offline: bool,
        ) -> None:
    """Enable install-from-cache, refusing the offline-mode combination."""
    if bool_option(options, 'install-from-cache'):
        if offline:
            raise zc.buildout.UserError(
                "install-from-cache can't be used with offline mode.\n"
                "Nothing is installed, even from cache, in offline\n"
                "mode, which might better be called 'no-install mode'.\n"
                )
        zc.buildout.easy_install.install_from_cache(True)


def _check_allow_hosts_with_uv(
        allow_hosts: tuple[str, ...],
        logger: logging.Logger,
        ) -> None:
    """Warn that a non-default allow-hosts is not enforced under uv.

    uv has no host allow-list; its ``--allow-insecure-host`` is TLS
    policy, not filtering, so there is nothing to map the option onto.
    """
    if allow_hosts != ('*',) and zc.buildout.easy_install.installer() == 'uv':
        logger.warning(
            'With installer = uv, the allow-hosts option is not'
            ' enforced: uv has no host allow-list'
            ' (its --allow-insecure-host flag is TLS policy,'
            ' not filtering).')


def _use_default_options(options: Mapping[str, str]) -> None:
    """"Use" each of the defaults so they aren't reported as unused options."""
    for name in _buildout_default_options:
        options[name]


def _split_parts(parts: str) -> list[str]:
    """Split a whitespace-separated part list option, mapping empty to
    ``[]``."""
    return parts.split() if parts else []
