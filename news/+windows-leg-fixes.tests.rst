Fix the five Windows-leg failures from GH run 38367315241
(gotcha/buildout): the uv-probe fixtures now lay the console binary per
platform (``Scripts/uv.exe`` on win32, ``bin/uv`` elsewhere — the shape
``install_backend``'s honored-location probe actually seeks) and the
exec-bit assertion is POSIX-only (Windows has no executable bit for
``os.access(X_OK)`` to check); the three upgrade doctests fold their
``Installing …`` line through ``normalize_upgrade_install_line`` since
Windows resolves the candidate set setuptools-first.  Product code
unchanged — the tests were wrong about Windows shapes and ordering.
[gt-coleader]
