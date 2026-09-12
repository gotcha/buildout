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

from collections.abc import Mapping, MutableMapping as DictMixin
from functools import partial
from hashlib import md5 as md5_original
from packaging import utils as packaging_utils
from zc.buildout.rmtree import rmtree

import zc.buildout.easy_install
import zc.buildout.configparser
import copy
import datetime
import distutils.errors  # ty: ignore[unresolved-import]  # runtime: setuptools distutils-precedence hook
import glob
import importlib
import inspect
import itertools
import logging
import os
import pkg_resources
import re
import shutil
import subprocess
import sys
import tempfile
import zc.buildout
import zc.buildout.download
from typing import (
    Any, Callable, ClassVar, Dict, Iterator, List, NoReturn, Optional,
    Sequence, Set, TextIO, Tuple, Type, TypeVar, Union, overload,
)


try:
    hashed = md5_original(b'test')
    md5 = md5_original
except ValueError:
    md5 = partial(md5_original, usedforsecurity=False)


def command(method: Callable) -> Callable:
    # The marker attribute is created dynamically at runtime.
    setattr(method, 'buildout_command', True)
    return method


def commands(cls: Type['Buildout']) -> Type['Buildout']:
    for name, method in cls.__dict__.items():
        if hasattr(method, "buildout_command"):
            cls.COMMANDS.add(name)
    return cls


def _print_options(sep: str=' ', end: str='\n', file: Optional[TextIO]=None) -> Tuple[str, str, Optional[TextIO]]:
    return sep, end, file

def print_(*args: Any, **kw: Any) -> None:
    sep, end, file = _print_options(**kw)
    if file is None:
        file = sys.stdout
    file.write(sep.join(map(str, args))+end)

realpath = zc.buildout.easy_install.realpath

_isurl = re.compile('([a-zA-Z0-9+.-]+)://').match

class MissingOption(zc.buildout.UserError, KeyError):
    """A required option was missing.
    """

class MissingSection(zc.buildout.UserError, KeyError):
    """A required section is missing.
    """

    def __str__(self) -> str:
        return "The referenced section, %r, was not defined." % self.args[0]


def _annotate_section(section: Dict[str, Any], source: str) -> Dict[str, 'SectionKey']:
    for key in section:
        section[key] = SectionKey(section[key], source)
    return section


class SectionKey(object):
    def __init__(self, value: str, source: str) -> None:
        self.history = []
        self.value = value
        self.addToHistory("SET", value, source)

    @property
    def source(self) -> str:
        return self.history[-1].source

    def overrideValue(self, sectionkey: "SectionKey") -> None:
        self.value = sectionkey.value
        if sectionkey.history[-1].operation not in ['ADD', 'REMOVE']:
            self.addToHistory("OVERRIDE", sectionkey.value, sectionkey.source)
        else:
            self.history = copy.deepcopy(sectionkey.history)

    def setDirectory(self, value: str) -> None:
        self.value = value
        self.addToHistory("DIRECTORY", value, self.source)

    def addToValue(self, added: str, source: str) -> None:
        subvalues = self.value.split('\n') + added.split('\n')
        self.value = "\n".join(subvalues)
        self.addToHistory("ADD", added, source)

    def removeFromValue(self, removed: str, source: str) -> None:
        subvalues = [
            v
            for v in self.value.split('\n')
            if v not in removed.split('\n')
        ]
        self.value = "\n".join(subvalues)
        self.addToHistory("REMOVE", removed, source)

    def addToHistory(self, operation: str, value: str, source: str) -> None:
        item = HistoryItem(operation, value, source)
        self.history.append(item)

    def printAll(self, key: str, basedir: str, verbose: bool) -> None:
        self.printKeyAndValue(key)
        if verbose:
            self.printVerbose(basedir)
        else:
            self.printTerse(basedir)

    def printKeyAndValue(self, key: str) -> None:
        lines = self.value.splitlines()
        if len(lines) <= 1:
            args = [key, "="]
            if self.value:
                args.append(" ")
                args.append(self.value)
            print_(*args, sep='')
        else:
            print_(key, "= ", lines[0], sep='')
            for line in lines[1:]:
                print_(line)

    def printVerbose(self, basedir: str) -> None:
        print_()
        for item in reversed(self.history):
            item.printAll(basedir)
        print_()

    def printTerse(self, basedir: str) -> None:
        toprint = []
        history = copy.deepcopy(self.history)
        while history:
            next = history.pop()
            if next.operation in ["ADD", "REMOVE"]:
                next.printShort(toprint, basedir)
            else:
                next.printShort(toprint, basedir)
                break

        for line in reversed(toprint):
            if line.strip():
                print_(line)

    def __repr__(self) -> str:
        return "<SectionKey value=%s source=%s>" % (
            " ".join(self.value.split('\n')), self.source)


class HistoryItem(object):
    def __init__(self, operation: str, value: str, source: str) -> None:
        self.operation = operation
        self.value = value
        self.source = source

    def printShort(self, toprint: List[str], basedir: str) -> None:
        source = self.source_for_human(basedir)
        if self.operation in ["OVERRIDE", "SET", "DIRECTORY"]:
            toprint.append("    " + source)
        elif self.operation == "ADD":
            toprint.append("+=  " + source)
        elif self.operation == "REMOVE":
            toprint.append("-=  " + source)

    def printOperation(self) -> None:
        lines = self.value.splitlines()
        if len(lines) <= 1:
            print_("  ", self.operation, "VALUE =", self.value)
        else:
            print_("  ", self.operation, "VALUE =")
            for line in lines:
                print_("  ", "  ", line)

    def printSource(self, basedir: str) -> None:
        if self.source in (
            'DEFAULT_VALUE', 'COMPUTED_VALUE', 'COMMAND_LINE_VALUE'
        ):
            prefix = "AS"
        else:
            prefix = "IN"
        print_("  ", prefix, self.source_for_human(basedir))

    def source_for_human(self, basedir: str) -> str:
        if self.source.startswith(basedir):
            return os.path.relpath(self.source, basedir)
        else:
            return self.source

    def printAll(self, basedir: str) -> None:
        self.printSource(basedir)
        self.printOperation()

    def __repr__(self) -> str:
        return "<HistoryItem operation=%s value=%s source=%s>" % (
            self.operation, " ".join(self.value.split('\n')), self.source)


# Annotated configuration data: maps section names to sections whose values
# are SectionKey objects once annotated (plain dicts while still raw).
ConfigData = Dict[str, Union[Dict[str, SectionKey], Dict[Any, Any]]]


