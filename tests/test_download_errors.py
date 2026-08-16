from __future__ import annotations

import errno
from pathlib import Path

import pytest
from yt_dlp.utils import DownloadError, ExtractorError, GeoRestrictedError, PostProcessingError, UnsupportedError

import ytsimpledownloader.app as app_module
from ytsimpledownloader.download_errors import (
    DownloadErrorInfo,
    DownloadErrorKind,
    classify_download_error,
)
from ytsimpledownloader.downloader import DownloadCancelled, OutputOptions
from ytsimpledownloader.queue_models import QueueTask
from ytsimpledownloader.transcoder import VideoTranscodeOptions
from ytsimpledownloader.ui_text import TEXT


def test_unknown_exception_has_no_retained_detail() -> None:
    sensitive = "https://example.invalid/video?token=secret C:\\Users\\jason\\Downloads\\private.mp4"

    info = classify_download_error(RuntimeError(sensitive))

    assert info == DownloadErrorInfo(DownloadErrorKind.UNKNOWN)
    assert sensitive not in repr(info)


def test_explicit_cancellation_is_classified_from_the_supplied_project_type() -> None:
    info = classify_download_error(
        DownloadCancelled("Download cancelled by user."),
        cancellation_types=(DownloadCancelled,),
    )

    assert info.kind is DownloadErrorKind.CANCELLED
    assert info.message_key is None


@pytest.mark.parametrize(
    ("exc", "kind", "message_key"),
    [
        (UnsupportedError("https://example.invalid/video"), DownloadErrorKind.UNSUPPORTED_URL, "error_unsupported"),
        (GeoRestrictedError("blocked"), DownloadErrorKind.UNAVAILABLE, "error_unavailable"),
        (ExtractorError("extractor failed"), DownloadErrorKind.EXTRACTOR, None),
        (PostProcessingError("postprocessor failed"), DownloadErrorKind.POSTPROCESSOR, None),
        (DownloadError("download failed"), DownloadErrorKind.UNKNOWN, None),
    ],
)
def test_public_ytdlp_exception_types_are_classified_offline(
    exc: BaseException,
    kind: DownloadErrorKind,
    message_key: str | None,
) -> None:
    assert classify_download_error(exc) == DownloadErrorInfo(kind, message_key)


def test_wrapped_timeout_uses_usable_preserved_exception_info() -> None:
    timeout = TimeoutError("synthetic timeout")
    wrapped = DownloadError("download failed", (TimeoutError, timeout, None))

    assert classify_download_error(wrapped) == DownloadErrorInfo(DownloadErrorKind.TIMEOUT, "error_network")


def test_extractor_error_uses_a_typed_preserved_cause_before_the_generic_extractor_kind() -> None:
    error = ExtractorError("extractor failed", cause=TimeoutError("synthetic timeout"))

    assert classify_download_error(error) == DownloadErrorInfo(DownloadErrorKind.TIMEOUT, "error_network")


@pytest.mark.parametrize(
    "exc_info",
    [
        None,
        (),
        (ValueError, ValueError("unknown"), None),
        (TimeoutError, "not an exception", None),
    ],
)
def test_unusable_or_unknown_wrapped_exception_info_falls_back_without_crashing(exc_info: object) -> None:
    assert classify_download_error(DownloadError("download failed", exc_info)) == DownloadErrorInfo(
        DownloadErrorKind.UNKNOWN
    )


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (TimeoutError("timed out"), DownloadErrorInfo(DownloadErrorKind.TIMEOUT, "error_network")),
        (PermissionError("access denied"), DownloadErrorInfo(DownloadErrorKind.FILESYSTEM, "error_permission")),
        (OSError(errno.ENOSPC, "disk full"), DownloadErrorInfo(DownloadErrorKind.FILESYSTEM)),
        (OSError("unspecified failure"), DownloadErrorInfo(DownloadErrorKind.UNKNOWN)),
    ],
)
def test_direct_python_and_filesystem_exceptions_are_classified(
    exc: BaseException,
    expected: DownloadErrorInfo,
) -> None:
    assert classify_download_error(exc) == expected


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Unsupported URL", DownloadErrorInfo(DownloadErrorKind.UNSUPPORTED_URL, "error_unsupported")),
        ("Video unavailable", DownloadErrorInfo(DownloadErrorKind.UNAVAILABLE, "error_unavailable")),
        ("Private video", DownloadErrorInfo(DownloadErrorKind.ACCESS_REQUIRED, "error_login")),
        ("Sign in to confirm your age", DownloadErrorInfo(DownloadErrorKind.ACCESS_REQUIRED, "error_login")),
        ("Connection reset by peer", DownloadErrorInfo(DownloadErrorKind.UNKNOWN)),
    ],
)
def test_narrow_message_fallback_avoids_broad_legacy_substrings(
    message: str,
    expected: DownloadErrorInfo,
) -> None:
    assert classify_download_error(RuntimeError(message)) == expected


def test_unrelated_failures_are_not_attributed_to_a_javascript_runtime() -> None:
    assert classify_download_error(RuntimeError("unrelated failure")) == DownloadErrorInfo(DownloadErrorKind.UNKNOWN)


