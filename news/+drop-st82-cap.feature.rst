Drop the ``setuptools<82`` ceiling: the declared requirement is now
``setuptools>=61.0.0`` and unpinned resolves no longer clamp setuptools
below 82.  The clamp (issue 744) existed because setuptools 82 removes
``pkg_resources``; the copy vendored for issue 685 covers that now, so
buildout runs fine — and can upgrade itself — on current setuptools.
[Fizz]