def _annotate(data: Dict[str, Union[Dict[str, str], Dict[Any, Any]]], note: str) -> Dict[str, Union[Dict[str, SectionKey], Dict[Any, Any]]]:
    for key in data:
        data[key] = _annotate_section(data[key], note)
    return data


def _print_annotate(data: Dict[str, Dict[str, SectionKey]], verbose: bool, chosen_sections: List[str], basedir: str) -> None:
    sections = list(data.keys())
    sections.sort()
    print_()
    print_("Annotated sections")
    print_("="*len("Annotated sections"))
    for section in sections:
        if (not chosen_sections) or (section in chosen_sections):
            print_()
            print_('[%s]' % section)
            keys = list(data[section].keys())
            keys.sort()
            for key in keys:
                sectionkey = data[section][key]
                sectionkey.printAll(key, basedir, verbose)


def _unannotate_section(section: Dict[str, SectionKey]) -> Dict[str, str]:
    return {key: entry.value for key, entry in section.items()}


def _unannotate(data: Dict[str, Dict[str, SectionKey]]) -> Dict[str, Dict[str, str]]:
    return {key: _unannotate_section(section) for key, section in data.items()}


def _format_picked_versions(picked_versions: List[Tuple[str, str]], required_by: Dict[str, Set[str]]) -> List[str]:
    output = ['[versions]']
    required_output = []
    for dist_, version in picked_versions:
        if dist_ in required_by:
            required_output.append('')
            required_output.append('# Required by:')
            for req_ in sorted(required_by[dist_]):
                required_output.append('# '+req_)
            target = required_output
        else:
            target = output
        target.append("%s = %s" % (dist_, version))
    output.extend(required_output)
    return output


_buildout_default_options = _annotate_section({
    'allow-hosts': '*',
    'allow-picked-versions': 'true',
    'bin-directory': 'bin',
    'develop-eggs-directory': 'develop-eggs',
    'eggs-directory': 'eggs',
    'eggs-directory-version': 'v5',
    'executable': sys.executable,
    'find-links': '',
    'install-from-cache': 'false',
    'installed': '.installed.cfg',
    'log-format': '',
    'log-level': 'INFO',
    'newest': 'true',
    'offline': 'false',
    'parts-directory': 'parts',
    'prefer-final': 'true',
    'python': 'buildout',
    'show-picked-versions': 'false',
    'socket-timeout': '',
    'update-versions-file': '',
    'use-dependency-links': 'true',
    'allow-unknown-extras': 'false',
    }, 'DEFAULT_VALUE')


def _get_user_config() -> str:
    buildout_home = os.path.join(os.path.expanduser('~'), '.buildout')
    buildout_home = os.environ.get('BUILDOUT_HOME', buildout_home)
    return os.path.join(buildout_home, 'default.cfg')


