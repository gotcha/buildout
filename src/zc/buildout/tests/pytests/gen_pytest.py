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
import ast
import doctest
import re
import sys
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


def get_env_names_used(examples):
    used = set()
    for ex in examples:
        try:
            sub = ast.parse(ex.source, mode='exec')
            for n in ast.walk(sub):
                if isinstance(n, ast.Name) and n.id in ENV_NAMES:
                    used.add(n.id)
        except SyntaxError:
            pass
    return sorted(used)


def dedent_strings(src):
    """Parse src, dedent every multiline string constant, re-emit via ast.unparse.

    Also replaces % globals() with % <fixture_var> so that %(sample_eggs)s-style
    substitutions use the fixture dict instead of module globals.
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
        kwargs = ', '.join('%s=%s' % (k.arg, ast.unparse(k.value))
                          for k in call.keywords)
        all_args = ', '.join(filter(None, [args, kwargs]))
        if all_args:
            return 'capture_print(%s, %s)' % (fn_name, all_args)
        return 'capture_print(%s)' % fn_name
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
        for l in (fixed if fixed is not None else textwrap.dedent(src_raw)).split('\n'):
            lines.append('    ' + l)
        return lines

    want_stripped = want.rstrip('\n')
    want_lines = ['' if l == '<BLANKLINE>' else l for l in want_stripped.split('\n')]
    expected = '\n'.join(want_lines)

    if stripped.startswith('print_('):
        inner = extract_print_arg(stripped)
        if inner is not None:
            if 'system(' in inner:
                lines.append('    assert_output(%s, %r, N)' % (inner, expected))
            else:
                lines.append('    assert_output(str(%s), %r, N)' % (inner, expected))
        else:
            lines.append(
                '    assert_output(capture_print(lambda: %s), %r, N)' % (stripped, expected))

    elif stripped.startswith('ls('):
        cp = make_capture_print(stripped)
        lines.append('    assert_output(%s, %r, N)' % (cp or 'capture_print(ls)', expected))

    elif stripped.startswith('cat('):
        cp = make_capture_print(stripped)
        lines.append('    assert_output(%s, %r, N)' % (cp or 'capture_print(cat)', expected))

    elif looks_like_traceback(expected):
        last_line = expected.strip().split('\n')[-1]
        exc_type = last_line.split(':')[0].strip()
        lines.append('    try:')
        for l in stripped.split('\n'):
            lines.append('        ' + l)
        lines.append('        assert False, "Expected %s not raised"' % exc_type)
        lines.append('    except Exception as _exc:')
        lines.append(
            '        assert_output(type(_exc).__name__ + ": " + str(_exc), %r, N)' % last_line)

    else:
        if looks_like_python_literal(expected):
            try:
                ast.parse(stripped, mode='eval')
                lines.append('    _val = (%s)' % stripped)
                lines.append(
                    '    assert repr(_val) == %r or str(_val) == %r' % (expected, expected))
            except SyntaxError:
                fixed = dedent_strings(src_raw)
                for l in (fixed or textwrap.dedent(src_raw)).split('\n'):
                    lines.append('    ' + l)
        else:
            try:
                ast.parse(stripped, mode='eval')
                lines.append(
                    '    assert_output(capture_print(lambda: %s), %r, N)' % (stripped, expected))
            except SyntaxError:
                fixed = dedent_strings(src_raw)
                for l in (fixed or textwrap.dedent(src_raw)).split('\n'):
                    lines.append('    ' + l)
                lines.append('    # TODO assert: ' + repr(expected[:80]))

    return lines


def emit_fn_from_docstring(fn_name, docstring, fixture_var='easy_install_env'):
    examples = doctest.DocTestParser().get_examples(docstring)
    env_used = get_env_names_used(examples)
    pytest_name = fn_name if fn_name.startswith('test_') else 'test_' + fn_name

    lines = ['def %s(%s):' % (pytest_name, fixture_var)]
    for name in env_used:
        lines.append("    %s = %s[%r]" % (name, fixture_var, name))
    if env_used:
        lines.append('')

    for ex in examples:
        lines.extend(emit_example(ex, fixture_var))

    lines.append('')
    return '\n'.join(lines)


def emit_fn_from_txt(txt_path, fixture_var='easy_install_env'):
    """Emit one pytest function from an entire .txt doctest file."""
    content = Path(txt_path).read_text()
    examples = doctest.DocTestParser().get_examples(content)
    stem = Path(txt_path).stem.replace('-', '_')
    fn_name = 'test_' + stem
    env_used = get_env_names_used(examples)

    lines = ['def %s(%s):' % (fn_name, fixture_var)]
    for name in env_used:
        lines.append("    %s = %s[%r]" % (name, fixture_var, name))
    if env_used:
        lines.append('')

    for ex in examples:
        lines.extend(emit_example(ex, fixture_var))

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
        if not (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and '>>>' in node.body[0].value.value):
            continue
        results.append((node.name, node.body[0].value.value))
    return results
