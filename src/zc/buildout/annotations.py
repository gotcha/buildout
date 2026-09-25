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
"""Annotation and history tracking for configuration data.

Everything here moved out of ``zc.buildout.buildout`` unchanged; that
module re-exports these names so existing import paths keep working.
"""

from __future__ import annotations

import copy
import os
import sys
from typing import cast

from zc.buildout.utils import print_


def _annotate_section(section: RawSection, source: str) -> AnnotatedSection:
    # The raw dict is annotated in place: write through the cast view,
    # which is the same object with its post-state type.
    annotated = cast(AnnotatedSection, section)
    for key, value in section.items():
        annotated[key] = SectionKey(value, source)
    return annotated


class SectionKey:
    def __init__(self, value: str, source: str) -> None:
        self.history = []
        self.value = value
        self.addToHistory("SET", value, source)

    @property
    def source(self) -> str:
        return self.history[-1].source

    def overrideValue(self, sectionkey: SectionKey) -> None:
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
        value = " ".join(self.value.split('\n'))
        return f"<SectionKey value={value} source={self.source}>"


class HistoryItem:
    def __init__(self, operation: str, value: str, source: str) -> None:
        self.operation = operation
        self.value = value
        self.source = source

    def printShort(self, toprint: list[str], basedir: str) -> None:
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
        value = " ".join(self.value.split('\n'))
        return (f"<HistoryItem operation={self.operation} value={value} "
                f"source={self.source}>")


# Configuration data in its two states: section values are plain strings
# while raw and SectionKey objects once annotated.  _annotate mutates the
# dicts in place, so one dict object changes state; the aliases name the
# states.  The raw state exists only between _parse_config_file and
# _annotate inside configfiles.py; everywhere else the data is annotated,
# which is what ConfigData names.
RawSection = dict[str, str]
AnnotatedSection = dict[str, SectionKey]
ConfigData = dict[str, AnnotatedSection]


def _annotate(data: dict[str, RawSection], note: str) -> dict[str, AnnotatedSection]:
    annotated = cast(dict[str, AnnotatedSection], data)
    for key, section in data.items():
        annotated[key] = _annotate_section(section, note)
    return annotated


def _print_annotate(data: dict[str, dict[str, SectionKey]], verbose: bool, chosen_sections: list[str], basedir: str) -> None:
    sections = list(data.keys())
    sections.sort()
    print_()
    print_("Annotated sections")
    print_("="*len("Annotated sections"))
    for section in sections:
        if (not chosen_sections) or (section in chosen_sections):
            print_()
            print_(f'[{section}]')
            keys = list(data[section].keys())
            keys.sort()
            for key in keys:
                sectionkey = data[section][key]
                sectionkey.printAll(key, basedir, verbose)


def _unannotate_section(section: dict[str, SectionKey]) -> dict[str, str]:
    return {key: entry.value for key, entry in section.items()}


def _unannotate(data: dict[str, dict[str, SectionKey]]) -> dict[str, dict[str, str]]:
    return {key: _unannotate_section(section) for key, section in data.items()}


def _format_picked_versions(picked_versions: list[tuple[str, str]], required_by: dict[str, set[str]]) -> list[str]:
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
        target.append(f"{dist_} = {version}")
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
