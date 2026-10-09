Ad-hoc test invocations (``bin/py -m pytest``, ``bin/test`` without the
Makefile wrappers) now default test subprocesses to
``PYTHONWARNINGS=ignore`` inside ``zc.buildout.testing.system``,
matching the environment every Makefile gate sets.  This retires the
long-standing ``test_runsetup`` "isolation flake": it was never leaking
cross-test state — bare runs let subprocess warning banners (the vendored
pkg_resources deprecation and the setuptools 75.8.2 ``setup.py`` banner)
interleave into the output doctests compare, while the gates silenced
them globally.
