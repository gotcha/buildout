#!/usr/bin/env python3
"""Generate pytest test functions from doctest functions and .txt doctest files.

Produces files with no DocTestRunner dependency. Each doctest example becomes
a direct Python statement or assert_output() call.

Usage (inline doctests):
    python gen_pytest.py --source src/zc/buildout/tests/test_all.py \
                         --output src/zc/buildout/tests/test_pytest_buildout_doctests.py

Usage (.txt file):
    python gen_pytest.py --txt runsetup.txt --fixture buildout_env \
                         --normalizer NORMALIZERS_BUILDOUT \
                         --output src/zc/buildout/tests/test_pytest_buildout_files.py
"""
from __future__ import annotations

import ast
import doctest
import re
import textwrap
from pathlib import Path

ENV_NAMES = frozenset({
    'sample_buildout', 'ls', 'cat', 'mkdir', 'rmdir', 'remove', 'tmpdir',
    'write', 'system', 'get', 'cd', 'uncd', 'join', 'sdist', 'bdist_egg',
    'start_server', 'stop_server', 'buildout', 'wait_until', 'print_',
    'clean_up_pyc', 'os', 'sample_eggs', 'link_server', 'update_extdemo',
    'new_releases',
})

FIXTURE_VAR = 'easy_install_env'  # overridden per call