@commands
class Buildout(DictMixin):

    COMMANDS = set()
    # Bound further below, where the Options class is defined
    # (``Buildout.Options = Options``).
    Options: ClassVar[Type['Options']]

    def __init__(self, config_file: Optional[str], cloptions: List[Tuple[str, str, str]],
                 use_user_defaults: bool=True,
                 command: Optional[str]=None, args: Union[Tuple[str, ...], List[str]]=()) -> None:

        __doing__ = 'Initializing.'

        # default options
        _buildout_default_options_copy = copy.deepcopy(
            _buildout_default_options)
        data: ConfigData = dict(buildout=_buildout_default_options_copy)
        self._buildout_dir = os.getcwd()

        if config_file and not _isurl(config_file):
            config_file = os.path.abspath(config_file)
            if not os.path.exists(config_file):
                if command == 'init':
                    self._init_config(config_file, args)
                elif command == 'setup':
                    # Sigh. This model of a buildout instance
                    # with methods is breaking down. :(
                    config_file = None
                    data['buildout']['directory'] = SectionKey(
                        '.', 'COMPUTED_VALUE')
                else:
                    raise zc.buildout.UserError(
                        "Couldn't open %s" % config_file)
            elif command == 'init':
                raise zc.buildout.UserError(
                    "%r already exists." % config_file)

            if config_file:
                data['buildout']['directory'] = SectionKey(
                    os.path.dirname(config_file), 'COMPUTED_VALUE')

        cloptions_dict: ConfigData = dict(
            (section, dict((option, SectionKey(value, 'COMMAND_LINE_VALUE'))
                           for (_, option, value) in v))
            for (section, v) in itertools.groupby(sorted(cloptions),
                                                  lambda v: v[0])
            )
        override = copy.deepcopy(cloptions_dict.get('buildout', {}))

        # load user defaults, which override defaults
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
            for_download_options = _update(data, user_defaults)
        else:
            user_defaults = {}
            for_download_options = copy.deepcopy(data)

        # load configuration files
        if config_file:
            download_options = for_download_options['buildout']
            cfg_data, _ = _open(
                os.path.dirname(config_file),
                config_file, [], download_options,
                override, set(), user_defaults
            )
            # A top-level _open call returns the dict form.
            assert isinstance(cfg_data, dict)
            data = _update(data, cfg_data)

        # extends from command-line
        if 'buildout' in cloptions_dict:
            cl_extends = cloptions_dict['buildout'].pop('extends', None)
            if cl_extends:
                for extends in cl_extends.value.split():
                    download_options = for_download_options['buildout']
                    cfg_data, _ = _open(
                        os.path.dirname(extends),
                        os.path.basename(extends),
                        [], download_options,
                        override, set(), user_defaults
                    )
                    # A top-level _open call returns the dict form.
                    assert isinstance(cfg_data, dict)
                    data = _update(data, cfg_data)

        # apply command-line options
        data = _update(data, cloptions_dict)

        # Set up versions section, if necessary
        if 'versions' not in data['buildout']:
            data['buildout']['versions'] = SectionKey(
                'versions', 'DEFAULT_VALUE')
            if 'versions' not in data:
                data['versions'] = {}

        # Default versions:
        versions_section_name = data['buildout']['versions'].value
        if versions_section_name:
            versions = data[versions_section_name]
        else:
            versions = {}
        if 'zc.buildout' not in versions:
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

        # Absolutize some particular directory, handling also the ~/foo form,
        # and considering the location of the configuration file that generated
        # the setting as the base path, falling back to the main configuration
        # file location
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
                            basedir = self._buildout_dir
                    else:
                        if _isurl(src):
                            raise zc.buildout.UserError(
                                'Setting "%s" to a non absolute location ("%s") '
                                'within a\n'
                                'remote configuration file ("%s") is ambiguous.' % (
                                    name, origdir, src))
                        basedir = os.path.dirname(src)
                    absdir = os.path.expanduser(origdir)
                    if not os.path.isabs(absdir):
                        absdir = os.path.join(basedir, absdir)
                    absdir = os.path.abspath(absdir)
                    sectionkey.setDirectory(absdir)

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
            for name in ('bin', 'parts', 'eggs', 'develop-eggs'):
                d = self._buildout_path(buildout_section[name+'-directory'])
                buildout_section[name+'-directory'] = d

        # Attributes on this buildout object shouldn't be used by
        # recipes in their __init__.  It can cause bugs, because the
        # recipes will be instantiated below (``options = self['buildout']``)
        # before this has completed initializing.  These attributes are
        # left behind for legacy support but recipe authors should
        # beware of using them.  A better practice is for a recipe to
        # use the buildout['buildout'] options.
        links = buildout_section['find-links']
        self._links = links and links.split() or ()
        allow_hosts = buildout_section['allow-hosts'].split('\n')
        self._allow_hosts = tuple([host.strip() for host in allow_hosts
                                   if host.strip() != ''])
        self._logger = logging.getLogger('zc.buildout')
        self.offline = bool_option(buildout_section, 'offline')
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
        links = options.get('find-links', '')
        self._links = links and links.split() or ()

        allow_hosts = options['allow-hosts'].split('\n')
        self._allow_hosts = tuple([host.strip() for host in allow_hosts
                                   if host.strip() != ''])

        self._buildout_dir = options['directory']

        # Make sure we have absolute paths for standard directories.  We do this
        # a second time here in case someone overrode these in their configs.
        for name in ('bin', 'parts', 'eggs', 'develop-eggs'):
            d = self._buildout_path(options[name+'-directory'])
            options[name+'-directory'] = d

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
            versions = dict((k, v.value) for (k, v) in versions.items())
        options['versions'] # refetching section name just to avoid a warning
        self.versions = versions
        zc.buildout.easy_install.default_versions(versions)

        zc.buildout.easy_install.prefer_final(
            bool_option(options, 'prefer-final'))
        zc.buildout.easy_install.use_dependency_links(
            bool_option(options, 'use-dependency-links'))
        zc.buildout.easy_install.index_url(options.get('index', '').strip())
        zc.buildout.easy_install.allow_picked_versions(
                bool_option(options, 'allow-picked-versions'))
        self.show_picked_versions = bool_option(options,
                                                'show-picked-versions')
        self.update_versions_file = options['update-versions-file']
        zc.buildout.easy_install.store_required_by(self.show_picked_versions or
                                                   self.update_versions_file)

        download_cache = options.get('download-cache')
        extends_cache = options.get('extends-cache')

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

        eggs_cache = options.get('eggs-directory')

        for cache in [download_cache, extends_cache, eggs_cache]:
            if cache:
                cache = os.path.join(options['directory'], cache)
                if not os.path.exists(cache):
                    self._logger.info('Creating directory %r.', cache)
                    os.makedirs(cache)

        if download_cache:
            # Actually, we want to use a subdirectory in there called 'dist'.
            download_cache = os.path.join(download_cache, 'dist')
            if not os.path.exists(download_cache):
                os.mkdir(download_cache)
            zc.buildout.easy_install.download_cache(download_cache)

        if bool_option(options, 'install-from-cache'):
            if self.offline:
                raise zc.buildout.UserError(
                    "install-from-cache can't be used with offline mode.\n"
                    "Nothing is installed, even from cache, in offline\n"
                    "mode, which might better be called 'no-install mode'.\n"
                    )
            zc.buildout.easy_install.install_from_cache(True)

        # "Use" each of the defaults so they aren't reported as unused options.
        for name in _buildout_default_options:
            options[name]

        os.chdir(options['directory'])

    def _buildout_path(self, name: str) -> str:
        if '${' in name:
            return name
        return os.path.join(self._buildout_dir, name)

    @command
    def bootstrap(self, args: Union[List[str], Tuple[str, ...]]) -> None:
        __doing__ = 'Bootstrapping.'

        if os.path.exists(self['buildout']['develop-eggs-directory']):
            if os.path.isdir(self['buildout']['develop-eggs-directory']):
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

    def _init_config(self, config_file: str, args: Union[Tuple[str, ...], List[str]]) -> None:
        print_('Creating %r.' % config_file)
        f = open(config_file, 'w')
        sep = re.compile(r'[\\/]')
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
                f.write('  %s\n' % eggs)
            if paths:
                f.write('extra-paths =\n  %s\n' % paths)
                for p in [a for a in args if sep.search(a)]:
                    if not os.path.exists(p):
                        os.mkdir(p)

        else:
            f.write('[buildout]\nparts =\n')
        f.close()

    @command
    def init(self, args: List[str]) -> None:
        self.bootstrap(())
        if args:
            self.install(())

    @command
    def install(self, install_args: Union[List[str], Tuple[str, ...]]) -> None:
        __doing__ = 'Installing.'

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
        conf_parts = self['buildout']['parts']
        conf_parts = conf_parts.split() if conf_parts else []
        installed_parts = installed_part_options['buildout']['parts']
        installed_parts = (installed_parts.split()
                           if installed_parts else [])

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
            sections = list(self)
            sections.sort()
            print_()
            print_('Configuration data:')
            for section in sorted(self._data):
                _save_options(section, self[section], sys.stdout)
            print_()


        # compute new part recipe signatures
        self._compute_part_signatures(install_parts)

        # uninstall parts that are no-longer used or who's configs
        # have changed
        for part in reversed(installed_parts):
            if part in install_parts:
                old_options = installed_part_options[part].copy()
                installed_files = old_options.pop('__buildout_installed__')
                new_options = self.get(part)
                # part is in install_parts, whose sections were all loaded
                # above, so the section exists.
                assert new_options is not None
                if old_options == new_options:
                    # The options are the same, but are all of the
                    # installed files still there?  If not, we should
                    # reinstall.
                    if not installed_files:
                        continue
                    for f in installed_files.split('\n'):
                        if not os.path.exists(self._buildout_path(f)):
                            break
                    else:
                        continue

                # output debugging info
                if self._logger.getEffectiveLevel() < logging.DEBUG:
                    for k in old_options:
                        if k not in new_options:
                            self._logger.debug("Part %s, dropped option %s.",
                                               part, k)
                        elif old_options[k] != new_options[k]:
                            self._logger.debug(
                                "Part %s, option %s changed:\n%r != %r",
                                part, k, new_options[k], old_options[k],
                                )
                    for k in new_options:
                        if k not in old_options:
                            self._logger.debug("Part %s, new option %s.",
                                               part, k)

            elif not uninstall_missing:
                continue

            self._uninstall_part(part, installed_part_options)
            installed_parts = [p for p in installed_parts if p != part]

            if installed_exists:
                self._update_installed(parts=' '.join(installed_parts))

        # Check for unused buildout options:
        _check_for_unused_options_in_section(self, 'buildout')

        # install new parts
        for part in install_parts:
            signature = self[part].pop('__buildout_signature__')
            saved_options = self[part].copy()
            recipe = self[part].recipe
            if part in installed_parts: # update
                need_to_save_installed = False
                __doing__ = 'Updating %s.', part
                self._logger.info(*__doing__)
                old_options = installed_part_options[part]
                old_installed_files = old_options['__buildout_installed__']

                try:
                    update = recipe.update
                except AttributeError:
                    update = recipe.install
                    self._logger.warning(
                        "The recipe for %s doesn't define an update "
                        "method. Using its install method.",
                        part)

                try:
                    installed_files = self[part]._call(update)
                except Exception:
                    installed_parts.remove(part)
                    self._uninstall(old_installed_files)
                    if installed_exists:
                        self._update_installed(
                            parts=' '.join(installed_parts))
                    raise

                old_installed_files = old_installed_files.split('\n')
                if installed_files is None:
                    installed_files = old_installed_files
                else:
                    if isinstance(installed_files, str):
                        installed_files = [installed_files]
                    else:
                        installed_files = list(installed_files)

                    need_to_save_installed = [
                        p for p in installed_files
                        if p not in old_installed_files]

                    if need_to_save_installed:
                        installed_files = (old_installed_files
                                           + need_to_save_installed)

            else: # install
                need_to_save_installed = True
                __doing__ = 'Installing %s.', part
                self._logger.info(*__doing__)
                installed_files = self[part]._call(recipe.install)
                if installed_files is None:
                    self._logger.warning(
                        "The %s install returned None.  A path or "
                        "iterable os paths should be returned.",
                        part)
                    installed_files = ()
                elif isinstance(installed_files, str):
                    installed_files = [installed_files]
                else:
                    installed_files = list(installed_files)

            installed_part_options[part] = saved_options
            saved_options['__buildout_installed__'
                          ] = '\n'.join(installed_files)
            saved_options['__buildout_signature__'] = signature

            installed_parts = [p for p in installed_parts if p != part]
            installed_parts.append(part)
            _check_for_unused_options_in_section(self, part)

            if need_to_save_installed:
                installed_part_options['buildout']['parts'] = (
                    ' '.join(installed_parts))
                self._save_installed_options(installed_part_options)
                installed_exists = True
            else:
                assert installed_exists
                self._update_installed(parts=' '.join(installed_parts))

        if installed_develop_eggs:
            if not installed_exists:
                self._save_installed_options(installed_part_options)
        elif (not installed_parts) and installed_exists:
            os.remove(self['buildout']['installed'])

        if self.show_picked_versions or self.update_versions_file:
            self._print_picked_versions()
        self._print_namespace_packages()
        self._unload_extensions()

    def _update_installed(self, **buildout_options: str) -> None:
        installed = self['buildout']['installed']
        f = open(installed, 'a')
        f.write('\n[buildout]\n')
        for option, value in list(buildout_options.items()):
            _save_option(option, value, f)
        f.close()

    def _uninstall_part(self, part: str, installed_part_options: Dict[str, Union['Options', Dict[str, str]]]) -> None:
        # uninstall part
        __doing__ = 'Uninstalling %s.', part
        self._logger.info(*__doing__)

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
        __doing__ = 'Setting up buildout directories'

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
        __doing__ = 'Processing directories listed in the develop option'

        develop = self['buildout'].get('develop')
        if not develop:
            self._uninstall(previously_installed)
            return ''

        dest = self['buildout']['develop-eggs-directory']
        old_files = os.listdir(dest)

        # Map the previously installed egg-links to the source directory
        # they point at, so we can tell which ones are still current.
        previous_links = {}
        for f in previously_installed.split('\n'):
            if not f:
                continue
            f = self._buildout_path(f)
            if not f.endswith('.egg-link') or not os.path.isfile(f):
                continue
            with open(f) as fp:
                egg_path = fp.readline().strip()
            # The egg path is the source directory itself or, for
            # src-layouts, its 'src' subdirectory.  Note that the source
            # directory itself may also be named 'src' (a flat layout in a
            # directory called src), so check which of the candidates
            # holds the packaging metadata.
            source = egg_path
            if os.path.basename(egg_path) == 'src':
                parent = os.path.dirname(egg_path)
                metadata = ('setup.py', 'setup.cfg', 'pyproject.toml')
                if (any(os.path.isfile(os.path.join(parent, name))
                        for name in metadata)
                        and not any(os.path.isfile(os.path.join(egg_path, name))
                                    for name in metadata)):
                    source = parent
            previous_links[os.path.realpath(source)] = f

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
                        __doing__ = ('Processing develop directory %r.',
                                     setup)
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
                self._uninstall('\n'.join(
                    [os.path.join(dest, f)
                     for f in os.listdir(dest)
                     if f not in old_files
                     ]))
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


    def _sanity_check_develop_eggs_files(self, dest: str, old_files: List[str]) -> None:
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
            recipe, entry = _recipe(options)
            req = pkg_resources.Requirement.parse(recipe)
            sig = _dists_sig(pkg_resources.working_set.resolve([req]))
            options['__buildout_signature__'] = ' '.join(sig)

    def _read_installed_part_options(self) -> Tuple[Dict[str, Union['Options', Dict[str, str]]], bool]:
        old = self['buildout']['installed']
        if old and os.path.isfile(old):
            fp = open(old)
            sections = zc.buildout.configparser.parse(fp, old)
            fp.close()
            result: Dict[str, Union['Options', Dict[str, str]]] = {}
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


    def _save_installed_options(self, installed_options: Mapping[str, Union['Options', Dict[str, str]]]) -> None:
        installed = self['buildout']['installed']
        if not installed:
            return
        f = open(installed, 'w')
        _save_options('buildout', installed_options['buildout'], f)
        for part in installed_options['buildout']['parts'].split():
            print_(file=f)
            _save_options(part, installed_options[part], f)
        f.close()

    def _error(self, message: str, *args: Any) -> NoReturn:
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
        __doing__ = 'Checking for upgrades.'

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
                self._logger.warning(
                    "Could not find %s in working set during upgrade check. Ignoring.",
                    project,
                )
                continue
            if not inspect.getfile(sys.modules[project]).startswith(
                    zc.buildout.easy_install._dist_location(dist)):
                upgraded.append(dist)

        if not upgraded:
            return

        __doing__ = 'Upgrading.'

        should_run = realpath(
            os.path.join(os.path.abspath(self['buildout']['bin-directory']),
                         'buildout')
            )
        if sys.platform == 'win32':
            should_run += '-script.py'

        if (realpath(os.path.abspath(sys.argv[0])) != should_run):
            self._logger.debug("Running %r.", realpath(sys.argv[0]))
            self._logger.debug("Local buildout is %r.", should_run)
            self._logger.warning("Not upgrading because not running a local "
                                 "buildout command.")
            return

        self._logger.info("Upgraded:\n  %s;\nRestarting.",
                          ",\n  ".join([("%s version %s"
                                       % (dist.project_name, dist.version)
                                       )
                                      for dist in upgraded
                                      ]
                                     ),
                          )

        # the new dist is different, so we've upgraded.
        # Update the scripts and return True
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

        # Restart
        args = sys.argv[:]
        if not __debug__:
            args.insert(0, '-O')
        args.insert(0, sys.executable)
        env=dict(os.environ, BUILDOUT_RESTART_AFTER_UPGRADE='1')
        sys.exit(subprocess.call(args, env=env))

    def _load_extensions(self) -> None:
        __doing__ = 'Loading extensions.'
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
        __doing__ = 'Unloading extensions.'
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
                    '# Added by buildout at %s' % datetime.datetime.now()
                ]
            output.append('')
            f = open(self.update_versions_file, 'a')
            f.write(('\n'.join(output)))
            f.close()
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
    def setup(self, args: List[str]) -> None:
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
            os.write(fd, (zc.buildout.easy_install.runsetup_template % dict(
                setupdir=os.path.dirname(setup),
                setup=setup,
                __file__ = setup,
                extra="",
                )).encode())
            args = [sys.executable, tsetup] + args
            zc.buildout.easy_install.call_subprocess(args)
        finally:
            os.close(fd)
            os.remove(tsetup)

    @command
    def runsetup(self, args: List[str]) -> None:
        self.setup(args)

    @command
    def query(self, args: Optional[List[str]]=None) -> None:
        interpolated = bool(args) and '--interpolated' in args
        if interpolated:
            args = [arg for arg in args if arg != '--interpolated']
        if args is None or len(args) != 1:
            _error('The query command requires a single argument.')
        option = args[0]
        option = option.split(':')
        if len(option) == 1:
            option = 'buildout', option[0]
        elif len(option) != 2:
            _error("Invalid query argument: %r (expected section:option)"
                   % args[0])
        section, option = option
        if not section or not option:
            _error("Invalid query argument: %r (expected section:option)"
                   % args[0])
        verbose = self['buildout'].get('verbosity', 0) != 0
        if verbose:
            print_('${%s:%s}' % (section, option))
        try:
            value = self._raw[section][option]
        except KeyError:
            if section in self._raw:
                _error('Key not found:', option)
            else:
                _error('Section not found:', section)
        if interpolated:
            value = self[section].get(option)
        print_(value)

    @command
    def annotate(self, args: Optional[List[str]]=None) -> None:
        verbose = self['buildout'].get('verbosity', 0) != 0
        section = None
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

    def _interpolated_annotated(self) -> Dict[str, Dict[str, SectionKey]]:
        data = copy.deepcopy(self._annotated)
        for section_name, section in data.items():
            options = self[section_name]
            for key, sectionkey in section.items():
                value = options.get(key)
                if value is not None:
                    sectionkey.value = value
        return data

    def print_options(self, base_path: Optional[str]=None) -> None:
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
                print_("%s =%s" % (k, v))

    def __getitem__(self, section: str) -> "Options":
        __doing__ = 'Getting section %s.', section
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

    def __setitem__(self, name: str, data: Dict[str, Any]) -> None:  # values str()-ified
        if name in self._raw:
            raise KeyError("Section already exists", name)
        self._raw[name] = dict((k, str(v)) for (k, v) in data.items())
        self[name] # Add to parts

    def parse(self, data: str) -> None:
        from io import StringIO
        import textwrap

        sections = zc.buildout.configparser.parse(
            StringIO(textwrap.dedent(data)), '', _default_globals)
        for name in sections:
            if name in self._raw:
                raise KeyError("Section already exists", name)
            self._raw[name] = dict((k, str(v))
                                   for (k, v) in sections[name].items())

        for name in sections:
            self[name] # Add to parts

    def __delitem__(self, key: str) -> None:
        raise NotImplementedError('__delitem__')

    # Legacy API: returns a real list, not a KeysView as Mapping.keys does.
    def keys(self) -> List[str]:  # ty: ignore[invalid-method-override]
        return list(self._raw.keys())

    def __iter__(self) -> Iterator[str]:
        return iter(self._raw)

    def __len__(self) -> int:
        return len(self._raw)


