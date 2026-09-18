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

"""Development (editable) installs and their egg-link bookkeeping.

The logger name stays the historical ``zc.buildout.easy_install`` so
doctest transcripts that assert it keep matching.
"""

from __future__ import annotations

import glob
import logging
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import setuptools.command.setopt

import zc.buildout.rmtree

logger = logging.getLogger('zc.buildout.easy_install')


def _rm(*paths: str) -> None:
    for path in paths:
        if os.path.isdir(path):
            zc.buildout.rmtree.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)


def _create_egg_link(directory: Path, dest: str, egg_name: str) -> str:
    """Create egg-link file.

    setuptools 80 basically removes its own 'setup.py develop' code, and
    replaces it with 'pip install -e' (which then calls setuptools again,
    but okay). See https://github.com/pypa/setuptools/pull/4955
    This leads to a different outcome.  There is no longer an .egg-link file
    that we can copy.
    So we create it ourselves, based on the previous setuptools code.

    So what should be in the .egg-link file?  Two lines: an egg path and a
    relative setup.py path.  For example with setuptools 79 we may have a
    file zc.recipe.egg.egg-link with as contents two lines:

      /Users/maurits/community/buildout/zc.recipe.egg_/src
      ../

    The relative setup.py path on the second line does not seem really used,
    but it should be there according to some checks, so let's try to get it
    right.  There is only so much we can do, but we support two common cases:
    a src-layout and a layout with the code starting at the same level as
    the setup.py file.
    """
    egg_path = os.path.realpath(directory)
    assert os.path.isdir(egg_path)
    if not egg_name:
        egg_name = os.path.basename(egg_path)
    if 'src' in os.listdir(egg_path):
        egg_path = os.path.join(egg_path, 'src')
        setup_path = '..'
    else:
        setup_path = '.'
    # Return TWO lines, so NO line ending on the last line.
    contents = f"{egg_path}\n{setup_path}"
    egg_link = os.path.join(dest, egg_name) + '.egg-link'
    with open(egg_link, "w") as myfile:
        myfile.write(contents)
    return egg_link


def _copyeggs(src: str, dest: str, suffix: str, undo: list[Callable]) -> str | None:
    """Copy eggs.

    Expected is:
    * 'src' is a temporary directory where the develop egg has been built.
    * 'dest' is the 'develop-eggs' directory
    * 'suffix' is '.egg-link'
    * 'undo' is a list of cleanup actions that will be undone automatically
      after this function returns (or throws an exception).

    The only thing we need to do: find the file with the given suffix in src,
    and move it to dest.  This works until and including setuptools 79.

    For setuptools 80+ we call _create_egg_link.
    """
    egg_links = glob.glob(os.path.join(src, "*" + suffix))
    if egg_links:
        assert len(egg_links) == 1, str(egg_links)
        egg_link = egg_links[0]
        name = os.path.basename(egg_link)
        new = os.path.join(dest, name)
        _rm(new)
        os.rename(egg_link, new)
        return new


_develop_distutils_scripts = {}


def _collect_distutils_dev_scripts(directory: str, dir_contents: list[str]) -> list[list[str]]:
    """Scan the files in ``directory`` for develop-mode distutils scripts.

    Returns ``[filename, actual script content]`` pairs for the files
    carrying the EASY-INSTALL-DEV-SCRIPT marker.
    """
    from zc.buildout.easy_install import DUNDER_FILE_PATTERN

    marker = 'EASY-INSTALL-DEV-SCRIPT'
    scripts_found = []
    for filename in dir_contents:
        if filename.endswith('.exe'):
            continue
        filepath = os.path.join(directory, filename)
        if not os.path.isfile(filepath):
            continue
        with open(filepath) as fp:
            dev_script_content = fp.read()
        if marker in dev_script_content:
            # The distutils bin script points at the actual file we need.
            for line in dev_script_content.splitlines():
                match = DUNDER_FILE_PATTERN.search(line)
                if match:
                    # The ``__file__ =`` line in the generated script points
                    # at the actual distutils script we need.
                    actual_script_filename = match.group('filename')
                    with open(actual_script_filename) as fp:
                        actual_script_content = fp.read()
                    scripts_found.append([filename, actual_script_content])
    return scripts_found


