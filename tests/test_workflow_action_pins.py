from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_workflow_action_pins import (
    ACTION_PINS,
    WorkflowActionPinError,
    discover_workflow_paths,
    verify_workflow_action_pins,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = PROJECT_ROOT / "scripts" / "check_workflow_action_pins.py"


def _write_workflow(root: Path, reference: str, release: str = "v7.0.1") -> Path:
    workflow_path = root / ".github" / "workflows" / "test.yml"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(
        "steps:\n"
        "  - uses: actions/checkout@"
        f"{reference} # {release}\n",
        encoding="utf-8",
    )
    return workflow_path.relative_to(root)


def test_repository_workflows_use_only_reviewed_immutable_action_pins() -> None:
    assert verify_workflow_action_pins() == 9


def test_mutable_action_reference_is_rejected(tmp_path: Path) -> None:
    workflow_path = _write_workflow(tmp_path, "v7")

    with pytest.raises(WorkflowActionPinError, match="mutable action reference"):
        verify_workflow_action_pins(tmp_path, (workflow_path,))


def test_unreviewed_action_is_rejected(tmp_path: Path) -> None:
    workflow_path = tmp_path / ".github" / "workflows" / "test.yml"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(
        "steps:\n"
        "  - uses: example/unreviewed@"
        "0123456789abcdef0123456789abcdef01234567 # v1.0.0\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkflowActionPinError, match="unreviewed external action"):
        verify_workflow_action_pins(tmp_path, (workflow_path.relative_to(tmp_path),))


def test_mismatched_reviewed_sha_is_rejected(tmp_path: Path) -> None:
    workflow_path = _write_workflow(tmp_path, "0" * 40)

    with pytest.raises(WorkflowActionPinError, match="expected"):
        verify_workflow_action_pins(tmp_path, (workflow_path,))


def test_release_comment_must_match_reviewed_release(tmp_path: Path) -> None:
    workflow_path = _write_workflow(
        tmp_path,
        ACTION_PINS["actions/checkout"].commit,
        release="v7.0.0",
    )

    with pytest.raises(WorkflowActionPinError, match="records release"):
        verify_workflow_action_pins(tmp_path, (workflow_path,))


def test_cli_reports_verified_references() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT), "--project-root", str(PROJECT_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Verified 9 immutable GitHub Action references." in result.stdout


def test_all_current_workflows_are_discovered() -> None:
    assert discover_workflow_paths() == (
        Path(".github/workflows/test.yml"),
        Path(".github/workflows/youtube-upstream-smoke.yml"),
    )
