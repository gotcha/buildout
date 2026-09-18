##############################################################################
#
# Copyright (c) 2006 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################

"""Script generation and interpreter wrappers.

Everything here moved out of ``zc.buildout.easy_install`` unchanged; that
module re-exports these names so existing import paths keep working.  The
logger name stays the historical ``zc.buildout.easy_install`` so doctest
transcripts that assert it keep matching.
"""

from __future__ import annotations

import errno
import logging
import os
import sys

import pkg_resources
from packaging.utils import canonicalize_name, is_normalized_name

logger = logging.getLogger('zc.buildout.easy_install')

# Local copies of the easy_install platform facts.  They derive from
# sys.platform, so the two modules can never disagree, and computing them
# here keeps this module free of a top-level import edge back into
# easy_install, which imports this module for its facade.
is_win32 = sys.platform == 'win32'
is_jython = sys.platform.startswith('java')

if is_jython:
    import java.lang.System
    jython_os_name = (java.lang.System.getProperties()['os.name']).lower()


def working_set(specs: tuple[str, ...], executable: str, path: list[str] | None=None,
                ) -> pkg_resources.WorkingSet:
    from zc.buildout.easy_install import install

    # Backward compat:
    if path is None:
        # Legacy quirk: the executable string is passed where a list of
        # paths is expected.
        path = executable  # ty: ignore[invalid-assignment]
    else:
        assert executable == sys.executable, (executable, sys.executable)

    return install(specs, None, path=path)



def _script_paths(
        working_set: pkg_resources.WorkingSet,
        extra_paths: tuple[str, ...] | list[str],
        ) -> list[str]:
    from zc.buildout.easy_install import _dist_location, realpath

    path = [_dist_location(dist) for dist in working_set]
    path.extend(extra_paths)
    # order preserving unique
    unique_path = []
    for p in path:
        if p not in unique_path:
            unique_path.append(p)
    return [realpath(p) for p in unique_path]


def _find_req_dist(
        req: str,
        working_set: pkg_resources.WorkingSet,
        ) -> pkg_resources.Distribution | None:
    """Resolve a requirement string to a dist of the working set.

    Returns ``None`` when the requirement's environment marker excludes
    the current environment; raises ``ValueError`` when no dist matches.
    """
    orig_req = pkg_resources.Requirement.parse(req)
    if orig_req.marker and not orig_req.marker.evaluate():
        return None
    if is_normalized_name(orig_req.name):
        dist = working_set.find(orig_req)
        if dist is None:
            raise ValueError(
                f"Could not find requirement '{orig_req.name}' in working set. "
            )
    else:
        # First try finding the package by its canonical name.
        canonicalized_name = canonicalize_name(orig_req.name)
        canonical_req = pkg_resources.Requirement.parse(canonicalized_name)
        dist = working_set.find(canonical_req)
        if dist is None:
            # Now try to find the package by the original name we got from
            # the requirements.  This may succeed with setuptools versions
            # older than 75.8.2.
            dist = working_set.find(orig_req)
            if dist is None:
                raise ValueError(
                    f"Could not find requirement '{orig_req.name}' in working "
                    f"set. Could not find it with normalized "
                    f"'{canonicalized_name}' either."
                )
    return dist


def _dist_entry_points(
        dist: pkg_resources.Distribution,
        ) -> list[tuple[str, str, str]]:
    # regular console_scripts entry points
    entry_points = []
    for name in pkg_resources.get_entry_map(dist, 'console_scripts'):
        entry_point = dist.get_entry_info('console_scripts', name)
        # The name comes from the dist's own entry map, so the
        # entry point is guaranteed to exist.
        assert entry_point is not None
        entry_points.append(
            (name, entry_point.module_name,
             '.'.join(entry_point.attrs))
            )
    return entry_points


