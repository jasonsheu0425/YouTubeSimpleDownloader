from __future__ import annotations

from pathlib import Path
from urllib.error import URLError

from yt_dlp.utils import ExtractorError

from scripts import youtube_upstream_smoke as smoke
from ytsimpledownloader.download_errors import DownloadErrorKind
from ytsimpledownloader.yt_dlp_runtime import NodeRuntimeDiagnostic, YtDlpRuntimeDiagnostics


VALID_VIDEO_ID = "jNQXAC9IVRw"


def diagnostics(*, supported: bool = True) -> YtDlpRuntimeDiagnostics:
    node = NodeRuntimeDiagnostic(
        found=supported,
        path=r"C:\\Program Files\\nodejs\\node.exe" if supported else "",
        version="22.17.1" if supported else "",
        version_tuple=(22, 17, 1) if supported else None,
        supported=supported,
        status="supported" if supported else "not_found",
        reason="synthetic",
    )
    return YtDlpRuntimeDiagnostics("2026.6.9", True, "synthetic", node)


class FakeYoutubeDL:
    calls: list[tuple[dict, str, bool]] = []
    outcomes: list[object] = []

    def __init__(self, options: dict) -> None:
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def extract_info(self, url: str, *, download: bool):
        self.calls.append((self.options, url, download))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def run(outcomes: list[object], *, supported: bool = True, video_id: str | None = VALID_VIDEO_ID, sleeps: list[float] | None = None):
    FakeYoutubeDL.calls = []
    FakeYoutubeDL.outcomes = list(outcomes)
    return smoke.run_smoke(
        video_id,
        diagnostics_factory=lambda: diagnostics(supported=supported),
        ydl_factory=FakeYoutubeDL,
        sleep=(sleeps.append if sleeps is not None else lambda _delay: None),
    )


def valid_metadata(**overrides: object) -> dict:
    metadata = {"id": "jNQXAC9IVRw", "title": "Synthetic title", "extractor_key": "Youtube"}
    metadata.update(overrides)
    return metadata


def test_missing_video_id_fails_without_constructing_a_downloader() -> None:
    result = run([valid_metadata()], video_id="")

    assert result.exit_code == smoke.CONFIGURATION_ERROR_EXIT
    assert result.outcome == "CONFIGURATION_ERROR"
    assert FakeYoutubeDL.calls == []


def test_invalid_video_ids_fail_without_constructing_a_downloader() -> None:
    invalid_ids = (
        "abc",
        "https://www.youtube.com/watch?v=abcdefghijk",
        "abcdefghijk?x=1",
        "abcdefghijk/",
        "abcdefghijk extra",
        " abcdefghij",
    )

    for video_id in invalid_ids:
        result = run([valid_metadata()], video_id=video_id)

        assert result.exit_code == smoke.CONFIGURATION_ERROR_EXIT
        assert result.outcome == "CONFIGURATION_ERROR"
        assert FakeYoutubeDL.calls == []


def test_valid_video_ids_accept_url_safe_characters() -> None:
    assert smoke.validate_video_id("AbCde_-1234") == "AbCde_-1234"


def test_successful_metadata_extraction_is_download_free_uses_runtime_options_and_constructs_a_canonical_url() -> None:
    result = run([valid_metadata()])

    assert result.exit_code == 0
    assert result.outcome == "PASS"
    options, url, download = FakeYoutubeDL.calls[0]
    assert url == f"https://www.youtube.com/watch?v={VALID_VIDEO_ID}"
    assert download is False
    assert options["skip_download"] is True
    assert options["noplaylist"] is True
    assert options["socket_timeout"] == smoke.SOCKET_TIMEOUT_SECONDS
    assert options["js_runtimes"] == {"node": {"path": r"C:\\Program Files\\nodejs\\node.exe"}}
    assert options["remote_components"] == ["ejs:github"]


def test_invalid_metadata_shape_fails_without_retaining_metadata() -> None:
    for metadata in (valid_metadata(id=""), valid_metadata(title=""), valid_metadata(extractor="", extractor_key="")):
        result = run([metadata])

        assert result.exit_code == smoke.EXTRACTION_ERROR_EXIT
        assert result.outcome == "METADATA_INVALID"


