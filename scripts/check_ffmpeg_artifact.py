from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "security" / "artifact_hashes.json"
ARTIFACT_KEY = "ffmpeg_windows_x64"
SHA256_PATTERN = re.compile(r"^[0-9A-F]{64}$")


class ArtifactVerificationError(RuntimeError):
    pass


def _load_policy(manifest_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        policy = manifest["artifacts"][ARTIFACT_KEY]
        expected_hash = policy["sha256"].upper()
    except (OSError, json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        raise ArtifactVerificationError(
            f"Unable to load FFmpeg artifact policy from {manifest_path}: {exc}"
        ) from exc

    if manifest.get("schema_version") != 1:
        raise ArtifactVerificationError(
            f"Unsupported artifact manifest schema in {manifest_path}."
        )
    if not SHA256_PATTERN.fullmatch(expected_hash):
        raise ArtifactVerificationError(
            f"Invalid FFmpeg SHA-256 policy in {manifest_path}."
        )
    return {**policy, "sha256": expected_hash}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def verify_ffmpeg_artifact(
    artifact_path: Path,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> str:
    policy = _load_policy(manifest_path)
    if not artifact_path.is_file():
        raise ArtifactVerificationError(f"FFmpeg artifact not found: {artifact_path}")

    actual_hash = _sha256(artifact_path)
    expected_hash = policy["sha256"]
    if actual_hash != expected_hash:
        raise ArtifactVerificationError(
            "FFmpeg artifact SHA-256 mismatch. "
            f"Expected {expected_hash}, got {actual_hash}: {artifact_path}"
        )
    return actual_hash


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the FFmpeg release artifact against the repository policy."
    )
    parser.add_argument("artifact", type=Path, help="Path to ffmpeg.exe")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Artifact policy manifest (defaults to security/artifact_hashes.json)",
    )
    args = parser.parse_args(argv)

    try:
        actual_hash = verify_ffmpeg_artifact(args.artifact, args.manifest)
    except ArtifactVerificationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Verified FFmpeg artifact SHA-256: {actual_hash}")
    print(f"Artifact: {args.artifact.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
