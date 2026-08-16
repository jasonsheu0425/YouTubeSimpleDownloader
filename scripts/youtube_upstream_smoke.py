from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import re
import sys
import time
from typing import Any

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(PROJECT_SRC))

from yt_dlp import YoutubeDL

from ytsimpledownloader.download_errors import DownloadErrorInfo, DownloadErrorKind, classify_download_error
from ytsimpledownloader.network_security import validate_youtube_url
from ytsimpledownloader.yt_dlp_runtime import (
    YtDlpRuntimeDiagnostics,
    collect_runtime_diagnostics,
    javascript_runtime_options,
)


SOCKET_TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 5
CONFIGURATION_ERROR_EXIT = 2
RUNTIME_ERROR_EXIT = 3
EXTRACTION_ERROR_EXIT = 1
VIDEO_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{11}\Z")


class SilentYtDlpLogger:
    def debug(self, _message: str) -> None:
        return

    def warning(self, _message: str) -> None:
        return

    def error(self, _message: str) -> None:
        return


@dataclass(frozen=True)
class SmokeResult:
    exit_code: int
    outcome: str
    target_configured: bool
    attempts: int
    diagnostics: YtDlpRuntimeDiagnostics | None = None
    classification: DownloadErrorInfo | None = None


def validate_video_id(value: str | None) -> str:
    if not isinstance(value, str) or not VIDEO_ID_PATTERN.fullmatch(value):
        raise ValueError("A YouTube video ID must contain exactly 11 URL-safe characters.")
    return value


def canonical_watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def build_metadata_options(diagnostics: YtDlpRuntimeDiagnostics) -> dict[str, Any]:
    options: dict[str, Any] = {
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": SOCKET_TIMEOUT_SECONDS,
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "logger": SilentYtDlpLogger(),
    }
    options.update(javascript_runtime_options(diagnostics))
    return options


def validate_metadata_shape(metadata: object) -> bool:
    if not isinstance(metadata, dict):
        return False
    if not isinstance(metadata.get("id"), str) or not metadata["id"].strip():
        return False
    if not isinstance(metadata.get("title"), str) or not metadata["title"].strip():
        return False
    return any(
        isinstance(metadata.get(key), str) and metadata[key].strip()
        for key in ("extractor", "extractor_key")
    )


def run_smoke(
    video_id_value: str | None,
    *,
    diagnostics_factory=collect_runtime_diagnostics,
    ydl_factory=YoutubeDL,
    sleep=time.sleep,
    retry_delay_seconds: float = RETRY_DELAY_SECONDS,
) -> SmokeResult:
    if not video_id_value:
        return SmokeResult(CONFIGURATION_ERROR_EXIT, "CONFIGURATION_ERROR", False, 0)

    try:
        video_id = validate_video_id(video_id_value)
        clean_target = validate_youtube_url(canonical_watch_url(video_id))
    except ValueError:
        return SmokeResult(CONFIGURATION_ERROR_EXIT, "CONFIGURATION_ERROR", True, 0)

    diagnostics = diagnostics_factory()
    if not diagnostics.node.supported:
        return SmokeResult(RUNTIME_ERROR_EXIT, "RUNTIME_FAILURE", True, 0, diagnostics)

    options = build_metadata_options(diagnostics)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with ydl_factory(options) as ydl:
                metadata = ydl.extract_info(clean_target, download=False)
        except Exception as exc:
            classification = classify_download_error(exc)
            if (
                classification.kind in {DownloadErrorKind.NETWORK, DownloadErrorKind.TIMEOUT}
                and attempt < MAX_ATTEMPTS
            ):
                sleep(retry_delay_seconds)
                continue
            return SmokeResult(EXTRACTION_ERROR_EXIT, "EXTRACTION_FAILURE", True, attempt, diagnostics, classification)

        if not validate_metadata_shape(metadata):
            return SmokeResult(EXTRACTION_ERROR_EXIT, "METADATA_INVALID", True, attempt, diagnostics)
        return SmokeResult(0, "PASS", True, attempt, diagnostics)

    raise AssertionError("The bounded smoke retry loop must return from an attempt.")


def summary_text(result: SmokeResult) -> str:
    lines = [
        "## YouTube Upstream Metadata Smoke",
        f"Python: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        f"Target configured: {'yes' if result.target_configured else 'no'}",
        f"Attempt: {result.attempts}/{MAX_ATTEMPTS}",
        f"Metadata extraction: {'PASS' if result.outcome == 'PASS' else 'FAIL'}",
        f"Outcome: {result.outcome}",
    ]
    if result.diagnostics is not None:
        node = result.diagnostics.node
        lines.insert(2, f"yt-dlp: {result.diagnostics.yt_dlp_version or 'unavailable'}")
        lines.insert(3, f"Node: {node.version or 'unavailable'} / {node.status}")
    if result.classification is not None:
        lines.append(f"Classification: {result.classification.kind.value.upper()}")
    return "\n".join(lines) + "\n"


def write_summary(result: SmokeResult, summary_path: str | None = None) -> None:
    path = summary_path if summary_path is not None else os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        Path(path).write_text(summary_text(result), encoding="utf-8")
    except OSError:
        return


def main() -> int:
    result = run_smoke(os.environ.get("YOUTUBE_UPSTREAM_SMOKE_VIDEO_ID"))
    print(summary_text(result), end="")
    write_summary(result)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
