"""Allow `python -m prognose`, so the Copilot agent never depends on PATH."""

from prognose.cli import main

raise SystemExit(main())
