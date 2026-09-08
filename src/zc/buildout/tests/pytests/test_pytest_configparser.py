import platform
import re
import sys
from io import StringIO
from pprint import pformat

import pytest

import zc.buildout.buildout
import zc.buildout.configparser


def parse(config, *args, **kw):
    return zc.buildout.configparser.parse(StringIO(config), "test", *args, **kw)


def test_basic_sections():
    text = """\
[s1]
a = 1

[   s2  ]         # a comment
long = a
    b

    c
l2 =


    a


    # not a comment

# comment
; also a comment

    b

      c


empty =

c=1

b    += 1

[s3]; comment
x =           a b
"""
    assert parse(text) == {
        "s1": {"a": "1"},
        "s2": {
            "b    +": "1",
            "c": "1",
            "empty": "",
            "l2": "a\n\n\n# not a comment\n\n\nb\n\n  c",
            "long": "a\nb\nc",
        },
        "s3": {"x": "a b"},
    }


def test_leading_blank_lines():
    text = "\n\n[buildout]\nz=1\n\n"
    assert parse(text) == {"buildout": {"z": "1"}}


def test_blank_line_after_section_header():
    text = """\
[buildout]

parts = hello
versions = versions

[versions]
# Add any version pins here.

[hello]

recipe = collective.recipe.cmd
on_install = true

on_update = true
cmds = echo Hello
"""
    assert parse(text) == {
        "buildout": {"parts": "hello", "versions": "versions"},
        "hello": {
            "cmds": "echo Hello",
            "on_install": "true",
            "on_update": "true",
            "recipe": "collective.recipe.cmd",
        },
        "versions": {},
    }


def test_conditional_sections_with_python_expressions():
    text = """\
[s1: 2 + 2 == 4] # this expression is true [therefore "this section" _will_ be NOT skipped
a = 1

[   s2 : 2 + 2 == 5  ]         # comment: this expression is false, so this section will be ignored]
long = a

[   s2 : 41 + 1 == 42  ]  # a comment: this expression is [true], so this section will be kept
long = b

[s3:2 in map(lambda i:i*2, [i for i in range(10)])] ;# Complex expressions are [possible!];, though they should not be (abused:)
# this section will not be skipped
long = c
"""
    assert parse(text) == {"s1": {"a": "1"}, "s2": {"long": "b"}, "s3": {"long": "c"}}


def test_hash_and_semicolon_comments_in_section_headers():
    text = """\
[ a ]
a=1

[ b ]  # []
b=1

[ c : True ]  # ]
c =1

[ d :  True]  # []
d=1

[ e ]  # []
e = 1

[ f ]  # ]
f = 1

[g:2 in map(lambda i:i*2, ['''\\x23\\x3b)'''] + [i for i in range(10)] + list('\\x23[]][\\x3b\\x23'))] # Complex #expressions; ][are [possible!] and can us escaped # and ; in literals
g = 1

[ h : True ]  ; ]
h =1

[ i :  True]  ; []
i=1

[j:2 in map(lambda i:i*2, ['''\\x23\\x3b)'''] + [i for i in range(10)] + list('\\x23[]][\\x3b\\x23'))] ; Complex #expressions; ][are [possible!] and can us escaped # and ; in literals
j = 1
"""
    assert parse(text) == {
        "a": {"a": "1"},
        "b": {"b": "1"},
        "c": {"c": "1"},
        "d": {"d": "1"},
        "e": {"e": "1"},
        "f": {"f": "1"},
        "g": {"g": "1"},
        "h": {"h": "1"},
        "i": {"i": "1"},
        "j": {"j": "1"},
    }


def test_semicolon_comments_without_expression():
    text = """\
[ a ]  ;semicolon comment are supported for lines without expressions ]
a = 1

[ b ]  ; []
b = 1

[ c ]  ; ]
c = 1

[ d ]  ; [
d = 1

[ e: True ]  ;semicolon comments are supported for lines with expressions ]
e = 1
"""
    assert parse(text) == {
        "a": {"a": "1"},
        "b": {"b": "1"},
        "c": {"c": "1"},
        "d": {"d": "1"},
        "e": {"e": "1"},
    }


def test_hash_comments_without_expression():
    text = """\
[ a ]  #hash comment ] are supported for lines without expressions ]
a = 1

[ b ]  # []
b = 1

[ c ]  # ]
c = 1

[ d ]  # [
d = 1

[ e: True ]  #hash comments] are supported for lines with expressions ]
e = 1
"""
    assert parse(text) == {
        "a": {"a": "1"},
        "b": {"b": "1"},
        "c": {"c": "1"},
        "d": {"d": "1"},
        "e": {"e": "1"},
    }


