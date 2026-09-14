The dagger CI module now gives each job command three attempts when the
failure matches a known transient index or fetch signature, up from one
retry. A cold shared devpi cache flakes in bursts, and run 34876803047
showed one cell burning both attempts on two different transient
fetches. [gotcha]
