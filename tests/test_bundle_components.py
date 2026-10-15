from __future__ import annotations

import hashlib
import subprocess
import sys
import types
from pathlib import Path

import pytest

from scripts import bundle_components as bundle


class Distribution:
    def __init__(self, name: str, version: str, files: list[str], license_expression: str | None = None,
                 root: Path | None = None):
        self.metadata = {"Name": name}
        if license_expression:
            self.metadata["License-Expression"] = license_expression
        self.version = version
        self.files = [Path(file) for file in files]
        self.root = root

    def locate_file(self, file):
        return self.root / file


def test_discovers_only_frozen_distributions_and_qualified_vendor(tmp_path, monkeypatch):
    exe = tmp_path / "YouTubeSimpleDownloader.exe"
    exe.write_bytes(b"frozen fixture")
    installed = [
        Distribution("setuptools", "82.0.1", ["setuptools/__init__.py"], "MIT"),
        Distribution("packaging", "26.3", ["packaging/__init__.py"], "Apache-2.0 OR BSD-2-Clause"),
        Distribution("unused-package", "1.0", ["unused_package/__init__.py"], "MIT"),
    ]
    vendored = [
        Distribution("packaging", "26.0", ["packaging/__init__.py"], "Apache-2.0 OR BSD-2-Clause"),
        Distribution("jaraco.context", "6.1.0", ["jaraco/context/__init__.py"], "MIT"),
    ]
    monkeypatch.setattr(bundle, "_frozen_modules", lambda _exe: {
        "setuptools", "packaging", "setuptools._vendor.packaging",
        "setuptools._vendor.jaraco", "setuptools._vendor.jaraco.context",
        "json", "ytsimpledownloader.app",
    })
    monkeypatch.setattr(bundle.metadata, "distributions", lambda: installed)
    monkeypatch.setattr(bundle, "_vendor_distributions", lambda: vendored)
    monkeypatch.setattr(bundle, "_native_components", lambda _dist, _evidence=None: [])

    components = bundle.discover_bundled_components(tmp_path)
    refs = {item["bom-ref"] for item in components}
    assert "pkg:pypi/packaging@26.3" in refs
    assert "pkg:pypi/packaging@26.0?vendored_by=setuptools" in refs
    assert "pkg:pypi/jaraco-context@6.1.0?vendored_by=setuptools" in refs
    assert "pkg:pypi/setuptools@82.0.1" not in refs  # Parent already emits runtime.lock.
    assert not any("unused-package" in ref for ref in refs)
    vendor = next(item for item in components if item["purl"].endswith("vendored_by=setuptools"))
    assert vendor["licenses"]
    assert {prop["name"]: prop["value"] for prop in vendor["properties"]}["ytsd:component-role"] == "bundled-vendored-python"
    assert any(prop == {"name": "ytsd:frozen-module", "value": "setuptools._vendor.packaging"}
               for item in components for prop in item["properties"])


def test_unattributed_third_party_module_fails(tmp_path, monkeypatch):
    (tmp_path / "YouTubeSimpleDownloader.exe").write_bytes(b"fixture")
    monkeypatch.setattr(bundle, "_frozen_modules", lambda _exe: {"mystery_plugin.core"})
    monkeypatch.setattr(bundle.metadata, "distributions", lambda: [])
    monkeypatch.setattr(bundle, "_vendor_distributions", lambda: [])
    with pytest.raises(bundle.BundleComponentError, match="mystery_plugin.core"):
        bundle.discover_bundled_components(tmp_path)


def test_reads_carchive_and_embedded_pyz_toc(tmp_path, monkeypatch):
    executable = tmp_path / "YouTubeSimpleDownloader.exe"
    executable.write_bytes(b"fixture")

    class Reader:
        def __init__(self, filename):
            assert filename == str(executable)
            self.toc = {"bootstrap": (0, 0, 0, 0, "m"), "PYZ.pyz": (0, 0, 0, 0, "z")}

        def open_embedded_archive(self, name):
            assert name == "PYZ.pyz"
            return types.SimpleNamespace(toc={"packaging": (0, 0, 0)})

    readers = types.ModuleType("PyInstaller.archive.readers")
    readers.CArchiveReader = Reader
    monkeypatch.setitem(sys.modules, "PyInstaller", types.ModuleType("PyInstaller"))
    monkeypatch.setitem(sys.modules, "PyInstaller.archive", types.ModuleType("PyInstaller.archive"))
    monkeypatch.setitem(sys.modules, "PyInstaller.archive.readers", readers)
    assert bundle._frozen_modules(executable) == {"bootstrap", "packaging"}