def _dist_distutils_scripts(
        dist: pkg_resources.Distribution,
        ) -> list[tuple[str, str]]:
    # Resolve the develop-egg script registry through the facade at call
    # time: the patch point for _develop_distutils_scripts lives on
    # zc.buildout.easy_install, where the dict used to be defined.
    from zc.buildout import easy_install

    develop_distutils_scripts = easy_install._develop_distutils_scripts
    # The metadata on "old-style" distutils scripts is not retained by
    # distutils/setuptools, except by placing the original scripts in
    # /EGG-INFO/scripts/.
    distutils_scripts = []
    if dist.metadata_isdir('scripts'):
        # egg-info metadata from installed egg.
        for name in dist.metadata_listdir('scripts'):
            if dist.metadata_isdir('scripts/' + name):
                # Probably Python 3 __pycache__ directory.
                continue
            if name.lower().endswith('.exe'):
                # windows: scripts are implemented with 2 files
                #          the .exe gets also into metadata_listdir
                #          get_metadata chokes on the binary
                continue
            contents = dist.get_metadata('scripts/' + name)
            distutils_scripts.append((name, contents))
    elif dist.key in develop_distutils_scripts:
        # Development eggs don't have metadata about scripts, so we
        # collected it ourselves in develop()/ and
        # _detect_distutils_scripts().
        for name, contents in develop_distutils_scripts[dist.key]:
            distutils_scripts.append((name, contents))
    return distutils_scripts


def _collect_req_scripts(
        reqs: list[tuple[str, str, str] | str],
        working_set: pkg_resources.WorkingSet,
        ) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    """Collect entry points and distutils scripts from requirements."""
    entry_points = []
    distutils_scripts = []
    for req in reqs:
        if isinstance(req, str):
            dist = _find_req_dist(req, working_set)
            if dist is None:
                # The requirement's marker excludes this environment.
                continue
            entry_points.extend(_dist_entry_points(dist))
            distutils_scripts.extend(_dist_distutils_scripts(dist))
        else:
            entry_points.append(req)
    return entry_points, distutils_scripts


def _script_target(
        name: str,
        scripts: dict[str, str] | None,
        dest: str | None,
        path: list[str],
        relative_paths: str | bool,
        ) -> tuple[str, str, str] | None:
    """Resolve a script name to its destination and path setup.

    Returns ``None`` when a ``scripts`` mapping was given that does not
    include the name.
    """
    if scripts is not None:
        sname = scripts.get(name)
        if sname is None:
            return None
    else:
        sname = name

    # Generating a script requires a destination directory.
    assert dest is not None
    sname = os.path.join(dest, sname)
    spath, rpsetup = _relative_path_and_setup(sname, path, relative_paths)
    return sname, spath, rpsetup


def _warn_missing_scripts(
        scripts: dict[str, str] | None,
        entry_points_names: list[str],
        ) -> None:
    # warn when a script name passed in 'scripts' argument
    # is not defined in an entry point.
    if scripts is None:
        return
    for name, target in scripts.items():
        if name not in entry_points_names:
            if name == target:
                logger.warning("Could not generate script '%s' as it is not "
                    "defined in the egg entry points.", name)
            else:
                logger.warning("Could not generate script '%s' as script "
                    "'%s' is not defined in the egg entry points.", name, target)


def scripts(reqs: list[tuple[str, str, str] | str], working_set: pkg_resources.WorkingSet, executable: str, dest: str | None=None,
            scripts: dict[str, str] | None=None,
            extra_paths: tuple[str, ...] | list[str]=(),
            arguments: str='',
            interpreter: str | None=None,
            initialization: str='',
            relative_paths: str | bool=False,
            ) -> list[str]:
    assert executable == sys.executable, (executable, sys.executable)

    path = _script_paths(working_set, extra_paths)

    generated = []

    if isinstance(reqs, str):
        raise TypeError('Expected iterable of requirements or entry points,'
                        ' got string.')

    if initialization:
        initialization = '\n'+initialization+'\n'

    entry_points, distutils_scripts = _collect_req_scripts(reqs, working_set)

    entry_points_names = []

    for name, module_name, attrs in entry_points:
        entry_points_names.append(name)
        target = _script_target(name, scripts, dest, path, relative_paths)
        if target is None:
            continue
        sname, spath, rpsetup = target
        generated.extend(
            _script(module_name, attrs, spath, sname, arguments,
                    initialization, rpsetup)
            )

    _warn_missing_scripts(scripts, entry_points_names)

    for name, contents in distutils_scripts:
        target = _script_target(name, scripts, dest, path, relative_paths)
        if target is None:
            continue
        sname, spath, rpsetup = target
        generated.extend(
            _distutils_script(spath, sname, contents, initialization, rpsetup)
            )

    if interpreter:
        # Generating a script requires a destination directory.
        assert dest is not None
        sname = os.path.join(dest, interpreter)
        spath, rpsetup = _relative_path_and_setup(sname, path, relative_paths)
        generated.extend(_pyscript(spath, sname, rpsetup, initialization))

    return generated


