"""Panel Importer: reads an Altium panel exported as ODB++, identifies the panel and
writes the Juki ISS placement program for it.

Phase 1 identifies circuits, step-and-repeat, placements and fiducials and saves a
``.panel.json`` project file.  Phase 2 (``panelimport.iss``) writes the ISS program from
that file alone and compares programs (ISS or JaNets ``.x21``).

Layering rule: ``panelimport.io``, ``panelimport.analysis``, ``panelimport.model`` and
``panelimport.iss`` never import Qt.  Only ``panelimport.gui`` and ``panelimport.app`` do.
"""

__version__ = "0.3.0"
