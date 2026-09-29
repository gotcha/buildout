Integration notes for the vendored ``pkg_resources`` (see issue 685):
the patch module now applies its ``Requirement.__contains__`` name
normalization as soon as a ``pkg_resources`` module is already loaded —
the vendored alias is installed at package import, before the lazy
import trigger could ever fire for it — and skips the
``WorkingSet.find`` backport for the vendored copy, which ships the
setuptools 75.8.2 fix natively.  The vendored tree is frozen
third-party code: excluded from the ruff/ty/mypy/radon gates and from
coverage.  ``platformdirs`` joins the declared dependencies because
the vendored copy uses it.  [Fizz]
