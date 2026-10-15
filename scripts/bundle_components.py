"""Attribute frozen Python modules and native binaries to SBOM components.

This module reads the *finished* onedir bundle. The build environment supplies
metadata for a module only after the module is observed in the frozen archive.
"""

from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts.check_dependency_locks import parse_lock
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    from check_dependency_locks import parse_lock


class BundleComponentError(RuntimeError):
    """Bundle contents cannot be attributed unambiguously."""


class MissingNativeVersionError(BundleComponentError):
    """A native file has no usable PE version resource."""


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().lower()


def _frozen_modules(executable: Path) -> set[str]:
    try:
        from PyInstaller.archive.readers import CArchiveReader
    except ImportError as exc:
        raise BundleComponentError("Pinned PyInstaller archive reader is unavailable") from exc
    archive = CArchiveReader(str(executable))
    modules = {name for name, entry in archive.toc.items() if entry[-1] in {"m", "M"}}
    pyz_names = [name for name, entry in archive.toc.items() if entry[-1] == "z"]
    if len(pyz_names) != 1:
        raise BundleComponentError("Expected exactly one frozen PYZ archive")
    modules.update(archive.open_embedded_archive(pyz_names[0]).toc)
    return modules


def _module_for_file(filename: str) -> str | None:
    path = Path(filename.replace("\\", "/"))
    if path.suffix.lower() not in {".py", ".pyd"}:
        return None
    parts = list(path.parts)
    if any(part.endswith((".dist-info", ".egg-info")) for part in parts):
        return None
    stem = path.stem.split(".")[0]
    if stem != "__init__":
        parts[-1] = stem
    else:
        parts.pop()
    return ".".join(parts) if parts else None


def _ownership(distributions: list[metadata.Distribution], prefix: str = "") -> dict[str, list[metadata.Distribution]]:
    owners: dict[str, list[metadata.Distribution]] = {}
    for distribution in distributions:
        for file in distribution.files or []:
            module = _module_for_file(str(file))
            if module is None:
                continue
            if (
                _normalize(distribution.metadata["Name"]) == "pyinstaller"
                and module.startswith("PyInstaller.fake-modules._pyi_rth_utils")
            ):
                module = module.removeprefix("PyInstaller.fake-modules.")
            key = prefix + module
            owners.setdefault(key, []).append(distribution)
    return owners


def _vendor_distributions() -> list[metadata.Distribution]:
    setuptools = metadata.distribution("setuptools")
    root = Path(setuptools.locate_file("setuptools/_vendor"))
    if not root.is_dir():
        return []
    return [metadata.PathDistribution(path) for path in sorted(root.glob("*.dist-info"))]


def _license(distribution: metadata.Distribution) -> list[dict[str, Any]]:
    expression = distribution.metadata.get("License-Expression")
    if expression:
        return [{"expression": expression}]
    # Legacy License fields can contain either SPDX expressions or free text.
    license_text = distribution.metadata.get("License")
    if license_text and "\n" not in license_text and len(license_text) < 100:
        try:
            from license_expression import get_spdx_licensing
        except ImportError as exc:
            raise BundleComponentError("Locked SPDX license parser is unavailable") from exc
        parsed = get_spdx_licensing().validate(license_text)
        if not parsed.errors:
            return [{"expression": parsed.normalized_expression}]
        return [{"license": {"name": license_text}}]
    if license_text:
        for line in license_text.splitlines():
            heading = line.strip().strip("#= ")
            if len(heading) <= 100 and re.search(r"\b(license|licence|public domain)\b", heading, re.I):
                return [{"license": {"name": heading}}]

    declared_files = []
    get_all = getattr(distribution.metadata, "get_all", None)
    if callable(get_all):
        declared_files.extend(get_all("License-File") or [])
    declared_files.extend(
        str(file) for file in distribution.files or []
        if re.match(r"^(LICENSE|LICENCE|COPYING|NOTICE)(?:[._-]|$)", Path(file).name, re.I)
    )
    relative_files = sorted({
        value.replace("\\", "/") for value in declared_files
        if value and not Path(value).is_absolute() and ".." not in Path(value).parts and ":" not in value
    })
    if relative_files:
        return [{"license": {"name": "See distribution license files: " + ", ".join(relative_files)}}]
    classifiers = distribution.metadata.get_all("Classifier") if callable(get_all) else []
    for classifier in classifiers or []:
        if classifier.startswith("License :: "):
            return [{"license": {"name": "Wheel classifier: " + classifier.removeprefix("License :: ")}}]
    return []


