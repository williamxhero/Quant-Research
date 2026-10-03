"""Run ``python -m manager_gui.web`` as a local WebUI server."""

from .server import main

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
