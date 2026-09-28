"""Byte-identity tests for install_backend's pkg_resources-free naming.

The egg base name and supported-platform helpers replace pkg_resources
calls on the uv-mode install path; egg directory names land in
.installed.cfg signatures and in generated script sys.path lines, so
the spelling must match what pkg_resources produced byte for byte.
"""

from __future__ import annotations

import pkg_resources

from zc.buildout.install_backend import _egg_base_name, _supported_platform

NAME_VERSION_CASES = [
    ('Pygments', '2.21.0'),
    ('zc.recipe.egg', '3.2'),
    ('zope.interface', '4.1.3'),
    ('pytest-xdist', '3.8.0'),
    ('foo_bar', '1.0'),
    ('foo.bar-baz', '1.0a1'),
    ('WebOb', '1.8.11'),
    ('demo', '0.3'),
    ('demoneeded', '1.1'),
    ('foo', '1.0-1'),
    ('Bar', '2.0.dev0'),
    ('foo--bar', '1.0'),
    ('foo bar', '1.0'),
    ('UPPER.Case-Name', '0.1'),
    ('x', '1.0rc1'),
    ('y', '2!1.0'),
    ('z', '1.0+local.1'),
    ('w', '1.0_beta'),
]


def test_egg_base_name_matches_pkg_resources():
    for name, version in NAME_VERSION_CASES:
        legacy = pkg_resources.Distribution(
            project_name=name, version=version).egg_name()
        assert _egg_base_name(name, version) == legacy, (name, version)


def test_supported_platform_matches_pkg_resources():
    assert _supported_platform() == pkg_resources.get_supported_platform()
