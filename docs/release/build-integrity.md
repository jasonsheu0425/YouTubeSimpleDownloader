# Release Build Integrity

The Windows release build uses a fresh, dedicated `.release-venv` and the
committed CPython 3.12 x64 dependency locks; the developer/test `.venv` is never
reused or modified. `build_exe.bat` refuses an existing `.release-venv`,
`build`, or `dist` directory, then installs the hash-locked bootstrap and build environments,
checks the source/version/lock policy, verifies FFmpeg, sanitizes the
PyInstaller search path, builds the application, and runs the packaged Qt
runtime gate. Python import-path overrides and user-site packages are disabled.
The native search path contains only the build interpreter and Windows runtime
directories; a separate collection-record check rejects native inputs from
unrelated installations and compares the copied bytes. It stops rather than
deleting existing `build` or `dist` directories.

The build records the clean source commit/tree, hashes of all tracked inputs,
and installed toolchain before packaging. It signs the application EXE and
finishes `build/ytsd-bundle-build.json` only if source and environment still
match. That receipt hashes the signed bundle and contains no machine paths.
The Inno builder requires a matching receipt, verifies the existing signature
without re-signing the EXE, then copies the signed bundle into a unique staged
payload, reruns the Qt/FFmpeg gates, and compiles only from that snapshot. It
compares a deterministic payload inventory digest before and after Inno
compilation, generates the SBOM from that same snapshot, and refuses to
overwrite existing release outputs or mutate the tracked Inno template.

## Sidecars

For an installer named `<name>.exe`, the installer build emits:

- `<name>.sbom.cdx.json`: CycloneDX 1.6 JSON generated with the locked
  `cyclonedx-bom` tool. It records resolved runtime package versions, CPython,
  Qt, FFmpeg, build tools, and a SHA-256 inventory of every file in the exact
  staged payload compiled into the installer. The application executable is
  inventoried after Authenticode signing. FFmpeg's source URL and manifest archive-hash policy
  are included separately from the verified bundled executable hash.
  The frozen archive also identifies shipped build packages and vendored Python
  code; observed native OpenSSL, SQLite, libffi and MSVC binaries have separate
  identities. Declared Python package licenses come from the installed wheel
  metadata. Native file versions come from PE resources. CPython's libffi DLL
  has no embedded release version, so its component deliberately omits a release
  version and records the ABI filename, exact hash and matching Python-runtime
  origin. This is an inventory with declared license evidence, not a complete
  legal review of every native dependency.
  Every bundled DLL/PYD is additionally assigned an owner by matching its path
  and bytes against the installed wheel, CPython, or Windows runtime. Unknown
  and ambiguous owners are rejected; unavailable license/version evidence is
  recorded explicitly instead of inferred from an unrelated component.
- `<name>.provenance.json`: a schema-validated version 3 local build record containing
  the clean source commit/tree, dependency lock and build-input hashes,
  Windows/Python/toolchain identity, FFmpeg facts, installer filename/size/
  SHA-256, staged bundle inventory digest/file count, SBOM SHA-256, the exact
  generated Inno script SHA-256, and Authenticode status/signer/certificate
  thumbprint, plus the producer's signed-bundle receipt. An old bundle from a
  different commit, source drift during packaging, changed bundle bytes, or a
  changed producer environment is rejected. The generated script's contents and machine-specific paths are
  not copied into the provenance record.

The sidecars are not embedded into the installer. The SBOM does not hash the
installer, and the provenance record hashes the installer and SBOM but never
itself, avoiding circular artifact hashes. The Inno build re-hashes the exact
generated `.iss` file and validates the complete staged installer/SBOM/
provenance set before promotion. It promotes the sidecars and public
certificate first, then the installer last as the visible success artifact;
any caught failure before final verification returns promoted files to the
retained staging directory.

## Verification

The integrity tooling requires a clean source tree, matching package/runtime
versions, consistent hash locks, and 64-bit CPython 3.12 on Windows. The local
build uses the FFmpeg executable already present in the verified project
location; it checks that executable's manifest SHA-256 and version. It records
the manifest's archive hash as policy and explicitly does not claim the archive
was downloaded and rehashed during that local build.

Run the deterministic fixture/schema/tamper checks with the hash-locked build
environment:

```powershell
python scripts/check_dependency_locks.py
python scripts/check_workflow_action_pins.py
python scripts/release_integrity.py self-test
```

After a successful installer build, verify its exact bundle and sidecars:

```powershell
python scripts/release_integrity.py verify `
  --installer release\<name>.exe `
  --sbom release\<name>.sbom.cdx.json `
  --provenance release\<name>.provenance.json `
  --ffmpeg dist\YouTubeSimpleDownloader\_internal\ffmpeg\ffmpeg.exe `
  --dist-dir dist\YouTubeSimpleDownloader
```

To re-check the generated Inno input during the active local build, also pass
`--staged-installer-script <path-to-staged-YouTubeSimpleDownloader.iss>`. That
path exists only in the temporary staging tree and is intentionally not
serialized into release metadata. Once staging is removed, the provenance
still records the input digest, while independent post-build verification can
validate the record and final artifact hashes without claiming to reproduce
the temporary path-dependent script.

PowerShell additionally verifies the Authenticode signatures and expected
signer before and after promotion. The project's self-signed test certificate
provides signature integrity but does not imply broad Windows trust.
The `write-provenance` and `verify` commands independently query Windows
Authenticode for both actual executables and compare status, subject, and
certificate thumbprint with the record. They require Windows; portable JSON
and hash checks alone must not be reported as signature verification.

The producer receipt detects stale bundles and persistent source/environment
drift between build start and completion. The local build host is trusted:
endpoint snapshots do not prevent a same-owner attacker from changing and
restoring inputs during compilation. Frozen Python package ownership is
inferred from observed archive modules and the locked build environment,
not a cryptographic source-to-byte proof. These limitations are not a claim
of a hermetic or independently attested build.

These files are local build records, not signed attestations. Their hashes
should be checked against the published GitHub asset digests during the
separate post-release audit. CI-built production installers, GitHub artifact
attestations, signing-key redesign, and making a CI artifact the canonical
release asset remain deferred.