def metadata_licenses(distribution_name: str) -> list[dict[str, Any]]:
    """Return CycloneDX licenses backed by installed wheel metadata."""
    distribution = metadata.distribution(distribution_name)
    if _normalize(distribution.metadata["Name"]) != _normalize(distribution_name):
        raise BundleComponentError(f"Unexpected distribution metadata for {distribution_name}")
    return _license(distribution)


def augment_component_licenses(component: dict[str, Any], distribution_name: str) -> dict[str, Any]:
    """Return a copy with license metadata from the installed distribution.

    Only declared metadata and relative license-file evidence are used. An
    explicitly supplied license remains authoritative.
    """
    result = dict(component)
    distribution = metadata.distribution(distribution_name)
    if _normalize(distribution.metadata["Name"]) != _normalize(distribution_name):
        raise BundleComponentError(f"Unexpected distribution metadata for {distribution_name}")
    if result.get("version") != distribution.version:
        raise BundleComponentError(f"Installed {distribution_name} version differs from SBOM component")
    licenses = metadata_licenses(distribution_name)
    if licenses and not result.get("licenses"):
        result["licenses"] = licenses
    return result


def parse_ffmpeg_license_output(output: str) -> list[dict[str, Any]]:
    """Accept only FFmpeg's explicit GPL/LGPL redistribution statement."""
    match = re.search(
        r"under the terms of the GNU (Lesser )?General Public License.*?"
        r"either version ([23]) of the License, or \(at your option\) any later version",
        output,
        re.I | re.S,
    )
    if not match:
        raise BundleComponentError("FFmpeg -L did not identify a supported license statement")
    return [{"expression": f"{'LGPL' if match.group(1) else 'GPL'}-{match.group(2)}.0-or-later"}]


def ffmpeg_license_from_verified_binary(path: Path, expected_sha256: str) -> list[dict[str, Any]]:
    if _hash(path) != expected_sha256.lower():
        raise BundleComponentError("FFmpeg hash differs from verified executable")
    result = subprocess.run([str(path), "-L"], capture_output=True, text=True, timeout=20, check=False)
    if result.returncode:
        raise BundleComponentError("Verified FFmpeg -L failed")
    return parse_ffmpeg_license_output(result.stdout)


def cpython_license_from_distribution(license_path: Path) -> list[dict[str, Any]]:
    """Name the PSF license only when the installed interpreter supplies it."""
    text = license_path.read_text(encoding="utf-8")
    if "PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2" not in text.upper():
        raise BundleComponentError("CPython distribution license evidence is missing")
    return [{"license": {"name": "Python Software Foundation License Version 2"}}]


def _native_info(path: Path) -> tuple[str, str]:
    """Return observed PE product and file version, never filename guesses."""
    try:
        import pefile
    except ImportError as exc:
        raise BundleComponentError("Pinned pefile parser is unavailable") from exc
    pe = pefile.PE(str(path), fast_load=False)
    try:
        fixed = getattr(pe, "VS_FIXEDFILEINFO", [])
        if not fixed:
            raise MissingNativeVersionError(f"Native binary has no observed PE version: {path.name}")
        version = fixed[0]
        value = ".".join(str(part) for part in (
            version.FileVersionMS >> 16, version.FileVersionMS & 0xffff,
            version.FileVersionLS >> 16, version.FileVersionLS & 0xffff,
        ))
        if value == "0.0.0.0":
            raise MissingNativeVersionError(f"Native binary has no observed PE version: {path.name}")
        product = ""
        for info in getattr(pe, "FileInfo", []):
            for table in info:
                for string_table in getattr(table, "StringTable", []):
                    product = string_table.entries.get(b"ProductName", b"").decode("utf-8", "replace") or product
        return product, value
    finally:
        pe.close()


_NATIVE_NAMES = {
    "libcrypto-3-x64.dll": "openssl",
    "libssl-3-x64.dll": "openssl",
    "libcrypto-3.dll": "openssl",
    "libssl-3.dll": "openssl",
    "sqlite3.dll": "sqlite",
    "libffi-8.dll": "libffi",
    "msvcp140.dll": "msvc-runtime",
    "msvcp140_1.dll": "msvc-runtime",
    "msvcp140_2.dll": "msvc-runtime",
    "vcruntime140.dll": "msvc-runtime",
    "vcruntime140_1.dll": "msvc-runtime",
    "ucrtbase.dll": "msvc-runtime",
}


