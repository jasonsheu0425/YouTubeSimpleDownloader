from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import ytsimpledownloader.app as app_module
from ytsimpledownloader.downloader import VideoInfo


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    application = QApplication.instance() or QApplication([])
    yield application


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
        monkeypatch.setattr(window, "video_info_for_start", lambda _url, _output: info)
        monkeypatch.setattr(window, "ask_file_exists_action", lambda _info, _mode: "number")
        monkeypatch.setattr(app_module, "history_downloads_by_video_id", lambda: {})
        monkeypatch.setattr(app_module.DownloadWorker, "start", lambda _worker: None)

        window.start_download()

        assert isinstance(window.worker, app_module.DownloadWorker)
        assert window.worker.mode == "mp3"
        assert window.worker.embed_audio_thumbnail is True
    finally:
        window.worker = None
        window.set_running(False)
        window.close()
