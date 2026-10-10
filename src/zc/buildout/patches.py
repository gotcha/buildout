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

from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys
from collections.abc import Sequence
from types import ModuleType
from typing import Any


def patch_PackageIndex() -> None:
    """Patch the package index from setuptools.

    Main goal: check the package urls on an index page to see if they are
    compatible with the Python version.
    """

    try:
        import logging
        logging.getLogger('pip._internal.index.collector').setLevel(logging.ERROR)
        # The patch is applied lazily since Phase 2 unit 4 (the index is
        # pip-mode-only), which moves pip's import-time logging into the
        # middle of runs that have logging configured: pip registers its
        # VCS backends at import and logs each at DEBUG level.  Silence
        # that here, the same way the collector is silenced above, so
        # verbose transcripts keep their pre-laziness content.
        logging.getLogger(
            'pip._internal.vcs.versioncontrol').setLevel(logging.ERROR)
        from ._package_index import URL_SCHEME, PackageIndex, distros_for_url

        try:
            # pip 22.2+
            from pip._internal.index.collector import IndexContent
        except ImportError:
            # pip 22.1-
            from pip._internal.index.collector import (
                HTMLPage as IndexContent,  # ty: ignore[unresolved-import]
            )

        from urllib.error import HTTPError

        from pip._internal.index.collector import parse_links
        from pip._internal.index.package_finder import _check_link_requires_python
        from pip._internal.models.target_python import TargetPython
    except ImportError:
        import logging
        logger = logging.getLogger('zc.buildout.patches')
        logger.warning(
            'Requires-Python support missing and could not be patched into '
            'zc.buildout. \n\n',
            exc_info=True
        )
        return

    PY_VERSION_INFO = TargetPython().py_version_info

    # method copied over from setuptools 46.1.3
    # Unchanged in setuptools 70.0.0.
    def process_url(self: Any, url: str, retrieve: bool=False) -> None:  # type: ignore[explicit-any]  # body is a verbatim copy from setuptools driving pip internals that do not survive static typing
        """Evaluate a URL as a possible download, and maybe retrieve it"""
        if url in self.scanned_urls and not retrieve:
            return
        self.scanned_urls[url] = True
        if not URL_SCHEME(url):
            self.process_filename(url)
            return
        else:
            dists = list(distros_for_url(url))
            if dists:
                if not self.url_ok(url):
                    return
                self.debug("Found link: %s", url)

        if dists or not retrieve or url in self.fetched_urls:
            list(map(self.add, dists))
            return  # don't need the actual page

        if not self.url_ok(url):
            self.fetched_urls[url] = True
            return

        self.info("Reading %s", url)
        self.fetched_urls[url] = True  # prevent multiple fetch attempts
        tmpl = "Download error on %s: %%s -- Some packages may not be found!"
        f = self.open_url(url, tmpl % url)
        if f is None:
            return
        # --- LOCAL CHANGES MADE HERE: ---
        if isinstance(f, HTTPError):
            if f.code == 401:
                self.info("Authentication error: %s", f.msg)
            else:
                self.info("HTTP error: %s", f.msg)
        # --- END OF LOCAL CHANGES ---
        self.fetched_urls[f.url] = True
        if 'html' not in f.headers.get('content-type', '').lower():
            f.close()  # not html, we can't process it
            return

        base = f.url  # handle redirects
        page = f.read()

        # --- LOCAL CHANGES MADE HERE: ---

        if isinstance(page, str):
            page = page.encode('utf8')
            charset = 'utf8'
        else:
            if isinstance(f, HTTPError):
                # Errors have no charset, assume latin1:
                charset = 'latin-1'
            else:
                try:
                    charset = f.headers.get_param('charset') or 'latin-1'
                except AttributeError:
                    # Python 2
                    charset = f.headers.getparam('charset') or 'latin-1'

        try:
            content_type = f.getheader('content-type')
        except AttributeError:
            # On at least Python 2.7:
            # addinfourl instance has no attribute 'getheader'
            content_type = "text/html"

        try:
            # pip 22.2+
            html_page = IndexContent(
                page,
                content_type=content_type,
                encoding=charset,
                url=base,
                cache_link_parsing=False,
            )
        except TypeError:
            try:
                # pip 20.1-22.1
                html_page = IndexContent(page, charset, base, cache_link_parsing=False)  # ty: ignore[missing-argument]  # old-pip signature; TypeError-guarded above
            except TypeError:
                # pip 20.0 or older
                html_page = IndexContent(page, charset, base)  # ty: ignore[missing-argument]  # old-pip signature; TypeError-guarded above

        # https://github.com/buildout/buildout/issues/598
        # use_deprecated_html5lib is a required addition in pip 22.0/22.1
        # and it is gone already in 22.2
        try:
            plinks = parse_links(html_page, use_deprecated_html5lib=False)  # ty: ignore[unknown-argument]  # pip 22.0/22.1 only; TypeError-guarded below
        except TypeError:
            plinks = parse_links(html_page)
        plinks = list(plinks)

        # --- END OF LOCAL CHANGES ---

        if not isinstance(page, str):
            # In Python 3 and got bytes but want str.
            page = page.decode(charset, "ignore")
        f.close()

        # --- LOCAL CHANGES MADE HERE: ---

        for link in plinks:
            if _check_link_requires_python(link, PY_VERSION_INFO):
                self.process_url(link.url)

        # --- END OF LOCAL CHANGES ---

        if url.startswith(self.index_url) and getattr(f, 'code', None) != 404:
            page = self.process_index(url, page)

    PackageIndex.process_url = process_url



