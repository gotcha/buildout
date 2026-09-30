``pip`` is no longer an unconditional dependency; the uv installer
needs no pip at all.  The legacy ``installer = pip`` mode requires pip
in the environment — install the new ``zc.buildout[pip]`` extra; pip
mode without pip now fails with a clear error instead of importing
whatever pip happened to be present.  [Fizz]
