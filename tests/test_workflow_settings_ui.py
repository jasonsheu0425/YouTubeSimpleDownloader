from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QSizePolicy

import ytsimpledownloader.app as app_module
from ytsimpledownloader.downloader import VideoInfo
from ytsimpledownloader.time_range import TimeRange


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


def _set_combo_data(combo, value: str) -> None:
    index = combo.findData(value)
    assert index >= 0
    combo.setCurrentIndex(index)


def _process_layout(qapp: QApplication, window: app_module.MainWindow) -> None:
    window.show()
    qapp.processEvents()
    window.layout().activate()
    qapp.processEvents()


def test_download_type_labels_keep_internal_mode_values(qapp, isolated_settings) -> None:
    window = app_module.MainWindow()
    try:
        assert [window.mode_combo.itemText(index) for index in range(3)] == [
            "只下載音訊",
            "只下載影片",
            "下載音訊與影片",
        ]
        assert [window.mode_combo.itemData(index) for index in range(3)] == ["mp3", "mp4", "both"]
        assert window.mode_label.text() == "下載類型"
    finally:
        window.close()


def test_language_switch_updates_mode_and_field_labels(qapp, isolated_settings) -> None:
    window = app_module.MainWindow()
    try:
        _set_combo_data(window.language_combo, "en")
        assert [window.mode_combo.itemText(index) for index in range(3)] == [
            "Audio only",
            "Video only",
            "Audio and video",
        ]
        assert window.mode_label.text() == "Download Type"
        assert window.mp4_quality_label.text() == "Download Quality Limit"
        assert window.resolution_label.text() == "Transcode Output Resolution"
        assert window.quality_label.text() == "Transcode Quality"
        assert window.video_audio_label.text() == "Audio After Transcode"
    finally:
        window.close()


@pytest.mark.parametrize(
    ("stored_mode", "expected"),
    [("MP3", "只下載音訊"), ("MP4", "只下載影片"), ("MP3 + MP4", "下載音訊與影片")],
)
def test_legacy_history_mode_text_is_displayed_with_current_labels(
    qapp,
    isolated_settings,
    stored_mode: str,
    expected: str,
) -> None:
    app_module.HISTORY_PATH.write_text(
        json.dumps([{"time": "now", "mode": stored_mode, "title": "Test", "paths": []}]),
        encoding="utf-8",
    )
    window = app_module.MainWindow()
    try:
        assert expected in window.history_list.item(0).text()
    finally:
        window.close()


@pytest.mark.parametrize(
    ("saved_value", "expected"),
    [
        ("mp3", "mp3"),
        ("mp4", "mp4"),
        ("both", "both"),
        ("MP3", "mp3"),
        ("MP4", "mp4"),
        ("MP3 + MP4", "both"),
    ],
)
def test_legacy_qsettings_modes_are_loaded(qapp, isolated_settings, saved_value: str, expected: str) -> None:
    isolated_settings.setValue("mode", saved_value)
    isolated_settings.sync()
    window = app_module.MainWindow()
    try:
        assert window.current_download_mode() == expected
    finally:
        window.close()


@pytest.mark.parametrize(
    ("mode", "audio_visible", "video_visible"),
    [("mp3", True, False), ("mp4", False, True), ("both", True, True)],
)
def test_download_type_controls_section_visibility(
    qapp,
    isolated_settings,
    mode: str,
    audio_visible: bool,
    video_visible: bool,
) -> None:
    window = app_module.MainWindow()
    try:
        _set_combo_data(window.mode_combo, mode)
        assert window.audio_settings_panel.isHidden() is not audio_visible
        assert window.video_settings_panel.isHidden() is not video_visible
        assert window.video_processing_panel.isHidden() is not video_visible
    finally:
        window.close()


