"""Build a PyInstaller PATH from interpreter and Windows runtime directories only."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def sanitize_pyinstaller_path(
    *,
    executable: str | Path | None = None,
    prefix: str | Path | None = None,
    base_prefix: str | Path | None = None,
    system_root: str | Path | None = None,
) -> str:
    """Return trusted tool/runtime directories without consulting ambient PATH."""
    interpreter = Path(executable or sys.executable).resolve(strict=True)
    environment = Path(prefix or sys.prefix).resolve(strict=True)
    base = Path(base_prefix or sys.base_prefix).resolve(strict=True)
    windows = Path(system_root or os.environ.get("SystemRoot", "")).resolve(strict=True)

    if not interpreter.is_file() or interpreter.parent != environment / "Scripts":
        raise ValueError("Build interpreter must be in the environment Scripts directory.")
    if environment == base or not (windows / "System32").is_dir():
        raise ValueError("A virtual environment and Windows System32 are required.")

    candidates = (
        interpreter.parent,
        base,
        base / "Scripts",
        base / "DLLs",
        windows / "System32",
        windows,
    )
    trusted: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        resolved = str(candidate.resolve(strict=True))
        key = os.path.normcase(resolved)
        if key not in seen:
            trusted.append(resolved)
            seen.add(key)
    return os.pathsep.join(trusted)


def main() -> int:
    print(sanitize_pyinstaller_path())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
