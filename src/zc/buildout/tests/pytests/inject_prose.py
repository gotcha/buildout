#!/usr/bin/env python3
"""Inject the narrative prose of legacy doctest sources into the generated
pytest files as comments.

Walks doctest.DocTestParser().parse() output for each source; prose preceding
an example becomes a comment block above that example's first emitted
statement in the matching generated function. Anchors follow gen_pytest's
emit_example() branches and are matched with an in-order cursor, so no
position is ever guessed. Idempotent: a block whose first content line
already sits at its anchor is skipped.

Usage:
    python inject_prose.py                 inject everywhere
    python inject_prose.py --check         report coverage, write nothing
    python inject_prose.py --only test_pytest_update.py
"""
import argparse
import ast
import doctest
import re
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import gen_pytest  # ty: ignore[unresolved-import]  # sibling module; this file runs as a script from its own dir
from gen_pytest import (  # ty: ignore[unresolved-import]  # sibling via sys.path.insert above
    collect_doctest_fns, dedent_strings, extract_print_arg,
    looks_like_python_literal, looks_like_traceback)

TESTS = HERE.parent

SPECS = {
    'test_pytest_buildout_files.py': [('txt', s) for s in (
        'runsetup.txt', 'repeatable.txt', 'setup.txt', 'debugging.txt',
        'windows.txt')],
    'test_pytest_buildout_txt.py': [('txt', s) for s in (
        'buildout.txt', 'configuration.txt', 'extending.txt', 'options.txt',
        'init.txt', 'extensions.txt')],
    'test_pytest_easy_install_files.py': [('txt', s) for s in (
        'easy_install.txt', 'downloadcache.txt', 'dependencylinks.txt',
        'allowhosts.txt', 'allow-unknown-extras.txt', 'download.txt',
        'extends-cache.txt', 'testing_bugfix.txt')],
    'test_pytest_update.py': [('txt', 'update.txt')],
    'test_pytest_configparser.py': [('preamble', 'configparser.test')],
    'test_pytest_buildout_doctests.py': [('docstrings', 'test_all.py')],
    'test_pytest_extras.py': [('docstrings', 'test_extras.py')],
    'test_pytest_increment.py': [('docstrings', 'test_increment.py')],
}

DIRECTIVE_RE = re.compile(r'\s*#\s*doctest:.*$')
UNPACK_RE = re.compile(r'^\s+\w+\s*=\s*\w+\[.*\]\s*$')
INDENT = '    '


def norm(s):
    return ' '.join(s.split())


def dequote(s):
    return s.replace("'", '').replace('"', '')


def clean_source(ex):
    src_lines = ex.source.rstrip('\n').split('\n')
    src_lines[-1] = DIRECTIVE_RE.sub('', src_lines[-1])
    return '\n'.join(src_lines)


def first_line(s):
    for line in s.split('\n'):
        if line.strip():
            return line.strip()
    return ''