def test_mp3_only_controls_follow_audio_format_without_losing_cover_choice(qapp, isolated_settings) -> None:
    window = app_module.MainWindow()
    try:
        _set_combo_data(window.mode_combo, "mp3")
        window.embed_audio_thumbnail_checkbox.setChecked(True)
        for audio_format in ("m4a", "opus", "wav", "flac"):
            _set_combo_data(window.audio_format_combo, audio_format)
            assert window.mp3_quality_combo.isEnabled() is False
            assert window.embed_audio_thumbnail_checkbox.isEnabled() is False
            assert window.embed_audio_thumbnail_checkbox.isChecked() is True

        _set_combo_data(window.audio_format_combo, "mp3")
        assert window.mp3_quality_combo.isEnabled() is True
        assert window.embed_audio_thumbnail_checkbox.isEnabled() is True
        assert window.embed_audio_thumbnail_checkbox.isChecked() is True
    finally:
        window.close()


def test_video_processing_and_custom_crf_rules_are_preserved(qapp, isolated_settings) -> None:
    window = app_module.MainWindow()
    try:
        _set_combo_data(window.mode_combo, "mp4")
        _set_combo_data(window.video_processing_combo, "keep")
        assert window.video_processing_combo.isEnabled() is True
        assert window.video_codec_combo.isEnabled() is False

        _set_combo_data(window.video_processing_combo, "transcode")
        assert window.video_codec_combo.isEnabled() is True
        _set_combo_data(window.quality_combo, "balanced")
        assert window.crf_spin.isEnabled() is False
        _set_combo_data(window.quality_combo, "custom")
        assert window.crf_spin.isEnabled() is True

        _set_combo_data(window.video_processing_combo, "osu")
        assert window.video_format_combo.currentData() == "mp4"
        assert window.resolution_combo.currentData() == "720"
        assert window.video_audio_combo.currentData() == "remove"
        assert window.video_format_combo.isEnabled() is False
        assert window.video_audio_combo.isEnabled() is False
    finally:
        window.close()


def test_advanced_settings_default_collapsed_and_toggle_preserves_values(qapp, isolated_settings) -> None:
    window = app_module.MainWindow()
    try:
        _set_combo_data(window.folder_rule_combo, "channel")
        assert window.advanced_toggle_button.isChecked() is False
        assert window.advanced_settings_widget.isHidden() is True

        window.advanced_toggle_button.setChecked(True)
        assert window.advanced_settings_widget.isHidden() is False
        window.advanced_toggle_button.setChecked(False)
        assert window.advanced_settings_widget.isHidden() is True
        assert window.folder_rule_combo.currentData() == "channel"
    finally:
        window.close()


def test_advanced_settings_relayout_after_switching_from_video_to_audio(qapp, isolated_settings) -> None:
    window = app_module.MainWindow()
    try:
        window.resize(1400, 880)
        _set_combo_data(window.mode_combo, "mp4")
        window.advanced_toggle_button.setChecked(True)
        _process_layout(qapp, window)

        advanced_layout = window.advanced_settings_widget.layout()
        file_organization_panel = advanced_layout.itemAt(0).widget()
        download_behavior_panel = advanced_layout.itemAt(1).widget()

        assert window.video_processing_panel.isVisible() is True
        _set_combo_data(window.mode_combo, "mp3")
        _process_layout(qapp, window)

        assert window.video_processing_panel.isHidden() is True
        for panel in (file_organization_panel, download_behavior_panel):
            assert panel.isVisible() is True
            assert panel.height() >= panel.sizeHint().height()

        expected_advanced_height = (
            file_organization_panel.sizeHint().height()
            + download_behavior_panel.sizeHint().height()
            + advanced_layout.spacing()
        )
        assert window.advanced_settings_widget.height() >= expected_advanced_height
        assert window.advanced_toggle_button.isEnabled() is True
        assert window.start_button.isEnabled() is True

        window.advanced_toggle_button.setChecked(False)
        _process_layout(qapp, window)
        assert window.advanced_settings_widget.isHidden() is True

        window.advanced_toggle_button.setChecked(True)
        _process_layout(qapp, window)
        assert window.advanced_settings_widget.isVisible() is True
        for panel in (file_organization_panel, download_behavior_panel):
            assert panel.height() >= panel.sizeHint().height()
    finally:
        window.close()


