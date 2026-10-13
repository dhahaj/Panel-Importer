"""Command line: ``panelimport analyze <odb path>`` prints the summary and issues the GUI shows.

``panelimport verify <project>`` checks a saved project against its source export
(SHA-256 and re-analysis).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from panelimport import __version__
from panelimport.io.bom import BomError
from panelimport.io.odb import OdbOpenError
from panelimport.model.panel import Decisions
from panelimport.model.project_file import ProjectFileError, check_source, load_project
from panelimport.model.serialize import SerializationError
from panelimport.report import format_report
from panelimport.session import Session, SessionError
from panelimport.settings import CORNERS, ORDERS, REFERENCE_KINDS, Settings


def _settings(args: argparse.Namespace) -> Settings:
    settings = Settings.load(args.settings) if args.settings else Settings.load()
    if args.copy_suffix is not None:
        settings.copy_suffix_regex = args.copy_suffix
    if args.part_number_attribute is not None:
        settings.part_number_attribute = args.part_number_attribute
    problems = settings.validate()
    if problems:
        raise SerializationError("; ".join(problems))
    return settings


def _analysis_json(a) -> dict:
    return {
        "summary": a.summary,
        "mode": a.mode,
        "panel_step": a.panel_step,
        "board_step": a.board_step,
        "layer_roles": a.layer_roles,
        "circuits": [
            {
                "index": c.index,
                "dx": c.dx,
                "dy": c.dy,
                "rotation": c.rotation,
                "mirror": c.mirror,
                "source": c.source,
                "residual": c.residual,
            }
            for c in a.circuits
        ],
        "placements": len(a.placements),
        "panel_parts": [p.designator for p in a.panel_parts],
        "fiducial_candidates": [
            {"name": f.name, "x": f.x, "y": f.y, "level": f.level, "sources": f.sources} for f in a.fiducial_candidates
        ],
        "issues": [
            {
                "severity": i.severity.value,
                "code": i.code,
                "message": i.message,
                "designator": i.designator,
                "circuit": i.circuit,
                "file": i.file,
                "acknowledged": a.is_acknowledged(i),
            }
            for i in a.issues
        ],
        "can_confirm": a.can_confirm()[0],
    }


def cmd_analyze(args: argparse.Namespace) -> int:
    settings = _settings(args)
    decisions = Decisions(
        panel_step=args.panel_step,
        board_step=args.board_step,
        numbering_first=args.first,
        numbering_order=args.order,
        circuit_reference=args.reference,
        panel_level=[d.strip() for d in (args.panel_level or "").split(",") if d.strip()],
        bom_path=args.bom,
    )
    session = Session(settings)
    analysis = session.open_source(args.path, decisions)
    if args.json:
        print(json.dumps(_analysis_json(analysis), indent=2, ensure_ascii=False))
    else:
        print(format_report(analysis, verbose=args.verbose))
    return 1 if analysis.errors else 0


def cmd_verify(args: argparse.Namespace) -> int:
    project = load_project(args.project)
    src, issue = check_source(project, args.project)
    print(f"Project: {args.project} ({project.mode}, {len(project.circuits)} circuits, {len(project.placements)} placements)")
    print(f"Source:  {src}")
    if issue is not None:
        print(f"  {issue.format()}")
        return 1
    print("  SHA-256 matches the saved export")
    session = Session()
    result = session.open_project(args.project)
    if result.differences:
        print(f"  Re-analysis differs from the saved project in: {', '.join(result.differences)}")
        return 1
    print("  Re-analysis reproduces the saved project")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="panelimport", description="Panel Importer (Phase 1)")
    parser.add_argument("--version", action="version", version=f"panelimport {__version__}")
    parser.add_argument("--log", default="WARNING", help="log level (DEBUG, INFO, WARNING)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("analyze", help="analyse an ODB++ export and print the summary and issues")
    p.add_argument("path", help="ODB++ folder, .tgz or .zip")
    p.add_argument("--settings", help="settings JSON file (default: the user's settings)")
    p.add_argument("--panel-step", help="step to use as the panel")
    p.add_argument("--board-step", help="step to use as the board")
    p.add_argument("--first", choices=CORNERS, help="corner of circuit 1")
    p.add_argument("--order", choices=ORDERS, help="circuit numbering order")
    p.add_argument("--reference", choices=REFERENCE_KINDS, help="circuit reference point")
    p.add_argument("--copy-suffix", help="regex for designator copy suffixes, e.g. '_(\\d+)$'")
    p.add_argument("--part-number-attribute", help="attribute or property holding the part number")
    p.add_argument("--panel-level", help="comma-separated designators confirmed as panel-level")
    p.add_argument("--bom", help="optional BOM CSV to cross-check designators")
    p.add_argument("--json", action="store_true", help="print JSON instead of text")
    p.add_argument("-v", "--verbose", action="store_true", help="also list the placements")
    p.set_defaults(func=cmd_analyze)

    v = sub.add_parser("verify", help="check a saved project against its source export")
    v.add_argument("project", help="<name>.panel.json")
    v.set_defaults(func=cmd_verify)
    return parser


def _utf8_output() -> None:
    """Write UTF-8 when the output is not already UTF-8 (e.g. redirected on Windows),
    so "3 × 2" and "ΔX" survive pipes and log files."""
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if stream is not None and encoding != "utf8" and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> int:
    _utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, str(args.log).upper(), logging.WARNING), format="%(levelname)s %(name)s: %(message)s")
    try:
        return args.func(args)
    except (OdbOpenError, ProjectFileError, SessionError, SerializationError, BomError, OSError) as exc:
        print(f"panelimport: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
