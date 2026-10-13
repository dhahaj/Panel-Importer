"""Access to an ODB++ export given as a folder, a ``.tgz``/``.tar`` or a ``.zip``.

* The job root is the directory that holds ``matrix/matrix``; it may sit one or more
  levels below the selected folder or archive root.
* Names are matched case-insensitively (ODB++ step and layer names are
  case-insensitive; exporters differ in the case they write on disk).
* Members compressed with Unix ``compress`` (``features.Z``) are decompressed with
  ``unlzw3``.
* Archives are read into memory; nothing is extracted to disk.
"""

from __future__ import annotations

import hashlib
import os
import tarfile
import zipfile
from pathlib import Path

import unlzw3

MAX_MEMBER_BYTES = 1 << 30  # 1 GiB per member
MAX_TOTAL_BYTES = 4 << 30  # 4 GiB per archive


class OdbOpenError(Exception):
    """The selected path is not a readable ODB++ export."""


class OdbReadError(Exception):
    """A member exists but could not be read or decompressed."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


def _norm(name: str) -> str:
    name = name.replace("\\", "/")
    while name.startswith("./"):
        name = name[2:]
    return name.strip("/")


class OdbSource:
    def __init__(self, path: str | os.PathLike) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise OdbOpenError(f"{self.path} does not exist")
        self._members: dict[str, bytes] = {}  # tar members held in memory
        self._zip: zipfile.ZipFile | None = None
        self._folder_root: Path | None = None
        all_files: list[str]

        if self.path.is_dir():
            self.kind = "folder"
            self._folder_root = self.path
            all_files = []
            for dirpath, _dirnames, filenames in os.walk(self.path):
                rel_dir = Path(dirpath).relative_to(self.path).as_posix()
                for fn in filenames:
                    all_files.append(_norm(f"{rel_dir}/{fn}" if rel_dir != "." else fn))
        elif zipfile.is_zipfile(self.path):
            self.kind = "zip"
            try:
                self._zip = zipfile.ZipFile(self.path)
            except zipfile.BadZipFile as exc:
                raise OdbOpenError(f"{self.path}: {exc}") from None
            all_files = [_norm(i.filename) for i in self._zip.infolist() if not i.is_dir()]
            self._zip_names = {
                _norm(i.filename): i.filename for i in self._zip.infolist() if not i.is_dir()
            }
        elif tarfile.is_tarfile(self.path):
            self.kind = "tgz"
            all_files = []
            total = 0
            try:
                with tarfile.open(self.path, "r:*") as tar:
                    for member in tar:
                        if not member.isfile():
                            continue
                        if member.size > MAX_MEMBER_BYTES:
                            raise OdbOpenError(f"{member.name}: member too large")
                        total += member.size
                        if total > MAX_TOTAL_BYTES:
                            raise OdbOpenError(f"{self.path}: archive too large")
                        fh = tar.extractfile(member)
                        if fh is None:
                            continue
                        name = _norm(member.name)
                        self._members[name] = fh.read()
                        all_files.append(name)
            except (tarfile.TarError, EOFError, OSError) as exc:
                raise OdbOpenError(f"{self.path}: {exc}") from None
        else:
            raise OdbOpenError(
                f"{self.path} is not a folder, .tgz or .zip archive"
            )

        self.root = self._find_root(all_files)
        prefix = f"{self.root}/" if self.root else ""
        self._index: dict[str, str] = {}
        for name in all_files:
            if prefix and not name.startswith(prefix):
                continue
            rel = name[len(prefix):]
            self._index[rel.lower()] = name

    # ------------------------------------------------------------------ discovery
    def _find_root(self, names: list[str]) -> str:
        roots = set()
        for name in names:
            low = name.lower()
            for suffix in ("matrix/matrix", "matrix/matrix.z"):
                if low == suffix:
                    roots.add("")
                elif low.endswith("/" + suffix):
                    roots.add(name[: len(name) - len(suffix) - 1])
        if not roots:
            raise OdbOpenError(
                f"{self.path}: no ODB++ job found (missing required file matrix/matrix)"
            )
        if len(roots) > 1:
            listed = ", ".join(sorted(r or "." for r in roots))
            raise OdbOpenError(f"{self.path}: contains several ODB++ jobs ({listed})")
        return roots.pop()

    @property
    def job_name(self) -> str:
        if self.root:
            return self.root.split("/")[-1]
        stem = self.path.name
        for ext in (".tgz", ".tar.gz", ".tar", ".zip"):
            if stem.lower().endswith(ext):
                return stem[: -len(ext)]
        return stem

    # ------------------------------------------------------------------ access
    def find(self, rel: str) -> tuple[str, bool] | None:
        """Return ``(member name, is_compressed)`` for a job-relative path."""
        low = _norm(rel).lower()
        name = self._index.get(low)
        if name is not None:
            return name, False
        name = self._index.get(low + ".z")
        if name is not None:
            return name, True
        return None

    def exists(self, rel: str) -> bool:
        return self.find(rel) is not None

    def display_name(self, rel: str) -> str:
        found = self.find(rel)
        if found is None:
            return _norm(rel)
        name = found[0]
        prefix = f"{self.root}/" if self.root else ""
        return name[len(prefix):] if prefix and name.startswith(prefix) else name

    def _raw(self, name: str) -> bytes:
        if self.kind == "folder":
            assert self._folder_root is not None
            return (self._folder_root / name).read_bytes()
        if self.kind == "zip":
            assert self._zip is not None
            info = self._zip.getinfo(self._zip_names[name])
            if info.file_size > MAX_MEMBER_BYTES:
                raise OdbReadError(name, "member too large")
            return self._zip.read(info)
        return self._members[name]

    def read_bytes(self, rel: str) -> bytes | None:
        found = self.find(rel)
        if found is None:
            return None
        name, compressed = found
        try:
            data = self._raw(name)
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            raise OdbReadError(self.display_name(rel), str(exc)) from None
        if compressed:
            try:
                data = unlzw3.unlzw(data)
            except (ValueError, TypeError, IndexError) as exc:
                raise OdbReadError(self.display_name(rel), f"cannot decompress: {exc}") from None
        return data

    def read_text(self, rel: str) -> str | None:
        data = self.read_bytes(rel)
        if data is None:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("latin-1")

    def listdir(self, rel: str) -> list[str]:
        """Names directly below a job-relative directory (original case)."""
        low = _norm(rel).lower()
        depth = len(low.split("/")) if low else 0
        prefix = f"{low}/" if low else ""
        root_prefix = f"{self.root}/" if self.root else ""
        out: dict[str, str] = {}
        for key, name in self._index.items():
            if key.startswith(prefix):
                child = name[len(root_prefix):].split("/")[depth]
                out.setdefault(child.lower(), child)
        return sorted(out.values(), key=str.lower)

    def files(self) -> list[str]:
        """All job-relative file names (original case)."""
        prefix = f"{self.root}/" if self.root else ""
        return sorted(n[len(prefix):] for n in self._index.values())

    # ------------------------------------------------------------------ hashing
    def sha256(self) -> str:
        return source_sha256(self.path)

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()
            self._zip = None


def source_sha256(path: str | os.PathLike) -> str:
    """SHA-256 of an export: the archive bytes, or every file of a folder.

    For a folder, the hash covers each file's relative path and content in sorted
    order, so it is independent of the platform and of file timestamps.
    """
    path = Path(path)
    h = hashlib.sha256()
    if path.is_dir():
        files = []
        for dirpath, _dirs, names in os.walk(path):
            for fn in names:
                full = Path(dirpath) / fn
                files.append((full.relative_to(path).as_posix(), full))
        for rel, full in sorted(files):
            h.update(rel.encode("utf-8"))
            h.update(b"\0")
            h.update(hashlib.sha256(full.read_bytes()).digest())
        return h.hexdigest()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
