from __future__ import annotations

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


def _print_options(sep: str=' ', end: str='\n', file: TextIO | None=None) -> tuple[str, str, TextIO | None]:
    return sep, end, file

def print_(*args: Any, **kw: Any) -> None:
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
