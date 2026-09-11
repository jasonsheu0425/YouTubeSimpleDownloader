"""Verify that external GitHub Actions use reviewed immutable revisions."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIRECTORY = Path(".github/workflows")
FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
USES_PATTERN = re.compile(
    r"^\s*(?:-\s+)?uses:\s*(?P<action>[^@\s]+)@(?P<reference>[^\s#]+)"
    r"(?:\s+#\s*(?P<release>[^\s]+))?\s*$"
)


@dataclass(frozen=True)
class ActionPin:
    release: str
    commit: str


ACTION_PINS = {
    "actions/checkout": ActionPin(
        release="v7.0.1",
        commit="3d3c42e5aac5ba805825da76410c181273ba90b1",
    ),
    "actions/setup-python": ActionPin(
        release="v7.0.0",
        commit="5fda3b95a4ea91299a34e894583c3862153e4b97",
    ),
    "actions/setup-node": ActionPin(
        release="v7.0.0",
        commit="820762786026740c76f36085b0efc47a31fe5020",
    ),
}


class WorkflowActionPinError(RuntimeError):
    """Raised when a workflow has an unreviewed or mutable action reference."""


def discover_workflow_paths(project_root: Path = PROJECT_ROOT) -> tuple[Path, ...]:
    """Return every tracked-style YAML workflow path under ``.github/workflows``."""
    workflow_directory = project_root / WORKFLOW_DIRECTORY
    return tuple(
        path.relative_to(project_root)
        for path in sorted(
            (
                *workflow_directory.rglob("*.yml"),
                *workflow_directory.rglob("*.yaml"),
            )
        )
        if path.is_file()
    )


def verify_workflow_action_pins(
    project_root: Path = PROJECT_ROOT,
    workflow_paths: tuple[Path, ...] | None = None,
) -> int:
    """Validate every external ``uses:`` reference in the selected workflows."""
    checked = 0
    workflow_paths = workflow_paths or discover_workflow_paths(project_root)

    for relative_path in workflow_paths:
        workflow_path = project_root / relative_path
        try:
            lines = workflow_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise WorkflowActionPinError(f"Unable to read workflow {relative_path}: {exc}") from exc

        for line_number, line in enumerate(lines, start=1):
            match = USES_PATTERN.match(line)
            if not match:
                continue

            action = match.group("action")
            if action.startswith("./"):
                continue

            reference = match.group("reference")
            release = match.group("release")
            location = f"{relative_path}:{line_number}"

            if not FULL_SHA_PATTERN.fullmatch(reference):
                raise WorkflowActionPinError(
                    f"{location} uses mutable action reference {action}@{reference}."
                )

            expected = ACTION_PINS.get(action)
            if expected is None:
                raise WorkflowActionPinError(f"{location} uses unreviewed external action {action}.")
            if reference != expected.commit:
                raise WorkflowActionPinError(
                    f"{location} pins {action} to {reference}, expected {expected.commit}."
                )
            if release != expected.release:
                raise WorkflowActionPinError(
                    f"{location} records release {release!r}, expected {expected.release!r}."
                )
            checked += 1

    if checked == 0:
        raise WorkflowActionPinError("No external action references were checked.")
    return checked


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify reviewed immutable GitHub Action revisions."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root containing the workflow files.",
    )
    args = parser.parse_args()

    try:
        checked = verify_workflow_action_pins(args.project_root)
    except WorkflowActionPinError as exc:
        parser.error(str(exc))

    print(f"Verified {checked} immutable GitHub Action references.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
