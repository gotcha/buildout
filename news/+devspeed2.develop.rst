Dagger CI: per-Python pip and uv caches now persist across cells and runs
(cache volumes mounted in every job container), so repeat bootstraps stop
re-downloading and re-unpacking the toolchain. [gotcha]
