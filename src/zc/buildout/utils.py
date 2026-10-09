from __future__ import annotations

import os
import re
import sys
from importlib.metadata import version
from typing import TYPE_CHECKING, Any, TextIO

import packaging.version

import zc.buildout

if TYPE_CHECKING:
    from zc.buildout.buildout import Options

# In some cases we need to check the setuptools version to know what we can do.
SETUPTOOLS_VERSION = packaging.version.parse(version("setuptools"))
IS_SETUPTOOLS_80_PLUS = SETUPTOOLS_VERSION >= packaging.version.Version('80')


def normalize_name(name: str) -> str:
    """PEP 503 normalization plus dashes as underscores.

    Taken over from importlib.metadata.
    I don't want to think about where to import this from in each
    Python version, or having it as extra dependency.

    Note that there is also packaging_utils.canonicalize_name
    which turns "foo.bar" into "foo-bar", so it is different.
    """
    return re.sub(r"[-_.]+", "-", name).lower().replace('-', '_')


def get_pth_paths(loc: str) -> list[str]:
    """Plain paths referenced by the ``*.pth`` files in directory ``loc``.

    A PEP 660 editable install lands a ``.pth`` file next to the
    ``.dist-info`` in the target directory; for a hatchling src-layout
    project that file is one line naming the checkout's ``src``
    directory.  ``import`` lines (setuptools' ``__editable__`` finders)
    and comments carry no path.  Relative entries resolve against the
    directory holding the ``.pth`` file, mirroring ``site``'s reading.
    """
    paths: list[str] = []
    if not os.path.isdir(loc):
        return paths
    for name in os.listdir(loc):
        if not name.endswith('.pth'):
            continue
        with open(os.path.join(loc, name)) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') \
                        and not line.startswith('import '):
                    path = os.path.abspath(os.path.join(loc, line))
                    if path not in paths:
                        paths.append(path)
    return paths


def _print_options(sep: str=' ', end: str='\n', file: TextIO | None=None) -> tuple[str, str, TextIO | None]:
    return sep, end, file

def print_(*args: object, **kw: Any) -> None:  # type: ignore[explicit-any]  # **kw forwards into _print_options, which types it
    sep, end, file = _print_options(**kw)
    if file is None:
        file = sys.stdout
    file.write(sep.join(map(str, args))+end)


_bool_names = {'true': True, 'false': False, True: True, False: False}
def bool_option(options: Options | dict[str, str], name: str, default: str | bool | None=None) -> bool:
    value = options.get(name, default)
    if value is None:
        raise KeyError(name)
    try:
        return _bool_names[value]
    except KeyError:
        raise zc.buildout.UserError(
            f'Invalid value for {name!r} option: {value!r}')
