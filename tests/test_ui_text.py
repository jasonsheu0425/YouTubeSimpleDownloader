from __future__ import annotations

import ytsimpledownloader.app as app_module
import ytsimpledownloader.ui_text as ui_text


def test_download_mode_helpers_preserve_legacy_values() -> None:
    expected = {
        "mp3": "mp3",
        "mp4": "mp4",
        "both": "both",
        "MP3": "mp3",
        "MP4": "mp4",
        "MP3 + MP4": "both",
    }

    assert {value: ui_text.normalize_download_mode(value) for value in expected} == expected


def test_download_mode_labels_are_unchanged() -> None:
    assert ui_text.download_mode_text("mp3", "zh") == "只下載音訊"
    assert ui_text.download_mode_text("mp4", "zh") == "只下載影片"
    assert ui_text.download_mode_text("both", "zh") == "下載音訊與影片"
    assert ui_text.download_mode_text("mp3", "en") == "Audio only"
    assert ui_text.download_mode_text("mp4", "en") == "Video only"
    assert ui_text.download_mode_text("both", "en") == "Audio and video"


def test_app_keeps_ui_text_compatibility_bindings() -> None:
    for name in (
        "TEXT",
        "MODE_TEXT_KEYS",
        "LEGACY_MODE_VALUES",
        "normalize_download_mode",
        "download_mode_text",
    ):
        assert getattr(app_module, name) is getattr(ui_text, name)
