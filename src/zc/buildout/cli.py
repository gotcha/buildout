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
"""Command-line parsing cluster.

Everything here moved out of ``zc.buildout.buildout`` unchanged; that
module re-exports these names so existing import paths keep working.
``main`` itself stays in ``zc.buildout.buildout``: the debugging doctest
pins its traceback frame to the ``buildout.py`` filename, which also
keeps the ``zc.buildout.buildout:main`` console-script path literal.
Cycle edges stay lazy at call time: ``Buildout``, ``_error``,
``_doing``, and ``_internal_error_template`` resolve from buildout.py
inside the functions that use them, and the pdb/traceback imports
inside ``_handle_buildout_error`` keep their historical laziness.
"""

from __future__ import annotations

import distutils.errors  # ty: ignore[unresolved-import]  # runtime: setuptools distutils-precedence hook
import sys
from typing import NoReturn

import pkg_resources

import zc.buildout
from zc.buildout.utils import print_

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
    print_(f"buildout version {dist.version}")
    sys.exit(0)


def _apply_letter_flag(
        flag: str,
        verbosity: int,
        use_user_defaults: bool,
        debug: bool,
        options: list[tuple[str, str, str]],
        ) -> tuple[int, bool, bool]:
    """Apply a bundled single-letter flag; return the updated
    ``(verbosity, use_user_defaults, debug)``."""
    if flag == 'v':
        verbosity += 10
    elif flag == 'q':
        verbosity -= 10
    elif flag == 'U':
        use_user_defaults = False
    elif flag == 'o':
        options.append(('buildout', 'offline', 'true'))
    elif flag == 'O':
        options.append(('buildout', 'offline', 'false'))
    elif flag == 'n':
        options.append(('buildout', 'newest', 'true'))
    elif flag == 'N':
        options.append(('buildout', 'newest', 'false'))
    elif flag == 'D':
        debug = True
    else:
        _help()
    return verbosity, use_user_defaults, debug


def _valued_option(
        op: str,
        orig_op: str,
        config_file: str,
        args: list[str],
        options: list[tuple[str, str, str]],
        ) -> str:
    """Handle the ``-c``/``-t`` options; return the (possibly new)
    config file."""
    from zc.buildout.buildout import _error
    op_ = op[:1]
    op = op[1:]

    if op_ == 'c':
        if op:
            config_file = op
        elif args:
            config_file = args.pop(0)
        else:
            _error("No file name specified for option", orig_op)
    elif op_ == 't':
        try:
            timeout_string = args.pop(0)
            # Quirk preserved: the value is only validated, never used.
            int(timeout_string)
            options.append(
                ('buildout', 'socket-timeout', timeout_string))
        except IndexError:
            _error("No timeout value specified for option", orig_op)
        except ValueError:
            _error("Timeout value must be numeric", orig_op)
    return config_file


def _long_option(orig_op: str, op: str) -> None:
    """Handle ``--help``/``--version``, rejecting any other option."""
    from zc.buildout.buildout import _error
    if orig_op == '--help':
        _help()
    elif orig_op == '--version':
        _version()
    else:
        _error("Invalid option", '-'+op[0])


def _option_assignment(arg: str) -> tuple[str, str, str]:
    """Parse a ``section:option=value`` command-line assignment into a
    stripped ``(section, option, value)`` tuple."""
    from zc.buildout.buildout import _error
    option, value = arg.split('=', 1)
    parts = option.split(':')
    if len(parts) == 1:
        section, name = 'buildout', parts[0]
    elif len(parts) != 2:
        # Quirk preserved: _error space-joins its arguments, so passing
        # the list raises TypeError instead of a clean error exit.
        _error('Invalid option:', parts)
    else:
        section, name = parts
    return section.strip(), name.strip(), value.strip()


def _pop_command(args: list[str]) -> str:
    """Pop the command from ``args``, defaulting to ``install``."""
    from zc.buildout.buildout import Buildout, _error
    if args:
        command = args.pop(0)
        if command not in Buildout.COMMANDS:
            _error('invalid command:', command)
    else:
        command = 'install'
    return command


def _handle_buildout_error(debug: bool) -> NoReturn:
    """Report a buildout failure (a pdb post-mortem under ``-D``) and
    exit 1."""
    from zc.buildout.buildout import _doing, _error, _internal_error_template
    v = sys.exc_info()[1]
    _doing()
    exc_info = sys.exc_info()
    import pdb  # noqa: T100 - the --debug flag's documented entry point
    import traceback
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


def _consume_letter_flags(
        op: str,
        verbosity: int,
        use_user_defaults: bool,
        debug: bool,
        options: list[tuple[str, str, str]],
        ) -> tuple[str, int, bool, bool]:
    """Consume the bundled single-letter flags of ``op``; return the
    remaining ``op`` and the updated ``(verbosity, use_user_defaults,
    debug)``."""
    while op and op[0] in 'vqhWUoOnNDA':
        verbosity, use_user_defaults, debug = _apply_letter_flag(
            op[0], verbosity, use_user_defaults, debug, options)
        op = op[1:]
    return op, verbosity, use_user_defaults, debug

