"""Reject settings access that can bypass the repository's test fixtures."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHARED_FIXTURES = {
    "isolated_user_environment",
    "isolated_settings_factory",
    "isolated_settings",
    "cleanup_qt_widgets",
}


class TestIsolationError(RuntimeError):
    """Raised before collection when a test could access native settings."""

    __test__ = False


def check_source(source: str, *, shared_conftest: bool = False) -> list[str]:
    """Check direct Qt aliases and prohibit shadowing the shared safety fixtures.

    This is an accidental-regression guard, not a sandbox for untrusted Python.
    Only the shared file-backed factory may construct QSettings in test code.
    """
    tree = ast.parse(source)
    aliases = {"QSettings"}
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for name in node.names:
                if name.name == "QSettings":
                    aliases.add(name.asname or name.name)
            if node.module == "winreg":
                errors.append(f"{node.lineno}: tests must not access the Windows registry")
            if node.module and node.module.startswith("PySide6") and any(
                name.name == "*" for name in node.names
            ):
                errors.append(f"{node.lineno}: wildcard Qt imports bypass settings isolation review")
        elif isinstance(node, ast.Import):
            if any(name.name == "winreg" for name in node.names):
                errors.append(f"{node.lineno}: tests must not access the Windows registry")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not shared_conftest and node.name in SHARED_FIXTURES:
                errors.append(f"{node.lineno}: {node.name} must use the shared conftest fixture")
            if not shared_conftest:
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and any(
                        keyword.arg == "name"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value in SHARED_FIXTURES
                        for keyword in decorator.keywords
                    ):
                        errors.append(f"{node.lineno}: shared isolation fixtures must not be aliased or replaced")

    # Also follow straightforward aliases assigned after an import.
    previous = set()
    while previous != aliases:
        previous = aliases.copy()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if (isinstance(value, ast.Name) and value.id in aliases) or (
                isinstance(value, ast.Attribute) and value.attr == "QSettings"
            ):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                aliases.update(target.id for target in targets if isinstance(target, ast.Name))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        settings_call = (
            isinstance(node.func, ast.Name) and node.func.id in aliases
        ) or (
            isinstance(node.func, ast.Attribute) and node.func.attr == "QSettings"
        )
        if not settings_call:
            continue
        # Keep the sole permitted constructor intentionally narrow and auditable.
        filename = node.args[0] if node.args else None
        allowed = (
            shared_conftest
            and len(node.args) == 2
            and not node.keywords
            and isinstance(filename, ast.Call)
            and isinstance(filename.func, ast.Name)
            and filename.func.id == "str"
            and len(filename.args) == 1
            and isinstance(filename.args[0], ast.Name)
            and filename.args[0].id == "settings_path"
            and isinstance(node.args[1], ast.Attribute)
            and node.args[1].attr == "IniFormat"
        )
        if not allowed:
            errors.append(f"{node.lineno}: use isolated_settings_factory, not a QSettings constructor")
    return errors


def verify_test_isolation(project_root: Path = PROJECT_ROOT) -> int:
    """Inspect test sources before importing/collecting any test module."""
    test_root = project_root.resolve() / "tests"
    checked = 0
    failures = []
    for path in sorted(test_root.rglob("*.py")):
        if not path.resolve().is_relative_to(test_root):
            raise TestIsolationError("Test sources must not escape the test directory")
        relative = path.relative_to(project_root.resolve()).as_posix()
        try:
            errors = check_source(
                path.read_text(encoding="utf-8-sig"),
                shared_conftest=relative == "tests/conftest.py",
            )
        except SyntaxError as exc:
            raise TestIsolationError(f"Cannot check {relative}: {exc}") from exc
        failures.extend(f"{relative}:{error}" for error in errors)
        checked += 1
    if failures:
        raise TestIsolationError("Unsafe test settings access:\n" + "\n".join(failures))
    return checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    try:
        count = verify_test_isolation(args.project_root)
    except TestIsolationError as exc:
        parser.error(str(exc))
    print(f"Verified settings isolation policy in {count} test source files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
