# Security Backlog

This backlog records follow-up work from the v0.9.7 read-only security audit.
It does not change the v0.9.7 release decision: the release has no blocking
security issue and does not need to be withdrawn.

## v0.9.8 Security Hardening

| ID | Priority | Work item | Acceptance criteria | Status |
| --- | --- | --- | --- | --- |
| YTSD-SEC-001 | High | Restrict URL and thumbnail preview traffic | Only supported YouTube HTTPS hosts are accepted; redirects and thumbnail URLs are validated; private-network destinations and oversized/non-image responses are rejected; regression tests cover the rules | Planned |
| YTSD-SEC-002 | High | Bring media probing inside the verified FFmpeg trust boundary | The app does not execute an unverified `ffprobe` from `PATH`; any selected probe meets the version/hash policy or verified FFmpeg fallback is used; all probe subprocesses have timeouts | Planned |
| YTSD-SEC-004 | Normal | Contain custom filename templates | Absolute paths and traversal are rejected; resolved outputs remain under the selected output folder; valid templates continue working; overwrite/skip/number behavior remains unchanged | Planned |

## Maintenance Backlog

| ID | Priority | Work item | Acceptance criteria | Status |
| --- | --- | --- | --- | --- |
| YTSD-SEC-003 | Normal | Hash-lock Python build dependencies | Reviewed direct and transitive dependency constraints include hashes; local and CI builds consume the same constraints; dependency updates remain intentional | Backlog |
| YTSD-MAINT-001 | Normal | Pin GitHub Actions immutably | Third-party Actions are pinned to reviewed commit SHAs and update notes record the corresponding release versions | Backlog |
| YTSD-MAINT-002 | Normal | Generate an SBOM | Each release can produce an SBOM covering bundled Python, Qt, yt-dlp, and FFmpeg components | Backlog |
| YTSD-MAINT-003 | Normal | Record build provenance | Release records identify source commit, build constraints, FFmpeg policy, artifact hash, and signing method | Backlog |
| YTSD-MAINT-004 | Low | Refresh development tooling advisories | pytest and setuptools constraints are reviewed and updated where compatible; Windows tests remain green | Backlog |
| YTSD-MAINT-005 | Low | Document history privacy | Support/security guidance warns that `history.json` contains URLs and full local paths and should be reviewed before sharing | Backlog |

## Scheduling Notes

- YTSD-SEC-001 and YTSD-SEC-002 should be addressed first in v0.9.8.
- YTSD-SEC-004 should ship in the same hardening release if its compatibility
  tests pass without changing existing filename behavior.
- Dependency locks, SBOM generation, provenance, and immutable Actions are
  maintenance work. They should not delay an urgent runtime security fix.
- No item in this backlog retroactively blocks or withdraws v0.9.7.
