"""PyInstaller entry point for Patreon Updater."""

from __future__ import annotations

import sys

from patreon_mega_audit.gui import main as gui_main
from patreon_mega_audit.update_posts import main as updater_main


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--run-updater":
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        return updater_main()
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