def _native_wheel_sources() -> dict[str, list[tuple[metadata.Distribution, str, Path]]]:
    sources: dict[str, list[tuple[metadata.Distribution, str, Path]]] = {}
    for distribution in metadata.distributions():
        for file in distribution.files or []:
            relative = str(file).replace("\\", "/")
            if Path(relative).suffix.lower() not in {".dll", ".pyd"}:
                continue
            if Path(relative).is_absolute() or ".." in Path(relative).parts or ":" in relative:
                raise BundleComponentError("Installed wheel has an unsafe native file path")
            source = Path(distribution.locate_file(file))
            sources.setdefault(Path(relative).name.lower(), []).append((distribution, relative, source))
    return sources


def _native_owner(
    relative: str, digest: str,
    wheel_sources: Mapping[str, list[tuple[metadata.Distribution, str, Path]]],
) -> tuple[str, str, str, list[dict[str, Any]]]:
    payload = relative.removeprefix("_internal/").lower()
    filename = Path(relative).name.lower()
    matches = []
    for distribution, wheel_path, source in wheel_sources.get(filename, []):
        if (payload == wheel_path.lower() or payload.endswith("/" + wheel_path.lower())) and source.is_file() and _hash(source) == digest:
            matches.append((distribution, wheel_path))
    if len(matches) != 1:
        if matches:
            raise BundleComponentError(f"Ambiguous installed-wheel owner for {relative}")
        # CPython's DLLs and extension modules are copied from the base runtime.
        base = Path(sys.base_prefix)
        for prefix in (base, base / "DLLs"):
            source = prefix / filename
            if source.is_file() and _hash(source) == digest:
                licenses = [] if filename in _NATIVE_NAMES else cpython_license_from_distribution(base / "LICENSE.txt")
                return (
                    "CPython", sys.version.split()[0],
                    f"CPython distribution/{source.relative_to(base).as_posix()}", licenses,
                )
        # A few MSVC/UCRT files are collected from Windows rather than a wheel.
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        source = system_root / "System32" / filename
        if source.is_file() and _hash(source) == digest:
            return ("Windows runtime", "", "Windows/System32/" + filename, [])
        raise BundleComponentError(f"Unattributed native bundle file: {relative}")
    distribution, wheel_path = matches[0]
    name = distribution.metadata["Name"]
    return (name, distribution.version, f"installed wheel {name}/{wheel_path}", _license(distribution))


def _native_components(
    dist_dir: Path, native_evidence: Mapping[str, Mapping[str, Any]] | None = None
) -> list[dict[str, Any]]:
    components = []
    wheel_sources = _native_wheel_sources()
    for path in sorted(dist_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".dll", ".pyd"}:
            continue
        relative = path.relative_to(dist_dir).as_posix()
        digest = _hash(path)
        owner, owner_version, source_origin, licenses = _native_owner(relative, digest, wheel_sources)
        family = _NATIVE_NAMES.get(path.name.lower(), _normalize(owner))
        version_source = "PE VS_FIXEDFILEINFO"
        version_status = "observed in PE"
        try:
            product, version = _native_info(path)
        except MissingNativeVersionError:
            receipt = (native_evidence or {}).get(relative, {})
            if path.name.lower() == "libffi-8.dll" and (
                receipt.get("approved") is not True
                or str(receipt.get("sha256", "")).lower() != digest
                or str(receipt.get("source_sha256", "")).lower() != digest
                or not isinstance(receipt.get("origin"), str)
                or not receipt["origin"]
                or "/" in receipt["origin"]
                or "\\" in receipt["origin"]
                or ":" in receipt["origin"]
            ):
                raise BundleComponentError(f"Native binary has no approved version evidence: {relative}") from None
            if path.name.lower() == "libffi-8.dll":
                version = receipt.get("version")
                version_status = "approved by hash-bound receipt"
            else:
                version = owner_version or None
                version_source = "hash-matched owner distribution"
                version_status = "owner version; PE version unavailable"
            if path.name.lower() == "libffi-8.dll" and version is None:
                if (
                    receipt.get("version_unavailable") is not True
                    or not re.fullmatch(r"CPython ?\d+\.\d+\.\d+(?:\.\d+)? distribution", receipt["origin"])
                ):
                    raise BundleComponentError(f"Unversioned native evidence is not approved: {relative}") from None
                version_status = "unavailable in trusted CPython binary"
            elif path.name.lower() == "libffi-8.dll" and (not isinstance(version, str) or not version or receipt.get("version_unavailable") is True):
                raise BundleComponentError(f"Native version evidence is malformed: {relative}") from None
            product = ""
            if path.name.lower() == "libffi-8.dll":
                version_source = "approved hash-bound origin receipt"
        # Path-qualified identity preserves side-by-side versions and copies.
        identity = f"pkg:generic/{family}/{path.name.lower()}"
        if version is not None:
            identity += f"@{version}"
        ref = f"{identity}?path={relative.replace('/', '%2F').lower()}"
        component = {
            "bom-ref": ref, "type": "library", "name": f"{family} {path.name}",
            "purl": ref,
            "hashes": [{"alg": "SHA-256", "content": digest}],
            "properties": [
                {"name": "ytsd:relative-path", "value": relative},
                {"name": "ytsd:pe-product-name", "value": product},
                {"name": "ytsd:version-source", "value": version_source},
                {"name": "ytsd:version-status", "value": version_status},
                {"name": "ytsd:abi-filename", "value": path.name},
                {"name": "ytsd:component-role", "value": "bundled-native"},
                {"name": "ytsd:owner", "value": owner},
                {"name": "ytsd:owner-version", "value": owner_version},
                {"name": "ytsd:source-origin", "value": source_origin},
            ],
        }
        if version is not None:
            component["version"] = version
        # Wheel ownership is evidence of distribution, not a license grant for
        # every included third-party native file (for example MSVC runtimes).
        if licenses:
            component["properties"].append({
                "name": "ytsd:owner-declared-licenses",
                "value": json.dumps(licenses, sort_keys=True, separators=(",", ":")),
            })
        component["properties"].append({
            "name": "ytsd:license-status", "value": "native-file license not independently established",
        })
        components.append(component)
    return components


