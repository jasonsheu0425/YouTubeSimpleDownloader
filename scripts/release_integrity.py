"""Generate and verify release SBOM and local build provenance sidecars."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import struct
import subprocess
import sys
import tempfile
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.check_dependency_locks import (
        parse_lock,
        verify_dependency_locks,
    )
    from scripts.dependency_lock_policy import normalized_name
except ModuleNotFoundError:
    from check_dependency_locks import parse_lock, verify_dependency_locks
    from dependency_lock_policy import normalized_name


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROVENANCE_SCHEMA = Path("security/release_provenance.schema.json")
REPOSITORY = "jasonsheu0425/YouTubeSimpleDownloader"
SIGNER_SUBJECT = "CN=Jason YouTube Simple Downloader Test Signing"
BUILD_INPUTS = (
    "pyproject.toml",
    "build_exe.bat",
    "build_inno_installer.ps1",
    "installer/YouTubeSimpleDownloader.iss",
    "installer/LICENSE.txt",
    "installer/README-INSTALLER.txt",
    "hooks/hook-imageio_ffmpeg.py",
    "run_app.py",
    "src/ytsimpledownloader/assets/app_icon.ico",
    ".github/workflows/test.yml",
    "scripts/check_dependency_locks.py",
    "scripts/dependency_lock_policy.py",
    "scripts/generate_windows_lock.py",
    "scripts/check_ffmpeg_artifact.py",
    "scripts/check_packaged_qt_runtime.py",
    "scripts/sanitize_pyinstaller_path.py",
    "scripts/release_integrity.py",
    "security/artifact_hashes.json",
    "security/release_provenance.schema.json",
)
LOCK_NAMES = ("bootstrap", "runtime", "dev", "build")
PIN_PATTERN = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[A-Za-z0-9][A-Za-z0-9.+!_-]*)$"
)


class ReleaseIntegrityError(RuntimeError):
    """Raised when release identity or integrity evidence does not validate."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise ReleaseIntegrityError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def verify_source_tree(root: Path = PROJECT_ROOT) -> dict[str, str]:
    """Require a clean tracked/untracked source tree and return its exact identity."""
    root = root.resolve()
    commit = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise ReleaseIntegrityError("The source worktree must be clean before release builds.")
    return {"commit": commit, "tree": tree, "clean": "true"}


def verify_build_environment() -> None:
    if (
        platform.system() != "Windows"
        or platform.python_implementation() != "CPython"
        or sys.version_info[:2] != (3, 12)
        or struct.calcsize("P") != 8
    ):
        raise ReleaseIntegrityError("Release builds require 64-bit CPython 3.12 on Windows.")


