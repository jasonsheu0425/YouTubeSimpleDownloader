from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

import ytsimpledownloader.app as app_module
from ytsimpledownloader.time_range import TimeRange


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


def _set_language(window: app_module.MainWindow, language: str) -> None:
    index = window.language_combo.findData(language)
    assert index >= 0
    window.language_combo.setCurrentIndex(index)


def _result_entry(path: Path, time_range: TimeRange | None = None) -> dict:
    return {
        "index": 1,
        "title": "Display Test",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "error": "",
        "results": [("mp3", str(path), False)],
        "time_range": time_range,
    }


def test_full_result_does_not_show_trim_range_and_keeps_action_path(
    qapp: QApplication,
    isolated_settings: QSettings,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "full.mp3"
    window = app_module.MainWindow()
    try:
        window.notify_checkbox.setChecked(False)
        window.download_finished([_result_entry(output_path)])

        row = window.result_list.item(0)
        assert "裁剪範圍" not in row.text()
        assert "Trim range" not in row.text()
        assert row.data(Qt.ItemDataRole.UserRole) == str(output_path)
        assert window.selected_result_path() == output_path
    finally:
        window.close()


def test_trimmed_result_shows_range_and_duration_in_current_language(
    qapp: QApplication,
    isolated_settings: QSettings,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "trimmed.mp3"
    window = app_module.MainWindow()
    try:
        window.notify_checkbox.setChecked(False)
        window.download_finished([_result_entry(output_path, TimeRange(30, 90))])

        row = window.result_list.item(0)
        assert "裁剪範圍：00:30 → 01:30（片段長度：01:00）" in row.text()
        assert row.data(Qt.ItemDataRole.UserRole) == str(output_path)

        _set_language(window, "en")
        second_path = tmp_path / "trimmed-en.mp3"
        window.download_finished([_result_entry(second_path, TimeRange(30, 90))])
        assert "Trim range: 00:30 → 01:30 (Duration: 01:00)" in window.result_list.item(1).text()
        assert window.result_list.item(1).data(Qt.ItemDataRole.UserRole) == str(second_path)
    finally:
        window.close()


def test_history_displays_only_valid_trim_metadata_and_keeps_paths(
    qapp: QApplication,
    isolated_settings: QSettings,
    tmp_path: Path,
) -> None:
    paths = [tmp_path / name for name in ("full.mp3", "trimmed.mp3", "legacy.mp3", "missing.mp3", "malformed.mp3")]
    records = [
        {
            "schema_version": 3,
            "time": "2026-07-31 10:00:00",
            "mode": "mp3",
            "title": "Full",
            "paths": [str(paths[0])],
            "trimmed": False,
        },
        {
            "schema_version": 3,
            "time": "2026-07-31 10:01:00",
            "mode": "mp3",
            "title": "Trimmed",
            "paths": [str(paths[1])],
            "trimmed": True,
            "trim_start_seconds": 30,
            "trim_end_seconds": 90,
            "trim_duration_seconds": 60,
        },
        {
            "schema_version": 2,
            "time": "2026-07-31 10:02:00",
            "mode": "MP3",
            "title": "Legacy",
            "paths": [str(paths[2])],
        },
        {
            "schema_version": 3,
            "time": "2026-07-31 10:03:00",
            "mode": "mp3",
            "title": "Missing fields",
            "paths": [str(paths[3])],
            "trimmed": True,
            "trim_start_seconds": 30,
        },
        {
            "schema_version": 3,
            "time": "2026-07-31 10:04:00",
            "mode": "mp3",
            "title": "Malformed",
            "paths": [str(paths[4])],
            "trimmed": True,
            "trim_start_seconds": 90,
            "trim_end_seconds": 30,
            "trim_duration_seconds": -60,
        },
    ]
    app_module.HISTORY_PATH.write_text(json.dumps(records), encoding="utf-8")

    window = app_module.MainWindow()
    try:
        assert window.history_list.count() == len(records)
        assert "裁剪範圍" not in window.history_list.item(0).text()
        assert "裁剪範圍：00:30 → 01:30（片段長度：01:00）" in window.history_list.item(1).text()
        assert "裁剪範圍" not in window.history_list.item(2).text()
        assert "裁剪範圍" not in window.history_list.item(3).text()
        assert "裁剪範圍" not in window.history_list.item(4).text()
        assert window.history_list.item(1).data(Qt.ItemDataRole.UserRole) == str(paths[1])
    finally:
        window.close()


def test_language_switch_reformats_trimmed_history(
    qapp: QApplication,
    isolated_settings: QSettings,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "trimmed.mp4"
    app_module.HISTORY_PATH.write_text(
        json.dumps(
            [
                {
                    "schema_version": 3,
                    "time": "2026-07-31 11:00:00",
                    "mode": "mp4",
                    "title": "Trimmed",
                    "paths": [str(output_path)],
                    "trimmed": True,
                    "trim_start_seconds": 30,
                    "trim_end_seconds": 90,
                    "trim_duration_seconds": 60,
                }
            ]
        ),
        encoding="utf-8",
    )

    window = app_module.MainWindow()
    try:
        assert "裁剪範圍：00:30 → 01:30（片段長度：01:00）" in window.history_list.item(0).text()
        _set_language(window, "en")
        assert "Trim range: 00:30 → 01:30 (Duration: 01:00)" in window.history_list.item(0).text()
        assert window.history_list.item(0).data(Qt.ItemDataRole.UserRole) == str(output_path)
    finally:
        window.close()
