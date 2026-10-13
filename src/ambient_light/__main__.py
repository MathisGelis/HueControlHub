import sys

if sys.argv[1:2] == ["hook"]:  # chemin rapide : n'importe pas la CLI
    from .hook import run
    raise SystemExit(run())

from .cli import main

raise SystemExit(main())
