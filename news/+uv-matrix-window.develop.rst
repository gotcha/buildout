CI: the uv version matrix under test moves from the floor-plus-five-recent
window to a curated set: the ``setup.py`` floor 0.12.11, mid anchors 0.12.16
and 0.12.21, the latest 0.12.x patch run 0.12.22 through 0.12.24, and 0.13.0
as the first 0.13.x cell. The default uv, the one exercised when
``UV_VERSION`` is unset, now pins to ``uv==0.12.24`` in ``prepare.sh``.
[gotcha]