def _relative_path_and_setup(sname: str, path: list[str], relative_paths: str | bool) -> tuple[str, str]:
    if relative_paths:
        # Callers pass either a falsy value or a base path string; a bare
        # ``True`` is not supported.
        assert isinstance(relative_paths, str)
        relative_paths = os.path.normcase(relative_paths)
        sname = os.path.normcase(os.path.abspath(sname))
        spath = ',\n  '.join(
            [_relativitize(os.path.normcase(path_item), sname, relative_paths)
             for path_item in path]
            )
        rpsetup = relative_paths_setup
        for i in range(_relative_depth(relative_paths, sname)):
            rpsetup += "base = os.path.dirname(base)\n"
    else:
        spath = repr(path)[1:-1].replace(', ', ',\n  ')
        rpsetup = ''
    return spath, rpsetup


def _relative_depth(common: str, path: str) -> int:
    n = 0
    while 1:
        dirname = os.path.dirname(path)
        if dirname == path:
            raise AssertionError(f"dirname of {dirname} is the same")
        if dirname == common:
            break
        n += 1
        path = dirname
    return n


def _relative_path(common: str, path: str) -> str:
    r = []
    while 1:
        dirname, basename = os.path.split(path)
        r.append(basename)
        if dirname == common:
            break
        if dirname == path:
            raise AssertionError(f"dirname of {dirname} is the same")
        path = dirname
    r.reverse()
    return os.path.join(*r)


def _relativitize(path: str, script: str, relative_paths: str) -> str:
    if path == script:
        raise AssertionError("path == script")
    if path == relative_paths:
        return "base"
    common = os.path.dirname(os.path.commonprefix([path, script]))
    if (common == relative_paths or
        common.startswith(os.path.join(relative_paths, ''))
        ):
        return f"join(base, {_relative_path(common, path)!r})"
    else:
        return repr(path)


relative_paths_setup = """
import os

join = os.path.join
base = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
"""

def _script(module_name: str, attrs: str, path: str, dest: str, arguments: str, initialization: str, rsetup: str) -> list[str]:
    from zc.buildout.easy_install import _safe_arg

    if is_win32:
        dest += '-script.py'

    python = _safe_arg(sys.executable)

    contents = script_template % {
        'python': python,
        'path': path,
        'module_name': module_name,
        'attrs': attrs,
        'arguments': arguments,
        'initialization': initialization,
        'relative_paths_setup': rsetup,
        }
    return _create_script(contents, dest)


def _distutils_script(path: str, dest: str, script_content: str, initialization: str, rsetup: str) -> list[str]:
    from zc.buildout.easy_install import _safe_arg

    if is_win32:
        dest += '-script.py'

    lines = script_content.splitlines(True)
    if '#!' not in lines[0] and ('python' in lines[0]):
        # The script doesn't follow distutil's rules.  Ignore it.
        return []
    lines = lines[1:]  # Strip off the first hashbang line.
    line_with_first_import = len(lines)
    for line_number, line in enumerate(lines):
        if 'import' not in line:
            continue
        if not line.startswith(('import', 'from')):
            continue
        if '__future__' in line:
            continue
        line_with_first_import = line_number
        break

    before = ''.join(lines[:line_with_first_import])
    after = ''.join(lines[line_with_first_import:])

    python = _safe_arg(sys.executable)

    contents = distutils_script_template % {
        'python': python,
        'path': path,
        'initialization': initialization,
        'relative_paths_setup': rsetup,
        'before': before,
        'after': after
        }
    return _create_script(contents, dest)

def _file_changed(filename: str, old_contents: str, mode: str='r') -> bool:
    try:
        with open(filename, mode) as f:
            return f.read() != old_contents
    except OSError as e:
        if e.errno == errno.ENOENT:
            return True
        else:
            raise

def _create_script(contents: str, dest: str) -> list[str]:
    from zc.buildout.easy_install import _execute_permission, get_win_launcher

    generated = []
    script = dest

    changed = _file_changed(dest, contents)

    if is_win32:
        # generate exe file and give the script a magic name:
        win32_exe = os.path.splitext(dest)[0] # remove ".py"
        win32_exe = win32_exe.removesuffix('-script') # remove "-script"
        win32_exe = win32_exe + '.exe' # add ".exe"
        new_data = get_win_launcher('cli')

        if _file_changed(win32_exe, new_data, 'rb'):
            # Only write it if it's different.
            with open(win32_exe, 'wb') as f:
                f.write(new_data)
        generated.append(win32_exe)

    if changed:
        with open(dest, 'w') as f:
            f.write(contents)
        logger.info(
            "Generated script %r.",
            # Normalize for windows
            script.endswith('-script.py') and script[:-10] or script)

        try:
            os.chmod(dest, _execute_permission())
        except (OSError, AttributeError):
            pass

    generated.append(dest)
    return generated