def _install_and_load(spec: str, group: str, entry: str, buildout: Buildout) -> Callable:
    __doing__ = 'Loading recipe %r.', spec
    try:
        req = pkg_resources.Requirement.parse(spec)

        buildout_options = buildout['buildout']
        if pkg_resources.working_set.find(req) is None:
            __doing__ = 'Installing recipe %s.', spec
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

        __doing__ = 'Loading %s recipe entry %s:%s.', group, spec, entry
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

    def __init__(self, buildout: Buildout, section: str, data: Dict[str, str]) -> None:
        self.buildout = buildout
        self.name = section
        self._raw = data
        self._cooked = {}
        self._data = {}
        # Only holds a value while a recipe is installing (see _call);
        # declared here so its type is known in created().
        self._created: Optional[List[str]]

    def _initialize(self) -> None:
        name = self.name
        __doing__ = 'Initializing section %s.', name

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

    def _do_extend_raw(self, name: str, data: Dict[str, str], doing: List[str]) -> Dict[str, str]:
        if name == 'buildout':
            return data
        if name in doing:
            raise zc.buildout.UserError("Infinite extending loop %r" % name)
        doing.append(name)
        try:
            to_do = data.get('<', None)
            if to_do is None:
                return data
            __doing__ = 'Loading input sections for %r', name

            result = {}
            for iname in to_do.split('\n'):
                iname = iname.strip()
                if not iname:
                    continue
                raw = self.buildout._raw.get(iname)
                if raw is None:
                    raise zc.buildout.UserError("No section named %r" % iname)
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
        __doing__ = 'Getting option %s:%s.', self.name, option
        seen = [(self.name, option)]
        v = '$$'.join([self._sub(s, seen) for s in v.split('$$')])
        self._cooked[option] = v

    # Option values are always strings; a non-string ``default`` is
    # returned as is, so its type shows up in the overloads.  The key
    # parameter is typed ``Any`` to stay compatible with ``Mapping.get``,
    # whose key type is not narrowed by this class.
    @overload
    def get(self, key: Any) -> Optional[str]: ...
    @overload
    def get(self, key: Any, default: _T, seen: Optional[List[Tuple[str, str]]]=None) -> Union[str, _T]: ...
    def get(self, key: Any, default: Optional[Union[str, int, bool]]=None, seen: Optional[List[Tuple[str, str]]]=None) -> Optional[Union[str, int, bool]]:
        try:
            return self._data[key]
        except KeyError:
            pass

        v = self._cooked.get(key)
        if v is None:
            v = self._raw.get(key)
            if v is None:
                return default

        __doing__ = 'Getting option %s:%s.', self.name, key

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
    def _sub(self, template: str, seen: List[Tuple[str, str]]) -> str:
        value = self._template_split(template)
        subs = []
        for ref in value[1::2]:
            s = tuple(ref[2:-1].split(':'))
            if not self._valid(ref):
                if len(s) < 2:
                    raise zc.buildout.UserError("The substitution, %s,\n"
                                                "doesn't contain a colon."
                                                % ref)
                if len(s) > 2:
                    raise zc.buildout.UserError("The substitution, %s,\n"
                                                "has too many colons."
                                                % ref)
                if not self._simple(s[0]):
                    raise zc.buildout.UserError(
                        "The section name in substitution, %s,\n"
                        "has invalid characters."
                        % ref)
                if not self._simple(s[1]):
                    raise zc.buildout.UserError(
                        "The option name in substitution, %s,\n"
                        "has invalid characters."
                        % ref)

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
            raise MissingOption("Missing option: %s:%s" % (self.name, key))
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
    def keys(self) -> List[str]:  # ty: ignore[invalid-method-override]
        raw = self._raw
        return list(self._raw) + [k for k in self._data if k not in raw]

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    def __len__(self) -> int:
        return len(self.keys())

    def copy(self) -> Dict[str, str]:
        result = copy.deepcopy(self._raw)
        result.update(self._cooked)
        result.update(self._data)
        return result

    def _call(self, f: Callable) -> Optional[Union[Tuple[str, ...], str, List[str]]]:
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

    def created(self, *paths: str) -> List[str]:
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

