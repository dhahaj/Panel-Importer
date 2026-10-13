import shutil
import tarfile
import zipfile

import pytest
import unlzw3

from panelimport.io.odb import OdbJob, OdbOpenError
from panelimport.io.odb.archive import OdbSource, source_sha256
from tests.conftest import write
from tests.synthetic.lzw import compress
from tests.synthetic.odbgen import sr_panel


@pytest.mark.parametrize(
    "data",
    [b"", b"a", b"abababababab", bytes(range(256)) * 300, b"P 1 2 3 P 0 8 0\n" * 20000],
    ids=["empty", "one", "repeat", "binary", "records"],
)
def test_lzw_roundtrip(data):
    assert unlzw3.unlzw(compress(data)) == data


@pytest.mark.skipif(shutil.which("uncompress") is None, reason="ncompress not installed")
def test_lzw_matches_unix_uncompress(tmp_path):
    import subprocess

    data = b"".join(f"P {i * 0.1:.4f} {i % 97} 3 P 0 8 90\n".encode() for i in range(30000))
    p = tmp_path / "x.Z"
    p.write_bytes(compress(data))
    out = subprocess.run(["uncompress", "-c", str(p)], capture_output=True, check=True).stdout
    assert out == data


@pytest.mark.parametrize("kind", ["folder", "tgz", "zip"])
@pytest.mark.parametrize("compressed", [False, True])
def test_open_every_container(tmp_path, kind, compressed):
    job = sr_panel(compress_members=compressed)
    j = OdbJob(write(job, tmp_path, kind))
    assert j.source.kind == kind
    assert [s.lower() for s in j.step_names] == ["pcb", "panel"]
    comps = j.components("pcb", "comp_+_top")
    assert {c.name for c in comps.components} >= {"U1", "C1", "R1", "J1"}
    assert not j.issues


def test_root_found_below_selected_folder(tmp_path):
    job = sr_panel()
    job.write_folder(tmp_path / "outputs" / "odb")
    j = OdbJob(tmp_path / "outputs")
    assert j.source.root.lower().endswith("synthetic")


def test_names_are_case_insensitive(tmp_path):
    root = sr_panel().write_folder(tmp_path)
    (root / "steps" / "pcb").rename(root / "steps" / "PCB")
    j = OdbJob(root)
    assert j.stephdr("pcb") is not None
    assert j.components("Pcb", "COMP_+_TOP") is not None


def test_missing_matrix_is_reported(tmp_path):
    (tmp_path / "steps").mkdir()
    with pytest.raises(OdbOpenError, match="matrix/matrix"):
        OdbJob(tmp_path)


def test_several_jobs_in_one_archive(tmp_path):
    a = sr_panel()
    a.name = "a"
    b = sr_panel()
    b.name = "b"
    p = tmp_path / "two.zip"
    with zipfile.ZipFile(p, "w") as zf:
        for job in (a, b):
            for rel, data in job.files().items():
                zf.writestr(f"{job.name}/{rel}", data)
    with pytest.raises(OdbOpenError, match="several ODB"):
        OdbSource(p)


def test_not_an_export(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("hello")
    with pytest.raises(OdbOpenError):
        OdbSource(p)


def test_corrupt_z_member_is_an_issue(tmp_path):
    root = sr_panel(compress_members=True).write_folder(tmp_path)
    (root / "steps" / "pcb" / "layers" / "top_paste" / "features.Z").write_bytes(b"\x1f\x9d\x90garbage")
    j = OdbJob(root)
    assert j.features("pcb", "top_paste") is None
    assert any(i.code == "read_error" for i in j.issues)


def test_tar_members_are_not_extracted(tmp_path):
    """Archives are read in memory; a member path with '..' cannot escape."""
    job = sr_panel()
    p = tmp_path / "evil.tgz"
    import io

    with tarfile.open(p, "w:gz") as tar:
        for rel, data in job.files().items():
            ti = tarfile.TarInfo(f"{job.name}/{rel}")
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))
        ti = tarfile.TarInfo("../../escape.txt")
        ti.size = 3
        tar.addfile(ti, io.BytesIO(b"bad"))
    OdbJob(p)
    assert not (tmp_path.parent / "escape.txt").exists()


def test_sha256_folder_and_archive(tmp_path):
    job = sr_panel()
    root = job.write_folder(tmp_path / "f")
    h1 = source_sha256(root)
    assert h1 == source_sha256(root)
    (root / "misc" / "info").write_text((root / "misc" / "info").read_text() + "\n")
    assert source_sha256(root) != h1
    tgz = job.write_tgz(tmp_path / "x.tgz")
    assert len(source_sha256(tgz)) == 64
