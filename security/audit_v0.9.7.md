# Security Audit Report - YouTubeSimpleDownloader v0.9.7

## Audit Metadata

- Audit date: 2026-07-18
- Branch: `main`
- Commit: `0b1d8a0bbc75c306970bf26a20d223353fa52737`
- Release tag: `v0.9.7`
- Audit type: standard single-pass, read-only static security review
- Scope: application source, tests, dependencies, build scripts, installer,
  CI workflow, security policy, and release documentation

The review did not execute the GUI, rebuild artifacts, download media, or run
untrusted media files. The repository was not modified during the audit.

## Release Decision

**v0.9.7 does not need to be withdrawn.** No release-blocking security issue
was identified. The findings below should be handled through the security
backlog, with the URL/thumbnail and `ffprobe` items prioritized for v0.9.8.

## Summary

| Severity | Count |
| --- | ---: |
| High | 0 |
| Medium | 3 |
| Low | 1 |
| Informational | 3 |

## Findings

### YTSD-SEC-001: Unrestricted URL preview and unbounded thumbnail read

- Severity: Medium
- Affected areas: `app.py` URL parsing and `PreviewWorker`;
  `downloader.py` metadata extraction
- Release blocking: No

The URL input accepts arbitrary lines and passes them to yt-dlp. A single URL
automatically starts a preview, and the extracted thumbnail URL is fetched with
`urlopen(...).read()` without a response-size limit or host validation.

An attacker-supplied non-YouTube URL could cause requests to local or private
network services or return an excessively large thumbnail that consumes memory.
Exploitation requires the user to paste the malicious URL. The application does
not attach cookies or login credentials, and the audit found no direct data
exfiltration path.

Recommended remediation:

- Accept only HTTPS URLs on exact supported YouTube hosts.
- Validate thumbnail URLs and redirect destinations.
- Reject private-network destinations where practical.
- Enforce response size and content-type limits before decoding thumbnails.

### YTSD-SEC-002: PATH ffprobe bypasses the FFmpeg security policy

- Severity: Medium
- Affected area: `media_probe.py`
- Release blocking: No

When no companion `ffprobe` is available next to the selected FFmpeg binary,
the application executes an `ffprobe.exe` found through `PATH`. That executable
is not subject to the minimum FFmpeg version or artifact hash checks, and the
probe subprocess has no timeout.

This can move media parsing outside the verified FFmpeg 8.1.2 trust boundary.
An outdated, substituted, or hanging `ffprobe` could process downloaded or local
media. Exploitation is conditional on an unsuitable executable being available
through `PATH`; the v0.9.7 package does not bundle `ffprobe`.

Recommended remediation:

- Bundle and verify a matching `ffprobe`, or stop resolving it through `PATH`.
- Prefer fallback probing through the already verified FFmpeg binary.
- Add a finite timeout to all probe subprocesses.

### YTSD-SEC-003: Python build dependencies are not fully reproducible

- Severity: Medium
- Affected areas: `build_exe.bat`, `pyproject.toml`, requirements files, and
  `.github/workflows/test.yml`
- Release blocking: No

Direct application dependencies are pinned, but transitive dependencies are not
locked with hashes. The build upgrades pip, build-system dependencies use a
version range, and GitHub Actions are referenced by mutable major-version tags.

A compromised or unexpectedly changed upstream dependency could affect a future
signed build. The audit found no evidence that the existing v0.9.7 artifact is
compromised, and the FFmpeg artifact is independently hash verified.

Recommended remediation:

- Introduce reviewed, hash-locked dependency and build constraints.
- Pin GitHub Actions to immutable commit revisions.
- Generate an SBOM and retain build provenance for release artifacts.

### YTSD-SEC-004: Custom filename templates can escape the output folder

- Severity: Low
- Affected area: `downloader.py` output-template handling
- Release blocking: No

A local proof confirmed that a custom template containing `..` or an absolute
path resolves outside the selected output directory. This can cause advanced
configuration to write new files outside the folder the user selected. For a
single download, overwriting an existing file still requires an explicit prompt
that displays the path, reducing the impact.

Recommended remediation:

- Reject absolute paths and parent-directory traversal in custom templates.
- Resolve the final output path and require it to remain below `output_dir`.
- Add tests for absolute paths, `..`, mixed separators, and valid templates.

## Informational Notes

### YTSD-INFO-001: Local history contains private path information

`history.json` stores URLs, titles, and full local source/output paths in
plaintext under the per-user application data directory. It is not transmitted
by the application. Users should not share this file as part of support logs
without reviewing or redacting it.

### YTSD-INFO-002: Development dependency advisories are not applicable

PyPI reported `CVE-2025-71176` for pytest and `CVE-2026-59890` for setuptools.
The reported behaviors concern Unix temporary directories and macOS source
distribution filename normalization respectively. They do not apply to the
Windows application or its Windows CI, but the tooling should be refreshed during
normal maintenance.

### YTSD-INFO-003: Local editable-package metadata was stale

The audited environment's editable distribution metadata reported version
`0.9.6`, while the imported source module correctly reported `0.9.7`. This was a
local development-environment consistency issue, not a release vulnerability.

## Positive Security Controls

- No `shell=True`, `os.system`, `eval`, `exec`, pickle, or marshal use was found.
- FFmpeg source and packaged artifacts passed the published SHA-256 policy and
  reported version 8.1.2; legacy imageio-ffmpeg 7.1 binaries were absent.
- The update checker uses a fixed GitHub API endpoint, strict HTTPS/repository
  release URL validation, 24-hour throttling, silent network failure, and no
  automatic download or installation.
- FFmpeg subprocesses use argument lists, concurrent pipe draining, cancellation,
  inactivity timeout, and terminate/kill fallback.
- The installer deletion rule is narrowly scoped to the legacy imageio-ffmpeg
  binaries directory.
- No tracked credentials, private keys, tokens, or signing secrets were found.
- The GitHub v0.9.7 asset digest matched the published installer SHA-256.

## Disposition

- Must fix before withdrawing v0.9.7: none.
- Recommended for v0.9.8: YTSD-SEC-001, YTSD-SEC-002, and YTSD-SEC-004.
- Maintenance backlog: YTSD-SEC-003, dependency-tool advisory refresh, SBOM,
  build provenance, and immutable GitHub Action revisions.