def discover_bundled_components(
    dist_dir: Path, *, native_evidence: Mapping[str, Mapping[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Identify extra components observed in a PyInstaller onedir bundle.

    The caller merges these with its lock-derived runtime components. Unknown
    third-party frozen modules fail closed; standard-library and application
    modules are represented by the parent CPython/application components.
    """
    dist_dir = dist_dir.resolve()
    executable = dist_dir / "YouTubeSimpleDownloader.exe"
    if not executable.is_file():
        raise BundleComponentError("Frozen application executable is missing")
    modules = _frozen_modules(executable)
    installed = _ownership(list(metadata.distributions()))
    vendored = _ownership(_vendor_distributions(), "setuptools._vendor.")
    runtime_names = set(parse_lock(Path(__file__).resolve().parents[1] / "requirements/runtime.lock"))
    observed: dict[str, tuple[metadata.Distribution, bool]] = {}
    module_evidence: dict[str, set[str]] = {}
    unknown = []
    for module in sorted(modules):
        candidates = vendored.get(module) or installed.get(module)
        if candidates is None:
            top = module.split(".", 1)[0]
            namespace = any(other.startswith(module + ".") for other in modules)
            if not namespace and top not in sys.stdlib_module_names and top not in {"ytsimpledownloader", "__main__", "pyimod01_archive", "pyimod02_importers", "pyimod03_ctypes", "pyimod04_pywin32"}:
                unknown.append(module)
            continue
        is_vendor = module in vendored
        if len(candidates) > 1:
            claimants = {_normalize(item.metadata["Name"]) for item in candidates}
            if not is_vendor and claimants <= runtime_names:
                continue
            raise BundleComponentError(f"Multiple distributions own frozen module {module}")
        owner = candidates[0]
        key = ("vendor:" if is_vendor else "installed:") + _normalize(owner.metadata["Name"])
        observed[key] = (owner, is_vendor)
        module_evidence.setdefault(key, set()).add(module)
    if unknown:
        raise BundleComponentError("Unattributed frozen modules: " + ", ".join(unknown[:12]))

    components = []
    for key, (owner, is_vendor) in observed.items():
        name = _normalize(owner.metadata["Name"])
        if not is_vendor and name in runtime_names:
            continue
        purl = f"pkg:pypi/{name}@{owner.version}"
        if is_vendor:
            purl += "?vendored_by=setuptools"
        component: dict[str, Any] = {
            "bom-ref": purl, "type": "library",
            "name": f"setuptools vendored {owner.metadata['Name']}" if is_vendor else owner.metadata["Name"],
            "version": owner.version, "purl": purl,
            "properties": [
                {"name": "ytsd:component-role", "value": "bundled-vendored-python" if is_vendor else "bundled-python-extra"},
                *([{"name": "ytsd:parent-component", "value": "pkg:pypi/setuptools@" + metadata.distribution("setuptools").version}] if is_vendor else []),
                *({"name": "ytsd:frozen-module", "value": module} for module in sorted(module_evidence[key])),
            ],
        }
        licenses = _license(owner)
        if licenses:
            component["licenses"] = licenses
        components.append(component)
    components.extend(_native_components(dist_dir, native_evidence))
    return sorted(components, key=lambda item: item["bom-ref"])