def test_pyinstaller_relocated_runtime_module_maps_to_wheel_record():
    owner = Distribution(
        "PyInstaller", "6.15.0",
        ["PyInstaller/fake-modules/_pyi_rth_utils/qt.py"],
    )
    assert bundle._ownership([owner])["_pyi_rth_utils.qt"] == [owner]


def test_direct_script_import_with_isolated_python(tmp_path):
    result = subprocess.run(
        [sys.executable, "-B", "-E", "-s", str(Path(bundle.__file__))],
        cwd=tmp_path, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_native_component_has_observed_version_hash_and_relative_evidence(tmp_path, monkeypatch):
    internal = tmp_path / "_internal"
    internal.mkdir()
    binary = internal / "libcrypto-3-x64.dll"
    binary.write_bytes(b"PE fixture")
    monkeypatch.setattr(bundle, "_native_info", lambda _path: ("The OpenSSL Toolkit", "3.4.0.0"))
    monkeypatch.setattr(bundle, "_native_owner", lambda *_args: ("CPython", "3.12.4", "CPython distribution/DLLs/libcrypto-3-x64.dll", []))

    components = bundle._native_components(tmp_path)
    assert len(components) == 1
    item = components[0]
    assert item["version"] == "3.4.0.0"
    assert item["hashes"][0]["content"] == hashlib.sha256(b"PE fixture").hexdigest()
    assert {prop["name"]: prop["value"] for prop in item["properties"]}["ytsd:relative-path"] == (
        "_internal/libcrypto-3-x64.dll"
    )
    assert "licenses" not in item


def test_native_missing_version_fails_instead_of_guessing(tmp_path, monkeypatch):
    internal = tmp_path / "_internal"
    internal.mkdir()
    (internal / "libffi-8.dll").write_bytes(b"no version fixture")
    monkeypatch.setattr(bundle, "_native_owner", lambda *_args: ("CPython", "3.12.4", "CPython distribution/DLLs/libffi-8.dll", []))
    monkeypatch.setattr(bundle, "_native_info", lambda _path: (_ for _ in ()).throw(
        bundle.MissingNativeVersionError("Native binary has no observed PE version: libffi-8.dll")
    ))
    with pytest.raises(bundle.BundleComponentError, match="no approved version evidence"):
        bundle._native_components(tmp_path)
    receipt = {
        "_internal/libffi-8.dll": {
            "approved": True,
            "sha256": hashlib.sha256(b"no version fixture").hexdigest(),
            "source_sha256": hashlib.sha256(b"no version fixture").hexdigest(),
            "version": None,
            "version_unavailable": True,
            "origin": "CPython3.12.4 distribution",
        }
    }
    component = bundle._native_components(tmp_path, receipt)[0]
    assert "version" not in component
    assert "@" not in component["purl"]
    props = {prop["name"]: prop["value"] for prop in component["properties"]}
    assert props["ytsd:version-status"] == "unavailable in trusted CPython binary"
    assert props["ytsd:abi-filename"] == "libffi-8.dll"
    assert props["ytsd:source-origin"] == "CPython distribution/DLLs/libffi-8.dll"
    receipt["_internal/libffi-8.dll"]["source_sha256"] = "0" * 64
    with pytest.raises(bundle.BundleComponentError, match="no approved version evidence"):
        bundle._native_components(tmp_path, receipt)
    receipt["_internal/libffi-8.dll"]["source_sha256"] = receipt["_internal/libffi-8.dll"]["sha256"]
    receipt["_internal/libffi-8.dll"]["approved"] = False
    with pytest.raises(bundle.BundleComponentError, match="no approved version evidence"):
        bundle._native_components(tmp_path, receipt)
    receipt["_internal/libffi-8.dll"]["approved"] = True
    receipt["_internal/libffi-8.dll"]["version_unavailable"] = False
    with pytest.raises(bundle.BundleComponentError, match="not approved"):
        bundle._native_components(tmp_path, receipt)
    receipt["_internal/libffi-8.dll"]["version_unavailable"] = True
    receipt["_internal/libffi-8.dll"]["origin"] = r"C:\Python312\DLLs\libffi-8.dll"
    with pytest.raises(bundle.BundleComponentError, match="no approved version evidence"):
        bundle._native_components(tmp_path, receipt)


def test_all_native_files_require_hash_matched_wheel_or_python_owner(tmp_path, monkeypatch):
    wheel_root = tmp_path / "site-packages"
    wheel_file = wheel_root / "PySide6" / "Qt6Widgets.dll"
    wheel_file.parent.mkdir(parents=True)
    wheel_file.write_bytes(b"Qt wheel bytes")
    dist = Distribution("PySide6-Essentials", "6.10.1", ["PySide6/Qt6Widgets.dll"],
                        "LGPL-3.0-only", wheel_root)
    monkeypatch.setattr(bundle.metadata, "distributions", lambda: [dist])
    base = tmp_path / "Python312"
    (base / "DLLs").mkdir(parents=True)
    (base / "DLLs" / "_sqlite3.pyd").write_bytes(b"Python extension bytes")
    (base / "LICENSE.txt").write_text("PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2", encoding="utf-8")
    monkeypatch.setattr(bundle.sys, "base_prefix", str(base))
    payload = tmp_path / "bundle" / "_internal"
    (payload / "PySide6").mkdir(parents=True)
    (payload / "PySide6" / "Qt6Widgets.dll").write_bytes(b"Qt wheel bytes")
    (payload / "_sqlite3.pyd").write_bytes(b"Python extension bytes")
    monkeypatch.setattr(bundle, "_native_info", lambda _path: (_ for _ in ()).throw(
        bundle.MissingNativeVersionError("no PE version")))

    components = bundle._native_components(payload.parent)
    assert len(components) == 2
    by_path = {
        next(prop["value"] for prop in item["properties"] if prop["name"] == "ytsd:relative-path"): item
        for item in components
    }
    qt = by_path["_internal/PySide6/Qt6Widgets.dll"]
    assert qt["version"] == "6.10.1"
    assert "licenses" not in qt
    assert any(prop == {"name": "ytsd:owner-declared-licenses", "value": '[{"expression":"LGPL-3.0-only"}]'}
               for prop in qt["properties"])
    assert any(prop == {"name": "ytsd:source-origin", "value": "installed wheel PySide6-Essentials/PySide6/Qt6Widgets.dll"}
               for prop in qt["properties"])
    assert "licenses" not in by_path["_internal/_sqlite3.pyd"]
    assert any(prop["name"] == "ytsd:owner-declared-licenses" and "Python Software Foundation" in prop["value"]
               for prop in by_path["_internal/_sqlite3.pyd"]["properties"])
    assert str(tmp_path) not in str(components)

    (payload / "PySide6" / "Qt6Widgets.dll").write_bytes(b"changed bytes")
    with pytest.raises(bundle.BundleComponentError, match="Unattributed native bundle file"):
        bundle._native_components(payload.parent)


def test_ambiguous_native_wheel_owners_fail(tmp_path, monkeypatch):
    wheel_root = tmp_path / "site-packages"
    source = wheel_root / "shared.dll"
    source.parent.mkdir()
    source.write_bytes(b"same bytes")
    owners = [Distribution(name, "1.0", ["shared.dll"], root=wheel_root) for name in ("first", "second")]
    monkeypatch.setattr(bundle.metadata, "distributions", lambda: owners)
    payload = tmp_path / "bundle" / "_internal"
    payload.mkdir(parents=True)
    (payload / "shared.dll").write_bytes(b"same bytes")
    with pytest.raises(bundle.BundleComponentError, match="Ambiguous installed-wheel owner"):
        bundle._native_components(payload.parent)


def test_license_augmentation_uses_installed_metadata_and_checks_version(monkeypatch):
    distribution = Distribution("PySide6", "6.10.1", [], "LGPL-3.0-only")
    monkeypatch.setattr(bundle.metadata, "distribution", lambda _name: distribution)
    component = {"name": "PySide6", "version": "6.10.1"}
    augmented = bundle.augment_component_licenses(component, "PySide6")
    assert augmented["licenses"] == [{"expression": "LGPL-3.0-only"}]
    assert bundle.metadata_licenses("PySide6") == [{"expression": "LGPL-3.0-only"}]
    assert "licenses" not in component
    with pytest.raises(bundle.BundleComponentError, match="version"):
        bundle.augment_component_licenses({"version": "0.0.0"}, "PySide6")


def test_long_legacy_license_retains_heading_or_relative_file_evidence(monkeypatch):
    class Message(dict):
        def get_all(self, key):
            return ["licenses/LICENSE.txt"] if key == "License-File" else []

    distribution = Distribution("example", "1.0", ["example/__init__.py"])
    distribution.metadata = Message(Name="example", License="Example Public License\n" + "terms " * 60)
    monkeypatch.setattr(bundle.metadata, "distribution", lambda _name: distribution)
    assert bundle.metadata_licenses("example") == [{"license": {"name": "Example Public License"}}]
    distribution.metadata["License"] = "copyright and conditions\n" + "terms " * 60
    assert bundle.metadata_licenses("example") == [
        {"license": {"name": "See distribution license files: licenses/LICENSE.txt"}}
    ]


def test_classifier_license_evidence_is_named_not_guessed(monkeypatch):
    class Message(dict):
        def get_all(self, key):
            return ["License :: OSI Approved :: BSD License"] if key == "Classifier" else []

    distribution = Distribution("example", "1.0", [])
    distribution.metadata = Message(Name="example")
    monkeypatch.setattr(bundle.metadata, "distribution", lambda _name: distribution)
    assert bundle.metadata_licenses("example") == [
        {"license": {"name": "Wheel classifier: OSI Approved :: BSD License"}}
    ]


def test_ffmpeg_license_requires_verified_bytes_and_explicit_output(tmp_path, monkeypatch):
    binary = tmp_path / "ffmpeg.exe"
    binary.write_bytes(b"verified")
    statement = (
        "under the terms of the GNU Lesser General Public License as published by "
        "the Free Software Foundation; either version 2 of the License, or "
        "(at your option) any later version"
    )
    monkeypatch.setattr(
        bundle.subprocess, "run",
        lambda *_args, **_kwargs: bundle.subprocess.CompletedProcess([], 0, statement, ""),
    )
    assert bundle.ffmpeg_license_from_verified_binary(binary, hashlib.sha256(b"verified").hexdigest()) == [
        {"expression": "LGPL-2.0-or-later"}
    ]
    with pytest.raises(bundle.BundleComponentError, match="hash"):
        bundle.ffmpeg_license_from_verified_binary(binary, "0" * 64)
    with pytest.raises(bundle.BundleComponentError, match="statement"):
        bundle.parse_ffmpeg_license_output("configuration: --enable-gpl")


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\t"])
def test_ffmpeg_license_accepts_actual_wrapped_redistribution_statement(separator):
    statement = (
        "ffmpeg is free software; you can redistribute it and/or modify\n"
        "it under the terms of the GNU General Public License as published by\n"
        "the Free Software Foundation; either version 3 of the License, or\n"
        "(at your option) any later version."
    ).replace("\n", separator)
    assert bundle.parse_ffmpeg_license_output(statement) == [{"expression": "GPL-3.0-or-later"}]


def test_cpython_license_requires_distribution_text(tmp_path):
    license_file = tmp_path / "LICENSE.txt"
    license_file.write_text("PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2\n", encoding="utf-8")
    assert bundle.cpython_license_from_distribution(license_file) == [
        {"license": {"name": "Python Software Foundation License Version 2"}}
    ]
    license_file.write_text("unrelated", encoding="utf-8")
    with pytest.raises(bundle.BundleComponentError, match="evidence"):
        bundle.cpython_license_from_distribution(license_file)
