Extract ``_available_dists``, ``_best_version_dists`` and
``_select_from_best`` helpers from ``Installer._obtain`` in
``zc.buildout.easy_install``, reusing ``_final_dists`` for the
final-release filter and reducing its cyclomatic complexity from 19
to 4, with unit tests pinning the source-flag filtering, version-tie
and download-cache selection branches. [gotcha]