def test_unsupported_runtime_fails_before_extraction() -> None:
    result = run([valid_metadata()], supported=False)

    assert result.exit_code == smoke.RUNTIME_ERROR_EXIT
    assert result.outcome == "RUNTIME_FAILURE"
    assert FakeYoutubeDL.calls == []


def test_network_and_timeout_failures_retry_once_then_succeed(monkeypatch) -> None:
    original_classifier = smoke.classify_download_error
    expected_kinds = {
        ConnectionError: DownloadErrorKind.NETWORK,
        TimeoutError: DownloadErrorKind.TIMEOUT,
    }
    for failure_type, expected_kind in expected_kinds.items():
        seen = []

        def capture_classifier(exc: BaseException):
            result = original_classifier(exc)
            seen.append(result)
            return result

        monkeypatch.setattr(smoke, "classify_download_error", capture_classifier)
        sleeps: list[float] = []
        result = run([failure_type("synthetic failure"), valid_metadata()], sleeps=sleeps)

        assert result.exit_code == 0
        assert result.attempts == 2
        assert len(FakeYoutubeDL.calls) == 2
        assert sleeps == [smoke.RETRY_DELAY_SECONDS]
        assert [item.kind for item in seen] == [expected_kind]


def test_non_retryable_failures_stop_after_one_attempt_with_safe_classification() -> None:
    for failure, expected_kind in (
        (RuntimeError("unknown"), DownloadErrorKind.UNKNOWN),
        (ExtractorError("extractor failed"), DownloadErrorKind.EXTRACTOR),
    ):
        result = run([failure])

        assert result.classification is not None
        assert result.classification.kind is expected_kind
        assert result.attempts == 1


def test_url_error_is_classified_as_network_for_the_bounded_retry(monkeypatch) -> None:
    seen = []
    original_classifier = smoke.classify_download_error

    def capture_classifier(exc: BaseException):
        result = original_classifier(exc)
        seen.append(result)
        return result

    monkeypatch.setattr(smoke, "classify_download_error", capture_classifier)
    result = run([URLError("network"), valid_metadata()])

    assert result.exit_code == 0
    assert result.attempts == 2
    assert [item.kind for item in seen] == [DownloadErrorKind.NETWORK]


def test_video_id_and_exception_details_do_not_appear_in_console_or_summary(tmp_path: Path, capsys) -> None:
    sensitive_error = "https://example.invalid/watch?token=secret C:\\Users\\jason\\private.mp4"
    result = run([RuntimeError(sensitive_error)])
    summary = tmp_path / "summary.md"

    print(smoke.summary_text(result), end="")
    smoke.write_summary(result, str(summary))

    output = capsys.readouterr().out + summary.read_text(encoding="utf-8")
    assert "secret" not in output
    assert "private.mp4" not in output
    assert VALID_VIDEO_ID not in output
    assert "Classification: UNKNOWN" in output


def test_summary_writes_when_available_and_local_execution_without_summary_is_safe(tmp_path: Path, monkeypatch) -> None:
    result = run([valid_metadata()])
    summary = tmp_path / "summary.md"

    smoke.write_summary(result, str(summary))
    assert "Metadata extraction: PASS" in summary.read_text(encoding="utf-8")

    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    smoke.write_summary(result)


def test_workflow_accepts_only_a_video_id_configuration_surface() -> None:
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "youtube-upstream-smoke.yml").read_text(
        encoding="utf-8"
    )

    assert "video_id:" in workflow
    assert "YOUTUBE_UPSTREAM_SMOKE_VIDEO_ID" in workflow
    assert "https://www.youtube.com" not in workflow
    assert "target" + "_url" not in workflow
    assert "YOUTUBE_UPSTREAM_SMOKE_" + "URL" not in workflow
    assert "YOUTUBE_UPSTREAM_SMOKE_" + "TARGET" not in workflow