def test_escaped_hash_and_semicolon_in_expressions():
    text = """\
[a:2 in map(lambda i:i*2, ['''\\x23\\x3b)'''] + [i for i in range(10)] + list('\\x23[]][\\x3b\\x23'))] # Complex #expressions; ][are [possible!] and can us escaped # and ; in literals
a = 1

[b:2 in map(lambda i:i*2, ['''\\x23\\x3b)'''] + [i for i in range(10)] + list('\\x23[]][\\x3b\\x23'))] ; Complex #expressions; ][are [possible!] and can us escaped # and ; in literals
b = 1
"""
    assert parse(text) == {"a": {"a": "1"}, "b": {"b": "1"}}


def test_unescaped_hash_in_expression_raises():
    text = """\
[a:'#' in '#;'] # this is not a supported expression
a = 1
"""
    with pytest.raises(zc.buildout.configparser.MissingSectionHeaderError):
        parse(text)


def test_exp_globals_with_platform_and_sys():
    text = """\
[s1: str(platform.python_version_tuple()[0]) in ('2', '3',)] # this expression is true, the major versions of python are either 2 or 3
a = 1

[s2:sys.version[0] == '0'] # comment: this expression "is false",  there no major version 0 of Python so this section will be ignored
long = a

[s2:len(platform.uname()) > 0]  # a comment: this expression is likely always true, so this section will be kept
long = b
"""
    globs = lambda: {"platform": platform, "sys": sys}
    assert parse(text, exp_globals=globs) == {"s1": {"a": "1"}, "s2": {"long": "b"}}


def test_default_globals_from_buildout():
    text = """\
#imported modules
[s1: sys and re and os and platform] # this expression is true: these modules are available
a = 1

[s2: any([python2, python3, python24 , python25 , python26 , python27 , python30 , python31 , python32 , python33 , python34 , python35 , python36, python37, python38, python39, python310, python311, python312, python313, python314, python315]) ]
b = 1

[s3:cpython or pypy or jython or ironpython]
c = 1

[s4:linux or windows or cygwin or macosx or solaris or posix or True]
d = 1

[s5:bits32 or bits64 or little_endian or big_endian]
e = 1
"""
    assert parse(text, zc.buildout.buildout._default_globals) == {
        "s1": {"a": "1"},
        "s2": {"b": "1"},
        "s3": {"c": "1"},
        "s4": {"d": "1"},
        "s5": {"e": "1"},
    }


def test_implication_arrow_shorthand():
    text = """\
[foo]
=> part1 part2
"""
    assert parse(text) == {"foo": {"<part-dependencies>": "part1 part2"}}


def test_pep508_markers():
    text = """\
[section]
# These are the values when no other section overrides them.
a = 1
b = 1

[section: python_version < "2.6"]
a = 26

[section: python_version < "4.0"]
b = 40
"""
    assert parse(text) == {"section": {"a": "1", "b": "40"}}


def test_pep508_unknown_platform_never_matches():
    text = """\
[section]
# These are the values when no other section overrides them.
a = 1

[section: platform_system == "msdos"]
a = 2
"""
    assert parse(text) == {"section": {"a": "1"}}


def test_pep508_combinations():
    text = """\
[section]
# These are the values when no other section overrides them.
a = 1
b = 1

[section: python_version >= "2.0" and platform_system != "msdos"]
a = 2

[section: python_version >= "2.0" or platform_system == "msdos"]
b = 3
"""
    assert parse(text) == {"section": {"a": "2", "b": "3"}}


def test_mixed_old_and_new_style_markers():
    text = """\
[section]
# These are the values when no other section overrides them.
a = 1
b = 1

[section: python_version >= "2.0"]
a = 4

[section:linux or windows or cygwin or macosx or solaris or posix or True]
b = 5
"""
    assert parse(text, zc.buildout.buildout._default_globals) == {
        "section": {"a": "4", "b": "5"}
    }


def test_conditional_sections_ordering_issue_656():
    text = """\
[section]
# =, +=
a =
  a
  b
  c

# =, -=
b =
  a
  b
  c

# =, =
c =
  a
  b
  c

# +=, =
d +=
  a
  b
  c

# +=, +=
e +=
  a
  b
  c

# +=, -=
f +=
  a
  b
  c

# -=, =
g -=
  a
  b
  c

# -=, +=
h -=
  a
  b
  c

# -=, -=
i -=
  a
  b
  c

[section:True]
a +=
  d

b -=
  b

c =
  x
  y
  z

d =
  x
  y
  z

e +=
  d
  e
  f

f -=
  a

g =
  d
  e
  f

h +=
  d
  e
  f

i -=
  d
"""
    assert parse(text) == {
        "section": {
            "a": "a\nb\nc",
            "a +": "d",
            "b": "a\nb\nc",
            "b -": "b",
            "c": "x\ny\nz",
            "d": "x\ny\nz",
            "e +": "a\nb\nc\nd\ne\nf",
            "f +": "a\nb\nc",
            "f -": "a",
            "g": "d\ne\nf",
            "h +": "d\ne\nf",
            "h -": "a\nb\nc",
            "i -": "a\nb\nc\nd",
        }
    }
