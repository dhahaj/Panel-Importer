"""``python -m panelimport``: the GUI without arguments, the CLI with them."""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from panelimport.cli import main as cli_main

        sys.exit(cli_main())
    from panelimport.app import main as gui_main

    sys.exit(gui_main())
