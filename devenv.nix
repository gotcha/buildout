# Development environment for zc.buildout, driven by devenv.sh.
#
# Enter with:  devenv shell
#
# Python version: defaults to 3.12 (known-good for the 5.x bootstrap).
# Override per shell from the command line — no file edits needed:
#
#   devenv shell --option languages.python.version:string 3.10
#
# The chosen version is exported as PYTHON_VERSION, so the repo's own
# bootstrap (`make bin/buildout`, i.e. ./prepare.sh) picks exactly the
# Python this environment provides. prepare.sh keys its venvs by Python
# version (venvs/python3.x), so switching versions does not require
# `make clean` — just re-run `make bin/buildout && bin/buildout`.
{ pkgs, config, ... }:

{
  languages.python = {
    enable = true;
    version = "3.12";
    # Deliberately no languages.python.venv here: the repo bootstraps
    # its own venvs/ via prepare.sh; a devenv-managed venv would
    # shadow it on PATH and confuse the test-suite runners.
  };

  # Tools for development and for the verify-buildout skill:
  # - git: version control
  # - gnumake: the Makefile entry points (make test / make pytest / ...)
  # - uv: fast path of prepare.sh (USE_UV), also fetches pythons
  # - coreutils: provides `timeout` etc. on macOS, where it is missing
  packages = with pkgs; [
    git
    gnumake
    uv
    coreutils
  ];

  # Feed the repo bootstrap the Python version selected above.
  env.PYTHON_VERSION = config.languages.python.version;
  # nixpkgs Pythons ship with ensurepip disabled, so `python -m venv`
  # cannot bootstrap pip. Route prepare.sh through uv (--seed installs
  # pip), using the uv provided by this environment.
  env.USE_UV = "1";
  # prepare.sh runs `uv venv` unconditionally; let it replace an
  # existing venvs/pythonX.Y instead of erroring out, so that
  # re-running `make bin/buildout` (e.g. after a version switch) just
  # works.
  env.UV_VENV_CLEAR = "1";
  # Known-good bootstrap pin: latest setuptools (>= 81) removed
  # pkg_resources, which the 5.x bootstrap (dev.py) still imports.
  # Override per command when probing newer setuptools:
  #   SETUPTOOLS_VERSION=84.0.0 make bin/buildout
  env.SETUPTOOLS_VERSION = "75.8.2";

  enterShell = ''
    echo "zc.buildout devenv — python $(python --version 2>&1 | awk '{print $2}') (PYTHON_VERSION=$PYTHON_VERSION)"
    echo "Override python: devenv shell --option languages.python.version:string <3.9-3.14>"
  '';
}
