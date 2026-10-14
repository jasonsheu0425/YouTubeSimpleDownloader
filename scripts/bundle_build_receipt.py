"""Bind a signed PyInstaller bundle to the source and environment that built it."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any


RECEIPT_RELATIVE_PATH = Path("build/ytsd-bundle-build.json")
HEX64 = re.compile(r"[0-9A-F]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")


class BundleBuildError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
    if result.returncode:
        raise BundleBuildError(f"Git {args[0]} failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def _source(root: Path) -> dict[str, Any]:
    root = root.resolve()
    git_root = Path(os.fsdecode(_git(root, "rev-parse", "--show-toplevel")).strip()).resolve()
    if git_root != root:
        raise BundleBuildError("Bundle build root is not the Git checkout root.")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all").strip():
        raise BundleBuildError("Source worktree is not clean.")
    commit = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    tree = _git(root, "rev-parse", "HEAD^{tree}").decode("ascii").strip()
    if not HEX40.fullmatch(commit) or not HEX40.fullmatch(tree):
        raise BundleBuildError("Invalid Git source identity.")
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = project.get("project", {}).get("version")
    init = (root / "src/ytsimpledownloader/__init__.py").read_text(encoding="utf-8")
    runtime_version = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']\s*$', init, re.M)
    if not isinstance(version, str) or not version or runtime_version is None or runtime_version.group(1) != version:
        raise BundleBuildError("Project and runtime versions differ.")
    raw_names = _git(root, "ls-files", "--cached", "-z").split(b"\0")
    names = sorted(os.fsdecode(name).replace("\\", "/") for name in raw_names if name)
    if not names or len(names) != len(set(names)):
        raise BundleBuildError("Tracked source inventory is empty or ambiguous.")
    files: dict[str, str] = {}
    fingerprint = hashlib.sha256()
    for name in names:
        path = root / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise BundleBuildError(f"Tracked input is not a regular in-tree file: {name}")
        file_hash = _sha256(path)
        files[name] = file_hash
        fingerprint.update(name.encode("utf-8"))
        fingerprint.update(b"\0")
        fingerprint.update(file_hash.encode("ascii"))
        fingerprint.update(b"\n")
    return {
        "commit": commit,
        "tree": tree,
        "version": version,
        "tracked_files": files,
        "fingerprint_sha256": fingerprint.hexdigest().upper(),
    }


def _environment() -> dict[str, Any]:
    distributions: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if not name or not distribution.version:
            raise BundleBuildError("Installed distribution has no name or version.")
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        if normalized in distributions and distributions[normalized] != distribution.version:
            raise BundleBuildError(f"Ambiguous installed distribution: {normalized}")
        distributions[normalized] = distribution.version
    for required in ("pip", "setuptools", "pyinstaller", "pyinstaller-hooks-contrib", "pyside6", "yt-dlp"):
        if required not in distributions:
            raise BundleBuildError(f"Required build distribution is absent: {required}")
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "architecture": platform.machine(),
        "operating_system": platform.system(),
        "distributions": dict(sorted(distributions.items())),
    }


def _bundle(dist_dir: Path) -> dict[str, Any]:
    root = dist_dir.resolve()
    if not root.is_dir():
        raise BundleBuildError("Bundle directory is missing.")
    files: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix().casefold()):
        if path.is_symlink():
            raise BundleBuildError("Bundle contains a symbolic link.")
        if not path.is_file():
            continue
        if not path.resolve().is_relative_to(root):
            raise BundleBuildError("Bundle file escapes its root.")
        files.append((path.relative_to(root).as_posix(), _sha256(path)))
    if not files or "YouTubeSimpleDownloader.exe" not in {name for name, _ in files}:
        raise BundleBuildError("Bundle application executable is missing.")
    digest = hashlib.sha256()
    for name, file_hash in files:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
    return {"file_count": len(files), "inventory_sha256": digest.hexdigest().upper()}


def _validate(document: Any, complete: bool) -> None:
    expected = {"schema_version", "record_type", "source", "environment"}
    if complete:
        expected.add("bundle")
    if not isinstance(document, dict) or set(document) != expected:
        raise BundleBuildError("Malformed bundle build record.")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise BundleBuildError("Unsupported bundle build schema.")
    if document["record_type"] != ("ytsd-bundle-build-receipt" if complete else "ytsd-bundle-build-start"):
        raise BundleBuildError("Wrong bundle build record type.")
    source = document["source"]
    if not isinstance(source, dict) or set(source) != {"commit", "tree", "version", "tracked_files", "fingerprint_sha256"}:
        raise BundleBuildError("Malformed source identity.")
    if not all(isinstance(source[key], str) and HEX40.fullmatch(source[key]) for key in ("commit", "tree")):
        raise BundleBuildError("Malformed Git identity.")
    if not isinstance(source["version"], str) or not source["version"] or not HEX64.fullmatch(source["fingerprint_sha256"]):
        raise BundleBuildError("Malformed source fingerprint.")
    files = source["tracked_files"]
    if not isinstance(files, dict) or not files or any(
        not isinstance(name, str) or not name or name.startswith("/") or ":" in name or "\\" in name
        or ".." in Path(name).parts or not isinstance(value, str) or not HEX64.fullmatch(value)
        for name, value in files.items()
    ):
        raise BundleBuildError("Malformed tracked source inventory.")
    fingerprint = hashlib.sha256()
    for name, file_hash in sorted(files.items()):
        fingerprint.update(name.encode("utf-8") + b"\0" + file_hash.encode("ascii") + b"\n")
    if fingerprint.hexdigest().upper() != source["fingerprint_sha256"]:
        raise BundleBuildError("Tracked source fingerprint is inconsistent.")
    environment = document["environment"]
    if not isinstance(environment, dict) or set(environment) != {"python", "implementation", "architecture", "operating_system", "distributions"}:
        raise BundleBuildError("Malformed build environment.")
    if any(not isinstance(environment[key], str) or not environment[key] for key in ("python", "implementation", "architecture", "operating_system")):
        raise BundleBuildError("Malformed build platform.")
    packages = environment["distributions"]
    if not isinstance(packages, dict) or not packages or any(
        not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
        or not isinstance(version, str) or not version or "/" in version or "\\" in version
        for name, version in packages.items()
    ):
        raise BundleBuildError("Malformed build toolchain.")
    if complete:
        bundle = document["bundle"]
        if not isinstance(bundle, dict) or set(bundle) != {"file_count", "inventory_sha256"}:
            raise BundleBuildError("Malformed bundle inventory.")
        if type(bundle["file_count"]) is not int or bundle["file_count"] < 1 or not isinstance(bundle["inventory_sha256"], str) or not HEX64.fullmatch(bundle["inventory_sha256"]):
            raise BundleBuildError("Malformed bundle digest.")


def _write_exclusive(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as target:
        json.dump(document, target, sort_keys=True, indent=2)
        target.write("\n")


def _read(path: Path, complete: bool) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BundleBuildError("Bundle build record is missing or unreadable.") from exc
    _validate(document, complete)
    return document


def begin_bundle_build(root: Path, output: Path) -> dict[str, Any]:
    document = {"schema_version": 1, "record_type": "ytsd-bundle-build-start", "source": _source(root), "environment": _environment()}
    _validate(document, False)
    _write_exclusive(output, document)
    return document


def finish_bundle_build(root: Path, start_record_path: Path, dist_dir: Path, output: Path) -> dict[str, Any]:
    start = _read(start_record_path, False)
    if start["source"] != _source(root) or start["environment"] != _environment():
        raise BundleBuildError("Source or build environment changed during bundle construction.")
    document = {**start, "record_type": "ytsd-bundle-build-receipt", "bundle": _bundle(dist_dir)}
    _validate(document, True)
    _write_exclusive(output, document)
    return document


def verify_bundle_build(root: Path, dist_dir: Path, document: dict[str, Any], check_source: bool = True, check_environment: bool = False) -> None:
    _validate(document, True)
    if document["bundle"] != _bundle(dist_dir):
        raise BundleBuildError("Bundle differs from its signed-build receipt.")
    if check_source and document["source"] != _source(root):
        raise BundleBuildError("Current source differs from the bundle build source.")
    if check_environment and document["environment"] != _environment():
        raise BundleBuildError("Current environment differs from the bundle build environment.")


def load_bundle_build_receipt(root: Path, dist_dir: Path) -> dict[str, Any]:
    document = _read(root / RECEIPT_RELATIVE_PATH, True)
    verify_bundle_build(root, dist_dir, document)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("begin", "finish", "verify"):
        sub = commands.add_parser(command)
        sub.add_argument("--project-root", type=Path, required=True)
        if command != "begin":
            sub.add_argument("--dist-dir", type=Path, required=True)
        if command == "begin":
            sub.add_argument("--output", type=Path, required=True)
        elif command == "finish":
            sub.add_argument("--start-record", type=Path, required=True)
            sub.add_argument("--output", type=Path, required=True)
        else:
            sub.add_argument("--receipt", type=Path)
            sub.add_argument("--check-environment", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "begin":
            begin_bundle_build(args.project_root, args.output)
        elif args.command == "finish":
            finish_bundle_build(args.project_root, args.start_record, args.dist_dir, args.output)
        else:
            document = _read(args.receipt, True) if args.receipt else load_bundle_build_receipt(args.project_root, args.dist_dir)
            verify_bundle_build(args.project_root, args.dist_dir, document, check_environment=args.check_environment)
    except (BundleBuildError, OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(f"Bundle build {args.command} passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
