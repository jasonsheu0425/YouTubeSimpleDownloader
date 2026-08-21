from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt
from PySide6.QtWidgets import QApplication

import ytsimpledownloader.app as app_module
from ytsimpledownloader.media_probe import MediaInfo
from ytsimpledownloader.time_range import TimeRange
from ytsimpledownloader.transcoder import TranscodeResult, VideoTranscodeOptions


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


def _source_file(tmp_path: Path) -> Path:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"local clip test source")
    return source


def _media_info(source: Path, duration: float | None = 120.0) -> MediaInfo:
    return MediaInfo(
        path=source,
        container="mov,mp4,m4a,3gp,3g2,mj2",
        video_codec="h264",
        audio_codec="aac",
        width=1280,
        height=720,
        fps=30.0,
        duration=duration,
        has_audio=True,
    )


def _ready_dialog(
    monkeypatch: pytest.MonkeyPatch,
    window: app_module.MainWindow,
    source: Path,
    duration: float | None = 120.0,
) -> app_module.LocalClipDialog:
    monkeypatch.setattr(app_module.LocalClipProbeWorker, "start", lambda _self: None)
    dialog = app_module.LocalClipDialog(window)
    dialog.set_source_path(source)
    assert dialog.probe_worker is not None
    dialog.probe_succeeded(dialog.probe_worker, _media_info(source, duration))
    return dialog


