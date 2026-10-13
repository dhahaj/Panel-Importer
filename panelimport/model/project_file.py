"""Project file: ``<name>.panel.json``, the direct serialization of :class:`PanelProject`.

Phase 2 reads only this file.  The source export is stored with its SHA-256 so that a
changed export is flagged when the project is reopened.
"""

from __future__ import annotations

import json
import os
from dataclasses import fields
from pathlib import Path

from panelimport.io.odb.archive import source_sha256
from panelimport.model.issues import Issue, error, warning
from panelimport.model.panel import PROJECT_FORMAT, PROJECT_VERSION, PanelProject
from panelimport.model.serialize import SerializationError, from_jsonable, to_jsonable

PROJECT_SUFFIX = ".panel.json"


class ProjectFileError(Exception):
    pass


def project_to_dict(project: PanelProject) -> dict:
    data = to_jsonable(project)
    # Acknowledgements read better without empty keys: {"code": "no_paste", "designator": "J1"}.
    data["acknowledged_warnings"] = [
        {k: v for k, v in ack.items() if v is not None} for ack in data["acknowledged_warnings"]
    ]
    return data


def project_from_dict(data: dict) -> PanelProject:
    if not isinstance(data, dict):
        raise ProjectFileError("not a project file (expected a JSON object)")
    if data.get("format") != PROJECT_FORMAT:
        raise ProjectFileError(f"not a panel project file (format {data.get('format')!r})")
    version = data.get("version")
    if version != PROJECT_VERSION:
        raise ProjectFileError(f"unsupported project version {version!r} (this program reads version {PROJECT_VERSION})")
    try:
        return from_jsonable(PanelProject, data)
    except SerializationError as exc:
        raise ProjectFileError(str(exc)) from None


def save_project(project: PanelProject, path: str | os.PathLike) -> Path:
    path = Path(path)
    text = json.dumps(project_to_dict(project), indent=2, ensure_ascii=False) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


def load_project(path: str | os.PathLike) -> PanelProject:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ProjectFileError(f"{path}: invalid JSON: {exc}") from None
    return project_from_dict(data)


def default_project_path(source: str | os.PathLike) -> Path:
    source = Path(source)
    name = source.name
    for ext in (".tgz", ".tar.gz", ".tar", ".zip"):
        if name.lower().endswith(ext):
            name = name[: -len(ext)]
            break
    return source.parent / f"{name}{PROJECT_SUFFIX}"


def resolve_source(project: PanelProject, project_path: str | os.PathLike) -> Path:
    p = Path(project.source.path)
    if not p.is_absolute():
        p = Path(project_path).resolve().parent / p
    return p


def check_source(project: PanelProject, project_path: str | os.PathLike) -> tuple[Path, Issue | None]:
    """Locate the project's source export and compare its SHA-256 with the saved one."""
    src = resolve_source(project, project_path)
    if not src.exists():
        return src, warning(
            "source_missing",
            f"The source export {project.source.path} was not found; showing the saved project only",
            subject="source",
        )
    digest = source_sha256(src)
    if digest != project.source.sha256:
        return src, error(
            "source_changed",
            f"The source export {project.source.path} has changed since the project was saved "
            f"(SHA-256 {digest[:12]}… ≠ saved {project.source.sha256[:12]}…)",
            subject="source",
            data={"sha256": digest, "saved": project.source.sha256},
        )
    return src, None


def diff_projects(a: PanelProject, b: PanelProject) -> list[str]:
    """Top-level fields that differ between two projects (for the reopen self-check)."""
    return [f.name for f in fields(PanelProject) if getattr(a, f.name) != getattr(b, f.name)]
