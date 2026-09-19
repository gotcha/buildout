Extract the CLI parsing cluster into the new zc.buildout.cli module; buildout keeps re-exporting it, and main stays at its pinned zc.buildout.buildout path. [gotcha]
