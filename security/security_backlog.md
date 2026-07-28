# Security Backlog

This backlog originated from the v0.9.7 read-only security audit and was
updated after the v0.9.8 security hardening release. The addressed items below
record shipped mitigations; the remaining maintenance items do not imply that
the project is risk-free.

## v0.9.8 Security Hardening

| ID | Priority | Work item | Acceptance criteria | Status |
| --- | --- | --- | --- | --- |
| YTSD-SEC-001 | High | Restrict URL and thumbnail preview traffic | Only supported YouTube HTTPS hosts are accepted; redirects and thumbnail URLs are validated; private-network destinations and oversized/non-image responses are rejected; regression tests cover the rules | Addressed in v0.9.8 |
| YTSD-SEC-002 | High | Bring media probing inside the verified FFmpeg trust boundary | The app does not execute an unverified `ffprobe` from `PATH`; any selected probe meets the version/hash policy or verified FFmpeg fallback is used; all probe subprocesses have timeouts | Addressed in v0.9.8 |
| YTSD-SEC-004 | Normal | Contain custom filename templates | Absolute paths and traversal are rejected; resolved outputs remain under the selected output folder; valid templates continue working; overwrite/skip/number behavior remains unchanged | Addressed in v0.9.8 |

### v0.9.8 Remediation Notes

- YTSD-SEC-001: URL parsing now accepts only supported HTTPS YouTube video,
  Shorts, and playlist forms. Thumbnail requests validate the initial URL,
  every redirect, and the final URL; permit only approved image hosts and
  content types; enforce a 15-second timeout and a 5 MiB read limit; and fail
  thumbnail loading without failing the metadata preview.
- YTSD-SEC-002: media probing no longer discovers or executes `ffprobe` from
  `PATH`. Until a separately verified ffprobe artifact is bundled, probing
  uses the already verified FFmpeg binary with a bounded timeout.
- YTSD-SEC-004: custom templates reject absolute paths, drive/UNC prefixes,
  and parent traversal. Prepared and reported output paths are resolved and
  checked for containment before directory creation, overwrite, or use.

## Maintenance Backlog

| ID | Priority | Work item | Acceptance criteria | Status |
| --- | --- | --- | --- | --- |
| YTSD-SEC-003 | Normal | Hash-lock Python build dependencies | Reviewed direct and transitive dependency constraints include hashes; local and CI builds consume the same constraints; dependency updates remain intentional | Backlog |
| YTSD-MAINT-001 | Normal | Pin GitHub Actions immutably | Third-party Actions are pinned to reviewed commit SHAs and update notes record the corresponding release versions | Backlog |
| YTSD-MAINT-002 | Normal | Generate an SBOM | Each release can produce an SBOM covering bundled Python, Qt, yt-dlp, and FFmpeg components | Backlog |
| YTSD-MAINT-003 | Normal | Record build provenance | Release records identify source commit, build constraints, FFmpeg policy, artifact hash, and signing method | Backlog |
| YTSD-MAINT-004 | Low | Refresh development tooling advisories | pytest and setuptools constraints are reviewed and updated where compatible; Windows tests remain green | Backlog |
| YTSD-MAINT-005 | Low | Document history privacy | Support/security guidance warns that `history.json` contains URLs and full local paths and should be reviewed before sharing | Addressed in v0.9.8 post-release documentation |

## Scheduling Notes

- YTSD-SEC-001, YTSD-SEC-002, and YTSD-SEC-004 shipped in v0.9.8 with
  regression coverage.
- YTSD-MAINT-005 was completed as post-release documentation and did not
  require a history schema or application behavior change.
- Dependency locks, SBOM generation, provenance, and immutable Actions are
  remaining maintenance work. They do not retroactively block the verified
  v0.9.8 release.
- No post-release blocker is currently recorded here. Future findings should
  still be evaluated on their own evidence and severity.