if is_jython and jython_os_name == 'linux':
    script_header = '#!/usr/bin/env %(python)s'
else:
    script_header = '#!%(python)s'


script_template = script_header + '''\

%(relative_paths_setup)s
import sys
sys.path[0:0] = [
  %(path)s,
  ]
%(initialization)s
import %(module_name)s

if __name__ == '__main__':
    sys.exit(%(module_name)s.%(attrs)s(%(arguments)s))
'''

distutils_script_template = script_header + '''
%(before)s
%(relative_paths_setup)s
import sys
sys.path[0:0] = [
  %(path)s,
  ]
%(initialization)s

%(after)s'''


def _pyscript(path: str, dest: str, rsetup: str, initialization: str='') -> list[str]:
    from zc.buildout.easy_install import _execute_permission, _safe_arg

    generated = []
    script = dest
    if is_win32:
        dest += '-script.py'

    python = _safe_arg(sys.executable)
    if path:
        path += ','  # Courtesy comma at the end of the list.

    contents = py_script_template % {
        'python': python,
        'path': path,
        'relative_paths_setup': rsetup,
        'initialization': initialization,
        }
    changed = _file_changed(dest, contents)

    if is_win32:
        # generate exe file and give the script a magic name:
        exe = script + '.exe'
        with open(exe, 'wb') as f:
            f.write(
                pkg_resources.resource_string('setuptools', 'cli.exe')
            )
        generated.append(exe)

    if changed:
        with open(dest, 'w') as f:
            f.write(contents)
        try:
            os.chmod(dest, _execute_permission())
        except (OSError, AttributeError):
            pass
        logger.info("Generated interpreter %r.", script)

    generated.append(dest)
    return generated

py_script_template = script_header + '''\

%(relative_paths_setup)s
import sys

sys.path[0:0] = [
  %(path)s
  ]
%(initialization)s

_interactive = True
if len(sys.argv) > 1:
    # The Python interpreter wrapper allows only some of the options that a
    # "regular" Python interpreter accepts.
    _options, _args = __import__("getopt").getopt(sys.argv[1:], 'Iic:m:')
    _interactive = False
    for (_opt, _val) in _options:
        if _opt == '-i':
            _interactive = True
        elif _opt == '-c':
            exec(_val)
        elif _opt == '-m':
            sys.argv[1:] = _args
            _args = []
            __import__("runpy").run_module(
                 _val, {}, "__main__", alter_sys=True)
        elif _opt == '-I':
            # Allow yet silently ignore the `-I` option. The original behaviour
            # for this option is to create an isolated Python runtime. It was
            # deemed acceptable to allow the option here as this Python wrapper
            # is isolated from the system Python already anyway.
            # The specific use-case that led to this change is how the Python
            # language extension for Visual Studio Code calls the Python
            # interpreter when initializing the extension.
            pass

    if _args:
        sys.argv[:] = _args
        __file__ = _args[0]
        del _options, _args
        with open(__file__) as __file__f:
            exec(compile(__file__f.read(), __file__, "exec"))

if _interactive:
    del _interactive
    __import__("code").interact(banner="", local=globals())
'''

# easy_install.py assembles the public runsetup_template as
# ``_runsetup_template % setuptools_path`` right after its import-time
# resolve defines setuptools_path; substituting here would import-time
# couple this module back into easy_install, which imports this module
# for its facade.
_runsetup_template = """
import sys
sys.path.insert(0, %%(setupdir)r)
sys.path[0:0] = %r

import os, setuptools

%%(extra)s

__file__ = %%(__file__)r

os.chdir(%%(setupdir)r)
sys.argv[0] = %%(setup)r

with open(%%(setup)r) as f:
    exec(compile(f.read(), %%(setup)r, 'exec'))
"""

disable_root_logger = """
import logging
root_logger = logging.getLogger()
handler = logging.NullHandler()
root_logger.addHandler(handler)
"""


