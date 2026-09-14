Floor ``build`` at ``>=1`` in ``prepare.sh``. Without the floor, a flaky
package index that momentarily hides ``pyproject_hooks`` let pip silently
backtrack to ``build`` 0.9.0, which lacks ``build.env.DefaultIsolatedEnv``
and failed the test suite much later with an ``ImportError``. With the
floor the same index hiccup fails the resolve loudly with ``No matching
distribution found``, which the dagger CI retry already treats as
transient. [gotcha]
