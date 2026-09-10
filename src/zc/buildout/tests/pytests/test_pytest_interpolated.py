"""Tests for the --interpolated flag of the query and annotate commands.

Raw output (as written in the configuration files) stays the default;
--interpolated shows the values with ${...} substitutions applied, the
way recipes see them.
"""
from zc.buildout.tests.pytests.conftest import (
    assert_output,
    NORMALIZERS_BUILDOUT,
)

N = NORMALIZERS_BUILDOUT

CONFIG = '''
[buildout]
parts =

[greeting]
message = hello ${greeting:audience}
audience = world
signature =
  yours
  ${greeting:audience}
'''


def test_query_raw_is_default(buildout_env):
    buildout = buildout_env['buildout']
    system = buildout_env['system']
    write = buildout_env['write']

    write('buildout.cfg', CONFIG)

    # Without the flag, query prints the raw, uninterpolated value.
    assert_output(
        system([buildout, 'query', 'greeting:message']),
        'hello ${greeting:audience}',
        N,
    )
    assert_output(
        system([buildout, 'query', 'greeting:audience']),
        'world',
        N,
    )


def test_query_interpolated(buildout_env):
    buildout = buildout_env['buildout']
    system = buildout_env['system']
    write = buildout_env['write']

    write('buildout.cfg', CONFIG)

    # With the flag, the value is shown as recipes see it.
    assert_output(
        system([buildout, 'query', 'greeting:message', '--interpolated']),
        'hello world',
        N,
    )
    # The flag may also be given before the section:key argument.
    assert_output(
        system([buildout, 'query', '--interpolated', 'greeting:message']),
        'hello world',
        N,
    )
    # Multi-line values are interpolated too.
    assert_output(
        system([buildout, 'query', 'greeting:signature', '--interpolated']),
        '''
yours
world
''',
        N,
    )
    # Combined with -v, the section and key are still displayed first.
    assert_output(
        system([buildout, '-v', 'query', 'greeting:message', '--interpolated']),
        '''
${greeting:message}
hello world
''',
        N,
    )


def test_query_interpolated_with_command_line_assignment(buildout_env):
    buildout = buildout_env['buildout']
    system = buildout_env['system']
    write = buildout_env['write']

    write('buildout.cfg', CONFIG)

    # Assignments are part of the cooked configuration recipes see.
    assert_output(
        system([buildout, 'greeting:audience=mars',
                'query', 'greeting:message', '--interpolated']),
        'hello mars',
        N,
    )
    # The raw view still shows the template.
    assert_output(
        system([buildout, 'greeting:audience=mars',
                'query', 'greeting:message']),
        'hello ${greeting:audience}',
        N,
    )


def test_query_interpolated_errors(buildout_env):
    buildout = buildout_env['buildout']
    system = buildout_env['system']
    write = buildout_env['write']

    write('buildout.cfg', CONFIG)

    assert_output(
        system([buildout, 'query', '--interpolated']),
        'Error: The query command requires a single argument.',
        N,
    )
    assert_output(
        system([buildout, 'query', 'greeting:nope', '--interpolated']),
        'Error: Key not found: nope',
        N,
    )
    assert_output(
        system([buildout, 'query', 'nope:message', '--interpolated']),
        'Error: Section not found: nope',
        N,
    )


def test_annotate_raw_is_default(buildout_env):
    buildout = buildout_env['buildout']
    system = buildout_env['system']
    write = buildout_env['write']

    write('buildout.cfg', CONFIG)

    # Without the flag, annotate shows the raw values.
    assert_output(
        system([buildout, 'annotate', 'greeting']),
        '''
Annotated sections
==================

[greeting]
audience= world
    buildout.cfg
message= hello ${greeting:audience}
    buildout.cfg
signature= yours
${greeting:audience}
    buildout.cfg
''',
        N,
    )


def test_annotate_interpolated(buildout_env):
    buildout = buildout_env['buildout']
    system = buildout_env['system']
    write = buildout_env['write']

    write('buildout.cfg', CONFIG)

    # With the flag, values are shown as recipes see them, while the
    # origin of each value is still reported.
    assert_output(
        system([buildout, 'annotate', '--interpolated', 'greeting']),
        '''
Annotated sections
==================

[greeting]
audience= world
    buildout.cfg
message= hello world
    buildout.cfg
signature= yours
world
    buildout.cfg
''',
        N,
    )

    # The flag also works without an explicit section; the interpolated
    # greeting section is part of the full output.
    assert_output(
        system([buildout, 'annotate', '--interpolated']),
        '''
...
[greeting]
audience= world
    buildout.cfg
message= hello world
    buildout.cfg
...
''',
        N,
    )
