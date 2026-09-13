"""Generate and work with PEP 425 Compatibility Tags."""

import sys
import warnings

import sysconfig
import distutils.util  # ty: ignore[unresolved-import]  # runtime: setuptools distutils-precedence hook

from typing import Callable, Optional, Tuple


def get_config_var(var: str) -> Optional[str]:
    try:
        return sysconfig.get_config_var(var)
    except IOError as e:  # pip Issue #1074
        warnings.warn("{0}".format(e), RuntimeWarning)
        return None


def get_abbr_impl() -> str:
    """Return abbreviated implementation name."""
    if hasattr(sys, 'pypy_version_info'):
        pyimpl = 'pp'
    elif sys.platform.startswith('java'):
        pyimpl = 'jy'
    elif sys.platform == 'cli':
        pyimpl = 'ip'
    else:
        pyimpl = 'cp'
    return pyimpl


def get_impl_ver() -> str:
    """Return implementation version."""
    impl_ver = get_config_var("py_version_nodot")
    if not impl_ver or get_abbr_impl() == 'pp':
        impl_ver = ''.join(map(str, get_impl_version_info()))
    return impl_ver


def get_impl_version_info() -> Tuple[int, ...]:
    """Return sys.version_info-like tuple for use in decrementing the minor
    version."""
    if get_abbr_impl() == 'pp':
        # as per https://github.com/pypa/pip/issues/2882
        return (sys.version_info[0], sys.pypy_version_info.major,  # ty: ignore[unresolved-attribute]  # exists on PyPy only; guarded by the 'pp' check above
                sys.pypy_version_info.minor)  # ty: ignore[unresolved-attribute]  # PyPy-only
    else:
        return sys.version_info[0], sys.version_info[1]


def get_flag(var: str, fallback: Callable[[], bool], expected: object=True, warn: bool=True) -> bool:
    """Use a fallback method for determining SOABI flags if the needed config
    var is unset or unavailable."""
    val = get_config_var(var)
    if val is None:
        if warn:
            warnings.warn("Config variable '{0}' is unset, Python ABI tag may "
                          "be incorrect".format(var), RuntimeWarning, 2)
        return fallback()
    return val == expected


def get_abi_tag() -> Optional[str]:
    """Return the ABI tag based on SOABI (if available) or emulate SOABI
    (CPython 2, PyPy)."""
    soabi = get_config_var('SOABI')
    impl = get_abbr_impl()
    if not soabi and impl in ('cp', 'pp') and hasattr(sys, 'maxunicode'):
        d = ''
        m = ''
        u = ''
        if get_flag('Py_DEBUG',
                    lambda: hasattr(sys, 'gettotalrefcount'),
                    warn=(impl == 'cp')):
            d = 'd'
        if get_flag('WITH_PYMALLOC',
                    lambda: impl == 'cp',
                    warn=(impl == 'cp')):
            m = 'm'
        if get_flag('Py_UNICODE_SIZE',
                    lambda: sys.maxunicode == 0x10ffff,
                    expected=4,
                    warn=(impl == 'cp' and
                          sys.version_info < (3, 3))) \
                and sys.version_info < (3, 3):
            u = 'u'
        abi = '%s%s%s%s%s' % (impl, get_impl_ver(), d, m, u)
    elif soabi and soabi.startswith('cpython-'):
        abi = 'cp' + soabi.split('-')[1]
    elif soabi:
        abi = soabi.replace('.', '_').replace('-', '_')
    else:
        abi = None
    return abi


def get_platform() -> str:
    """Return our platform name 'win32', 'linux_x86_64'"""
    # XXX remove distutils dependency
    result = distutils.util.get_platform().replace('.', '_').replace('-', '_')
    if result == "linux_x86_64" and sys.maxsize == 2147483647:
        # pip pull request #3497
        result = "linux_i686"
    return result
