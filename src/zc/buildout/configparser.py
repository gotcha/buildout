##############################################################################
#
# Copyright Zope Foundation and Contributors.
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

from __future__ import annotations

import logging

# The following copied from Python 2 config parser because:
# - The py3 configparser isn't backward compatible
# - Both strip option values in undesirable ways
# - dict of dicts is a much simpler api
import re
import textwrap
from collections.abc import Callable
from io import StringIO, TextIOWrapper
from typing import Any

from packaging import markers

Marker = markers.Marker
InvalidMarker = markers.InvalidMarker


logger = logging.getLogger('zc.buildout')

class Error(Exception):
    """Base class for ConfigParser exceptions."""

    def _get_message(self) -> str:
        """Getter for 'message'; needed only to override deprecation in
        BaseException."""
        return self.__message

    def _set_message(self, value: str) -> None:
        """Setter for 'message'; needed only to override deprecation in
        BaseException."""
        self.__message = value

    # BaseException.message has been deprecated since Python 2.6.  To prevent
    # DeprecationWarning from popping up over this pre-existing attribute, use
    # a new property that takes lookup precedence.
    message = property(_get_message, _set_message)

    def __init__(self, msg: str='') -> None:
        self.message = msg
        Exception.__init__(self, msg)

    def __repr__(self) -> str:
        return self.message

    __str__ = __repr__

class ParsingError(Error):
    """Raised when a configuration file does not follow legal syntax."""

    def __init__(self, filename: str) -> None:
        Error.__init__(self, f'File contains parsing errors: {filename}')
        self.filename = filename
        self.errors = []

    def append(self, lineno: int, line: str) -> None:
        self.errors.append((lineno, line))
        self.message += f'\n\t[line {lineno:2d}]: {line}'

class MissingSectionHeaderError(ParsingError):
    """Raised when a key-value pair is found before any section header."""

    def __init__(self, filename: str, lineno: int, line: str) -> None:
        Error.__init__(
            self,
            f'File contains no section headers.\nfile: {filename}, line: '
            f'{lineno}\n{line!r}')
        self.filename = filename
        self.lineno = lineno
        self.line = line

# This regex captures either sections headers with optional trailing comment
# separated by a semicolon or a hash.  Section headers can have an optional
# expression. Expressions and comments can contain brackets but no verbatim '#'
# and ';' : these need to be escaped.
# A title line with an expression has the general form:
#  [section_name: some Python expression] #; some comment
# This regex leverages the fact that the following is a valid Python expression:
#  [some Python expression] # some comment
# and that section headers are also delimited by [brackets] that are also [list]
# delimiters.
# So instead of doing complex parsing to balance brackets in an expression, we
# capture just enough from a header line to collect then remove the section_name
# and colon expression separator keeping only a list-enclosed expression and
# optional comments. The parsing and validation of this Python expression can be
# entirely delegated to Python's eval. The result of the evaluated expression is
# the always returned wrapped in a list with a single item that contains the
# original expression

section_header  = re.compile(
    r'(?P<head>\[)'
    r'\s*'
    r'(?P<name>[^\s#[\]:;{}]+)'
    r'\s*'
    r'(:(?P<expression>[^#;]*))?'
    r'\s*'
    r'(?P<tail>]'
    r'\s*'
    r'([#;].*)?$)'
    ).match

option_start = re.compile(
    r'(?P<name>[^\s{}[\]=:]+\s*[-+]?)'
    r'='
    r'(?P<value>.*)$').match

leading_blank_lines = re.compile(r"^(\s*\n)+")

