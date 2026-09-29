uv dependency removal, Phase 2 unit 6c: flip the installer to the
facade dist model in uv mode.  ``easy_install`` drops its module-level
pkg_resources import: the ``Environment`` class, the toolchain resolve
(buildout/setuptools/pip paths) and requirement parsing now resolve
lazily, in the installer mode in effect at first use — bit-identical
in pip mode, pkg_resources-free in uv mode.  ``install_backend``,
``scripts``, ``parts`` and ``testing`` consume the facade adapters on
the uv path; probe lanes show zero ``pkg_resources`` imports in uv
runs with the pip control transcript unchanged.  Cross-shape seams
(facade requirements meeting pkg_resources-shaped distributions in
test environments) are duck-typed rather than isinstance-checked.
The facade ``Distribution`` gains ``clone`` with pkg_resources
semantics (keyword substitution over carried-over attributes,
provider preserved) for the uv source-build path.  The uv compile
now receives every develop distribution of the environment as an
override, not only the batch-named ones: the compile resolves the
full dependency closure, so a fetched project's transitive
requirements settle from the develop dists the legacy fetch loop
would have found.  The zc.recipe.egg working-set-caching doctest
names the facade working set in uv mode.
[Fizz]