_spacey_nl = re.compile('[ \t\r\f\v]*\n[ \t\r\f\v\n]*'
                        '|'
                        '^[ \t\r\f\v]+'
                        '|'
                        '[ \t\r\f\v]+$'
                        )

_spacey_defaults = [
    ('%(__buildout_space__)s',   ' '),
    ('%(__buildout_space_n__)s', '\n'),
    ('%(__buildout_space_r__)s', '\r'),
    ('%(__buildout_space_f__)s', '\f'),
    ('%(__buildout_space_v__)s', '\v'),
    ]

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

def _save_options(section: str, options: Union[Options, Dict[str, str]], f: TextIO) -> None:
    print_('[%s]' % section, file=f)
    items = list(options.items())
    items.sort()
    for option, value in items:
        _save_option(option, value, f)

def _default_globals() -> Dict[str, Any]:
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
    import sys
    import os
    import platform
    import re

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

variable_template_split = re.compile('([$]{[^}]*})').split

def _open(
        base: str, filename: str, seen: List[str], download_options: Dict[str, SectionKey],
        override: Dict[str, SectionKey], downloaded: Set[str], user_defaults: Dict[str, Dict[str, SectionKey]]
        ) -> Union[Tuple[ConfigData, Dict[str, Dict[str, SectionKey]]], Tuple[List[ConfigData], Dict[str, Dict[str, SectionKey]]]]:
    """Open a configuration file and return the result as a dictionary,

    Recursively open other files based on buildout options found.

    Return type: a top-level call (empty ``seen``) returns the merged
    config dict; a recursive call (for ``extends``) returns the list of
    per-file config dicts.  Callers narrow with isinstance asserts.
    """
    download_options = _update_section(download_options, override)
    raw_download_options = _unannotate_section(download_options)
    newest = bool_option(raw_download_options, 'newest', 'false')
    fallback = newest and not (filename in downloaded)
    extends_cache = raw_download_options.get('extends-cache')
    if extends_cache and variable_template_split(extends_cache)[1::2]:
        raise ValueError(
            "extends-cache '%s' may not contain ${section:variable} to expand."
            % extends_cache
        )
    download = zc.buildout.download.Download(
        raw_download_options, cache=extends_cache,
        fallback=fallback, hash_name=True)
    is_temp = False
    downloaded_filename = None
    if _isurl(filename):
        downloaded_filename, is_temp = download(filename)
        fp = open(downloaded_filename)
        base = filename[:filename.rfind('/')]
    elif _isurl(base):
        if os.path.isabs(filename):
            fp = open(filename)
            base = os.path.dirname(filename)
        else:
            filename = base + '/' + filename
            downloaded_filename, is_temp = download(filename)
            fp = open(downloaded_filename)
            base = filename[:filename.rfind('/')]
    else:
        filename = os.path.join(base, filename)
        fp = open(filename)
        base = os.path.dirname(filename)
    downloaded.add(filename)

    if filename in seen:
        if is_temp:
            fp.close()
            # downloaded_filename is always set when is_temp is true.
            assert downloaded_filename is not None
            os.remove(downloaded_filename)
        raise zc.buildout.UserError("Recursive file include", seen, filename)

    root_config_file = not seen
    seen.append(filename)

    filename_for_logging = filename
    if downloaded_filename:
        filename_for_logging = '%s (downloaded as %s)' % (
            filename, downloaded_filename)
    result = zc.buildout.configparser.parse(
        fp, filename_for_logging, _default_globals)

    fp.close()
    if is_temp:
        # downloaded_filename is always set when is_temp is true.
        assert downloaded_filename is not None
        os.remove(downloaded_filename)

    # Values are plain strings for now; _annotate below mutates them into
    # SectionKey objects in place.
    options: Dict[str, Any] = result.get('buildout', {})
    extends = options.pop('extends', None)
    if 'extended-by' in options:
        raise zc.buildout.UserError(
            'No-longer supported "extended-by" option found in %s.' %
            filename)

    result = _annotate(result, filename)

    if root_config_file and 'buildout' in result:
        download_options = _update_section(
            download_options, result['buildout']
        )

    # Process extends to handle nested += and -=
    eresults: List[ConfigData] = []
    if extends:
        extends = extends.split()
        for fname in extends:
            next_extend, user_defaults = _open(
                base, fname, seen, download_options, override,
                downloaded, user_defaults)
            # A recursive _open call returns the list form.
            assert isinstance(next_extend, list)
            eresults.extend(next_extend)
    else:
        if user_defaults:
            result = _update(user_defaults, result)
            user_defaults = {}

    optional_extends = options.pop('optional-extends', None)
    if optional_extends:
        optional_extends = optional_extends.value.split()
        for fname in optional_extends:
            if not os.path.exists(fname):
                print("optional-extends file not found: %s" % fname)
                continue
            next_extend, user_defaults = _open(
                base, fname, seen, download_options, override,
                downloaded, user_defaults)
            # A recursive _open call returns the list form.
            assert isinstance(next_extend, list)
            eresults.extend(next_extend)

    eresults.append(result)
    seen.pop()

    if root_config_file:
        final_result: ConfigData = {}
        for eresult in eresults:
            final_result = _update(final_result, eresult)
        return final_result, user_defaults
    else:
        return eresults, user_defaults


