"""Phase 2: Juki ISS output from a confirmed ``<name>.panel.json``, and program comparison.

``mapping`` turns the project into the machine frame (pure math), ``checks`` decides
whether a program can be written, ``writer`` serializes it, ``reader`` reads ISS and
JaNets ``.x21`` programs back into one model and ``compare`` diffs two programs part by
part in panel coordinates.  Like ``io/``, ``analysis/`` and ``model/``, this package
never imports Qt.
"""

from panelimport.iss.settings import IssSettings

__all__ = ["IssSettings"]
