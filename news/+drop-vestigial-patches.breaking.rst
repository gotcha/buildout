With the ``setuptools >= 75.8.2`` floor, the following patches are gone
from ``zc.buildout.patches``:
``patch_pkg_resources_working_set_find`` (back-ported the 75.8.2
``WorkingSet.find`` fix; the vendored ``pkg_resources`` 81.0.0 copy
carries the fix already) and ``patch_Distribution`` (disabled for
years).
``patch_PackageIndex``, ``patch_pkg_resources_requirement_contains``
and the import-hook machinery are unchanged.
See `issue 755 <https://github.com/buildout/buildout/issues/755>`_.
