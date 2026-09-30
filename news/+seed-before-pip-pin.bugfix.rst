Fix ``prepare.sh`` on old-pip legs: the pip pin now lands *after* the
test-seed downloads instead of before them.  An old pinned pip cannot
read current releases' metadata (platformdirs 4.12.2 is invisible to
pip 23.3.2), so the seed download failed the whole prepare on those
legs.  pip is brought current right after the venv creation, the seeds
download under it, and ``PIP_VERSION`` is installed once the seed no
longer needs the network.