class _UsageVisitor(ast.NodeVisitor):
    """First load line and first bind line of each ENV_NAME in a body.

    Bodies bind their own imports and rewrite fixture calls, so the
    unpacking set must come from the emitted statements, not the
    doctest source. A name loaded before the body's own binding (line
    order) stays load-bearing and keeps its unpacking line. A name the
    body binds first would shadow its unpacking unused (F811) or go
    unread entirely (F841).

    Loads inside nested scopes count as loads of the outer name even
    when the nested scope shadows it through a parameter: over-keeping
    an unpacking line is the safe direction, and a lint run after
    generation catches any residue.
    """

    def __init__(self) -> None:
        super().__init__()
        self.first_load: dict[str, int] = {}
        self.first_bind: dict[str, int] = {}

    def _note(self, name: str, lineno: int, book: dict[str, int]) -> None:
        if name in ENV_NAMES:
            book.setdefault(name, lineno)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self._note(node.id, node.lineno, self.first_load)
        else:
            self._note(node.id, node.lineno, self.first_bind)

    def _note_import(self, node: ast.Import | ast.ImportFrom) -> None:
        for alias in node.names:
            name = alias.asname or alias.name.split('.')[0]
            self._note(name, node.lineno, self.first_bind)

    def visit_Import(self, node: ast.Import) -> None:
        self._note_import(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self._note_import(node)

    def _note_def(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    ) -> None:
        self._note(node.name, node.lineno, self.first_bind)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._note_def(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._note_def(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._note_def(node)


def env_names_loaded(emitted_lines: list[str]) -> list[str]:
    """Fixture names the emitted body loads before binding anything itself."""
    if not any(line.strip() for line in emitted_lines):
        return []
    # Wrapping in a def keeps the lines parseable even when triple-quoted
    # string interiors sit at column zero, where textwrap.dedent would
    # leave the first statement unexpectedly indented.
    tree = ast.parse('def _emitted():\n' + '\n'.join(emitted_lines))
    visitor = _UsageVisitor()
    visitor.visit(tree)
    return sorted(name for name, line in visitor.first_load.items()
                  if line <= visitor.first_bind.get(name, line))


def dedent_strings(src):
    """Parse src, dedent every multiline string constant, re-emit via ast.unparse.

    Also replaces % globals() with % <fixture_var> (and the same for
    .format_map(globals())) so that substitutions use the fixture dict
    instead of module globals.
    """
    try:
        mod = ast.parse(src, mode='exec')
    except SyntaxError:
        return None

    class _Fixer(ast.NodeTransformer):
        def visit_Constant(self, node):
            if isinstance(node.value, str) and '\n' in node.value:
                node.value = textwrap.dedent(node.value)
            return node

        def visit_BinOp(self, node):
            self.generic_visit(node)
            # Replace 'string' % globals() with 'string' % <fixture>
            if (isinstance(node.op, ast.Mod) and
                    isinstance(node.right, ast.Call) and
                    isinstance(node.right.func, ast.Name) and
                    node.right.func.id == 'globals'):
                node.right = ast.Name(id=FIXTURE_VAR, ctx=ast.Load())
            return node

        def visit_Call(self, node):
            self.generic_visit(node)
            # Replace 'string'.format_map(globals()) with
            # 'string'.format_map(<fixture>)
            if (isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'format_map'
                    and len(node.args) == 1
                    and isinstance(node.args[0], ast.Call)
                    and isinstance(node.args[0].func, ast.Name)
                    and node.args[0].func.id == 'globals'
                    and not node.args[0].args):
                node.args[0] = ast.Name(id=FIXTURE_VAR, ctx=ast.Load())
            return node

    fixed = _Fixer().visit(mod)
    ast.fix_missing_locations(fixed)
    return '\n'.join(ast.unparse(stmt) for stmt in fixed.body)


def looks_like_python_literal(s):
    try:
        ast.literal_eval(s.strip())
        return True
    except (ValueError, SyntaxError):
        return False


def looks_like_traceback(s):
    return s.strip().startswith('Traceback (most recent call last):')


def extract_print_arg(src_text):
    try:
        call = ast.parse(src_text.strip(), mode='eval').body
        if (isinstance(call, ast.Call) and
                isinstance(call.func, ast.Name) and
                call.func.id == 'print_' and call.args):
            return ast.unparse(call.args[0])
    except SyntaxError:
        pass
    try:
        mod = ast.parse(src_text.strip(), mode='exec')
        for node in ast.walk(mod):
            if (isinstance(node, ast.Call) and
                    isinstance(node.func, ast.Name) and
                    node.func.id == 'print_' and node.args):
                return ast.unparse(node.args[0])
    except SyntaxError:
        pass
    return None


def make_capture_print(stripped):
    """For ls(a, b) emit capture_print(ls, a, b) — pass fn and args separately."""
    try:
        call = ast.parse(stripped, mode='eval').body
        fn_name = ast.unparse(call.func)
        args = ', '.join(ast.unparse(a) for a in call.args)
        kwargs = ', '.join(f'{k.arg}={ast.unparse(k.value)}'
                          for k in call.keywords)
        all_args = ', '.join(filter(None, [args, kwargs]))
        if all_args:
            return f'capture_print({fn_name}, {all_args})'
        return f'capture_print({fn_name})'
    except SyntaxError:
        return None


def emit_example(ex, fixture_var):
    """Return a list of source lines for one doctest example."""
    global FIXTURE_VAR
    FIXTURE_VAR = fixture_var

    src_raw = ex.source.rstrip('\n')
    want = ex.want

    src_lines = src_raw.split('\n')
    src_lines[-1] = re.sub(r'\s*#\s*doctest:.*$', '', src_lines[-1])
    src_raw = '\n'.join(src_lines)
    stripped = src_raw.strip()

    lines = []

    if not want.strip():
        fixed = dedent_strings(src_raw)
        for line in (fixed if fixed is not None else textwrap.dedent(src_raw)).split('\n'):
            lines.append('    ' + line)
        return lines

    want_stripped = want.rstrip('\n')
    want_lines = ['' if line == '<BLANKLINE>' else line
                  for line in want_stripped.split('\n')]
    expected = '\n'.join(want_lines)

    if stripped.startswith('print_('):
        inner = extract_print_arg(stripped)
        if inner is not None:
            if 'system(' in inner:
                lines.append(f'    assert_output({inner}, {expected!r}, N)')
            else:
                lines.append(f'    assert_output(str({inner}), {expected!r}, N)')
        else:
            lines.append(
                f'    assert_output(capture_print(lambda: {stripped}), {expected!r}, N)')

    elif stripped.startswith('ls('):
        cp = make_capture_print(stripped)
        lines.append(f"    assert_output({cp or 'capture_print(ls)'}, {expected!r}, N)")

    elif stripped.startswith('cat('):
        cp = make_capture_print(stripped)
        lines.append(f"    assert_output({cp or 'capture_print(cat)'}, {expected!r}, N)")

    elif looks_like_traceback(expected):
        last_line = expected.strip().split('\n')[-1]
        exc_type = last_line.split(':')[0].strip()
        lines.append('    try:')
        for line in stripped.split('\n'):
            lines.append('        ' + line)
        lines.append(f'        assert False, "Expected {exc_type} not raised"')
        lines.append('    except Exception as _exc:')
        lines.append(
            f'        assert_output(type(_exc).__name__ + ": " + str(_exc), {last_line!r}, N)')

    else:
        if looks_like_python_literal(expected):
            try:
                ast.parse(stripped, mode='eval')
                if stripped.startswith('(') and stripped.endswith(')'):
                    # Already parenthesized: another layer would trip UP034.
                    lines.append(f'    _val = {stripped}')
                else:
                    lines.append(f'    _val = ({stripped})')
                lines.append(
                    f'    assert repr(_val) == {expected!r} or str(_val) == {expected!r}')
            except SyntaxError:
                fixed = dedent_strings(src_raw)
                for line in (fixed or textwrap.dedent(src_raw)).split('\n'):
                    lines.append('    ' + line)
        else:
            try:
                ast.parse(stripped, mode='eval')
                lines.append(
                    f'    assert_output(capture_print(lambda: {stripped}), {expected!r}, N)')
            except SyntaxError:
                fixed = dedent_strings(src_raw)
                for line in (fixed or textwrap.dedent(src_raw)).split('\n'):
                    lines.append('    ' + line)
                lines.append('    # TODO assert: ' + repr(expected[:80]))

    return lines


def emit_fn_from_docstring(fn_name, docstring, fixture_var='easy_install_env'):
    examples = doctest.DocTestParser().get_examples(docstring)
    pytest_name = fn_name if fn_name.startswith('test_') else 'test_' + fn_name
    body = []
    for ex in examples:
        body.extend(emit_example(ex, fixture_var))
    env_used = env_names_loaded(body)

    lines = [f'def {pytest_name}({fixture_var}):']
    for name in env_used:
        lines.append(f"    {name} = {fixture_var}[{name!r}]")
    if env_used:
        lines.append('')
    lines.extend(body)

    lines.append('')
    return '\n'.join(lines)


def emit_fn_from_txt(txt_path, fixture_var='easy_install_env'):
    """Emit one pytest function from an entire .txt doctest file."""
    content = Path(txt_path).read_text()
    examples = doctest.DocTestParser().get_examples(content)
    stem = Path(txt_path).stem.replace('-', '_')
    fn_name = 'test_' + stem
    body = []
    for ex in examples:
        body.extend(emit_example(ex, fixture_var))
    env_used = env_names_loaded(body)

    lines = [f'def {fn_name}({fixture_var}):']
    for name in env_used:
        lines.append(f"    {name} = {fixture_var}[{name!r}]")
    if env_used:
        lines.append('')
    lines.extend(body)

    lines.append('')
    return '\n'.join(lines)


def collect_doctest_fns(source_path):
    src = Path(source_path).read_text()
    tree = ast.parse(src)
    results = []
    for node in tree.body:
        if not (isinstance(node, ast.FunctionDef) and node.col_offset == 0):
            continue
        if node.name == 'test_suite':
            continue
        if not (node.body and isinstance(node.body[0], ast.Expr)):
            continue
        doc = node.body[0].value
        if not (isinstance(doc, ast.Constant) and isinstance(doc.value, str)
                and '>>>' in doc.value):
            continue
        results.append((node.name, doc.value))
    return results
