"""Panel Importer: reads an Altium panel exported as ODB++ and identifies the panel.

Phase 1 identifies circuits, step-and-repeat, placements and fiducials and saves a
``.panel.json`` project file.  It writes no machine program.

Layering rule: ``panelimport.io``, ``panelimport.analysis`` and ``panelimport.model``
never import Qt.  Only ``panelimport.gui`` and ``panelimport.app`` do.
"""

__version__ = "0.2.0"