def _detect_distutils_scripts(directory: str) -> None:
    """Record detected distutils scripts from develop eggs

    ``setup.py develop`` doesn't generate metadata on distutils scripts, in
    contrast to ``setup.py install``. So we have to store the information for
    later.

    This won't find anything on setuptools 80.0.0+, because this does the
    editable install with pip, instead of its previous own code.  The result
    is different.  There is no egg-link file, so our code stops early.

    Maybe we could skip this check, use a different way of getting the proper
    egg_name, and still look for the 'EASY-INSTALL-DEV-SCRIPT' marker that
    setuptools adds.  But after setuptools 80.3.0 this marker is not set
    anymore: the setuptools.command.easy_install module was first removed,
    and later only partially restored.

    So if we would change the logic here, it would only be potentially useful
    for a very short range of setuptools versions.
    Also, we look for distutils scripts, which sounds like something that is
    long deprecated.
    """
    dir_contents = os.listdir(directory)
    # TODO For newer dists maybe just look for a 'bin' directory and get
    # any script in there.
    egginfo_filenames = [filename for filename in dir_contents
                         if filename.endswith('.egg-link')]
    if not egginfo_filenames:
        return
    egg_name = egginfo_filenames[0].replace('.egg-link', '')
    scripts_found = _collect_distutils_dev_scripts(directory, dir_contents)

    if scripts_found:
        # Resolved through the facade at call time: the patch point for
        # _develop_distutils_scripts lives on zc.buildout.easy_install,
        # where the dict used to be defined.
        from zc.buildout import easy_install

        logger.debug(
            "Distutils scripts found for develop egg %s: %s",
            egg_name, scripts_found)
        easy_install._develop_distutils_scripts[egg_name] = scripts_found


def develop(setup: str, dest: str,
            build_ext: dict[str, str] | None=None,
            executable: str=sys.executable) -> str | None:
    """Make a development/editable install of a package.

    This expects to get a path to a directory or a file as the first argument.
    If it is a file, we used to expect it to be a `setup.py` file.
    And then we would basically call `python setup.py develop`.
    Nowadays it could also be a `pyproject.toml` file.

    Calling `setup.py develop` is a deprecated way of installing a package.
    In setuptools 80 this still works, but setuptools has internally
    changed to call `pip install`.  Since zc.buildout 5 we also do that.

    We basically ignore the file, and just get its directory instead.

    With the `build_ext` option you can influence how C extensions in the
    package are built.  This may not be possible in a project that is using
    hatchling, unless you have some hatchling extensions.  So the current
    code assumes you are using setuptools.  It will create or edit a
    `setup.cfg` file in the package directory and put the build_ext
    options in there.
    """
    from zc.buildout.easy_install import call_pip_install

    assert executable == sys.executable, (executable, sys.executable)
    if os.path.isdir(setup):
        directory = setup
    else:
        directory = os.path.dirname(setup)
    # We will be calling `pip install -e directory` later on.  This works when
    # directory is `src/something`.  But if it is just `something`, pip will
    # try to get `something` from PyPI, even if there is a sub directory
    # `something`.  So let's make it an absolute path.
    # See https://github.com/buildout/buildout/issues/734
    # Let's also handle '~/'.
    directory = Path(directory).expanduser().resolve()
    logger.debug("Making editable install of %s", setup)

    undo = []
    try:
        if build_ext:
            setup_cfg = os.path.join(directory, 'setup.cfg')
            if os.path.exists(setup_cfg):
                os.rename(setup_cfg, setup_cfg+'-develop-aside')
                def restore_old_setup() -> None:
                    if os.path.exists(setup_cfg):
                        os.remove(setup_cfg)
                    os.rename(setup_cfg+'-develop-aside', setup_cfg)
                undo.append(restore_old_setup)
            else:
                with open(setup_cfg, 'w'):
                    pass  # create the empty file that edit_config expects
                undo.append(lambda: os.remove(setup_cfg))
            setuptools.command.setopt.edit_config(
                setup_cfg, {'build_ext': build_ext})

        tmp3 = tempfile.mkdtemp('build', dir=dest)
        undo.append(lambda : zc.buildout.rmtree.rmtree(tmp3))

        egg_name = call_pip_install(directory.as_uri(), tmp3, editable=True)
        # For an editable install call_pip_install returns the package name.
        assert isinstance(egg_name, str)

        # output = get_subprocess_output(args)
        # if log_level <= logging.DEBUG:
        #     print(output)

        # This won't find anything on setuptools 80+.
        # Can't be helped, I think.
        _detect_distutils_scripts(tmp3)

        # This won't find anything on setuptools 80+.
        # But on older setuptools it still works fine.
        egg_link = _copyeggs(tmp3, dest, '.egg-link', undo)
        if egg_link:
            logger.debug("Successfully made editable install: %s", egg_link)
            return egg_link

        egg_link = _create_egg_link(directory, dest, egg_name)
        if egg_link:
            logger.debug("Successfully made editable install: %s", egg_link)
            return egg_link
        logger.error(
            "Failure making editable install: no egg-link created for %s",
            setup,
        )

    finally:
        undo.reverse()
        [f() for f in undo]
