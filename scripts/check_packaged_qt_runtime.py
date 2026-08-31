"""Reject root-level ICU DLLs that can shadow the Windows runtime used by Qt."""

from __future__ import annotations

import argparse
from pathlib import Path


class PackagedQtRuntimeError(RuntimeError):
    """Raised when the bundle contains an unsafe ambient ICU DLL."""


def find_unsafe_root_icu_files(internal_dir: Path) -> list[Path]:
    """Return ICU DLLs placed directly in a PyInstaller ``_internal`` directory."""
    if not internal_dir.is_dir():
        raise PackagedQtRuntimeError(f"PyInstaller _internal directory not found: {internal_dir}")

    return sorted(
        path
        for path in internal_dir.glob("icu*.dll")
        if path.is_file()
    )


def verify_packaged_qt_runtime(internal_dir: Path) -> None:
    unsafe_files = find_unsafe_root_icu_files(internal_dir)
    if not unsafe_files:
        return

    names = ", ".join(path.name for path in unsafe_files)
    raise PackagedQtRuntimeError(
        "Unsafe root-level ICU DLL(s) in the PyInstaller bundle: "
        f"{names}. These files can shadow the Windows ICU runtime required by Qt "
        "and are usually ambient build-environment contamination."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that a PyInstaller bundle has no unsafe root-level ICU DLLs."
    )
    parser.add_argument("internal_dir", type=Path, help="PyInstaller _internal directory")
    args = parser.parse_args()

    try:
        verify_packaged_qt_runtime(args.internal_dir)
    except PackagedQtRuntimeError as exc:
        parser.error(str(exc))

    print(f"Verified packaged Qt runtime: {args.internal_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
