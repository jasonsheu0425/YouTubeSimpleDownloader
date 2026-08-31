"""Produce a PyInstaller PATH without unrelated ambient native runtimes."""

from __future__ import annotations

import os


BLOCKED_PATH_MARKERS = ("codex-runtimes", "poppler")


def sanitize_pyinstaller_path(path_value: str) -> str:
    """Keep build-tool paths while removing known unrelated native runtime roots."""
    return ";".join(
        entry
        for entry in path_value.split(";")
        if entry
        and not any(marker in entry.lower() for marker in BLOCKED_PATH_MARKERS)
    )


def main() -> int:
    print(sanitize_pyinstaller_path(os.environ.get("PATH", "")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