def _merge_option(cursect: dict[str, str], optname: str, optval: str) -> None:
    """Merge one option line into a section dict.

    A ``name +``/``name -`` operator accumulates values across
    conditional sections. A plain ``name =`` assignment overrides and
    replaces preceding extends/removes of the same name.
    """
    optname = optname.rstrip()
    optval = optval.strip()
    opt_op = optname[-1]
    if opt_op not in '+-':
        opt_op = '='
    if optname in cursect and opt_op in '+-':
        # Strip any trailing \n, which happens when we have multiple
        # +=/-= in one file
        cursect[optname] = cursect[optname].rstrip()
        if optval:
            cursect[optname] = f"{cursect[optname]}\n{optval}"
    else:
        if opt_op == '=':
            for suffix in '+-':
                tempname = f"{optname} {suffix}"
                if tempname in cursect:
                    del cursect[tempname]
        cursect[optname] = optval


def _evaluate_section_condition(head: str, expression: str, tail: str, context_getter: Callable) -> bool:
    """Evaluate the condition expression of a section header.

    New-style markers as used in pip constraints are tried first, e.g.:
    'python_version < "3.11" and platform_system == "Windows"'.
    On InvalidMarker, fall back to the old-style buildout expression:
    rebuild a valid Python expression wrapped in a list and evaluate
    its first element.
    """
    # normalize tail comments to Python style
    tail = tail.replace(';', '#') if tail else ''
    # un-escape literal # and ; . Do not use a string-escape decode
    expr = expression.replace(r'\x23', '#').replace(r'\x3b', ';')
    try:
        return Marker(expr).evaluate()
    except InvalidMarker:
        # lazily populate context for old-style expressions only
        # evaluated expression is in list: get first element
        return eval(head + expr + tail, context_getter())[0]


def _append_continuation(cursect: dict[str, str], optname: str, line: str, blockmode: bool) -> None:
    """Append a continuation line to the current option value."""
    if blockmode:
        line = line.rstrip()
    else:
        line = line.strip()
    cursect[optname] = f"{cursect[optname]}\n{line}"


