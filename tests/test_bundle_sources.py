from pathlib import Path

import pytest

from scripts.check_bundle_sources import BundleSourceError, verify_collected_sources


def _fixture(tmp_path: Path):
    root = tmp_path / "repo"
    dist = root / "dist/YouTubeSimpleDownloader"
    python = tmp_path / "Python312"
    windows = tmp_path / "Windows"
    source = root / ".release-venv/Lib/site-packages/PySide6/Qt6Core.dll"
    target = dist / "_internal/PySide6/Qt6Core.dll"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_bytes(b"approved native library")
    target.write_bytes(source.read_bytes())
    toc = root / "collection.toc"
    toc.write_text(repr(([("PySide6/Qt6Core.dll", str(source), "BINARY")],)), encoding="utf-8")
    return root, dist, python, windows, source, target, toc


def test_verified_native_origin_and_bytes_pass(tmp_path):
    root, dist, python, windows, _, _, toc = _fixture(tmp_path)
    assert verify_collected_sources(root, dist, toc, python_base=python, windows_root=windows) == 1


def test_foreign_native_origin_fails_even_when_bytes_match(tmp_path):
    root, dist, python, windows, source, _, toc = _fixture(tmp_path)
    foreign = tmp_path / "HP/Qt6Core.dll"
    foreign.parent.mkdir()
    foreign.write_bytes(source.read_bytes())
    toc.write_text(repr(([("PySide6/Qt6Core.dll", str(foreign), "BINARY")],)), encoding="utf-8")
    with pytest.raises(BundleSourceError, match="Unapproved native source"):
        verify_collected_sources(root, dist, toc, python_base=python, windows_root=windows)


@pytest.mark.parametrize("failure", ["tamper", "unexpected", "escape"])
def test_native_bytes_and_inventory_fail_closed(tmp_path, failure):
    root, dist, python, windows, source, target, toc = _fixture(tmp_path)
    if failure == "tamper":
        target.write_bytes(b"changed")
    elif failure == "unexpected":
        (dist / "_internal/untracked.dll").write_bytes(b"extra")
    else:
        toc.write_text(repr(([("../Qt6Core.dll", str(source), "BINARY")],)), encoding="utf-8")
    with pytest.raises(BundleSourceError):
        verify_collected_sources(root, dist, toc, python_base=python, windows_root=windows)
