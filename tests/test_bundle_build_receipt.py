from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts import bundle_build_receipt as receipt


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def bundle_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    root = tmp_path / "project"
    package = root / "src" / "ytsimpledownloader"
    package.mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "fixture"\nversion = "0.11.0"\n', encoding="utf-8")
    (package / "__init__.py").write_text('__version__ = "0.11.0"\n', encoding="utf-8")
    (root / ".gitignore").write_text("build/\ndist/\n", encoding="utf-8")
    _git(root, "init")
    _git(root, "config", "user.name", "Receipt Test")
    _git(root, "config", "user.email", "receipt@example.invalid")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")
    dist = root / "dist" / "YouTubeSimpleDownloader"
    dist.mkdir(parents=True)
    (dist / "YouTubeSimpleDownloader.exe").write_bytes(b"signed app fixture")
    (dist / "_internal").mkdir()
    (dist / "_internal" / "library.dll").write_bytes(b"library fixture")
    monkeypatch.setattr(receipt, "_environment", lambda: {
        "python": "3.12.0", "implementation": "CPython", "architecture": "AMD64",
        "operating_system": "Windows", "distributions": {"pip": "1", "pyinstaller": "2"},
    })
    return root, dist


def _completed(root: Path, dist: Path) -> dict:
    start = root / "build" / "ytsd-bundle-build-start.json"
    final = root / receipt.RECEIPT_RELATIVE_PATH
    receipt.begin_bundle_build(root, start)
    return receipt.finish_bundle_build(root, start, dist, final)


def test_receipt_hashes_signed_bundle_with_release_inventory_format(bundle_project: tuple[Path, Path]) -> None:
    root, dist = bundle_project
    document = _completed(root, dist)
    expected = hashlib.sha256()
    for name in ("_internal/library.dll", "YouTubeSimpleDownloader.exe"):
        digest = hashlib.sha256((dist / name).read_bytes()).hexdigest().upper()
        expected.update(name.encode() + b"\0" + digest.encode() + b"\n")
    assert document["bundle"] == {"file_count": 2, "inventory_sha256": expected.hexdigest().upper()}
    assert receipt.load_bundle_build_receipt(root, dist) == document
    assert str(root) not in json.dumps(document)


def test_finish_rejects_source_drift_mid_build(bundle_project: tuple[Path, Path]) -> None:
    root, dist = bundle_project
    start = root / "build" / "ytsd-bundle-build-start.json"
    receipt.begin_bundle_build(root, start)
    (root / "pyproject.toml").write_text('[project]\nname = "changed"\nversion = "0.11.0"\n', encoding="utf-8")
    with pytest.raises(receipt.BundleBuildError, match="not clean"):
        receipt.finish_bundle_build(root, start, dist, root / receipt.RECEIPT_RELATIVE_PATH)


def test_finish_rejects_environment_drift(bundle_project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    root, dist = bundle_project
    start = root / "build" / "ytsd-bundle-build-start.json"
    receipt.begin_bundle_build(root, start)
    changed = receipt._environment() | {"python": "3.12.1"}
    monkeypatch.setattr(receipt, "_environment", lambda: changed)
    with pytest.raises(receipt.BundleBuildError, match="environment changed"):
        receipt.finish_bundle_build(root, start, dist, root / receipt.RECEIPT_RELATIVE_PATH)


def test_optional_environment_check_rejects_drift(bundle_project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    root, dist = bundle_project
    document = _completed(root, dist)
    changed = receipt._environment() | {"python": "3.12.1"}
    monkeypatch.setattr(receipt, "_environment", lambda: changed)
    receipt.verify_bundle_build(root, dist, document)
    with pytest.raises(receipt.BundleBuildError, match="Current environment differs"):
        receipt.verify_bundle_build(root, dist, document, check_environment=True)


def test_stale_commit_is_rejected_even_when_version_is_unchanged(bundle_project: tuple[Path, Path]) -> None:
    root, dist = bundle_project
    document = _completed(root, dist)
    (root / "new_feature.py").write_text("new source\n", encoding="utf-8")
    _git(root, "add", "new_feature.py")
    _git(root, "commit", "-m", "new source, same version")
    with pytest.raises(receipt.BundleBuildError, match="Current source differs"):
        receipt.verify_bundle_build(root, dist, document)


def test_bundle_tamper_and_missing_receipt_are_rejected(bundle_project: tuple[Path, Path]) -> None:
    root, dist = bundle_project
    document = _completed(root, dist)
    (dist / "YouTubeSimpleDownloader.exe").write_bytes(b"different signed app")
    with pytest.raises(receipt.BundleBuildError, match="Bundle differs"):
        receipt.verify_bundle_build(root, dist, document)
    (root / receipt.RECEIPT_RELATIVE_PATH).unlink()
    with pytest.raises(receipt.BundleBuildError, match="missing or unreadable"):
        receipt.load_bundle_build_receipt(root, dist)


def test_malformed_receipt_fails_closed(bundle_project: tuple[Path, Path]) -> None:
    root, dist = bundle_project
    document = _completed(root, dist)
    document["bundle"]["file_count"] = True
    with pytest.raises(receipt.BundleBuildError, match="Malformed bundle digest"):
        receipt.verify_bundle_build(root, dist, document)