def test_running_lock_restores_derived_control_state(qapp, isolated_settings) -> None:
    window = app_module.MainWindow()
    try:
        _set_combo_data(window.mode_combo, "mp3")
        _set_combo_data(window.audio_format_combo, "m4a")
        window.advanced_toggle_button.setChecked(True)

        window.set_running(True)
        for widget in (
            window.url_input,
            window.paste_url_button,
            window.clear_url_button,
            window.output_input,
            window.browse_button,
            window.mode_combo,
            window.audio_format_combo,
            window.advanced_toggle_button,
            window.notify_checkbox,
        ):
            assert widget.isEnabled() is False
        assert window.cancel_button.isEnabled() is True

        window.set_running(False)
        assert window.url_input.isEnabled() is True
        assert window.mode_combo.isEnabled() is True
        assert window.audio_format_combo.isEnabled() is True
        assert window.mp3_quality_combo.isEnabled() is False
        assert window.embed_audio_thumbnail_checkbox.isEnabled() is False
        assert window.video_settings_panel.isHidden() is True
        assert window.cancel_button.isEnabled() is False
    finally:
        window.close()


@pytest.mark.parametrize(
    ("mode", "audio_visible", "video_visible"),
    [("mp3", True, False), ("mp4", False, True), ("both", True, True)],
)
def test_preview_paths_follow_download_type(
    qapp,
    isolated_settings,
    mode: str,
    audio_visible: bool,
    video_visible: bool,
) -> None:
    window = app_module.MainWindow()
    try:
        _set_combo_data(window.mode_combo, mode)
        window.clear_preview()
        assert window.mp3_path_label.isHidden() is not audio_visible
        assert window.mp4_path_label.isHidden() is not video_visible
    finally:
        window.close()