def test_preview_worker_emits_structured_error_info(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingDownloader:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def fetch_video_info(self, _url: str):
            raise UnsupportedError("https://example.invalid/video?token=secret")

    monkeypatch.setattr(app_module, "SingleVideoDownloader", FailingDownloader)
    failures: list[DownloadErrorInfo] = []
    worker = app_module.PreviewWorker(
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        tmp_path,
        OutputOptions(),
        "mp3",
        "mp4",
        VideoTranscodeOptions(),
    )
    worker.failed.connect(failures.append)

    worker.run()

    assert failures == [DownloadErrorInfo(DownloadErrorKind.UNSUPPORTED_URL, "error_unsupported")]


def test_direct_preview_uses_structured_error_info_for_its_user_message(
    qapp,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingDownloader:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def fetch_video_info(self, _url: str):
            raise UnsupportedError("https://example.invalid/video?token=secret")

    class PreviewHarness:
        current_info = None
        current_info_url = ""
        current_info_key = ""
        language = "en"

        @staticmethod
        def preview_context_key(url: str, output_dir: Path) -> tuple[str, Path]:
            return url, output_dir

        @staticmethod
        def output_options() -> OutputOptions:
            return OutputOptions()

        @staticmethod
        def current_audio_format() -> str:
            return "mp3"

        @staticmethod
        def current_video_format() -> str:
            return "mp4"

        @staticmethod
        def current_video_transcode_options() -> VideoTranscodeOptions:
            return VideoTranscodeOptions()

        def preview_finished(self, *_args) -> None:
            raise AssertionError("preview_finished must not be called after an error")

        @staticmethod
        def t(key: str) -> str:
            return TEXT["en"][key]

    monkeypatch.setattr(app_module, "SingleVideoDownloader", FailingDownloader)
    warnings = []
    monkeypatch.setattr(app_module.QMessageBox, "warning", lambda *_args: warnings.append(_args))

    result = app_module.MainWindow.video_info_for_start(
        PreviewHarness(),
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        tmp_path,
    )

    assert result is None
    assert warnings[-1][-1] == TEXT["en"]["error_unsupported"]


def test_download_result_uses_the_structured_message_key_without_raw_details(qapp) -> None:
    window = app_module.MainWindow()
    try:
        window.notify_checkbox.setChecked(False)
        window.download_finished(
            [
                {
                    "index": 1,
                    "title": "Test video",
                    "error": "",
                    "error_info": DownloadErrorInfo(DownloadErrorKind.TIMEOUT, "error_network"),
                    "results": [],
                }
            ]
        )

        assert TEXT[window.language]["error_network"] in window.result_list.item(0).text()
        assert "token" not in window.result_list.item(0).text()
    finally:
        window.preview_timer.stop()
        window.close()


def test_queue_worker_reports_validation_and_playlist_errors_as_structured_info(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingDownloader:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def fetch_playlist_info(self, _url: str):
            raise GeoRestrictedError("blocked")

    monkeypatch.setattr(app_module, "SingleVideoDownloader", FailingDownloader)
    completed = []
    worker = app_module.QueueBuildWorker(
        [
            "https://example.com/watch?v=unsafe",
            "https://www.youtube.com/playlist?list=PL1234567890",
        ],
        tmp_path,
    )
    worker.finished_ok.connect(lambda tasks, errors: completed.append((tasks, errors)))

    worker.run()

    tasks, errors = completed[0]
    assert tasks == []
    assert errors == [
        DownloadErrorInfo(DownloadErrorKind.INVALID_INPUT, "error_unsupported"),
        DownloadErrorInfo(DownloadErrorKind.UNAVAILABLE, "error_unavailable"),
    ]


def _worker(task: QueueTask, tmp_path: Path) -> app_module.DownloadWorker:
    return app_module.DownloadWorker(
        [task],
        tmp_path,
        "mp3",
        "number",
        "192",
        "best",
        "mp3",
        False,
        "mp4",
        VideoTranscodeOptions(),
        OutputOptions(),
        True,
        "Batch {current}/{total}",
        "Download failed",
        "Reading playlist: {url}",
        "Playlist loaded: {title} ({count})",
        False,
        {},
        "Skipped: {url}",
        "Skipped {skipped}",
        "Retry {attempt}/{max}: {url}",
    )


def test_download_worker_preserves_retry_count_and_emits_safe_structured_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    class FailingDownloader:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def fetch_video_info(self, _url: str, *_args):
            calls.append(_url)
            raise TimeoutError("https://example.invalid/video?token=secret")

    monkeypatch.setattr(app_module, "SingleVideoDownloader", FailingDownloader)
    worker = _worker(QueueTask(url="https://www.youtube.com/watch?v=jNQXAC9IVRw", max_retries=1), tmp_path)
    completed = []
    updates = []
    worker.finished_ok.connect(completed.append)
    worker.task_updated.connect(lambda *args: updates.append(args))

    worker.run()

    assert len(calls) == 2
    entries = completed[0]
    assert entries[0]["error"] == ""
    assert entries[0]["error_info"] == DownloadErrorInfo(DownloadErrorKind.TIMEOUT, "error_network")
    structured_updates = [update for update in updates if isinstance(update[3], DownloadErrorInfo)]
    assert [update[4] for update in structured_updates] == [1, 2]
    assert all("secret" not in repr(update[3]) for update in structured_updates)


def test_download_worker_cancellation_is_not_retried_or_reported_as_an_unknown_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    class CancellingDownloader:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def fetch_video_info(self, _url: str, *_args):
            calls.append(_url)
            raise DownloadCancelled("Download cancelled by user.")

    monkeypatch.setattr(app_module, "SingleVideoDownloader", CancellingDownloader)
    worker = _worker(QueueTask(url="https://www.youtube.com/watch?v=jNQXAC9IVRw", max_retries=3), tmp_path)
    failures = []
    worker.failed.connect(failures.append)

    worker.run()

    assert len(calls) == 1
    assert failures == [DownloadErrorInfo(DownloadErrorKind.CANCELLED)]