def _finalize_sections(sections: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Dedent and right-strip multi-line option values in place."""
    for sectname in sections:
        section = sections[sectname]
        for name in section:
            value = section[name]
            if value[:1].isspace():
                section[name] = leading_blank_lines.sub(
                    '', textwrap.dedent(value.rstrip()))
    return sections


def _handle_continuation(
        line: str, cursect: dict[str, str] | None, optname: str | None,
        section_condition: bool, blockmode: bool) -> bool:
    """Handle a continuation line of the current option value.

    Return True when the line was consumed, appended or skipped; return
    False when it is not a continuation line and must be dispatched as
    a section header, option, or preamble line.
    """
    if not line[0].isspace() or cursect is None or not optname:
        return False
    if not section_condition:
        #skip section based on its expression condition
        return True
    if not blockmode and not line.strip():
        return True
    # continuation line
    _append_continuation(cursect, optname, line, blockmode)
    return True


def _expression_context(context: list[Any], exp_globals: Callable) -> Any:
    """Return the evaluation context for old-style section expressions,
    lazily populated from ``exp_globals``.

    Quirk preserved: a falsy context (e.g. an empty dict) is re-fetched
    from ``exp_globals`` on every old-style expression.
    """
    if context and context[0]:
        return context[0]
    value = exp_globals()
    context[:] = [value]
    return value


def _start_section(
        header: re.Match, sections: dict[str, dict[str, str]],
        context: list[Any], exp_globals: Callable,
        ) -> tuple[dict[str, str] | None, bool]:
    """Start the section named by a section header match.

    Return ``(cursect, section_condition)``; the condition is reset to
    True unless the header carries an expression evaluating to false.
    A false condition ignores the section: cursect is None and the
    caller must leave its current section and option untouched, so
    that following continuation and option lines get filtered out.
    """
    # reset to True when starting a new section
    section_condition = True
    sectname = header.group('name')

    expression = header.group('expression')
    if expression:
        section_condition = _evaluate_section_condition(
            header.group('head'), expression, header.group('tail'),
            lambda: _expression_context(context, exp_globals))
        # finally, ignore section when an expression
        # evaluates to false
        if not section_condition:
            # Keep eager printf here: logging's lazy args cannot do
            # mapping-key substitution (msg % mapping raises TypeError).
            logger.debug(
                'Ignoring section %(sectname)r with [expression]:'  # noqa: UP031
                ' %(expression)r' % locals())
            return None, section_condition

    if sectname in sections:
        cursect = sections[sectname]
    else:
        sections[sectname] = cursect = {}
    return cursect, section_condition


def _handle_preamble_line(line: str, fpname: str, lineno: int) -> None:
    """Only blank lines are allowed before the first section header."""
    if line.strip():
        # no section header in the file?
        raise MissingSectionHeaderError(fpname, lineno, line)


def _handle_option_line(
        line: str, cursect: dict[str, str], optname: str | None,
        blockmode: bool, section_condition: bool, fpname: str,
        lineno: int, error: ParsingError | None,
        ) -> tuple[str | None, bool, ParsingError | None] | None:
    """Process an option or bogus line within a section.

    Return None when the line must be skipped: an option filtered out
    of a conditionally ignored section.  Otherwise return the possibly
    updated ``(optname, blockmode, error)``; a non-fatal parsing error
    is collected into ``error``, to be raised at the end of the file
    with a list of all bogus lines.
    """
    if line[:2] == '=>':
        line = '<part-dependencies> = ' + line[2:]
    mo = option_start(line)
    if mo:
        if not section_condition:
            # filter out options of conditionally ignored section
            return None
        # option start line
        optname, optval = mo.group('name', 'value')
        optname = optname.rstrip()
        _merge_option(cursect, optname, optval)
        blockmode = not optval
    elif optname or line.strip():
        # a non-fatal parsing error occurred.  set up the
        # exception but keep going. the exception will be
        # raised at the end of the file and will contain a
        # list of all bogus lines
        if not error:
            error = ParsingError(fpname)
        error.append(lineno, repr(line))
    return optname, blockmode, error


def parse(fp: StringIO | TextIOWrapper, fpname: str, exp_globals: type[dict] | Callable=dict) -> dict[str, dict[str, str]]:
    """Parse a sectioned setup file.

    The sections in setup files contain a title line at the top,
    indicated by a name in square brackets (`[]'), plus key/value
    options lines, indicated by `name: value' format lines.
    Continuations are represented by an embedded newline then
    leading whitespace.  Blank lines, lines beginning with a '#',
    and just about everything else are ignored.

    The title line is in the form [name] followed by an optional trailing
    comment separated by a semicolon `;' or a hash `#' character.

    Optionally the title line can have the form `[name:expression]' where
    expression is an arbitrary Python expression. Sections with an expression
    that evaluates to False are ignored. Semicolon `;' an hash `#' characters
    must be string-escaped in expression literals.

    exp_globals is a callable returning a mapping of defaults used as globals
    during the evaluation of a section conditional expression.
    """
    sections = {}
    # the current section condition, possibly updated from a section expression
    section_condition = True
    context: list[Any] = []  # lazy expression context, see _expression_context
    cursect = None                            # None, or a dictionary
    blockmode = False
    optname = None
    lineno = 0
    e = None                                  # None, or an exception
    while True:
        line = fp.readline()
        if not line:
            break # EOF

        lineno = lineno + 1

        if line[0] in '#;':
            continue # comment

        if _handle_continuation(
                line, cursect, optname, section_condition, blockmode):
            continue

        header = section_header(line)
        if header:
            new_cursect, section_condition = _start_section(
                header, sections, context, exp_globals)
            if new_cursect is None:
                continue
            cursect = new_cursect
            # So sections can't start with a continuation line
            optname = None
        elif cursect is None:
            _handle_preamble_line(line, fpname, lineno)
        else:
            handled = _handle_option_line(
                line, cursect, optname, blockmode, section_condition,
                fpname, lineno, e)
            if handled is None:
                continue
            optname, blockmode, e = handled

    # if any parsing errors occurred, raise an exception
    if e:
        raise e

    return _finalize_sections(sections)
