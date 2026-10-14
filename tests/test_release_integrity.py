from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts import release_integrity as integrity
from scripts.check_dependency_locks import parse_lock


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_inventory_hash_cli_does_not_require_project_root(tmp_path, monkeypatch, capsys) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "app.exe").write_bytes(b"fixture")
    monkeypatch.setattr(
        sys,
        "argv",
        ["release_integrity.py", "inventory-hash", "--dist-dir", str(dist)],
    )

    assert integrity.main() == 0
    assert capsys.readouterr().out.strip() == (
        f"bundle-inventory-sha256={integrity.bundle_inventory_sha256(dist)}"
    )


def test_sbom_generator_uses_locked_python_module_cli(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(integrity.sys, "executable", r"C:\Python312\python.exe")
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        output_path = Path(command[command.index("--output-file") + 1])
        output_path.write_text('{"bomFormat":"CycloneDX"}', encoding="utf-8")
        return integrity.subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(integrity.subprocess, "run", fake_run)
    result = integrity._generate_base_bom(PROJECT_ROOT, tmp_path / "base.json", 123)

    assert result == {"bomFormat": "CycloneDX"}
    assert calls[0][:3] == [r"C:\Python312\python.exe", "-m", "cyclonedx_py"]


def _write_fake_ffmpeg_policy(tmp_path: Path, ffmpeg_path: Path) -> Path:
    trusted = integrity._load_policy(PROJECT_ROOT / "security/artifact_hashes.json")
    policy = {
        "schema_version": 1,
        "artifacts": {
            "ffmpeg_windows_x64": {
                "filename": "ffmpeg.exe",
                "version": trusted["version"],
                "source_url": trusted["source_url"],
                "archive_sha256": trusted["archive_sha256"],
                "sha256": integrity.sha256_file(ffmpeg_path),
            }
        },
    }
    path = tmp_path / "artifact_hashes.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    return path


def _base_bom() -> dict[str, object]:
    runtime_entries = parse_lock(PROJECT_ROOT / "requirements/runtime.lock")
    components = []
    for name, (version, _) in sorted(runtime_entries.items()):
        if name == "setuptools":
            continue
        purl = f"pkg:pypi/{name}@{version}"
        components.append(
            {
                "bom-ref": purl,
                "type": "library",
                "name": name,
                "version": version,
                "purl": purl,
            }
        )
    return {
        "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": "urn:uuid:00000000-0000-4000-8000-000000000001",
        "version": 1,
        "metadata": {
            "component": {
                "bom-ref": "root-component",
                "type": "application",
                "name": "youtube-simple-downloader",
                "version": "0.11.0",
            },
            "tools": {"components": []},
        },
        "components": components,
        "dependencies": [],
    }


def _fixture_bundle(tmp_path: Path) -> tuple[Path, Path, Path]:
    dist = tmp_path / "dist"
    ffmpeg = dist / "_internal" / "ffmpeg" / "ffmpeg.exe"
    qt_core = dist / "_internal" / "PySide6" / "Qt6Core.dll"
    app_exe = dist / "YouTubeSimpleDownloader.exe"
    ffmpeg.parent.mkdir(parents=True)
    qt_core.parent.mkdir(parents=True)
    app_exe.write_bytes(b"fixture app")
    ffmpeg.write_bytes(b"fixture ffmpeg")
    qt_core.write_bytes(b"fixture Qt")
    return dist, ffmpeg, qt_core


def test_sbom_lists_runtime_packages_and_hashes_every_bundled_file(tmp_path, monkeypatch) -> None:
    dist, ffmpeg, qt_core = _fixture_bundle(tmp_path)
    policy_path = _write_fake_ffmpeg_policy(tmp_path, ffmpeg)
    policy = integrity._load_policy(policy_path)
    monkeypatch.setattr(
        integrity,
        "verify_ffmpeg",
        lambda _path, _policy: (policy, "ffmpeg version 8.1.2-essentials_build-www.gyan.dev fixture"),
    )
    monkeypatch.setattr(integrity, "_cyclonedx_validate", lambda _doc: None)

    source = integrity._git(PROJECT_ROOT, "rev-parse", "HEAD")
    epoch = int(integrity._git(PROJECT_ROOT, "show", "-s", "--format=%ct", source))
    base = _base_bom()
    for index, component in enumerate(base["components"], start=1):
        component["bom-ref"] = f"requirements-L{index}"
    first = integrity.build_sbom_document(
        base,
        root=PROJECT_ROOT,
        dist_dir=dist,
        ffmpeg_path=ffmpeg,
        policy_path=policy_path,
        qt_version="6.10.1.0",
        commit=source,
        commit_epoch=epoch,
        inno_version="6.5.4",
    )
    second = integrity.build_sbom_document(
        _base_bom(),
        root=PROJECT_ROOT,
        dist_dir=dist,
        ffmpeg_path=ffmpeg,
        policy_path=policy_path,
        qt_version="6.10.1.0",
        commit=source,
        commit_epoch=epoch,
        inno_version="6.5.4",
    )

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["metadata"]["component"]["version"] == "0.11.0"
    assert first["metadata"]["timestamp"].endswith("Z")
    packages = {
        integrity.normalized_name(component["name"]): component["version"]
        for component in first["components"]
        if component["type"] == "library"
    }
    assert packages["yt-dlp"] == "2026.8.19"
    assert "setuptools" not in packages
    assert all(
        component["bom-ref"] == component["purl"]
        for component in first["components"]
        if component["type"] == "library"
    )
    dependency_graph = {
        item["ref"]: set(item.get("dependsOn", []))
        for item in first["dependencies"]
    }
    assert "pkg:pypi/pyside6-essentials@6.10.1" in dependency_graph[
        "pkg:pypi/pyside6@6.10.1"
    ]
    assert "pkg:generic/ffmpeg@8.1.2" in dependency_graph[
        "pkg:generic/youtube-simple-downloader@0.11.0"
    ]
    file_components = [item for item in first["components"] if item["type"] == "file"]
    paths = {
        next(prop["value"] for prop in item["properties"] if prop["name"] == "ytsd:relative-path")
        for item in file_components
    }
    assert paths == {
        "YouTubeSimpleDownloader.exe",
        "_internal/ffmpeg/ffmpeg.exe",
        "_internal/PySide6/Qt6Core.dll",
    }
    qt_rel = qt_core.relative_to(dist).as_posix()
    assert any(prop["value"] == qt_rel for item in file_components for prop in item["properties"])
    integrity.verify_sbom_matches_dist(first, dist)
    assert str(tmp_path) not in json.dumps(first)

    changed_purl = json.loads(json.dumps(first))
    yt_dlp = next(item for item in changed_purl["components"] if item.get("name") == "yt-dlp")
    yt_dlp["purl"] = "pkg:pypi/yt-dlp@0.0.0"
    with pytest.raises(integrity.ReleaseIntegrityError, match="package URL identity"):
        integrity._verify_sbom_semantics(
            changed_purl,
            root=PROJECT_ROOT,
            policy_path=policy_path,
            source_commit=source,
            qt_version="6.10.1.0",
            python_version=next(
                item["version"] for item in first["components"] if item.get("name") == "CPython"
            ),
            inno_version="6.5.4",
            ffmpeg_version_line="ffmpeg version 8.1.2-essentials_build-www.gyan.dev fixture",
        )

    changed_graph = json.loads(json.dumps(first))
    pyside_ref = "pkg:pypi/pyside6@6.10.1"
    pyside_dependencies = next(
        item for item in changed_graph["dependencies"] if item["ref"] == pyside_ref
    )
    pyside_dependencies["dependsOn"].remove("pkg:pypi/pyside6-essentials@6.10.1")
    with pytest.raises(integrity.ReleaseIntegrityError, match="relationships are incomplete"):
        integrity._verify_sbom_semantics(
            changed_graph,
            root=PROJECT_ROOT,
            policy_path=policy_path,
            source_commit=source,
            qt_version="6.10.1.0",
            python_version=next(
                item["version"] for item in first["components"] if item.get("name") == "CPython"
            ),
            inno_version="6.5.4",
            ffmpeg_version_line="ffmpeg version 8.1.2-essentials_build-www.gyan.dev fixture",
        )


def test_sbom_file_inventory_rejects_tampered_payload(tmp_path, monkeypatch) -> None:
    dist, ffmpeg, qt_core = _fixture_bundle(tmp_path)
    inventory_before = integrity.bundle_inventory_sha256(dist)
    policy_path = _write_fake_ffmpeg_policy(tmp_path, ffmpeg)
    policy = integrity._load_policy(policy_path)
    monkeypatch.setattr(
        integrity,
        "verify_ffmpeg",
        lambda _path, _policy: (policy, "ffmpeg version 8.1.2-essentials_build-www.gyan.dev fixture"),
    )
    monkeypatch.setattr(integrity, "_cyclonedx_validate", lambda _doc: None)
    source = integrity._git(PROJECT_ROOT, "rev-parse", "HEAD")
    epoch = int(integrity._git(PROJECT_ROOT, "show", "-s", "--format=%ct", source))
    document = integrity.build_sbom_document(
        _base_bom(),
        root=PROJECT_ROOT,
        dist_dir=dist,
        ffmpeg_path=ffmpeg,
        policy_path=policy_path,
        qt_version="6.10.1.0",
        commit=source,
        commit_epoch=epoch,
        inno_version="6.5.4",
    )
    qt_core.write_bytes(b"tampered Qt")
    assert integrity.bundle_inventory_sha256(dist) != inventory_before

    with pytest.raises(integrity.ReleaseIntegrityError, match="do not match"):
        integrity.verify_sbom_matches_dist(document, dist)


def test_sbom_rejects_wrong_ffmpeg_executable_digest(tmp_path, monkeypatch) -> None:
    dist, ffmpeg, _ = _fixture_bundle(tmp_path)
    policy_path = _write_fake_ffmpeg_policy(tmp_path, ffmpeg)
    policy = integrity._load_policy(policy_path)
    policy["sha256"] = "0" * 64
    monkeypatch.setattr(
        integrity,
        "verify_ffmpeg",
        lambda _path, _policy: (policy, "ffmpeg version 8.1.2-essentials_build-www.gyan.dev fixture"),
    )
    monkeypatch.setattr(integrity, "_cyclonedx_validate", lambda _doc: None)
    source = integrity._git(PROJECT_ROOT, "rev-parse", "HEAD")
    epoch = int(integrity._git(PROJECT_ROOT, "show", "-s", "--format=%ct", source))

    with pytest.raises(integrity.ReleaseIntegrityError, match="FFmpeg bundle inventory"):
        integrity.build_sbom_document(
            _base_bom(),
            root=PROJECT_ROOT,
            dist_dir=dist,
            ffmpeg_path=ffmpeg,
            policy_path=policy_path,
            qt_version="6.10.1.0",
            commit=source,
            commit_epoch=epoch,
            inno_version="6.5.4",
        )


def test_provenance_rejects_tampered_installer(tmp_path, monkeypatch) -> None:
    dist, ffmpeg, _ = _fixture_bundle(tmp_path)
    policy_path = _write_fake_ffmpeg_policy(tmp_path, ffmpeg)
    policy = integrity._load_policy(policy_path)
    version_line = "ffmpeg version 8.1.2-essentials_build-www.gyan.dev fixture"
    monkeypatch.setattr(integrity, "verify_ffmpeg", lambda _path, _policy: (policy, version_line))
    source = integrity._git(PROJECT_ROOT, "rev-parse", "HEAD")
    tree = integrity._git(PROJECT_ROOT, "rev-parse", "HEAD^{tree}")
    monkeypatch.setattr(
        integrity,
        "verify_source_tree",
        lambda _root: {"commit": source, "tree": tree, "clean": "true"},
    )
    monkeypatch.setattr(integrity, "_cyclonedx_validate", lambda _doc: None)
    monkeypatch.setattr(integrity, "_schema_validate_provenance", lambda _doc, _root: None)
    locked_tool_versions = {
        name: version for name, (version, _) in parse_lock(PROJECT_ROOT / "requirements/build.lock").items()
    }
    locked_tool_versions["pip"] = parse_lock(PROJECT_ROOT / "requirements/bootstrap.lock")["pip"][0]
    monkeypatch.setattr(
        integrity,
        "_tool_version",
        lambda distribution: locked_tool_versions[integrity.normalized_name(distribution)],
    )

    installer = tmp_path / "candidate.exe"
    sbom = tmp_path / "candidate.sbom.cdx.json"
    installer.write_bytes(b"signed candidate")
    epoch = int(integrity._git(PROJECT_ROOT, "show", "-s", "--format=%ct", source))
    bom = integrity.build_sbom_document(
        _base_bom(),
        root=PROJECT_ROOT,
        dist_dir=dist,
        ffmpeg_path=ffmpeg,
        policy_path=policy_path,
        qt_version="6.10.1.0",
        commit=source,
        commit_epoch=epoch,
        inno_version="6.5.4",
    )
    sbom.write_text(json.dumps(bom), encoding="utf-8")
    record = integrity.build_provenance_document(
        root=PROJECT_ROOT,
        installer_path=installer,
        sbom_path=sbom,
        dist_dir=dist,
        ffmpeg_path=ffmpeg,
        policy_path=policy_path,
        installer_filename=installer.name,
        sbom_filename=sbom.name,
        inno_version="6.5.4",
        qt_version="6.10.1.0",
        signing={
            "application_exe_status": "Valid",
            "installer_status": "Valid",
            "signer_subject": integrity.SIGNER_SUBJECT,
            "certificate_thumbprint": "A" * 40,
        },
    )
    assert record["toolchain"]["inno_setup"] == "6.5.4"
    verify = lambda: integrity.verify_provenance_artifacts(
        record,
        root=PROJECT_ROOT,
        installer_path=installer,
        sbom_path=sbom,
        dist_dir=dist,
        ffmpeg_path=ffmpeg,
        policy_path=policy_path,
        check_source=False,
    )
    original_pip = record["toolchain"]["pip"]
    record["toolchain"]["pip"] = "0.0.0"
    with pytest.raises(integrity.ReleaseIntegrityError, match="toolchain versions"):
        verify()
    record["toolchain"]["pip"] = original_pip
    verify()
    original_bundle_hash = record["artifacts"]["bundle"]["inventory_sha256"]
    record["artifacts"]["bundle"]["inventory_sha256"] = "0" * 64
    with pytest.raises(integrity.ReleaseIntegrityError, match="bundle inventory"):
        verify()
    record["artifacts"]["bundle"]["inventory_sha256"] = original_bundle_hash
    verify()
    omitted_lock = record["inputs"]["dependency_locks_sha256"].pop("requirements/dev.lock")
    with pytest.raises(integrity.ReleaseIntegrityError, match="input inventory or hashes"):
        verify()
    record["inputs"]["dependency_locks_sha256"]["requirements/dev.lock"] = omitted_lock
    installer.write_bytes(b"X" * len(b"signed candidate"))

    with pytest.raises(integrity.ReleaseIntegrityError, match="SHA-256"):
        verify()


def test_provenance_refuses_non_valid_signature_status() -> None:
    assert integrity.SIGNER_SUBJECT == "CN=Jason YouTube Simple Downloader Test Signing"
    with pytest.raises(integrity.ReleaseIntegrityError, match="valid signature"):
        integrity.build_provenance_document(
            root=PROJECT_ROOT,
            installer_path=PROJECT_ROOT / "missing.exe",
            sbom_path=PROJECT_ROOT / "missing.sbom.cdx.json",
            dist_dir=PROJECT_ROOT / "missing-dist",
            ffmpeg_path=PROJECT_ROOT / "missing-ffmpeg.exe",
            policy_path=PROJECT_ROOT / "security/artifact_hashes.json",
            installer_filename="candidate.exe",
            sbom_filename="candidate.sbom.cdx.json",
            inno_version="6.5.4",
            qt_version="6.10.1",
            signing={
                "application_exe_status": "NotSigned",
                "installer_status": "Valid",
                "signer_subject": integrity.SIGNER_SUBJECT,
                "certificate_thumbprint": "A" * 40,
            },
        )


def test_build_script_refuses_existing_outputs_instead_of_deleting_them() -> None:
    content = (PROJECT_ROOT / "build_exe.bat").read_text(encoding="utf-8")
    assert 'set "PROJECT_ROOT=%PROJECT_DIR:~0,-1%"' in content
    assert '--project-root "%PROJECT_ROOT%"' in content
    assert ".release-venv*/" in (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "Refusing to overwrite existing build output" in content
    assert "Refusing to overwrite existing dist output" in content
    assert "Refusing to reuse existing release build environment" in content
    assert 'C:\\Windows\\py.exe -3.12 -m venv .release-venv' in content
    assert '".release-venv\\Scripts\\python.exe" -m pip install --require-hashes -r requirements-build.txt' in content
    assert '".venv\\Scripts\\python.exe"' not in content
    assert "rmdir /s /q" not in content.lower()


def test_inno_build_records_compiler_engine_version_not_file_metadata() -> None:
    content = (PROJECT_ROOT / "build_inno_installer.ps1").read_text(encoding="utf-8")
    assert "DisplayVersion" in content
    assert "InstallLocation" in content
    assert 'Publisher = [string]$entry.Publisher' in content
    assert '$registeredInnoInstallations[0].DisplayName -cne "Inno Setup version $ISCCVersion"' in content
    assert '$registeredInnoInstallations[0].Publisher -cne "jrsoftware.org"' in content
    assert 'Get-AuthenticodeSignature -FilePath $ISCC' in content
    assert '$ISCCSignature.Status.ToString() -ne "Valid"' in content
    assert "registeredInnoInstallations.Count -ne 1" in content
    assert "GetVersionInfo($ISCC.FullName)" not in content


def test_integrity_sidecar_writer_refuses_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    integrity._write_json_exclusive(path, {"value": "first"})
    first_bytes = path.read_bytes()

    with pytest.raises(integrity.ReleaseIntegrityError, match="Refusing to overwrite"):
        integrity._write_json_exclusive(path, {"value": "second"})

    assert path.read_bytes() == first_bytes
