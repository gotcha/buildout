#!/usr/bin/env python3
"""Rewrite assert_output expected-string arguments from escaped \n to triple-quoted strings.

For each assert_output call whose second argument is a single-quoted or
double-quoted string containing at least one \n escape, replaces it with a
triple-quoted string using real newlines.  Single-line strings are left alone.

The rewriter uses tokenize + ast.literal_eval to find string tokens and prove
the rewrite is semantically equivalent.

Usage:
    python rewrite_assert_output.py [file ...]
    # If no files given, processes all test_pytest_*.py in tests/pytests/
"""
import ast
import io
import re
import sys
import tokenize
from pathlib import Path


PYTESTS_DIR = Path(__file__).parent / 'src/zc/buildout/tests/pytests'


def find_assert_output_string_spans(src: str):
    """Return list of (start_offset, end_offset, string_value) for the second
    argument of each assert_output(...) call that contains a newline."""
    results = []
    tokens = list(tokenize.generate_tokens(io.StringIO(src).readline))

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        # Look for NAME token 'assert_output'
        if tok.type == tokenize.NAME and tok.string == 'assert_output':
            # Next non-NEWLINE/NL/COMMENT token should be OP '('
            j = i + 1
            while j < len(tokens) and tokens[j].type in (
                tokenize.NEWLINE, tokenize.NL, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT
            ):
                j += 1
            if j < len(tokens) and tokens[j].type == tokenize.OP and tokens[j].string == '(':
                # Find the second argument: skip first arg, then find the string
                depth = 1
                k = j + 1
                comma_count = 0
                arg2_start = None
                arg2_end = None
                while k < len(tokens) and depth > 0:
                    t = tokens[k]
                    if t.type == tokenize.OP:
                        if t.string in ('(', '[', '{'):
                            depth += 1
                        elif t.string in (')', ']', '}'):
                            depth -= 1
                            if depth == 0:
                                break
                        elif t.string == ',' and depth == 1:
                            comma_count += 1
                            if comma_count == 1:
                                # Next meaningful token is arg2 start
                                m = k + 1
                                while m < len(tokens) and tokens[m].type in (
                                    tokenize.NEWLINE, tokenize.NL, tokenize.COMMENT,
                                    tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING,
                                ):
                                    m += 1
                                if m < len(tokens) and tokens[m].type == tokenize.STRING:
                                    arg2_start = m
                            elif comma_count == 2:
                                # arg2 ended at previous non-whitespace token
                                m = k - 1
                                while m > 0 and tokens[m].type in (
                                    tokenize.NEWLINE, tokenize.NL, tokenize.COMMENT,
                                    tokenize.INDENT, tokenize.DEDENT,
                                ):
                                    m -= 1
                                if arg2_start is not None and tokens[m].type == tokenize.STRING:
                                    arg2_end = m
                                break
                    k += 1
                else:
                    # Loop ended without finding comma_count == 2 (two-arg call)
                    if arg2_start is not None and arg2_end is None:
                        # Check if the token just before ) is a STRING
                        m = k - 1 if depth == 0 else k
                        while m > 0 and tokens[m].type in (
                            tokenize.NEWLINE, tokenize.NL, tokenize.COMMENT,
                            tokenize.INDENT, tokenize.DEDENT,
                        ):
                            m -= 1
                        if tokens[m].type == tokenize.STRING:
                            arg2_end = m

                if arg2_start is not None and arg2_end is not None and arg2_start == arg2_end:
                    tok_str = tokens[arg2_start]
                    raw = tok_str.string
                    # Skip already-triple-quoted strings
                    if raw.startswith(('"""', "'''")):
                        i = j
                        continue
                    try:
                        value = ast.literal_eval(raw)
                    except Exception:
                        i = j
                        continue
                    if not isinstance(value, str) or '\n' not in value:
                        i = j
                        continue
                    # Compute byte offsets in src
                    lines = src.splitlines(keepends=True)
                    start_offset = sum(len(l) for l in lines[:tok_str.start[0] - 1]) + tok_str.start[1]
                    end_offset = sum(len(l) for l in lines[:tok_str.end[0] - 1]) + tok_str.end[1]
                    results.append((start_offset, end_offset, value, tok_str.start[1]))
            i = j
        i += 1

    return results


def make_triple_quoted(value: str, indent: int) -> str:
    """Convert a string value to a triple-quoted representation.

    Produces a \"\"\"...\"\"\" literal that evaluates to exactly `value`.

    The opening triple-quote is followed immediately by the content.
    A leading newline is added so the first content line is on its own
    source line (cosmetic only — assert_output strips it via _norm_ws).
    The closing triple-quote sits on its own line at `indent` spaces.

    If the value ends with '\\n', the closing triple-quote aligns cleanly.
    If not, a trailing newline is added (assert_output strips it too).
    """
    pad = ' ' * indent

    # Escape only what must be escaped inside """: backslashes and runs of """.
    # Newlines stay as real newlines.
    body = value.replace('\\', '\\\\')
    body = re.sub(r'"{3,}', lambda m: '\\"' * len(m.group()), body)

    # Ensure body ends with a newline so the closing """ sits on its own line.
    if not body.endswith('\n'):
        body += '\n'

    # Closing """ at column 0 — no padding — so no spaces enter the string value.
    return f'"""\n{body}"""'


def rewrite_file(path: Path, dry_run: bool = False) -> int:
    src = path.read_text()
    spans = find_assert_output_string_spans(src)
    if not spans:
        return 0

    # Process in reverse order so offsets stay valid
    result = src
    count = 0
    for start, end, value, col in reversed(spans):
        triple = make_triple_quoted(value, col)
        # Verify equivalence: the new triple-quoted string must eval to same value
        try:
            check = ast.literal_eval(triple)
        except SyntaxError:
            print(f"  SKIP (triple-quote syntax error): {path.name}:{start}", file=sys.stderr)
            continue
        # assert_output strips leading/trailing newlines via _norm_ws, so the
        # triple-quoted form (which gains a leading \n from """\n) is equivalent.
        if check.strip('\n') != value.strip('\n'):
            print(f"  SKIP (value mismatch): {path.name}:{start}", file=sys.stderr)
            continue
        result = result[:start] + triple + result[end:]
        count += 1

    if count and not dry_run:
        path.write_text(result)
    return count


def main():
    if len(sys.argv) > 1:
        files = [Path(f) for f in sys.argv[1:]]
    else:
        files = sorted(PYTESTS_DIR.glob('test_pytest_*.py'))
        # Exclude the unit-test file for assert_output itself
        files = [f for f in files if 'assert_output' not in f.name]

    total = 0
    for f in files:
        n = rewrite_file(f)
        if n:
            print(f"{f.name}: {n} rewrites")
            total += n
    print(f"Total: {total} strings rewritten")


if __name__ == '__main__':
    main()
