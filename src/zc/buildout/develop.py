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

import zc.buildout.rmtree

logger = logging.getLogger('zc.buildout.easy_install')


def _rm(*paths: str) -> None:
    for path in paths:
        if os.path.isdir(path):
            zc.buildout.rmtree.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)


def _egg_link_target(directory: Path) -> str:
    """The checkout path an egg-link for ``directory`` should point at.

    Two common cases are supported: a src-layout (the ``src``
    directory) and a layout with the code at the checkout's top level.
    """
    egg_path = os.path.realpath(directory)
    assert os.path.isdir(egg_path)
    if 'src' in os.listdir(egg_path):
        egg_path = os.path.join(egg_path, 'src')
    return egg_path


def _create_egg_link(directory: Path, dest: str, egg_name: str) -> str:
    """Create egg-link file.

    setuptools 80 basically removes its own 'setup.py develop' code, and
    replaces it with 'pip install -e' (which then calls setuptools again,
    but okay). See https://github.com/pypa/setuptools/pull/4955
    Other PEP 660 build backends (hatchling) never created an .egg-link
    file either.
    So we create it ourselves, based on the previous setuptools code.

    So what should be in the .egg-link file?  Two lines: an egg path and a
    relative setup.py path.  For example with setuptools 79 we may have a
    file zc.recipe.egg.egg-link with as contents two lines:

      /Users/maurits/community/buildout/zc.recipe.egg_/src
      ../

    The relative setup.py path on the second line does not seem really used,
    but it should be there according to some checks, so let's try to get it
    right.
    """
    root = os.path.realpath(directory)
    if not egg_name:
        egg_name = os.path.basename(root)
    egg_path = _egg_link_target(directory)
    setup_path = '..' if egg_path != root else '.'
    # Return TWO lines, so NO line ending on the last line.
    contents = f"{egg_path}\n{setup_path}"
    egg_link = os.path.join(dest, egg_name) + '.egg-link'
    with open(egg_link, "w") as myfile:
        myfile.write(contents)
    return egg_link


def _dist_metadata_present(target: str) -> bool:
    """True when an editable install left dist metadata at ``target``.

    setuptools writes ``*.egg-info`` into the source checkout; pyproject
    -only backends like hatchling leave the checkout bare, in which case
    the metadata only exists in the installer target directory.
    """
    return bool(glob.glob(os.path.join(target, '*.egg-info'))
                or glob.glob(os.path.join(target, '*.dist-info')))


def _copy_metadata(src: str, dest: str, undo: list[Callable]) -> None:
    """Move PEP 660 editable-install metadata from ``src`` into ``dest``.

    A ``pip``/``uv install -e`` of a pyproject-only package puts its
    ``.dist-info`` and a ``.pth`` file in the target directory ``src``
    and writes nothing into the source checkout.  Moving the metadata
    into the develop-eggs directory ``dest`` keeps the dist visible to
    the working set scanner, lets the buildout process import the
    package once develop-eggs is processed with ``site.addsitedir``,
    and lets script generation resolve the ``.pth``'s plain path.

    Only plain-path ``.pth`` files get resolved for generated scripts
    (``get_pth_paths``); a backend whose editable install is carried by
    an ``import`` hook line alone (no metadata in the checkout, no
    plain path) is outside the supported realistic layouts — its dist
    metadata is kept, but imports from generated scripts will fail.

    ``undo`` is accepted for interface symmetry with ``_copyeggs``: the
    final ``rmtree`` of ``src`` removes whatever stays behind, and a
    failed develop run rolls the develop-eggs directory back as a
    whole.
    """
    for name in os.listdir(src):
        if name == '__pycache__':
            continue
        if not (name.endswith(('.dist-info', '.egg-info', '.pth'))
                or (name.startswith('__editable__') and name.endswith('.py'))):
            continue
        new = os.path.join(dest, name)
        _rm(new)
        os.rename(os.path.join(src, name), new)


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

    This expects a path to a directory or a file as the first argument.
    The file may be a ``setup.py`` or a ``pyproject.toml``; we basically
    ignore it and take its directory instead.  The directory is
    installed in editable mode with ``pip install -e`` or, in uv mode,
    ``uv pip install -e``.

    setuptools older than 80 writes an ``.egg-link`` file into the
    installer's target directory, which we move into the develop-eggs
    directory.  Newer setuptools and other PEP 660 backends leave no
    egg-link, so we fabricate one pointing at the checkout.  setuptools
    additionally leaves its ``*.egg-info`` in the checkout, which is
    what the fabricated link resolves against; a pyproject-only backend
    like hatchling leaves no metadata in the checkout at all, so its
    ``.dist-info`` and ``.pth`` are kept in the develop-eggs directory
    instead (see ``_copy_metadata``).

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
            # Local import: only the legacy develop path needs setuptools,
            # and it must not load when the module is imported in uv mode.
            import setuptools.command.setopt
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

        # setuptools older than 80 still puts an .egg-link in tmp3; newer
        # setuptools and other PEP 660 backends do not.
        egg_link = _copyeggs(tmp3, dest, '.egg-link', undo)
        if egg_link:
            logger.debug("Successfully made editable install: %s", egg_link)
            return egg_link

        # Fabricate the egg-link (kept for backward compatibility with
        # existing tests and tools).  When the editable install left no
        # dist metadata in the source checkout — pyproject-only backends
        # like hatchling — the fabricated link alone cannot make the dist
        # visible, so keep the PEP 660 metadata in the develop-eggs
        # directory as well.
        egg_link = _create_egg_link(directory, dest, egg_name)
        if not _dist_metadata_present(_egg_link_target(directory)):
            _copy_metadata(tmp3, dest, undo)
        logger.debug("Successfully made editable install: %s", egg_link)
        return egg_link

    finally:
        undo.reverse()
        [f() for f in undo]
