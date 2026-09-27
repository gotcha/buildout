In uv mode, importing zc.buildout no longer loads pkg_resources through
``__init__``, ``cli``, ``configsetup`` or ``errors``: the
version lookups now use importlib.metadata, the errors module needs
pkg_resources only for type annotations, and the deprecation-warning
filter that required naming a pkg_resources class is dropped (the
doctest suite's output normalizer already covers legacy-mode
occurrences). [Fizz]
