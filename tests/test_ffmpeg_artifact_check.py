from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = PROJECT_ROOT / "scripts" / "check_ffmpeg_artifact.py"


def _write_manifest(path: Path, expected_hash: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifacts": {
                    "ffmpeg_windows_x64": {
                        "filename": "ffmpeg.exe",
                        "version": "8.1.2",
                        "source_url": "https://example.invalid/ffmpeg.zip",
                        "archive_sha256": "0" * 64,
                        "sha256": expected_hash,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _run_check(artifact: Path, manifest: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECK_SCRIPT), str(artifact), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_matching_ffmpeg_hash_is_accepted(tmp_path: Path) -> None:
    artifact = tmp_path / "ffmpeg.exe"
    artifact.write_bytes(b"approved ffmpeg artifact")
    expected_hash = hashlib.sha256(artifact.read_bytes()).hexdigest().upper()
    manifest = tmp_path / "artifact_hashes.json"
    _write_manifest(manifest, expected_hash)

    result = _run_check(artifact, manifest)

    assert result.returncode == 0
    assert expected_hash in result.stdout


def test_mismatched_ffmpeg_hash_is_rejected(tmp_path: Path) -> None:
    artifact = tmp_path / "ffmpeg.exe"
    artifact.write_bytes(b"substituted ffmpeg artifact")
    manifest = tmp_path / "artifact_hashes.json"
    _write_manifest(manifest, "A" * 64)

    result = _run_check(artifact, manifest)

    assert result.returncode == 1
    assert "SHA-256 mismatch" in result.stderr


def test_missing_ffmpeg_artifact_is_rejected(tmp_path: Path) -> None:
    manifest = tmp_path / "artifact_hashes.json"
    _write_manifest(manifest, "A" * 64)

    result = _run_check(tmp_path / "missing-ffmpeg.exe", manifest)

    assert result.returncode == 1
    assert "artifact not found" in result.stderr