def _load_project(root: Path) -> tuple[dict[str, Any], str]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(project.get("project", {}).get("version", ""))
    init_text = (root / "src/ytsimpledownloader/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']\s*$', init_text, re.M)
    if not version or match is None or match.group(1) != version:
        raise ReleaseIntegrityError("pyproject.toml and package runtime versions do not match.")
    return project, version


def _load_policy(path: Path) -> dict[str, str]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    artifact = policy["artifacts"]["ffmpeg_windows_x64"]
    expected = {
        "filename": str(artifact["filename"]),
        "version": str(artifact["version"]),
        "source_url": str(artifact["source_url"]),
        "archive_sha256": str(artifact["archive_sha256"]).upper(),
        "sha256": str(artifact["sha256"]).upper(),
    }
    if expected["filename"] != "ffmpeg.exe" or not expected["source_url"].startswith("https://"):
        raise ReleaseIntegrityError("FFmpeg manifest identity is not an expected HTTPS executable policy.")
    if any(not re.fullmatch(r"[A-F0-9]{64}", expected[key]) for key in ("archive_sha256", "sha256")):
        raise ReleaseIntegrityError("FFmpeg manifest contains an invalid SHA-256 value.")
    return expected


def verify_ffmpeg(ffmpeg_path: Path, policy_path: Path) -> tuple[dict[str, str], str]:
    policy = _load_policy(policy_path)
    if not ffmpeg_path.is_file() or ffmpeg_path.name.lower() != policy["filename"]:
        raise ReleaseIntegrityError(f"Verified FFmpeg executable is missing: {ffmpeg_path.name}.")
    observed_hash = sha256_file(ffmpeg_path)
    if observed_hash != policy["sha256"]:
        raise ReleaseIntegrityError(
            f"FFmpeg executable SHA-256 mismatch: expected {policy['sha256']}, got {observed_hash}."
        )
    result = subprocess.run(
        [str(ffmpeg_path), "-version"], capture_output=True, text=True, timeout=20, check=False
    )
    if result.returncode:
        raise ReleaseIntegrityError(f"FFmpeg -version failed with exit code {result.returncode}.")
    version_line = (result.stdout or result.stderr).splitlines()[0].strip()
    if not re.match(rf"^ffmpeg version {re.escape(policy['version'])}(?:-|\s)", version_line):
        raise ReleaseIntegrityError(f"FFmpeg version does not match the pinned policy: {version_line}.")
    return policy, version_line


def _requirement_pins(project: dict[str, Any]) -> dict[str, str]:
    pins: dict[str, str] = {}
    for requirement in project.get("project", {}).get("dependencies", []):
        match = PIN_PATTERN.fullmatch(requirement) if isinstance(requirement, str) else None
        if match is None:
            raise ReleaseIntegrityError("All application dependencies must be exact name==version pins.")
        pins[normalized_name(match.group("name"))] = match.group("version")
    return pins


def _file_inventory(dist_dir: Path) -> list[tuple[str, Path, str]]:
    root = dist_dir.resolve()
    if not root.is_dir():
        raise ReleaseIntegrityError(f"PyInstaller bundle does not exist: {dist_dir.name}.")
    result: list[tuple[str, Path, str]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix().casefold()):
        if path.is_symlink():
            raise ReleaseIntegrityError("PyInstaller bundle must not contain symbolic links.")
        if not path.is_file():
            continue
        try:
            path.resolve().relative_to(root)
        except ValueError as exc:
            raise ReleaseIntegrityError("A bundle file resolves outside the PyInstaller tree.") from exc
        relative = path.relative_to(root).as_posix()
        result.append((relative, path, sha256_file(path)))
    if not result:
        raise ReleaseIntegrityError("PyInstaller bundle contains no files.")
    return result


def bundle_inventory_sha256(dist_dir: Path) -> str:
    digest = hashlib.sha256()
    for relative, _, file_hash in _file_inventory(dist_dir):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest().upper()


def _cyclonedx_validate(document: dict[str, Any]) -> None:
    try:
        from cyclonedx.schema import SchemaVersion
        from cyclonedx.validation.json import JsonStrictValidator
    except ImportError as exc:
        raise ReleaseIntegrityError("CycloneDX build validator is not installed from requirements/build.lock.") from exc
    rendered = json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    errors = JsonStrictValidator(SchemaVersion.V1_6).validate_str(rendered, all_errors=True)
    if errors is None:
        return
    if not isinstance(errors, (list, tuple)):
        errors = [errors]
    messages = "; ".join(str(error) for error in errors)
    raise ReleaseIntegrityError(f"CycloneDX 1.6 schema validation failed: {messages}")


def _bom_component(
    *,
    name: str,
    version: str,
    component_type: str,
    purl: str,
    properties: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    component: dict[str, Any] = {
        "bom-ref": purl,
        "type": component_type,
        "name": name,
        "version": version,
        "purl": purl,
    }
    if properties:
        component["properties"] = properties
    return component


def _runtime_dependency_graph(
    runtime_components: dict[str, dict[str, Any]],
    *,
    app_ref: str,
    app_direct_refs: list[str],
    base_dependencies: list[dict[str, Any]],
    base_ref_map: dict[str, str],
) -> list[dict[str, Any]]:
    """Build a closed runtime graph, retaining generator edges and package metadata edges."""
    try:
        from packaging.requirements import Requirement
    except ImportError as exc:
        raise ReleaseIntegrityError("The locked packaging parser is required to build runtime relationships.") from exc

    refs = {name: component["bom-ref"] for name, component in runtime_components.items()}
    graph: dict[str, set[str]] = {
        ref: set() for ref in {*refs.values(), *app_direct_refs}
    }

    # The CycloneDX requirements generator may emit only isolated requirement nodes, but
    # retain any package relationships it does provide after canonicalizing its refs.
    for item in base_dependencies:
        original_ref = item.get("ref")
        if original_ref not in base_ref_map:
            raise ReleaseIntegrityError("CycloneDX dependency graph references an unknown component.")
        ref = base_ref_map[original_ref]
        if ref == app_ref:
            continue
        if ref not in graph:
            raise ReleaseIntegrityError("CycloneDX dependency graph contains a non-runtime package node.")
        targets = item.get("dependsOn", [])
        if not isinstance(targets, list) or any(not isinstance(target, str) for target in targets):
            raise ReleaseIntegrityError("CycloneDX dependency target list is malformed.")
        for target in targets:
            canonical_target = base_ref_map.get(target)
            if canonical_target not in graph:
                raise ReleaseIntegrityError("CycloneDX runtime relationship targets an unknown package.")
            graph[ref].add(canonical_target)

    # The requirements-mode generator does not resolve package-to-package edges. Derive
    # the active default-extra graph from locked distribution metadata and fail if the
    # runtime lock omits a dependency needed on this build platform.
    for name, component in runtime_components.items():
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise ReleaseIntegrityError(f"Locked runtime package {name} is not installed in the build environment.") from exc
        if distribution.version != component.get("version"):
            raise ReleaseIntegrityError(f"Installed runtime package {name} differs from its SBOM version.")
        for raw_requirement in distribution.requires or []:
            try:
                requirement = Requirement(raw_requirement)
            except Exception as exc:
                raise ReleaseIntegrityError(f"Runtime dependency metadata is invalid for {name}.") from exc
            if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
                continue
            if requirement.extras:
                raise ReleaseIntegrityError(
                    f"Runtime package {name} requests dependency extras that are not represented by the runtime lock."
                )
            dependency_name = normalized_name(requirement.name)
            dependency_ref = refs.get(dependency_name)
            if dependency_ref is None:
                raise ReleaseIntegrityError(
                    f"Runtime lock omits active dependency {requirement.name} required by {name}."
                )
            graph[refs[name]].add(dependency_ref)

    graph[app_ref] = set(app_direct_refs)
    return [
        {"ref": ref, "dependsOn": sorted(targets)}
        for ref, targets in sorted(graph.items())
    ]


def build_sbom_document(
    base_document: dict[str, Any],
    *,
    root: Path,
    dist_dir: Path,
    ffmpeg_path: Path,
    policy_path: Path,
    qt_version: str,
    commit: str,
    commit_epoch: int,
    inno_version: str,
) -> dict[str, Any]:
    """Augment a validated CycloneDX requirements BOM with actual bundle files."""
    if base_document.get("bomFormat") != "CycloneDX" or base_document.get("specVersion") != "1.6":
        raise ReleaseIntegrityError("CycloneDX generator must produce a version 1.6 JSON BOM.")
    project, version = _load_project(root)
    policy, ffmpeg_version_line = verify_ffmpeg(ffmpeg_path, policy_path)
    runtime_entries = parse_lock(root / "requirements/runtime.lock")
    build_entries = parse_lock(root / "requirements/build.lock")
    bootstrap_entries = parse_lock(root / "requirements/bootstrap.lock")
    app_pins = _requirement_pins(project)
    components = base_document.get("components")
    if not isinstance(components, list):
        raise ReleaseIntegrityError("CycloneDX generator returned no component inventory.")

    runtime_components: dict[str, dict[str, Any]] = {}
    for component in components:
        name = normalized_name(str(component.get("name", "")))
        if name == "setuptools":
            continue
        if name in runtime_components:
            raise ReleaseIntegrityError(f"CycloneDX BOM duplicates runtime package {name}.")
        runtime_components[name] = component

    expected_runtime = {name: item[0] for name, item in runtime_entries.items() if name != "setuptools"}
    actual_runtime = {
        name: str(component.get("version", "")) for name, component in runtime_components.items()
    }
    if actual_runtime != expected_runtime:
        raise ReleaseIntegrityError("CycloneDX package versions do not exactly match the runtime lock.")
    for name, version_pin in app_pins.items():
        if name not in runtime_components or str(runtime_components[name].get("version")) != version_pin:
            raise ReleaseIntegrityError(f"Application runtime pin {name} is absent or mismatched in the SBOM.")

    base_dependencies = base_document.get("dependencies", [])
    if not isinstance(base_dependencies, list):
        raise ReleaseIntegrityError("CycloneDX generator returned a malformed dependency graph.")
    base_ref_map: dict[str, str] = {}
    for name, component in runtime_components.items():
        expected_purl = f"pkg:pypi/{name}@{component.get('version')}"
        original_ref = component.get("bom-ref")
        if not isinstance(original_ref, str) or not original_ref:
            raise ReleaseIntegrityError(f"CycloneDX component {name} has no stable reference.")
        if component.get("purl") != expected_purl:
            raise ReleaseIntegrityError(f"CycloneDX package URL identity is inconsistent for {name}.")
        for ref in (original_ref, expected_purl):
            if ref in base_ref_map and base_ref_map[ref] != expected_purl:
                raise ReleaseIntegrityError("CycloneDX generator returned a duplicate component reference.")
            base_ref_map[ref] = expected_purl
        component["bom-ref"] = expected_purl

    files = _file_inventory(dist_dir)
    ffmpeg_relative = ffmpeg_path.resolve().relative_to(dist_dir.resolve()).as_posix()
    if ffmpeg_relative not in {relative for relative, _, _ in files}:
        raise ReleaseIntegrityError("Verified FFmpeg executable is not part of the PyInstaller bundle.")
    ffmpeg_hash = next(digest for relative, _, digest in files if relative == ffmpeg_relative)
    if ffmpeg_hash != policy["sha256"]:
        raise ReleaseIntegrityError("FFmpeg bundle inventory does not match the verified executable hash.")

    app_name = str(project["project"]["name"])
    app_purl = f"pkg:generic/{normalized_name(app_name)}@{version}"
    root_component = base_document.setdefault("metadata", {}).get("component")
    if not isinstance(root_component, dict):
        raise ReleaseIntegrityError("CycloneDX generator did not include the application root component.")
    original_root_ref = root_component.get("bom-ref")
    if not isinstance(original_root_ref, str) or not original_root_ref:
        raise ReleaseIntegrityError("CycloneDX application root has no stable reference.")
    root_ref = app_purl
    base_ref_map[original_root_ref] = root_ref
    base_ref_map[root_ref] = root_ref
    root_component.update(
        {
            "bom-ref": root_ref,
            "type": "application",
            "name": app_name,
            "version": version,
            "purl": app_purl,
        }
    )

    py_version = platform.python_version()
    python_purl = f"pkg:generic/cpython@{py_version}"
    qt_purl = f"pkg:generic/qt@{qt_version}"
    ffmpeg_purl = f"pkg:generic/ffmpeg@{policy['version']}"
    extra_components = [
        _bom_component(
            name="CPython",
            version=py_version,
            component_type="framework",
            purl=python_purl,
            properties=[{"name": "ytsd:runtime-role", "value": "bundled-interpreter"}],
        ),
        _bom_component(
            name="Qt",
            version=qt_version,
            component_type="framework",
            purl=qt_purl,
            properties=[{"name": "ytsd:version-source", "value": "bundled Qt6Core.dll product version"}],
        ),
        {
            **_bom_component(
                name="FFmpeg",
                version=policy["version"],
                component_type="framework",
                purl=ffmpeg_purl,
                properties=[
                    {"name": "ytsd:source-url", "value": policy["source_url"]},
                    {"name": "ytsd:archive-sha256-policy", "value": policy["archive_sha256"]},
                    {"name": "ytsd:archive-downloaded-and-rehashed-for-local-build", "value": "false"},
                    {"name": "ytsd:executable-sha256-verified", "value": "true"},
                    {"name": "ytsd:version-output", "value": ffmpeg_version_line},
                ],
            ),
            "hashes": [{"alg": "SHA-256", "content": ffmpeg_hash.lower()}],
            "externalReferences": [
                {
                    "type": "distribution",
                    "url": policy["source_url"],
                    "comment": "Version-pinned archive source; archive digest is a policy value, executable digest is verified locally.",
                }
            ],
        },
    ]

    file_components: list[dict[str, Any]] = []
    for relative, _, digest in files:
        file_component = {
            "bom-ref": f"urn:ytsd:file:{hashlib.sha256(relative.encode('utf-8')).hexdigest()}",
            "type": "file",
            "name": Path(relative).name,
            "hashes": [{"alg": "SHA-256", "content": digest.lower()}],
            "properties": [{"name": "ytsd:relative-path", "value": relative}],
        }
        if relative == ffmpeg_relative:
            file_component["properties"].extend(
                [
                    {"name": "ytsd:component", "value": "FFmpeg executable"},
                    {"name": "ytsd:version", "value": policy["version"]},
                    {"name": "ytsd:source-url", "value": policy["source_url"]},
                ]
            )
        file_components.append(file_component)

    base_document["components"] = sorted(
        [*runtime_components.values(), *extra_components, *file_components],
        key=lambda item: (str(item.get("type")), str(item.get("name")).casefold(), str(item.get("bom-ref"))),
    )

    direct_refs = [runtime_components[name]["bom-ref"] for name in sorted(app_pins)]
    direct_refs.extend((python_purl, qt_purl, ffmpeg_purl))
    base_document["dependencies"] = _runtime_dependency_graph(
        runtime_components,
        app_ref=root_ref,
        app_direct_refs=sorted(set(direct_refs)),
        base_dependencies=base_dependencies,
        base_ref_map=base_ref_map,
    )

    metadata = base_document.setdefault("metadata", {})
    metadata["timestamp"] = datetime.fromtimestamp(commit_epoch, timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    metadata_properties = metadata.setdefault("properties", [])
    if not isinstance(metadata_properties, list):
        raise ReleaseIntegrityError("CycloneDX metadata properties have an unexpected shape.")
    metadata_properties.extend(
        [
            {"name": "ytsd:source-commit", "value": commit},
            {"name": "ytsd:source-tree-clean", "value": "true"},
            {"name": "ytsd:runtime-lock-sha256", "value": sha256_file(root / "requirements/runtime.lock")},
            {"name": "ytsd:ffmpeg-archive-sha256-policy", "value": policy["archive_sha256"]},
            {"name": "ytsd:ffmpeg-executable-sha256-verified", "value": ffmpeg_hash},
        ]
    )
    metadata["properties"] = sorted(metadata_properties, key=lambda item: (item["name"], item["value"]))

    tools = metadata.setdefault("tools", {}).setdefault("components", [])
    if not isinstance(tools, list):
        raise ReleaseIntegrityError("CycloneDX generator returned an unexpected tools structure.")
    tool_versions = {
        name: entries[0]
        for name, entries in build_entries.items()
        if name not in runtime_entries or name == "setuptools"
    }
    tool_versions.update({"pip": bootstrap_entries["pip"][0]})
    tool_versions["inno-setup"] = inno_version
    existing_tool_keys = {
        (normalized_name(str(item.get("name", ""))), str(item.get("version", "")))
        for item in tools
    }
    for name, tool_version in sorted(tool_versions.items()):
        key = (name, tool_version)
        if key in existing_tool_keys:
            continue
        tool_type = "application" if name in {"pyinstaller", "cyclonedx-bom", "inno-setup", "pip"} else "library"
        tool = {
            "type": tool_type,
            "name": "Inno Setup" if name == "inno-setup" else name,
            "version": tool_version,
            "properties": [{"name": "ytsd:tool-role", "value": "build-only"}],
        }
        if name != "inno-setup":
            tool["purl"] = f"pkg:pypi/{name}@{tool_version}"
        tools.append(tool)
    tools.append(
        {
            "type": "application",
            "name": "CPython build interpreter",
            "version": py_version,
            "properties": [{"name": "ytsd:tool-role", "value": "build-only"}],
        }
    )
    metadata["tools"]["components"] = sorted(
        tools,
        key=lambda item: (normalized_name(str(item.get("name", ""))), str(item.get("version", ""))),
    )

    file_inventory_material = "\n".join(f"{name}\0{digest}" for name, _, digest in files)
    deterministic_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"https://github.com/{REPOSITORY}/sbom/{commit}/{sha256_file(root / 'requirements/runtime.lock')}/{hashlib.sha256(file_inventory_material.encode()).hexdigest()}",
    )
    base_document["serialNumber"] = f"urn:uuid:{deterministic_id}"
    base_document["version"] = 1
    _cyclonedx_validate(base_document)
    _verify_sbom_semantics(
        base_document,
        root=root,
        policy_path=policy_path,
        source_commit=commit,
        qt_version=qt_version,
        python_version=py_version,
        inno_version=inno_version,
        ffmpeg_version_line=ffmpeg_version_line,
    )
    return base_document


def _generate_base_bom(root: Path, output_path: Path, commit_epoch: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ytsd-cdx-", dir=output_path.parent) as temp_name:
        temp_root = Path(temp_name)
        package_list = temp_root / "runtime-packages.in"
        entries = parse_lock(root / "requirements/runtime.lock")
        package_list.write_text(
            "".join(
                f"{name}=={version}\n"
                for name, (version, _) in sorted(entries.items())
                if name != "setuptools"
            ),
            encoding="utf-8",
            newline="\n",
        )
        base_path = temp_root / "base.json"
        executable = Path(sys.executable).with_name("cyclonedx-py.exe")
        if not executable.is_file():
            raise ReleaseIntegrityError("Pinned cyclonedx-py.exe was not installed from requirements/build.lock.")
        env = os.environ.copy()
        env["SOURCE_DATE_EPOCH"] = str(commit_epoch)
        command = [
            str(executable),
            "requirements",
            str(package_list),
            "--pyproject",
            str(root / "pyproject.toml"),
            "--mc-type",
            "application",
            "--sv",
            "1.6",
            "--output-reproducible",
            "--of",
            "JSON",
            "--validate",
            "--output-file",
            str(base_path),
        ]
        result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, check=False)
        if result.returncode:
            raise ReleaseIntegrityError(
                "CycloneDX generator failed: " + (result.stderr.strip() or result.stdout.strip())
            )
        try:
            return json.loads(base_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReleaseIntegrityError("CycloneDX generator did not produce valid JSON.") from exc


def generate_sbom(
    *,
    root: Path,
    dist_dir: Path,
    ffmpeg_path: Path,
    output_path: Path,
    qt_version: str,
    inno_version: str,
) -> dict[str, Any]:
    verify_build_environment()
    source = verify_source_tree(root)
    verify_dependency_locks(root)
    _, version = _load_project(root)
    commit_epoch = int(_git(root, "show", "-s", "--format=%ct", source["commit"]))
    base = _generate_base_bom(root, output_path, commit_epoch)
    document = build_sbom_document(
        base,
        root=root,
        dist_dir=dist_dir,
        ffmpeg_path=ffmpeg_path,
        policy_path=root / "security/artifact_hashes.json",
        qt_version=qt_version,
        commit=source["commit"],
        commit_epoch=commit_epoch,
        inno_version=inno_version,
    )
    verify_sbom_matches_dist(document, dist_dir)
    _write_json_exclusive(output_path, document)
    print(
        f"CycloneDX 1.6 SBOM validated: {output_path.name} "
        f"({version}, {len(_file_inventory(dist_dir))} bundled files)."
    )
    return document


def verify_sbom_matches_dist(document: dict[str, Any], dist_dir: Path) -> None:
    expected = {
        relative: digest for relative, _, digest in _file_inventory(dist_dir)
    }
    observed: dict[str, str] = {}
    for component in document.get("components", []):
        if component.get("type") != "file":
            continue
        properties = {
            item.get("name"): item.get("value")
            for item in component.get("properties", [])
            if isinstance(item, dict)
        }
        relative = properties.get("ytsd:relative-path")
        hashes = component.get("hashes", [])
        sha = next(
            (item.get("content", "").upper() for item in hashes if item.get("alg") == "SHA-256"),
            None,
        )
        if not isinstance(relative, str) or not isinstance(sha, str) or relative in observed:
            raise ReleaseIntegrityError("SBOM contains a malformed or duplicate bundled file record.")
        observed[relative] = sha
    if observed != expected:
        raise ReleaseIntegrityError("SBOM file inventory or SHA-256 values do not match the PyInstaller bundle.")


def _verify_sbom_semantics(
    document: dict[str, Any],
    *,
    root: Path,
    policy_path: Path,
    source_commit: str,
    qt_version: str,
    python_version: str,
    inno_version: str,
    ffmpeg_version_line: str,
) -> None:
    project, app_version = _load_project(root)
    policy = _load_policy(policy_path)
    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        raise ReleaseIntegrityError("SBOM metadata is missing.")
    app = metadata.get("component")
    expected_app_ref = f"pkg:generic/{normalized_name(project['project']['name'])}@{app_version}"
    if not isinstance(app, dict) or any(
        app.get(key) != expected
        for key, expected in (
            ("bom-ref", expected_app_ref),
            ("name", project["project"]["name"]),
            ("version", app_version),
            ("type", "application"),
        )
    ):
        raise ReleaseIntegrityError("SBOM application identity does not match the project metadata.")

    properties = metadata.get("properties", [])
    if not isinstance(properties, list):
        raise ReleaseIntegrityError("SBOM metadata properties are malformed.")
    property_map: dict[str, str] = {}
    for item in properties:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("value"), str):
            raise ReleaseIntegrityError("SBOM metadata property entry is malformed.")
        if item["name"] in property_map:
            raise ReleaseIntegrityError(f"SBOM metadata property is duplicated: {item['name']}.")
        property_map[item["name"]] = item["value"]
    expected_properties = {
        "ytsd:source-commit": source_commit,
        "ytsd:source-tree-clean": "true",
        "ytsd:runtime-lock-sha256": sha256_file(root / "requirements/runtime.lock"),
        "ytsd:ffmpeg-archive-sha256-policy": policy["archive_sha256"],
        "ytsd:ffmpeg-executable-sha256-verified": policy["sha256"],
    }
    if any(property_map.get(key) != value for key, value in expected_properties.items()):
        raise ReleaseIntegrityError("SBOM source, runtime-lock, or FFmpeg policy metadata is inconsistent.")

    components = document.get("components")
    if not isinstance(components, list):
        raise ReleaseIntegrityError("SBOM component inventory is missing.")
    package_versions: dict[str, str] = {}
    frameworks: dict[str, dict[str, Any]] = {}
    component_refs: set[str] = set()
    for component in components:
        if not isinstance(component, dict):
            raise ReleaseIntegrityError("SBOM component entry is malformed.")
        ref = component.get("bom-ref")
        if not isinstance(ref, str) or not ref or ref in component_refs:
            raise ReleaseIntegrityError("SBOM component references are missing or duplicated.")
        component_refs.add(ref)
        component_type = component.get("type")
        name = normalized_name(str(component.get("name", "")))
        if component_type == "library":
            if name in package_versions:
                raise ReleaseIntegrityError(f"SBOM duplicates runtime package {name}.")
            version = str(component.get("version", ""))
            expected_purl = f"pkg:pypi/{name}@{version}"
            if component.get("purl") != expected_purl or ref != expected_purl:
                raise ReleaseIntegrityError(f"SBOM package URL identity is inconsistent for {name}.")
            package_versions[name] = version
        elif component_type == "framework":
            if name in frameworks:
                raise ReleaseIntegrityError(f"SBOM duplicates framework component {name}.")
            frameworks[name] = component

    locked_runtime = {
        name: data[0]
        for name, data in parse_lock(root / "requirements/runtime.lock").items()
        if name != "setuptools"
    }
    if package_versions != locked_runtime:
        raise ReleaseIntegrityError("SBOM runtime component versions do not exactly match runtime.lock.")
    if set(frameworks) != {"cpython", "qt", "ffmpeg"}:
        raise ReleaseIntegrityError("SBOM framework inventory contains missing or unexpected components.")
    pyside_version = locked_runtime.get("pyside6")
    if pyside_version is None or qt_version not in {pyside_version, f"{pyside_version}.0"}:
        raise ReleaseIntegrityError("SBOM Qt binary version does not match the pinned PySide6 version.")
    expected_frameworks = {
        "cpython": (python_version, f"pkg:generic/cpython@{python_version}"),
        "qt": (qt_version, f"pkg:generic/qt@{qt_version}"),
        "ffmpeg": (policy["version"], f"pkg:generic/ffmpeg@{policy['version']}"),
    }
    if set(frameworks) != set(expected_frameworks):
        raise ReleaseIntegrityError("SBOM framework inventory contains missing or unexpected components.")
    for name, (version, purl) in expected_frameworks.items():
        component = frameworks.get(name)
        if not isinstance(component, dict) or component.get("version") != version or component.get("purl") != purl:
            raise ReleaseIntegrityError(f"SBOM {name} framework identity is inconsistent.")

    ffmpeg_component = frameworks["ffmpeg"]
    ffmpeg_properties = {
        item.get("name"): item.get("value")
        for item in ffmpeg_component.get("properties", [])
        if isinstance(item, dict)
    }
    if any(
        ffmpeg_properties.get(key) != value
        for key, value in (
            ("ytsd:source-url", policy["source_url"]),
            ("ytsd:archive-sha256-policy", policy["archive_sha256"]),
            ("ytsd:archive-downloaded-and-rehashed-for-local-build", "false"),
            ("ytsd:executable-sha256-verified", "true"),
            ("ytsd:version-output", ffmpeg_version_line),
        )
    ):
        raise ReleaseIntegrityError("SBOM FFmpeg source or verification properties are inconsistent.")
    expected_ffmpeg_hash = policy["sha256"].lower()
    if not any(
        item.get("alg") == "SHA-256" and item.get("content", "").lower() == expected_ffmpeg_hash
        for item in ffmpeg_component.get("hashes", [])
        if isinstance(item, dict)
    ):
        raise ReleaseIntegrityError("SBOM FFmpeg component hash does not match the verified policy.")

    build_entries = parse_lock(root / "requirements/build.lock")
    runtime_names = set(locked_runtime)
    expected_tools = {
        name: version
        for name, (version, _) in build_entries.items()
        if name not in runtime_names or name == "setuptools"
    }
    expected_tools["pip"] = parse_lock(root / "requirements/bootstrap.lock")["pip"][0]
    expected_tools["inno-setup"] = inno_version
    tools = metadata.get("tools", {}).get("components", [])
    observed_tools: dict[str, str] = {}
    for tool in tools:
        if not isinstance(tool, dict):
            raise ReleaseIntegrityError("SBOM tool entry is malformed.")
        name = normalized_name(str(tool.get("name", "")).replace(" ", "-"))
        version = str(tool.get("version", ""))
        if name in observed_tools and observed_tools[name] != version:
            raise ReleaseIntegrityError(f"SBOM tool {name} has conflicting versions.")
        observed_tools[name] = version
    for name, version in expected_tools.items():
        if not version or observed_tools.get(name) != version:
            raise ReleaseIntegrityError(f"SBOM build tool {name} does not match its lock/version source.")

    expected_refs = {
        component.get("bom-ref")
        for component in components
        if component.get("type") == "library" and normalized_name(str(component.get("name", ""))) in _requirement_pins(project)
    }
    expected_refs.update(component["purl"] for component in frameworks.values())
    runtime_components = {
        normalized_name(str(component.get("name", ""))): component
        for component in components
        if component.get("type") == "library"
    }
    dependencies = document.get("dependencies", [])
    if not isinstance(dependencies, list):
        raise ReleaseIntegrityError("SBOM dependency graph is malformed.")
    expected_graph = _runtime_dependency_graph(
        runtime_components,
        app_ref=expected_app_ref,
        app_direct_refs=sorted(expected_refs),
        base_dependencies=[],
        base_ref_map={},
    )
    if dependencies != expected_graph:
        raise ReleaseIntegrityError("SBOM runtime dependency relationships are incomplete or inconsistent.")


def _schema_validate_provenance(document: dict[str, Any], root: Path) -> None:
    try:
        import jsonschema

        schema = json.loads((root / PROVENANCE_SCHEMA).read_text(encoding="utf-8"))
        jsonschema.validators.validator_for(schema).check_schema(schema)
        jsonschema.validate(instance=document, schema=schema)
    except ImportError as exc:
        raise ReleaseIntegrityError("Provenance schema validator is not installed from the build lock.") from exc
    except Exception as exc:
        raise ReleaseIntegrityError(f"Provenance schema validation failed: {exc}") from exc


def _input_hashes(root: Path, relative_paths: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in relative_paths:
        path = root / Path(relative)
        if not path.is_file():
            raise ReleaseIntegrityError(f"Provenance input is missing: {relative}.")
        result[Path(relative).as_posix()] = sha256_file(path)
    return result


def _provenance_input_paths() -> dict[str, tuple[str, ...]]:
    locks = tuple(f"requirements/{name}.lock" for name in LOCK_NAMES)
    manifests = tuple(
        f"requirements/{name}.in" for name in ("bootstrap", "base", "runtime", "dev", "build")
    )
    build_inputs = tuple(
        dict.fromkeys(
            (*BUILD_INPUTS, *locks, *manifests, "requirements.txt", "requirements-dev.txt", "requirements-build.txt")
        )
    )
    return {
        "dependency_locks_sha256": locks,
        "requirement_manifests_sha256": manifests,
        "build_inputs_sha256": build_inputs,
    }


def _verify_provenance_toolchain(document: dict[str, Any], root: Path) -> None:
    toolchain = document["toolchain"]
    build_environment = document["build_environment"]
    build_lock = parse_lock(root / "requirements/build.lock")
    bootstrap_lock = parse_lock(root / "requirements/bootstrap.lock")
    expected = {
        "pip": bootstrap_lock["pip"][0],
        "setuptools": build_lock["setuptools"][0],
        "pyinstaller": build_lock["pyinstaller"][0],
        "pyinstaller_hooks_contrib": build_lock["pyinstaller-hooks-contrib"][0],
        "cyclonedx_bom": build_lock["cyclonedx-bom"][0],
        "cyclonedx_python_lib": build_lock["cyclonedx-python-lib"][0],
    }
    if any(toolchain.get(key) != version for key, version in expected.items()):
        raise ReleaseIntegrityError("Provenance toolchain versions do not match the committed dependency locks.")
    if (
        build_environment.get("python") != toolchain.get("python")
        or build_environment.get("python_implementation") != toolchain.get("python_implementation")
        or toolchain.get("python_implementation") != "CPython"
    ):
        raise ReleaseIntegrityError("Provenance build environment and toolchain identities disagree.")
    pyside_version = parse_lock(root / "requirements/runtime.lock").get("pyside6", (None,))[0]
    if pyside_version is None or toolchain.get("qt") not in {pyside_version, f"{pyside_version}.0"}:
        raise ReleaseIntegrityError("Provenance Qt version does not match the pinned PySide6 version.")


def _tool_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError as exc:
        raise ReleaseIntegrityError(f"Build tool {distribution} is not installed from the locked build environment.") from exc


def build_provenance_document(
    *,
    root: Path,
    installer_path: Path,
    sbom_path: Path,
    dist_dir: Path,
    ffmpeg_path: Path,
    policy_path: Path,
    installer_filename: str,
    sbom_filename: str,
    inno_version: str,
    qt_version: str,
    signing: dict[str, str],
) -> dict[str, Any]:
    verify_build_environment()
    required_signing = {
        "application_exe_status": "Valid",
        "installer_status": "Valid",
        "signer_subject": SIGNER_SUBJECT,
    }
    if any(signing.get(key) != value for key, value in required_signing.items()):
        raise ReleaseIntegrityError("Both release artifacts must have a valid signature from the expected signer.")
    if not re.fullmatch(r"[A-Fa-f0-9]{40}", signing.get("certificate_thumbprint", "")):
        raise ReleaseIntegrityError("Signing certificate thumbprint is missing or invalid.")
    source = verify_source_tree(root)
    verify_dependency_locks(root)
    project, version = _load_project(root)
    policy, ffmpeg_version_line = verify_ffmpeg(ffmpeg_path, policy_path)
    if not installer_path.is_file() or not sbom_path.is_file():
        raise ReleaseIntegrityError("Installer and SBOM must both exist before provenance is recorded.")
    try:
        sbom_document = json.loads(sbom_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseIntegrityError("SBOM is missing or malformed before provenance generation.") from exc
    _cyclonedx_validate(sbom_document)
    verify_sbom_matches_dist(sbom_document, dist_dir)
    _verify_sbom_semantics(
        sbom_document,
        root=root,
        policy_path=policy_path,
        source_commit=source["commit"],
        qt_version=qt_version,
        python_version=platform.python_version(),
        inno_version=inno_version,
        ffmpeg_version_line=ffmpeg_version_line,
    )

    commit_epoch = int(_git(root, "show", "-s", "--format=%ct", source["commit"]))
    input_paths = _provenance_input_paths()
    build_lock_entries = parse_lock(root / "requirements/build.lock")
    toolchain = {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "pip": _tool_version("pip"),
        "setuptools": _tool_version("setuptools"),
        "pyinstaller": _tool_version("pyinstaller"),
        "pyinstaller_hooks_contrib": _tool_version("pyinstaller-hooks-contrib"),
        "cyclonedx_bom": _tool_version("cyclonedx-bom"),
        "cyclonedx_python_lib": _tool_version("cyclonedx-python-lib"),
        "inno_setup": inno_version,
        "qt": qt_version,
    }
    for package, key in (
        ("pyinstaller", "pyinstaller"),
        ("pyinstaller-hooks-contrib", "pyinstaller_hooks_contrib"),
        ("cyclonedx-bom", "cyclonedx_bom"),
        ("cyclonedx-python-lib", "cyclonedx_python_lib"),
        ("setuptools", "setuptools"),
    ):
        if build_lock_entries.get(package, (None,))[0] != toolchain[key]:
            raise ReleaseIntegrityError(f"Installed build tool {package} does not match its hash lock.")
    bootstrap_pip = parse_lock(root / "requirements/bootstrap.lock").get("pip", (None,))[0]
    if bootstrap_pip != toolchain["pip"]:
        raise ReleaseIntegrityError("Installed pip does not match the bootstrap lock.")

    document = {
        "$schema": PROVENANCE_SCHEMA.as_posix(),
        "schema_version": 1,
        "record_type": "ytsd-local-release-build-integrity-record",
        "unsigned": True,
        "application": {
            "name": str(project["project"]["name"]),
            "version": version,
        },
        "source": {
            "repository": REPOSITORY,
            "commit": source["commit"],
            "tree": source["tree"],
            "clean": True,
            "commit_time_utc": datetime.fromtimestamp(commit_epoch, timezone.utc).isoformat(
                timespec="seconds"
            ).replace("+00:00", "Z"),
        },
        "build_environment": {
            "operating_system": platform.system(),
            "operating_system_version": platform.version(),
            "architecture": platform.machine(),
            "python": toolchain["python"],
            "python_implementation": toolchain["python_implementation"],
        },
        "toolchain": toolchain,
        "inputs": {
            name: _input_hashes(root, paths) for name, paths in input_paths.items()
        },
        "ffmpeg": {
            "version": policy["version"],
            "version_output": ffmpeg_version_line,
            "source_url": policy["source_url"],
            "archive_sha256_policy": policy["archive_sha256"],
            "archive_downloaded_and_rehashed_for_this_local_build": False,
            "executable_sha256": sha256_file(ffmpeg_path),
            "executable_sha256_verified": True,
        },
        "artifacts": {
            "bundle": {
                "file_count": len(_file_inventory(dist_dir)),
                "inventory_sha256": bundle_inventory_sha256(dist_dir),
            },
            "installer": {
                "filename": installer_filename,
                "size_bytes": installer_path.stat().st_size,
                "sha256": sha256_file(installer_path),
            },
            "sbom": {
                "filename": sbom_filename,
                "format": "CycloneDX",
                "spec_version": "1.6",
                "sha256": sha256_file(sbom_path),
            },
        },
        "signing": {
            "method": "Authenticode SHA-256",
            "application_exe_status": signing["application_exe_status"],
            "installer_status": signing["installer_status"],
            "signer_subject": signing["signer_subject"],
            "certificate_thumbprint": signing["certificate_thumbprint"].upper(),
            "trust_note": "Self-signed test certificate; Valid records signature integrity, not broad Windows trust.",
        },
    }
    _schema_validate_provenance(document, root)
    return document


def verify_provenance_artifacts(
    document: dict[str, Any],
    *,
    root: Path,
    installer_path: Path,
    sbom_path: Path,
    dist_dir: Path,
    ffmpeg_path: Path,
    policy_path: Path,
    check_source: bool = True,
) -> None:
    _schema_validate_provenance(document, root)
    _verify_provenance_toolchain(document, root)
    installer = document["artifacts"]["installer"]
    sbom = document["artifacts"]["sbom"]
    if installer_path.name != installer["filename"] or installer_path.stat().st_size != installer["size_bytes"]:
        raise ReleaseIntegrityError("Installer filename or size differs from the provenance record.")
    if sha256_file(installer_path) != installer["sha256"]:
        raise ReleaseIntegrityError("Installer SHA-256 differs from the provenance record.")
    if sbom_path.name != sbom["filename"] or sha256_file(sbom_path) != sbom["sha256"]:
        raise ReleaseIntegrityError("SBOM filename or SHA-256 differs from the provenance record.")
    policy, version_line = verify_ffmpeg(ffmpeg_path, policy_path)
    try:
        bom = json.loads(sbom_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseIntegrityError("SBOM is missing or malformed during provenance verification.") from exc
    _cyclonedx_validate(bom)
    verify_sbom_matches_dist(bom, dist_dir)
    bundle = document["artifacts"]["bundle"]
    if (
        bundle["file_count"] != len(_file_inventory(dist_dir))
        or bundle["inventory_sha256"] != bundle_inventory_sha256(dist_dir)
    ):
        raise ReleaseIntegrityError("Staged bundle inventory differs from the provenance record.")
    _verify_sbom_semantics(
        bom,
        root=root,
        policy_path=policy_path,
        source_commit=document["source"]["commit"],
        qt_version=document["toolchain"]["qt"],
        python_version=document["toolchain"]["python"],
        inno_version=document["toolchain"]["inno_setup"],
        ffmpeg_version_line=version_line,
    )
    ffmpeg = document["ffmpeg"]
    if (
        ffmpeg["version"] != policy["version"]
        or ffmpeg["source_url"] != policy["source_url"]
        or ffmpeg["archive_sha256_policy"] != policy["archive_sha256"]
        or ffmpeg["executable_sha256"] != sha256_file(ffmpeg_path)
        or ffmpeg["version_output"] != version_line
        or ffmpeg["executable_sha256_verified"] is not True
    ):
        raise ReleaseIntegrityError("FFmpeg facts differ from the verified manifest and executable.")
    expected_inputs = {
        name: _input_hashes(root, paths) for name, paths in _provenance_input_paths().items()
    }
    if document["inputs"] != expected_inputs:
        raise ReleaseIntegrityError("Provenance dependency/build input inventory or hashes differ from the source tree.")
    if check_source:
        source = verify_source_tree(root)
        if source["commit"] != document["source"]["commit"] or source["tree"] != document["source"]["tree"]:
            raise ReleaseIntegrityError("Current source commit/tree differs from the provenance record.")
    _, current_version = _load_project(root)
    if current_version != document["application"]["version"]:
        raise ReleaseIntegrityError("Current application version differs from the provenance record.")
    if not document["source"]["clean"] or not document["unsigned"]:
        raise ReleaseIntegrityError("Provenance source cleanliness or unsigned-record status is invalid.")


def _write_json_exclusive(path: Path, document: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ReleaseIntegrityError(f"Refusing to overwrite existing integrity sidecar: {path.name}.")
    payload = (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        if path.exists():
            raise ReleaseIntegrityError(f"Refusing to overwrite existing integrity sidecar: {path.name}.")
        os.rename(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _read_signatures(args: argparse.Namespace) -> dict[str, str]:
    return {
        "application_exe_status": args.application_exe_status,
        "installer_status": args.installer_status,
        "signer_subject": args.signer_subject,
        "certificate_thumbprint": args.certificate_thumbprint,
    }


def _run_self_test(root: Path) -> None:
    source = verify_source_tree(root)
    commit_epoch = int(_git(root, "show", "-s", "--format=%ct", source["commit"]))
    with tempfile.TemporaryDirectory(prefix="ytsd-integrity-selftest-") as temp_name:
        temp_root = Path(temp_name)
        dist = temp_root / "dist"
        ffmpeg = dist / "_internal" / "ffmpeg" / "ffmpeg.exe"
        qt_core = dist / "_internal" / "PySide6" / "Qt6Core.dll"
        app_exe = dist / "YouTubeSimpleDownloader.exe"
        ffmpeg.parent.mkdir(parents=True)
        qt_core.parent.mkdir(parents=True)
        app_exe.write_bytes(b"fixture-app-exe")
        ffmpeg.write_bytes(b"fixture-ffmpeg")
        qt_core.write_bytes(b"fixture-qt-core")
        trusted_policy = _load_policy(root / "security/artifact_hashes.json")
        fake_policy = {
            "schema_version": 1,
            "artifacts": {
                "ffmpeg_windows_x64": {
                    "filename": "ffmpeg.exe",
                    "version": trusted_policy["version"],
                    "source_url": trusted_policy["source_url"],
                    "archive_sha256": trusted_policy["archive_sha256"],
                    "sha256": sha256_file(ffmpeg),
                }
            },
        }
        fake_policy_path = temp_root / "artifact_hashes.json"
        fake_policy_path.write_text(json.dumps(fake_policy), encoding="utf-8")
        fake_version_line = "ffmpeg version 8.1.2-essentials_build-www.gyan.dev fixture"

        # Use a small process-free fixture for structural and tamper checks; real builds
        # additionally execute the verified FFmpeg before writing the SBOM.
        original_verify_ffmpeg = verify_ffmpeg
        try:
            def fixture_verify_ffmpeg(path: Path, policy_path: Path) -> tuple[dict[str, str], str]:
                policy = _load_policy(policy_path)
                if sha256_file(path) != policy["sha256"]:
                    raise ReleaseIntegrityError("FFmpeg executable SHA-256 mismatch in self-test.")
                return policy, fake_version_line

            globals()["verify_ffmpeg"] = fixture_verify_ffmpeg
            base = _generate_base_bom(root, temp_root / "base.json", commit_epoch)
            base_template = json.loads(json.dumps(base))
            sbom = build_sbom_document(
                json.loads(json.dumps(base_template)),
                root=root,
                dist_dir=dist,
                ffmpeg_path=ffmpeg,
                policy_path=fake_policy_path,
                qt_version="6.10.1.0",
                commit=source["commit"],
                commit_epoch=commit_epoch,
                inno_version="6.5.4",
            )
            verify_sbom_matches_dist(sbom, dist)
            before = json.dumps(sbom, sort_keys=True, separators=(",", ":"))
            again = build_sbom_document(
                json.loads(json.dumps(base)),
                root=root,
                dist_dir=dist,
                ffmpeg_path=ffmpeg,
                policy_path=fake_policy_path,
                qt_version="6.10.1.0",
                commit=source["commit"],
                commit_epoch=commit_epoch,
                inno_version="6.5.4",
            )
            if before != json.dumps(again, sort_keys=True, separators=(",", ":")):
                raise ReleaseIntegrityError("SBOM fixture generation was not deterministic.")
            qt_core.write_bytes(b"tampered-qt-core")
            try:
                verify_sbom_matches_dist(sbom, dist)
            except ReleaseIntegrityError:
                pass
            else:
                raise ReleaseIntegrityError("SBOM tamper check did not reject a changed bundled file.")
            qt_core.write_bytes(b"fixture-qt-core")

            provenance_installer = temp_root / "fixture-installer.exe"
            provenance_installer.write_bytes(b"fixture-installer")
            provenance_sbom = temp_root / "fixture.sbom.cdx.json"
            _write_json_exclusive(provenance_sbom, sbom)
            provenance = build_provenance_document(
                root=root,
                installer_path=provenance_installer,
                sbom_path=provenance_sbom,
                dist_dir=dist,
                ffmpeg_path=ffmpeg,
                policy_path=fake_policy_path,
                installer_filename=provenance_installer.name,
                sbom_filename=provenance_sbom.name,
                inno_version="6.5.4",
                qt_version="6.10.1.0",
                signing={
                    "application_exe_status": "Valid",
                    "installer_status": "Valid",
                    "signer_subject": SIGNER_SUBJECT,
                    "certificate_thumbprint": "A" * 40,
                },
            )
            verify_provenance_artifacts(
                provenance,
                root=root,
                installer_path=provenance_installer,
                sbom_path=provenance_sbom,
                dist_dir=dist,
                ffmpeg_path=ffmpeg,
                policy_path=fake_policy_path,
                check_source=True,
            )
            provenance_installer.write_bytes(b"tampered-installer")
            try:
                verify_provenance_artifacts(
                    provenance,
                    root=root,
                    installer_path=provenance_installer,
                    sbom_path=provenance_sbom,
                    dist_dir=dist,
                    ffmpeg_path=ffmpeg,
                    policy_path=fake_policy_path,
                    check_source=True,
                )
            except ReleaseIntegrityError:
                pass
            else:
                raise ReleaseIntegrityError("Provenance tamper check did not reject a changed installer.")
        finally:
            globals()["verify_ffmpeg"] = original_verify_ffmpeg
    print("Release integrity self-test passed: CycloneDX schema, determinism, and tamper rejection.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and verify release integrity sidecars.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight_parser = subparsers.add_parser("preflight", help="Require clean source and consistent version/locks.")
    preflight_parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)

    sbom_parser = subparsers.add_parser("generate-sbom", help="Generate a validated CycloneDX 1.6 bundle SBOM.")
    sbom_parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    sbom_parser.add_argument("--dist-dir", type=Path, required=True)
    sbom_parser.add_argument("--ffmpeg", type=Path, required=True)
    sbom_parser.add_argument("--output", type=Path, required=True)
    sbom_parser.add_argument("--qt-version", required=True)
    sbom_parser.add_argument("--inno-version", required=True)

    provenance_parser = subparsers.add_parser("write-provenance", help="Record and validate local installer provenance.")
    provenance_parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    provenance_parser.add_argument("--installer", type=Path, required=True)
    provenance_parser.add_argument("--sbom", type=Path, required=True)
    provenance_parser.add_argument("--dist-dir", type=Path, required=True)
    provenance_parser.add_argument("--ffmpeg", type=Path, required=True)
    provenance_parser.add_argument("--output", type=Path, required=True)
    provenance_parser.add_argument("--installer-filename", required=True)
    provenance_parser.add_argument("--sbom-filename", required=True)
    provenance_parser.add_argument("--qt-version", required=True)
    provenance_parser.add_argument("--inno-version", required=True)
    provenance_parser.add_argument("--application-exe-status", required=True)
    provenance_parser.add_argument("--installer-status", required=True)
    provenance_parser.add_argument("--signer-subject", required=True)
    provenance_parser.add_argument("--certificate-thumbprint", required=True)

    verify_parser = subparsers.add_parser("verify", help="Re-verify SBOM and provenance artifact hashes.")
    verify_parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    verify_parser.add_argument("--installer", type=Path, required=True)
    verify_parser.add_argument("--sbom", type=Path, required=True)
    verify_parser.add_argument("--provenance", type=Path, required=True)
    verify_parser.add_argument("--ffmpeg", type=Path, required=True)
    verify_parser.add_argument("--dist-dir", type=Path, required=True)

    self_test_parser = subparsers.add_parser("self-test", help="Run schema and tamper checks with generated fixture bytes.")
    self_test_parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)

    inventory_parser = subparsers.add_parser(
        "inventory-hash", help="Print a deterministic digest of a PyInstaller payload tree."
    )
    inventory_parser.add_argument("--dist-dir", type=Path, required=True)

    args = parser.parse_args()
    try:
        root = getattr(args, "project_root", PROJECT_ROOT).resolve()
        if args.command == "preflight":
            verify_build_environment()
            source = verify_source_tree(root)
            verify_dependency_locks(root)
            _, version = _load_project(root)
            print(f"Release source preflight passed: version={version}, commit={source['commit']}.")
        elif args.command == "generate-sbom":
            generate_sbom(
                root=root,
                dist_dir=args.dist_dir.resolve(),
                ffmpeg_path=args.ffmpeg.resolve(),
                output_path=args.output.resolve(),
                qt_version=args.qt_version,
                inno_version=args.inno_version,
            )
        elif args.command == "write-provenance":
            document = build_provenance_document(
                root=root,
                installer_path=args.installer.resolve(),
                sbom_path=args.sbom.resolve(),
                dist_dir=args.dist_dir.resolve(),
                ffmpeg_path=args.ffmpeg.resolve(),
                policy_path=root / "security/artifact_hashes.json",
                installer_filename=args.installer_filename,
                sbom_filename=args.sbom_filename,
                inno_version=args.inno_version,
                qt_version=args.qt_version,
                signing=_read_signatures(args),
            )
            _write_json_exclusive(args.output, document)
            verify_provenance_artifacts(
                document,
                root=root,
                installer_path=args.installer.resolve(),
                sbom_path=args.sbom.resolve(),
                dist_dir=args.dist_dir.resolve(),
                ffmpeg_path=args.ffmpeg.resolve(),
                policy_path=root / "security/artifact_hashes.json",
            )
            print(f"Local build provenance validated: {args.output.name}.")
        elif args.command == "verify":
            document = json.loads(args.provenance.read_text(encoding="utf-8"))
            bom = json.loads(args.sbom.read_text(encoding="utf-8"))
            _cyclonedx_validate(bom)
            verify_sbom_matches_dist(bom, args.dist_dir.resolve())
            verify_provenance_artifacts(
                document,
                root=root,
                installer_path=args.installer.resolve(),
                sbom_path=args.sbom.resolve(),
                dist_dir=args.dist_dir.resolve(),
                ffmpeg_path=args.ffmpeg.resolve(),
                policy_path=root / "security/artifact_hashes.json",
            )
            print("Release integrity sidecars and artifact hashes verified.")
        elif args.command == "self-test":
            verify_source_tree(root)
            verify_dependency_locks(root)
            _run_self_test(root)
        elif args.command == "inventory-hash":
            print(f"bundle-inventory-sha256={bundle_inventory_sha256(args.dist_dir.resolve())}")
    except (OSError, KeyError, ValueError, subprocess.TimeoutExpired, ReleaseIntegrityError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