def patch_pkg_resources_requirement_contains() -> None:
    """Patch pkg_resources.Requirement contains method.

    What this hopefully solves, is checking if a Requirement contains
    a Distribution, without the key needing to be exactly the same.
    We want to compare normalized names.
    """
    try:
        from packaging.version import Version
        from pkg_resources import Distribution, Requirement

        from zc.buildout.utils import normalize_name
    except ImportError:
        return

    def __contains__(self: Requirement, item: Distribution | Version | str) -> bool:
        if isinstance(item, Distribution):
            # if item.key != self.key:
            if normalize_name(item.key) != normalize_name(self.key):
                return False

            item = item.version
        else:
            # Also accept dist-shaped objects that are not a Distribution
            # of whichever pkg_resources copy is live: uv mode's facade
            # dists (zc.buildout._workingset.Distribution) deliberately do
            # not subclass it.  Falling through to the specifier with the
            # object itself makes old vendored packagings (setuptools
            # < 68's copy) raise TypeError instead of comparing versions.
            item_key = getattr(item, 'key', None)
            item_version = getattr(item, 'version', None)
            if item_key is not None and item_version is not None:
                if normalize_name(item_key) != normalize_name(self.key):
                    return False

                item = item_version

        # Allow prereleases always in order to match the previous behavior of
        # this method. In the future this should be smarter and follow PEP 440
        # more accurately.
        try:
            return self.specifier.contains(item, prereleases=True)
        except Exception:  # noqa: BLE001 - see the note below: the
            # InvalidVersion class may come from either packaging copy
            # For example on https://pypi.org/simple/zope-exceptions/
            # the first distribution is zope.exceptions-3.4dev-r73107.tar.gz
            # I want to catch version.InvalidVersion, but it may
            # come from a different place then I think.
            return False

    Requirement.__contains__ = __contains__


_applying = False


def apply_patches() -> None:
    """Apply the pkg_resources patches; safe to call repeatedly.

    Each patch function is idempotent.  The pkg_resources copy to patch
    is either already loaded when this module is first imported (a real
    copy pre-imported under setuptools < 82, covered by the
    module-bottom branch below) or loads post-init on demand: the
    bridge in zc/buildout/__init__.py resolves ``pkg_resources``
    imports to the vendored copy and calls this function as part of
    that load, bit-identical to the legacy timing — the patches are in
    place before any pkg_resources object is used.

    ``patch_PackageIndex`` is deliberately not applied here: it needs
    ``zc.buildout._package_index``, which is legacy pip-mode-only, and
    importing it eagerly would drag the index module (and setuptools)
    into every uv-mode run that loads pkg_resources.  The
    ``zc.buildout._package_index`` import trigger applies it as soon
    as that module finishes loading instead, which is always before
    its first use.
    """
    global _applying
    if _applying:
        # Re-entrant import triggered while applying: the outer call
        # completes the work.
        return
    _applying = True
    try:
        patch_pkg_resources_requirement_contains()
    finally:
        _applying = False


def apply_index_patch() -> None:
    """Apply the PackageIndex patch once _package_index is loaded.

    Runs from the ``zc.buildout._package_index`` import trigger, after
    the module's exec completed, so the names it imports are fully
    initialized.  Also applies the pkg_resources patches first: a
    direct import of _package_index fires the zc/buildout/__init__.py
    bridge mid-exec, which covers those, and the call is idempotent
    anyway.
    """
    apply_patches()
    global _applying
    if _applying:
        return
    _applying = True
    try:
        patch_PackageIndex()
    finally:
        _applying = False


class _PatchTriggerLoader(importlib.abc.Loader):
    """Loader wrapper that applies its patch hook right after exec."""

    def __init__(self, loader: importlib.abc.Loader, apply) -> None:
        self._loader = loader
        self._apply = apply

    def __getattr__(self, name: str):
        return getattr(self._loader, name)

    def exec_module(self, module: ModuleType) -> None:
        self._loader.exec_module(module)
        self._apply()


class _PatchTriggerFinder(importlib.abc.MetaPathFinder):
    """Apply the PackageIndex patch when zc.buildout._package_index loads.

    pkg_resources itself is no longer a trigger name here: the
    on-demand bridge in zc/buildout/__init__.py resolves
    ``pkg_resources`` imports to the vendored copy and applies the
    pkg_resources patches as part of that load.  Resolving it through
    PathFinder as well would hand a real pkg_resources to processes
    running with an old setuptools that ships one, against the bridge
    policy (the vendored copy answers unless pkg_resources was already
    imported before zc.buildout).

    ``zc.buildout._package_index`` stays a trigger: it imports
    pkg_resources at its own top, and if it is imported directly, the
    bridge fires while _package_index is only partially initialized, so
    its own patch (``patch_PackageIndex``) is applied only once the
    module finishes loading.
    """

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if fullname != 'zc.buildout._package_index':
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None or spec.loader is None:
            return None
        spec.loader = _PatchTriggerLoader(spec.loader, apply_index_patch)
        return spec


def install_import_hook() -> None:
    """Install the trigger once; importing this module installs it.

    The finder must sit ahead of PathFinder, or PathFinder resolves
    pkg_resources first and the wrapper never gets consulted.
    """
    if not any(isinstance(finder, _PatchTriggerFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _PatchTriggerFinder())


install_import_hook()


# When pkg_resources is already loaded by the time this module is first
# imported — a real copy from setuptools < 82 that some code imported
# before zc.buildout — the bridge never fires for it (finders are not
# consulted for modules in sys.modules), so its load would never pick
# up the patches.  The patches are required in both modes —
# Requirement.__contains__ name normalization backs the membership
# checks uv mode gates on — so apply them on the pre-existing copy now.
# The module is already loaded, so this costs no import, and each
# patch is idempotent.
if 'pkg_resources' in sys.modules:
    apply_patches()
