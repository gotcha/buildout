Fix a bootstrap crash under setuptools older than 75:
``_constrained_requirement`` asserted that the incoming requirement is a
``packaging.Requirement``, but ``pkg_resources.Requirement`` only derives
from it since setuptools 75, so the pip-mode toolchain resolve died with
``AssertionError`` on the older setuptools the legacy path still supports.
The assert now accepts exactly the two requirement classes in play — the
uv facade's, and ``pkg_resources``' taken from ``sys.modules`` when that
module is already loaded, so uv mode still never imports it. [Fizz]
