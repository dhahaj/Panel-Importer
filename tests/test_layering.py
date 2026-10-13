"""Rule: analysis/, io/ and model/ never import Qt."""

import ast
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "panelimport"
QT_FREE = [PKG / "io", PKG / "analysis", PKG / "model", PKG / "settings.py", PKG / "session.py", PKG / "report.py", PKG / "cli.py"]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_no_qt_imports_in_core_sources():
    files = []
    for p in QT_FREE:
        files.extend(p.rglob("*.py") if p.is_dir() else [p])
    offenders = {
        str(f.relative_to(PKG)): sorted(n for n in _imports(f) if n.split(".")[0] in ("PySide6", "PyQt5", "PyQt6", "shiboken6") or n.startswith("panelimport.gui"))
        for f in files
    }
    assert {k: v for k, v in offenders.items() if v} == {}


def test_core_import_does_not_load_qt():
    code = (
        "import sys, panelimport.cli, panelimport.analysis.pipeline, panelimport.model.project_file;"
        "print(any(m.startswith('PySide6') for m in sys.modules))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "False"
