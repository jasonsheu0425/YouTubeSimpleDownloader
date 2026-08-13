from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QListWidgetItem

import ytsimpledownloader.app as app_module
from ytsimpledownloader.downloader import VideoInfo
from ytsimpledownloader.history_store import HistoryLoadResult, HistoryLoadStatus


@pytest.fixture
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> QSettings:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.SystemScope, str(tmp_path))
    settings = QSettings("YouTubeSimpleDownloader", "YouTubeSimpleDownloader")
    settings.clear()
    settings.sync()
    monkeypatch.setattr(app_module, "ensure_default_dirs", lambda: None)
    monkeypatch.setattr(app_module, "HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(app_module, "DEFAULT_DOWNLOAD_DIR", tmp_path)
    return settings


def _unsafe_result(path: Path, status: HistoryLoadStatus) -> HistoryLoadResult:
    return HistoryLoadResult(items=[], status=status, path=path, error=OSError("blocked"))


def _video_info(tmp_path: Path) -> VideoInfo:
    return VideoInfo(
        title="History Test",
        uploader="Test",
        duration=10,
        thumbnail_url="",
        webpage_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        mp3_path=tmp_path / "test.mp3",
        mp4_path=tmp_path / "test.mp4",
    )


@pytest.mark.parametrize(
    "status",
    [HistoryLoadStatus.READ_ERROR, HistoryLoadStatus.RECOVERY_FAILED],
)
def test_refresh_preserves_visible_history_when_read_is_unsafe(
    qapp,
    isolated_settings: QSettings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    status: HistoryLoadStatus,
) -> None:
    window = app_module.MainWindow()
    try:
        window.history_list.addItem(QListWidgetItem("Existing visible history"))
        monkeypatch.setattr(app_module, "load_history_result", lambda: _unsafe_result(tmp_path, status))

        window.refresh_history()

        assert window.history_list.count() == 1
        assert window.history_list.item(0).text() == "Existing visible history"
        expected_key = (
            "history_read_error"
            if status == HistoryLoadStatus.READ_ERROR
            else "history_recovery_failed"
        )
        assert window.t(expected_key) in window.status_box.toPlainText()
    finally:
        window.close()


@pytest.mark.parametrize(
    "operation",
    ["clear", "download", "local"],
)
def test_unsafe_history_state_blocks_all_app_writes(
    qapp,
    isolated_settings: QSettings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    operation: str,
) -> None:
    window = app_module.MainWindow()
    saved = []
    try:
        monkeypatch.setattr(
            app_module,
            "load_history_result",
            lambda: _unsafe_result(tmp_path, HistoryLoadStatus.READ_ERROR),
        )
        monkeypatch.setattr(app_module, "save_history", lambda items: saved.append(items))

        if operation == "clear":
            window.clear_history()
        elif operation == "download":
            window.add_history(
                _video_info(tmp_path),
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                [str(tmp_path / "test.mp3")],
            )
        else:
            window.add_local_history(
                {"title": "Local", "source_path": str(tmp_path / "source.mp4")},
                [str(tmp_path / "result.mp4")],
            )

        assert saved == []
    finally:
        window.close()


def test_history_lookup_returns_empty_without_retrying_unsafe_load(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = []

    def unsafe_load() -> HistoryLoadResult:
        calls.append(True)
        return _unsafe_result(tmp_path, HistoryLoadStatus.READ_ERROR)

    monkeypatch.setattr(app_module, "load_history_result", unsafe_load)

    assert app_module.history_downloads_by_video_id() == {}
    assert calls == [True]


def test_start_download_keeps_unsafe_history_warning_visible(
    qapp,
    isolated_settings: QSettings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = app_module.MainWindow()
    try:
        window.url_input.setPlainText("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        window.skip_downloaded_checkbox.setChecked(False)
        monkeypatch.setattr(
            app_module,
            "load_history_result",
            lambda: _unsafe_result(tmp_path, HistoryLoadStatus.READ_ERROR),
        )
        monkeypatch.setattr(app_module, "history_downloads_by_video_id", lambda *_args: {})
        monkeypatch.setattr(window, "selected_output_dir_or_warn", lambda: tmp_path)
        monkeypatch.setattr(
            window,
            "video_info_for_start",
            lambda _url, _output, _time_range=None: _video_info(tmp_path),
        )
        monkeypatch.setattr(window, "ask_file_exists_action", lambda _info, _mode: "number")
        monkeypatch.setattr(app_module.DownloadWorker, "start", lambda _worker: None)

        window.start_download()

        assert window.worker is not None
        assert window.t("history_read_error") in window.status_box.toPlainText()
    finally:
        window.set_running(False)
        window.close()


def test_recovered_corruption_is_reported_with_backup_path(
    qapp,
    isolated_settings: QSettings,
) -> None:
    app_module.HISTORY_PATH.write_bytes(b"not json")
    window = app_module.MainWindow()
    try:
        status = window.status_box.toPlainText()
        backups = list(app_module.HISTORY_PATH.parent.glob("history.json.corrupt-*.bak"))

        assert len(backups) == 1
        assert str(backups[0]) in status
        assert app_module.HISTORY_PATH.exists() is False
        assert window.history_list.count() == 0
    finally:
        window.close()


@pytest.mark.parametrize("operation", ["clear", "download", "local"])
def test_history_save_failure_is_nonfatal_and_reported(
    qapp,
    isolated_settings: QSettings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    operation: str,
) -> None:
    window = app_module.MainWindow()
    try:
        monkeypatch.setattr(
            app_module,
            "save_history",
            lambda _items: (_ for _ in ()).throw(OSError("disk full")),
        )

        if operation == "clear":
            window.clear_history()
        elif operation == "download":
            window.add_history(
                _video_info(tmp_path),
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                [str(tmp_path / "test.mp3")],
            )
        else:
            window.add_local_history(
                {"title": "Local", "source_path": str(tmp_path / "source.mp4")},
                [str(tmp_path / "result.mp4")],
            )

        assert "disk full" in window.status_box.toPlainText()
    finally:
        window.close()


def test_download_completion_remains_successful_when_history_save_fails(
    qapp,
    isolated_settings: QSettings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "completed.mp3"
    window = app_module.MainWindow()
    try:
        window.notify_checkbox.setChecked(False)
        window.set_running(True)
        monkeypatch.setattr(
            app_module,
            "save_history",
            lambda _items: (_ for _ in ()).throw(OSError("disk full")),
        )

        window.download_finished(
            [
                {
                    "title": "Completed",
                    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "error": "",
                    "results": [("mp3", str(output_path), False)],
                    "info": _video_info(tmp_path),
                }
            ]
        )

        assert window.result_list.count() == 1
        assert "disk full" in window.status_box.toPlainText()
        assert window.start_button.isEnabled() is True
    finally:
        window.close()