ignore_directories = '.svn', 'CVS', '__pycache__', '.git'
_dir_hashes = {}
def _dir_hash(dir: str) -> str:
    dir_hash = _dir_hashes.get(dir, None)
    if dir_hash is not None:
        return dir_hash
    hash = md5()
    for (dirpath, dirnames, filenames) in os.walk(dir):
        dirnames[:] = sorted(n for n in dirnames if n not in ignore_directories)
        filenames[:] = sorted(f for f in filenames
                              if (not (f.endswith('pyc') or f.endswith('pyo'))
                                  and os.path.exists(os.path.join(dirpath, f)))
                          )
        for_hash = ' '.join(dirnames + filenames)
        if isinstance(for_hash, str):
            for_hash = for_hash.encode()
        hash.update(for_hash)
        for name in filenames:
            path = os.path.join(dirpath, name)
            if name == 'entry_points.txt':
                f = open(path)
                # Entry points aren't written in stable order. :(
                try:
                    sections = zc.buildout.configparser.parse(f, path)
                    data = repr([(sname, sorted(sections[sname].items()))
                                 for sname in sorted(sections)]).encode('utf-8')
                except Exception:
                    f.close()
                    f = open(path, 'rb')
                    data = f.read()
            else:
                f = open(path, 'rb')
                data = f.read()
            f.close()
            hash.update(data)
    _dir_hashes[dir] = dir_hash = hash.hexdigest()
    return dir_hash

