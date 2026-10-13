"""PyInstaller entry point for the command line (panelimport.exe)."""

import sys

from panelimport.cli import main

if __name__ == "__main__":
    sys.exit(main())