def identifiers(src, skip=()):
    try:
        tree = ast.parse(src.strip(), mode='exec')
    except SyntaxError:
        try:
            tree = ast.parse(src.strip(), mode='eval')
        except SyntaxError:
            return []
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.append(node.id)
        elif isinstance(node, ast.Attribute):
            found.append(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value.strip()
            if v and ' ' not in v and '%' not in v and len(v) <= 30:
                found.append(v)
    seen, out = set(), []
    for i in found:
        if i not in seen and i not in skip:
            seen.add(i)
            out.append(i)
    return out


def anchor_plan(ex, fixture_var):
    """(candidate normalized prefixes, identifier fallback, in try: block)."""
    gen_pytest.FIXTURE_VAR = fixture_var
    src = clean_source(ex)
    stripped = src.strip()
    want = ex.want
    fsrc = first_line(stripped)
    cands, idents, in_try = [], None, False
    if not stripped:
        return cands, idents, in_try

    def via_dedent():
        fixed = dedent_strings(src)
        if fixed is not None:
            cands.append(norm(fixed.split('\n')[0].strip()))
        cands.append(norm(fsrc))

    if not want.strip():
        via_dedent()
        idents = identifiers(stripped)
    elif stripped.startswith('print_('):
        inner = extract_print_arg(stripped)
        if inner is not None:
            if 'system(' in inner:
                cands.append(norm('assert_output(%s' % inner))
            else:
                cands.append(norm('assert_output(str(%s' % inner))
            idents = identifiers(inner)
        else:
            cands.append('assert_output(capture_print(lambda: print_(')
            idents = identifiers(stripped, skip=('print_',))
    elif stripped.startswith('ls('):
        cands.append('assert_output(capture_print(ls')
        idents = identifiers(stripped)
    elif stripped.startswith('cat('):
        cands.append('assert_output(capture_print(cat')
        idents = identifiers(stripped)
    elif looks_like_traceback(want):
        cands.append(norm(fsrc))
        in_try = True
        idents = identifiers(stripped)
    elif looks_like_python_literal(want):
        try:
            ast.parse(stripped, mode='eval')
            cands.append(norm('_val = (%s' % fsrc))
        except SyntaxError:
            via_dedent()
        idents = identifiers(stripped)
    else:
        try:
            ast.parse(stripped, mode='eval')
            cands.append(norm('assert_output(capture_print(lambda: %s' % fsrc))
        except SyntaxError:
            via_dedent()
        idents = identifiers(stripped)
    cands.append(norm(fsrc))
    return [c for c in cands if c], idents, in_try


def find_anchor(lines, lo, hi, cands, idents):
    def searchable(i):
        return lines[i].strip() and not lines[i].lstrip().startswith('#')
    for cand in cands:
        for i in range(lo, hi):
            if not searchable(i):
                continue
            g = norm(lines[i])
            if g.startswith(cand) or (len(g) >= 10 and cand.startswith(g)):
                return i
    if idents:
        wanted = [dequote(i) for i in idents]
        for i in range(lo, hi):
            if not searchable(i):
                continue
            g = dequote(norm(lines[i]))
            if all(w in g for w in wanted):
                return i
    frag = dequote(cands[-1]) if cands else ''
    for _ in range(3):
        if len(frag) < 12:
            break
        for i in range(lo, hi):
            if searchable(i) and frag in dequote(norm(lines[i])):
                return i
        m = re.match(r'^\w+(?:\.\w+)*\((.*)$', frag)
        if not m:
            break
        frag = m.group(1)
    return None


def render_block(prose, indent=INDENT):
    lines = textwrap.dedent(prose).split('\n')
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    out = []
    for line in lines:
        line = line.rstrip()
        out.append(indent + '# ' + line if line else indent + '#')
    return out


def first_content(block):
    for line in block:
        if line.strip() != '#':
            return norm(line)
    return None


def already_present(lines, idx, block):
    target = first_content(block)
    if target is None:
        return True
    j = idx - 1
    while j >= 0 and (not lines[j].strip()
                      or lines[j].lstrip().startswith('#')):
        if norm(lines[j]) == target:
            return True
        j -= 1
    j = idx
    while j < len(lines) and (not lines[j].strip()
                              or lines[j].lstrip().startswith('#')):
        if norm(lines[j]) == target:
            return True
        j += 1
    return False


class Stats:
    def __init__(self):
        self.placed = self.present = self.missed = 0
        self.anchored = self.unplaced = 0
        self.misses = []


def walk_function(lines, span, fixture_var, parts, stats):
    fstart, fend = span
    cursor = fstart + 1
    while cursor < fend and (UNPACK_RE.match(lines[cursor])
                             or not lines[cursor].strip()):
        cursor += 1
    insertions = []
    pending = []
    for part in parts:
        if isinstance(part, str):
            pending.append(part)
            continue
        prose = ''.join(pending)
        pending = []
        block = render_block(prose) if prose.strip() else None
        cands, idents, in_try = anchor_plan(part, fixture_var)
        idx = find_anchor(lines, cursor, fend, cands, idents)
        if idx is None:
            stats.unplaced += 1
            if block:
                stats.missed += 1
            stats.misses.append(first_line(clean_source(part)))
            continue
        stats.anchored += 1
        aidx = idx
        if in_try and idx > fstart and norm(lines[idx - 1]) == 'try:':
            aidx = idx - 1
        cursor = idx + 1
        if block:
            if already_present(lines, aidx, block):
                stats.present += 1
            else:
                insertions.append((aidx, block))
                stats.placed += 1
    trailing = ''.join(pending)
    if trailing.strip():
        block = render_block(trailing)
        if already_present(lines, fend, block):
            stats.present += 1
        else:
            insertions.append((fend, block))
            stats.placed += 1
    return insertions


def targets_for(kind, srcname):
    parser = doctest.DocTestParser()
    if kind == 'txt':
        stem = Path(srcname).stem.replace('-', '_')
        parts = parser.parse((TESTS / srcname).read_text())
        return [('test_' + stem, parts)]
    out = []
    for name, doc in collect_doctest_fns(str(TESTS / srcname)):
        pyname = name if name.startswith('test_') else 'test_' + name
        out.append((pyname, parser.parse(doc)))
    return out


def process_file(gen_path, sources, write):
    text = gen_path.read_text()
    lines = text.split('\n')
    tree = ast.parse(text)
    fns = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            arg = node.args.args[0].arg if node.args.args else ''
            fns[node.name] = ((node.lineno - 1, node.end_lineno), arg)
    stats = Stats()
    insertions = []
    for kind, srcname in sources:
        if kind == 'preamble':
            parser = doctest.DocTestParser()
            prose = [p for p in parser.parse((TESTS / srcname).read_text())
                     if isinstance(p, str) and p.strip()]
            block = ['# Context from %s, the legacy doctest this file was '
                     'hand-ported from.' % srcname]
            for p in prose:
                block.extend(render_block(p, ''))
                block.append('#')
            if already_present(lines, 0, block):
                stats.present += len(prose)
            else:
                insertions.append((0, block))
                stats.placed += len(prose)
            continue
        for fn_name, parts in targets_for(kind, srcname):
            if fn_name not in fns:
                stats.misses.append('function %s (from %s) not found'
                                    % (fn_name, srcname))
                stats.unplaced += len(
                    [p for p in parts if isinstance(p, doctest.Example)])
                continue
            span, fixture_var = fns[fn_name]
            insertions.extend(
                walk_function(lines, span, fixture_var, parts, stats))
    added = sum(len(b) for _, b in insertions)
    if write and insertions:
        for idx, block in sorted(insertions, reverse=True):
            lines[idx:idx] = block
        gen_path.write_text('\n'.join(lines))
    return stats, added


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--check', action='store_true',
                    help='report coverage without writing')
    ap.add_argument('--only', metavar='NAME',
                    help='process only the given generated file')
    args = ap.parse_args(argv)

    specs = SPECS
    if args.only:
        name = args.only
        if not name.endswith('.py'):
            name += '.py'
        if name not in SPECS:
            ap.error('unknown file %r (choose from: %s)'
                     % (args.only, ', '.join(sorted(SPECS))))
        specs = {name: SPECS[name]}

    total_unplaced = 0
    for fname in sorted(specs):
        stats, added = process_file(HERE / fname, specs[fname],
                                    write=not args.check)
        total_unplaced += stats.unplaced
        action = 'would add' if args.check else 'added'
        print('%s: blocks placed=%d already-present=%d missed=%d '
              '(comment lines %s: %d); examples anchored=%d unplaced=%d'
              % (fname, stats.placed, stats.present, stats.missed,
                 action, added, stats.anchored, stats.unplaced))
        for m in stats.misses:
            print('    unplaced: %s' % m)
    return 1 if total_unplaced else 0


if __name__ == '__main__':
    sys.exit(main())