def test_local_clip_dialog_defaults_and_independent_output_folder(
    qapp: QApplication,
    isolated_settings: QSettings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = _source_file(tmp_path)
    window = app_module.MainWindow()
    try:
        dialog = app_module.LocalClipDialog(window)
        assert dialog.start_input.text() == "00:00"
        assert dialog.end_input.text() == ""
        assert dialog.duration_value_label.text() == "00:00"
        assert not dialog.clip_button.isEnabled()
        assert isolated_settings.value("local_clip_source") is None
        assert isolated_settings.value("local_clip_output") is None
        dialog.close()

        dialog = _ready_dialog(monkeypatch, window, source)
        dialog.end_input.setText("01:30")

        assert dialog.source_input.text() == str(source)
        assert dialog.output_input.text() == str(source.parent)
        assert dialog.requested_time_range() == TimeRange(0, 90)
        assert dialog.duration_value_label.text() == "01:30"
        assert dialog.expected_output_label.text().endswith("source_clip_0s-90s.mp4")
        assert dialog.expected_output_label.toolTip() == dialog.expected_output_label.text()
        assert dialog.clip_button.isEnabled()
        assert isolated_settings.value("local_clip_source") is None
        assert isolated_settings.value("local_clip_output") is None
        dialog.close()
    finally:
        window.close()


def test_local_clip_dialog_validates_ranges_and_requires_known_duration(
    qapp: QApplication,
    isolated_settings: QSettings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = _source_file(tmp_path)
    window = app_module.MainWindow()
    try:
        dialog = _ready_dialog(monkeypatch, window, source, duration=120.8)
        assert dialog.duration_seconds == 120
        assert not dialog.clip_button.isEnabled()
        assert "結束時間" in dialog.range_error_label.text()

        dialog.start_input.setText("00:30")
        dialog.end_input.setText("00:30")
        assert "大於開始時間" in dialog.range_error_label.text()
        assert not dialog.clip_button.isEnabled()

        dialog.end_input.setText("02:01")
        assert "不可超過影片長度" in dialog.range_error_label.text()
        assert not dialog.clip_button.isEnabled()

        dialog.start_input.setText("")
        dialog.end_input.setText("01:00")
        assert dialog.requested_time_range() == TimeRange(0, 60)
        assert dialog.clip_button.isEnabled()
        dialog.close()

        unknown = _ready_dialog(monkeypatch, window, source, duration=None)
        assert not unknown.clip_button.isEnabled()
        assert "已知且大於 0" in unknown.range_error_label.text()
        unknown.close()
    finally:
        window.close()


def test_local_clip_dialog_uses_english_labels(
    qapp: QApplication,
    isolated_settings: QSettings,
) -> None:
    window = app_module.MainWindow()
    try:
        language_index = window.language_combo.findData("en")
        assert language_index >= 0
        window.language_combo.setCurrentIndex(language_index)
        dialog = app_module.LocalClipDialog(window)

        assert dialog.windowTitle() == "Local Clip"
        assert dialog.clip_button.text() == "Create Clip"
        assert dialog.start_label.text() == "Start"
        assert dialog.end_label.text() == "End"
        dialog.close()
    finally:
        window.close()


def test_local_clip_dialog_accepts_asynchronous_probe_result(
    qapp: QApplication,
    isolated_settings: QSettings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = _source_file(tmp_path)
    info = _media_info(source)

    class FakeTranscoder:
        ffmpeg_path = "verified-ffmpeg.exe"

        def __init__(self, **_kwargs) -> None:
            pass

    monkeypatch.setattr(app_module, "VideoTranscoder", FakeTranscoder)
    monkeypatch.setattr(app_module, "probe_media", lambda path, ffmpeg_path: info)
    window = app_module.MainWindow()
    try:
        dialog = app_module.LocalClipDialog(window)
        dialog.set_source_path(source)
        worker = dialog.probe_worker
        assert worker is not None
        assert worker.wait(1_000)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qapp.processEvents()

        assert dialog.duration_seconds == 120
        assert "container=" in dialog.media_info_label.text()
        assert dialog.probe_worker is None
        assert not window._local_clip_probe_workers
        dialog.close()
    finally:
        window.close()


def test_local_clip_worker_uses_fixed_single_item_contract(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = _source_file(tmp_path)
    output = tmp_path / "clips"
    output.mkdir()
    time_range = TimeRange(30, 90)
    options = VideoTranscodeOptions.local_clip(time_range)
    media_info = _media_info(source)
    output_path = output / "source_clip_30s-90s.mp4"
    calls: list[dict] = []

    class FakeTranscoder:
        ffmpeg_path = "verified-ffmpeg.exe"

        def __init__(self, **kwargs) -> None:
            calls.append({"init": kwargs})

        def transcode(self, received_source, received_options, **kwargs) -> TranscodeResult:
            calls.append(
                {
                    "source": Path(received_source),
                    "options": received_options,
                    **kwargs,
                }
            )
            return TranscodeResult(output_path, source, media_info)

    monkeypatch.setattr(app_module, "VideoTranscoder", FakeTranscoder)
    monkeypatch.setattr(app_module, "probe_media", lambda *_args: media_info)
    worker = app_module.LocalTranscodeWorker([str(source)], output, options, "number", time_range=time_range)
    successes: list[list[dict]] = []
    failures: list[str] = []
    worker.finished_ok.connect(successes.append)
    worker.failed.connect(failures.append)

    worker.run()

    assert failures == []
    assert len(successes) == 1
    entry = successes[0][0]
    assert entry["local_clip"] is True
    assert entry["time_range"] == time_range
    assert entry["transcode_options"] == options
    assert [tuple(result) for result in entry["results"]] == [("mp4", str(output_path), False)]
    transcode_call = calls[1]
    assert transcode_call["time_range"] == time_range
    assert transcode_call["file_exists_action"] == "number"
    assert transcode_call["output_dir"] == output


def test_local_clip_start_uses_fixed_profile_and_running_lock(
    qapp: QApplication,
    isolated_settings: QSettings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = _source_file(tmp_path)
    output = tmp_path / "clips"
    output.mkdir()
    window = app_module.MainWindow()
    try:
        global_output = window.output_input.text()
        monkeypatch.setattr(app_module.LocalTranscodeWorker, "start", lambda _self: None)
        window.start_local_clip(str(source), str(output), TimeRange(30, 90))

        assert isinstance(window.worker, app_module.LocalTranscodeWorker)
        assert window.worker.time_range == TimeRange(30, 90)
        assert window.worker.output_dir == output
        assert window.worker.options == VideoTranscodeOptions.local_clip(TimeRange(30, 90))
        assert window.worker.file_exists_action == "number"
        assert not window.local_clip_button.isEnabled()
        assert not window.add_local_video_button.isEnabled()
        assert window.output_input.text() == global_output
        assert not window.trim_enabled_checkbox.isChecked()
        assert window.download_queue == []
        assert isolated_settings.value("local_clip_source") is None
        assert isolated_settings.value("local_clip_output") is None
        window.set_running(False)
        window.worker = None
    finally:
        window.close()


def test_local_clip_success_preserves_result_path_and_writes_trimmed_local_history(
    qapp: QApplication,
    isolated_settings: QSettings,
    tmp_path: Path,
) -> None:
    source = _source_file(tmp_path)
    output = tmp_path / "clips" / "source_clip_30s-90s.mp4"
    output.parent.mkdir()
    time_range = TimeRange(30, 90)
    options = VideoTranscodeOptions.local_clip(time_range)
    window = app_module.MainWindow()
    try:
        window.notify_checkbox.setChecked(False)
        window.download_finished(
            [
                {
                    "index": 1,
                    "title": source.stem,
                    "url": "",
                    "source_path": str(source),
                    "source_media_info": _media_info(source),
                    "media_info": _media_info(output),
                    "error": "",
                    "results": [("mp4", str(output), False)],
                    "local_clip": True,
                    "time_range": time_range,
                    "transcode_options": options,
                }
            ]
        )

        result_row = window.result_list.item(0)
        assert "剪輯範圍：00:30 → 01:30（片段長度：01:00）" in result_row.text()
        assert result_row.data(Qt.ItemDataRole.UserRole) == str(output)
        assert window.selected_result_path() == output

        records = json.loads(app_module.HISTORY_PATH.read_text(encoding="utf-8"))
        record = records[0]
        assert record["schema_version"] == 3
        assert record["mode"] == "Local Clip"
        assert record["local_clip"] is True
        assert record["source_path"] == str(source)
        assert record["paths"] == [str(output)]
        assert record["trimmed"] is True
        assert record["trim_start_seconds"] == 30
        assert record["trim_end_seconds"] == 90
        assert record["trim_duration_seconds"] == 60
        assert record["video_codec"] == "h264"
        assert record["crf"] == 20
        assert record["preset"] == "medium"
        assert "剪輯範圍" in window.history_list.item(0).text()

        language_index = window.language_combo.findData("en")
        assert language_index >= 0
        window.language_combo.setCurrentIndex(language_index)
        assert "Clip range: 00:30 → 01:30 (Duration: 01:00)" in window.history_list.item(0).text()
    finally:
        window.close()


def test_local_clip_malformed_history_is_nonfatal_and_failure_avoids_download_taxonomy(
    qapp: QApplication,
    isolated_settings: QSettings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = _source_file(tmp_path)
    app_module.HISTORY_PATH.write_text(
        json.dumps(
            [
                {
                    "schema_version": 3,
                    "time": "2026-08-22 10:00:00",
                    "mode": "Local Clip",
                    "title": source.stem,
                    "paths": [str(tmp_path / "missing.mp4")],
                    "local_clip": True,
                    "trimmed": True,
                    "trim_start_seconds": 30,
                }
            ]
        ),
        encoding="utf-8",
    )
    window = app_module.MainWindow()
    try:
        assert window.history_list.count() == 1
        assert "剪輯範圍" not in window.history_list.item(0).text()

        monkeypatch.setattr(app_module, "friendly_error", lambda *_args: pytest.fail("download taxonomy used"))
        window.set_running(True)
        window.local_clip_failed("permission denied")

        assert "輸出資料夾沒有寫入權限" in window.status_box.toPlainText()
        assert "Local Clip diagnostic: permission denied" in window.status_box.toPlainText()
        assert window.result_list.count() == 0
        assert not window._running
        history_before_cancel = app_module.HISTORY_PATH.read_text(encoding="utf-8")
        window.set_running(True)
        window.local_clip_failed("Transcode cancelled by user")
        assert "本機影片裁剪已取消" in window.status_box.toPlainText()
        assert window.result_list.count() == 0
        assert app_module.HISTORY_PATH.read_text(encoding="utf-8") == history_before_cancel
    finally:
        window.close()