def _dists_sig(dists: List[pkg_resources.Distribution]) -> List[str]:
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

def _update_section(in1: Dict[str, SectionKey], s2: Dict[str, SectionKey]) -> Dict[str, SectionKey]:
    s1 = copy.deepcopy(in1)
    # Base section 2 on section 1; section 1 is copied, with key-value pairs
    # in section 2 overriding those in section 1. If there are += or -=
    # operators in section 2, process these to add or subtract items (delimited
    # by newlines) from the preexisting values.
    s2 = copy.deepcopy(s2) # avoid mutating the second argument, which is unexpected
    # Sort on key, then on the addition or subtraction operator (+ comes first)
    for k, v in sorted(s2.items(), key=lambda x: (x[0].rstrip(' +'), x[0][-1])):
        if k.endswith('+'):
            key = k.rstrip(' +')
            implicit_value = SectionKey("", "IMPLICIT_VALUE")
            # Find v1 in s2 first; it may have been defined locally too.
            section_key = s2.get(key, s1.get(key, implicit_value))
            section_key = copy.deepcopy(section_key)
            section_key.addToValue(v.value, v.source)
            s2[key] = section_key
            del s2[k]
        elif k.endswith('-'):
            key = k.rstrip(' -')
            implicit_value = SectionKey("", "IMPLICIT_VALUE")
            # Find v1 in s2 first; it may have been set by a += operation first
            section_key = s2.get(key, s1.get(key, implicit_value))
            section_key = copy.deepcopy(section_key)
            section_key.removeFromValue(v.value, v.source)
            s2[key] = section_key
            del s2[k]

    _update_verbose(s1, s2)
    return s1

def _update_verbose(s1: Dict[str, SectionKey], s2: Dict[str, SectionKey]) -> None:
    for key, v2 in s2.items():
        if key in s1:
            v1 = s1[key]
            v1.overrideValue(v2)
        else:
            s1[key] = copy.deepcopy(v2)

def _update(in1: Dict[str, Union[Dict[str, SectionKey], Dict[Any, Any]]], d2: Dict[str, Union[Dict[str, SectionKey], Dict[Any, Any]]]) -> Dict[str, Union[Dict[str, SectionKey], Dict[Any, Any]]]:
    d1 = copy.deepcopy(in1)
    for section in d2:
        if section in d1:
            d1[section] = _update_section(d1[section], d2[section])
        elif '<' not in d2[section].keys():
            # Skip sections that extend in other sections (macros), as we don't
            # have all the data (these will be processed when the section is
            # extended)
            temp = copy.deepcopy(d2[section])
            # 641 - Process base definitions done with += and -=
            for k, v in sorted(temp.items(), key=lambda item: item[0]):
                # Process + before -, configparser resolves conflicts
                if k[-1] == '+' and k[:-2] not in temp:
                    # Turn += without a preceding = into an assignment
                    temp[k[:-2]] = temp[k]
                    del temp[k]
                elif k[-1] == '-' and k[:-2] not in temp:
                    # Turn -= without a preceding = into an empty assignment
                    temp[k[:-2]] = temp[k]
                    temp[k[:-2]].removeFromValue(
                        temp[k[:-2]].value, "IMPLICIT_VALUE"
                        )
                    del temp[k]

            # 656 - Handle multiple option assignments/extensions/removals
            # in the same file, which can happen with conditional sections
            d1[section] = _update_section({}, temp)
        else:
            d1[section] = copy.deepcopy(d2[section])

    return d1

def _recipe(options: Union[Options, Dict[str, str]]) -> Tuple[str, str]:
    recipe = options['recipe']
    if ':' in recipe:
        recipe, entry = recipe.split(':')
    else:
        entry = 'default'

    return recipe, entry

def _doing() -> None:
    _, v, tb = sys.exc_info()
    message = str(v)
    doing = []
    while tb is not None:
        d = tb.tb_frame.f_locals.get('__doing__')
        if d:
            doing.append(d)
        tb = tb.tb_next

    if doing:
        sys.stderr.write('While:\n')
        for d in doing:
            if not isinstance(d, str):
                d = d[0] % d[1:]
            sys.stderr.write('  %s\n' % d)