def test_start_download_passes_internal_mode_and_cover_value_to_worker(
    qapp,
    isolated_settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = app_module.MainWindow()
    try:
        _set_combo_data(window.mode_combo, "mp3")
        window.embed_audio_thumbnail_checkbox.setChecked(True)
        window.skip_downloaded_checkbox.setChecked(False)
        window.url_input.setPlainText("https://www.youtube.com/watch?v=jNQXAC9IVRw")
        info = VideoInfo(
            title="Test",
            uploader="Test",
            duration=1,
            thumbnail_url="",
            webpage_url="https://www.youtube.com/watch?v=jNQXAC9IVRw",
            mp3_path=tmp_path / "test.mp3",
            mp4_path=tmp_path / "test.mp4",
        )
        monkeypatch.setattr(window, "selected_output_dir_or_warn", lambda: tmp_path)
        monkeypatch.setattr(window, "video_info_for_start", lambda _url, _output, _time_range=None: info)
        monkeypatch.setattr(window, "ask_file_exists_action", lambda _info, _mode: "number")
        monkeypatch.setattr(app_module, "history_downloads_by_video_id", lambda: {})
        monkeypatch.setattr(app_module.DownloadWorker, "start", lambda _worker: None)

        window.start_download()

        assert isinstance(window.worker, app_module.DownloadWorker)
        assert window.worker.mode == "mp3"
        assert window.worker.embed_audio_thumbnail is True
        assert window.worker.time_range is None
    finally:
        window.worker = None
        window.set_running(False)
        window.close()


def test_trim_controls_default_disabled(qapp, isolated_settings) -> None:
    window = app_module.MainWindow()
    try:
        assert window.trim_enabled_checkbox.isChecked() is False
        assert window.trim_start_input.text() == "00:00"
        assert window.trim_end_input.text() == ""
        assert window.trim_start_input.isEnabled() is False
        assert window.trim_end_input.isEnabled() is False
        assert window.trim_duration_value_label.text() == "00:00"
    finally:
        window.close()


def test_trim_qsettings_save_and_restore(qapp, isolated_settings) -> None:
    window = app_module.MainWindow()
    window.trim_enabled_checkbox.setChecked(True)
    window.trim_start_input.setText("00:30")
    window.trim_end_input.setText("01:30")
    window.settings.sync()
    isolated_settings.sync()
    assert isolated_settings.value("trim_enabled") == "true"
    assert isolated_settings.value("trim_start") == "00:30"
    assert isolated_settings.value("trim_end") == "01:30"
    window.close()

    restored = app_module.MainWindow()
    try:
        assert restored.trim_enabled_checkbox.isChecked() is True
        assert restored.trim_start_input.text() == "00:30"
        assert restored.trim_end_input.text() == "01:30"
        assert restored.requested_time_range() == TimeRange(30, 90)
    finally:
        restored.close()


def test_invalid_saved_trim_settings_fall_back_safely(qapp, isolated_settings) -> None:
    isolated_settings.setValue("trim_enabled", "true")
    isolated_settings.setValue("trim_start", "00:30")
    isolated_settings.setValue("trim_end", "not-a-time")
    isolated_settings.sync()

    window = app_module.MainWindow()
    try:
        assert window.trim_enabled_checkbox.isChecked() is False
        assert window.trim_start_input.text() == "00:00"
        assert window.trim_end_input.text() == ""
        assert window.trim_start_input.isEnabled() is False
    finally:
        window.close()


@pytest.mark.parametrize("start", ["", "00:00"])
def test_trim_start_blank_or_zero_is_valid(qapp, isolated_settings, start: str) -> None:
    window = app_module.MainWindow()
    try:
        window.trim_enabled_checkbox.setChecked(True)
        window.trim_start_input.setText(start)
        window.trim_end_input.setText("00:30")

        assert window.requested_time_range() == TimeRange(0, 30)
        assert window.trim_duration_value_label.text() == "00:30"
    finally:
        window.close()


@pytest.mark.parametrize(
    ("start", "end", "message_key"),
    [
        ("00:00", "", "trim_error_end_required"),
        ("00:30", "00:30", "trim_error_end_after_start"),
        ("01:00", "00:30", "trim_error_end_after_start"),
    ],
)
def test_invalid_trim_range_is_rejected_before_download(
    qapp,
    isolated_settings,
    monkeypatch: pytest.MonkeyPatch,
    start: str,
    end: str,
    message_key: str,
) -> None:
    window = app_module.MainWindow()
    warnings = []
    try:
        window.trim_enabled_checkbox.setChecked(True)
        window.trim_start_input.setText(start)
        window.trim_end_input.setText(end)
        window.url_input.setPlainText("https://www.youtube.com/watch?v=jNQXAC9IVRw")
        monkeypatch.setattr(
            app_module.QMessageBox,
            "warning",
            lambda _parent, _title, message: warnings.append(message),
        )

        window.start_download()

        assert window.worker is None
        assert warnings == [window.t(message_key)]
    finally:
        window.close()


def test_trim_end_after_known_duration_is_rejected(
    qapp,
    isolated_settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = app_module.MainWindow()
    warnings = []
    try:
        window.trim_enabled_checkbox.setChecked(True)
        window.trim_start_input.setText("00:00")
        window.trim_end_input.setText("00:30")
        window.skip_downloaded_checkbox.setChecked(False)
        window.url_input.setPlainText("https://www.youtube.com/watch?v=jNQXAC9IVRw")
        info = VideoInfo(
            title="Test",
            uploader="Test",
            duration=10,
            thumbnail_url="",
            webpage_url="https://www.youtube.com/watch?v=jNQXAC9IVRw",
            mp3_path=tmp_path / "test_trim_0s-30s.mp3",
            mp4_path=tmp_path / "test_trim_0s-30s.mp4",
        )
        monkeypatch.setattr(window, "selected_output_dir_or_warn", lambda: tmp_path)
        monkeypatch.setattr(window, "video_info_for_start", lambda _url, _output, _time_range=None: info)
        monkeypatch.setattr(
            app_module.QMessageBox,
            "warning",
            lambda _parent, _title, message: warnings.append(message),
        )

        window.start_download()

        assert window.worker is None
        assert warnings == [window.t("trim_error_end_after_duration")]
    finally:
        window.close()


def test_start_download_passes_trim_range_to_worker(
    qapp,
    isolated_settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = app_module.MainWindow()
    try:
        window.trim_enabled_checkbox.setChecked(True)
        window.trim_start_input.setText("00:30")
        window.trim_end_input.setText("01:30")
        window.skip_downloaded_checkbox.setChecked(False)
        window.url_input.setPlainText("https://www.youtube.com/watch?v=jNQXAC9IVRw")
        info = VideoInfo(
            title="Test",
            uploader="Test",
            duration=120,
            thumbnail_url="",
            webpage_url="https://www.youtube.com/watch?v=jNQXAC9IVRw",
            mp3_path=tmp_path / "test_trim_30s-90s.mp3",
            mp4_path=tmp_path / "test_trim_30s-90s.mp4",
        )
        monkeypatch.setattr(window, "selected_output_dir_or_warn", lambda: tmp_path)
        monkeypatch.setattr(window, "video_info_for_start", lambda _url, _output, _time_range=None: info)
        monkeypatch.setattr(window, "ask_file_exists_action", lambda _info, _mode: "number")
        monkeypatch.setattr(app_module, "history_downloads_by_video_id", lambda: {})
        monkeypatch.setattr(app_module.DownloadWorker, "start", lambda _worker: None)

        window.start_download()

        assert isinstance(window.worker, app_module.DownloadWorker)
        assert window.worker.time_range == TimeRange(30, 90)
    finally:
        window.worker = None
        window.set_running(False)
        window.close()


def test_trim_controls_follow_running_lock(qapp, isolated_settings) -> None:
    window = app_module.MainWindow()
    try:
        window.trim_enabled_checkbox.setChecked(True)
        window.trim_end_input.setText("00:30")

        window.set_running(True)
        assert window.trim_enabled_checkbox.isEnabled() is False
        assert window.trim_start_input.isEnabled() is False
        assert window.trim_end_input.isEnabled() is False

        window.set_running(False)
        assert window.trim_enabled_checkbox.isEnabled() is True
        assert window.trim_start_input.isEnabled() is True
        assert window.trim_end_input.isEnabled() is True
    finally:
        window.close()


def test_trim_labels_update_with_language(qapp, isolated_settings) -> None:
    window = app_module.MainWindow()
    try:
        window.trim_enabled_checkbox.setChecked(True)
        window.trim_start_input.setText("00:30")
        window.trim_end_input.setText("01:30")
        window.update_trim_preview()

        _set_combo_data(window.language_combo, "en")
        assert window.trim_section_title_label.text() == "Time Range (Optional)"
        assert window.trim_enabled_checkbox.text() == "Download only the selected segment"
        assert window.trim_start_label.text() == "Start"
        assert window.trim_end_label.text() == "End"
        assert window.trim_duration_label.text() == "Segment duration"
        assert "00:30 → 01:30" in window.trim_preview_label.text()

        _set_combo_data(window.language_combo, "zh")
        assert window.trim_section_title_label.text() == "時間範圍（可選）"
        assert window.trim_enabled_checkbox.text() == "只下載指定片段"
        assert "00:30 → 01:30" in window.trim_preview_label.text()
    finally:
        window.close()


@pytest.mark.parametrize(
    "url_text",
    [
        "https://www.youtube.com/watch?v=jNQXAC9IVRw\nhttps://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/playlist?list=PL1234567890abcdef",
    ],
)
def test_trim_is_clearly_disabled_for_multi_url_or_playlist(
    qapp,
    isolated_settings,
    url_text: str,
) -> None:
    window = app_module.MainWindow()
    try:
        window.trim_enabled_checkbox.setChecked(True)
        window.trim_end_input.setText("00:30")
        window.url_input.setPlainText(url_text)
        window.schedule_preview()

        assert window.trim_enabled_checkbox.isEnabled() is False
        assert window.trim_enabled_checkbox.isChecked() is False
        assert window.trim_scope_hint_label.isHidden() is False
        assert window.trim_scope_hint_label.text() == window.t("trim_single_video_only")
    finally:
        window.close()


def test_trim_is_disabled_for_single_item_expanded_from_playlist(qapp, isolated_settings) -> None:
    window = app_module.MainWindow()
    try:
        window.trim_enabled_checkbox.setChecked(True)
        window.trim_end_input.setText("00:30")
        window.download_queue = [
            app_module.QueueTask(
                url="https://www.youtube.com/watch?v=jNQXAC9IVRw",
                playlist_title="Test Playlist",
                playlist_index=1,
            )
        ]
        window.refresh_queue()

        assert window.trim_enabled_checkbox.isChecked() is False
        assert window.trim_enabled_checkbox.isEnabled() is False
        assert window.trim_scope_hint_label.isHidden() is False
    finally:
        window.close()


def test_preview_worker_and_labels_use_trim_range(
    qapp,
    isolated_settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = app_module.MainWindow()
    url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    try:
        window.url_input.setPlainText(url)
        window.trim_enabled_checkbox.setChecked(True)
        window.trim_start_input.setText("00:30")
        window.trim_end_input.setText("01:30")
        monkeypatch.setattr(app_module.PreviewWorker, "start", lambda _worker: None)

        window.start_preview()

        assert isinstance(window.preview_worker, app_module.PreviewWorker)
        assert window.preview_worker.time_range == TimeRange(30, 90)
        info = VideoInfo(
            title="Test",
            uploader="Test",
            duration=120,
            thumbnail_url="",
            webpage_url=url,
            mp3_path=tmp_path / "Test_trim_30s-90s.mp3",
            mp4_path=tmp_path / "Test_trim_30s-90s.mp4",
        )
        request_key = window.preview_context_key(url, window.current_output_dir())
        window.preview_finished(url, info, b"", request_key)

        assert "00:30 → 01:30" in window.trim_preview_label.text()
        assert "01:00" in window.trim_preview_label.text()
        assert "_trim_30s-90s" in window.mp3_path_label.text()
        assert "_trim_30s-90s" in window.mp4_path_label.text()
    finally:
        window.preview_worker = None
        window.close()


def test_long_preview_paths_do_not_expand_scrollable_content(
    qapp,
    isolated_settings,
    tmp_path: Path,
) -> None:
    window = app_module.MainWindow()
    url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    long_title = "Very_Long_Video_Title_" * 14
    mp3_path = tmp_path / f"{long_title}_trim_30s-90s.mp3"
    mp4_path = tmp_path / f"{long_title}_trim_30s-90s.mp4"
    try:
        window.resize(1400, 900)
        _set_combo_data(window.mode_combo, "both")
        window.url_input.setPlainText(url)
        window.trim_enabled_checkbox.setChecked(True)
        window.trim_start_input.setText("00:30")
        window.trim_end_input.setText("01:30")
        window.preview_timer.stop()
        info = VideoInfo(
            title=long_title,
            uploader="Test",
            duration=120,
            thumbnail_url="",
            webpage_url=url,
            mp3_path=mp3_path,
            mp4_path=mp4_path,
        )
        request_key = window.preview_context_key(url, window.current_output_dir())

        window.preview_finished(url, info, b"", request_key)
        _process_layout(qapp, window)

        viewport_width = window.content_scroll.viewport().width()
        assert window.content_scroll.horizontalScrollBar().maximum() == 0
        assert window.content_root.minimumSizeHint().width() <= viewport_width
        assert window.queue_group.isVisible() is True
        assert window.trim_end_input.isVisible() is True
        for label, expected_path in (
            (window.mp3_path_label, mp3_path),
            (window.mp4_path_label, mp4_path),
        ):
            assert label.minimumWidth() == 0
            assert label.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored
            assert label.wordWrap() is True
            assert "_trim_30s-90s" in label.text()
            assert str(expected_path) in label.toolTip()
        assert "00:30" in window.trim_preview_label.text()
        assert "01:30" in window.trim_preview_label.text()
        assert "01:00" in window.trim_preview_label.text()
    finally:
        window.close()


def test_preview_rejects_trim_end_after_video_duration(
    qapp,
    isolated_settings,
    tmp_path: Path,
) -> None:
    window = app_module.MainWindow()
    url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    try:
        window.url_input.setPlainText(url)
        window.trim_enabled_checkbox.setChecked(True)
        window.trim_start_input.setText("00:00")
        window.trim_end_input.setText("00:30")
        info = VideoInfo(
            title="Test",
            uploader="Test",
            duration=10,
            thumbnail_url="",
            webpage_url=url,
            mp3_path=tmp_path / "Test_trim_0s-30s.mp3",
            mp4_path=tmp_path / "Test_trim_0s-30s.mp4",
        )
        request_key = window.preview_context_key(url, window.current_output_dir())

        window.preview_finished(url, info, b"", request_key)

        assert window.trim_preview_label.text() == window.t("trim_error_end_after_duration")
        assert window.mp3_path_label.text().endswith(": -")
        assert window.mp4_path_label.text().endswith(": -")
    finally:
        window.close()