def _error(*message: Any) -> NoReturn:
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
            "or a bug in the used recipe." %
            (section, ' '.join(map(repr, unused)))
        )

_usage = """\
Usage: buildout [options] [assignments] [command [command arguments]]

Options:

  -c config_file

    Specify the path to the buildout configuration file to be used.
    This defaults to the file named "buildout.cfg" in the current
    working directory.

  -D

    Debug errors.  If an error occurs, then the post-mortem debugger
    will be started. This is especially useful for debugging recipe
    problems.

  -h, --help

    Print this message and exit.

  -N

    Run in non-newest mode.  This is equivalent to the assignment
    buildout:newest=false.  With this setting, buildout will not seek
    new distributions if installed distributions satisfy it's
    requirements.

  -q

    Decrease the level of verbosity.  This option can be used multiple times.

  -t socket_timeout

    Specify the socket timeout in seconds.

  -U

    Don't read user defaults.

  -v

    Increase the level of verbosity.  This option can be used multiple times.

  --version

    Print buildout version number and exit.

Assignments are of the form: section:option=value and are used to
provide configuration options that override those given in the
configuration file.  For example, to run the buildout in offline mode,
use buildout:offline=true.

Options and assignments can be interspersed.

Commands:

  install

    Install the parts specified in the buildout configuration.  This is
    the default command if no command is specified.

  bootstrap

    Create a new buildout in the current working directory, copying
    the buildout and setuptools eggs and, creating a basic directory
    structure and a buildout-local buildout script.

  init [requirements]

    Initialize a buildout, creating a minimal buildout.cfg file if it doesn't
    exist and then performing the same actions as for the bootstrap
    command.

    If requirements are supplied, then the generated configuration
    will include an interpreter script that requires them.  This
    provides an easy way to quickly set up a buildout to experiment
    with some packages.

  setup script [setup command and options]

    Run a given setup script arranging that setuptools is in the
    script's path and and that it has been imported so that
    setuptools-provided commands (like bdist_egg) can be used even if
    the setup script doesn't import setuptools.

    The script can be given either as a script path or a path to a
    directory containing a setup.py script.

  annotate [--interpolated] [section ...]

    Display annotated sections. All sections are displayed, sorted
    alphabetically. For each section, all key-value pairs are displayed,
    sorted alphabetically, along with the origin of the value (file name or
    COMPUTED_VALUE, DEFAULT_VALUE, COMMAND_LINE_VALUE).

    Values are shown raw, as written in the configuration.  Pass
    --interpolated to show the values with ${...} substitutions
    applied, as recipes see them.

  query [--interpolated] section:key

    Display value of given section key pair.  The value is shown raw,
    as written in the configuration.  Pass --interpolated to show the
    value with ${...} substitutions applied, as recipes see it.
"""

def _help() -> NoReturn:
    print_(_usage)
    sys.exit(0)

def _version() -> NoReturn:
    dist = pkg_resources.working_set.find(
        pkg_resources.Requirement.parse('zc.buildout'))
    # We are running, so zc.buildout is in the working set.
    assert dist is not None
    print_("buildout version %s" % dist.version)
    sys.exit(0)

def main(args: Optional[List[str]]=None) -> None:
    if args is None:
        args = sys.argv[1:]

    config_file = 'buildout.cfg'
    verbosity = 0
    options = []
    use_user_defaults = True
    debug = False
    while args:
        if args[0][0] == '-':
            op = orig_op = args.pop(0)
            op = op[1:]
            while op and op[0] in 'vqhWUoOnNDA':
                if op[0] == 'v':
                    verbosity += 10
                elif op[0] == 'q':
                    verbosity -= 10
                elif op[0] == 'U':
                    use_user_defaults = False
                elif op[0] == 'o':
                    options.append(('buildout', 'offline', 'true'))
                elif op[0] == 'O':
                    options.append(('buildout', 'offline', 'false'))
                elif op[0] == 'n':
                    options.append(('buildout', 'newest', 'true'))
                elif op[0] == 'N':
                    options.append(('buildout', 'newest', 'false'))
                elif op[0] == 'D':
                    debug = True
                else:
                    _help()
                op = op[1:]

            if op[:1] in  ('c', 't'):
                op_ = op[:1]
                op = op[1:]

                if op_ == 'c':
                    if op:
                        config_file = op
                    else:
                        if args:
                            config_file = args.pop(0)
                        else:
                            _error("No file name specified for option", orig_op)
                elif op_ == 't':
                    try:
                        timeout_string = args.pop(0)
                        timeout = int(timeout_string)
                        options.append(
                            ('buildout', 'socket-timeout', timeout_string))
                    except IndexError:
                        _error("No timeout value specified for option", orig_op)
                    except ValueError:
                        _error("Timeout value must be numeric", orig_op)
            elif op:
                if orig_op == '--help':
                    _help()
                elif orig_op == '--version':
                    _version()
                else:
                    _error("Invalid option", '-'+op[0])
        elif '=' in args[0]:
            option, value = args.pop(0).split('=', 1)
            option = option.split(':')
            if len(option) == 1:
                option = 'buildout', option[0]
            elif len(option) != 2:
                _error('Invalid option:', option)
            section, option = option
            options.append((section.strip(), option.strip(), value.strip()))
        else:
            # We've run out of command-line options and option assignments
            # The rest should be commands, so we'll stop here
            break

    if verbosity:
        options.append(('buildout', 'verbosity', str(verbosity)))

    if args:
        command = args.pop(0)
        if command not in Buildout.COMMANDS:
            _error('invalid command:', command)
    else:
        command = 'install'

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
        except Exception:
            v = sys.exc_info()[1]
            _doing()
            exc_info = sys.exc_info()
            import pdb, traceback
            if debug:
                traceback.print_exception(*exc_info)
                sys.stderr.write('\nStarting pdb:\n')
                pdb.post_mortem(exc_info[2])
            else:
                if isinstance(v, (zc.buildout.UserError,
                                  distutils.errors.DistutilsError
                                  )
                              ):
                    _error(str(v))
                else:
                    sys.stderr.write(_internal_error_template)
                    traceback.print_exception(*exc_info)
            sys.exit(1)

    finally:
        logging.shutdown()


_bool_names = {'true': True, 'false': False, True: True, False: False}
def bool_option(options: Union[Options, Dict[str, str]], name: str, default: Optional[Union[str, bool]]=None) -> bool:
    value = options.get(name, default)
    if value is None:
        raise KeyError(name)
    try:
        return _bool_names[value]
    except KeyError:
        raise zc.buildout.UserError(
            'Invalid value for %r option: %r' % (name, value))
