from __future__ import annotations

import ytsimpledownloader.app as app_module
import ytsimpledownloader.result_display as result_display
from ytsimpledownloader.time_range import TimeRange


ZH_TRIM_TEMPLATE = "裁剪範圍：{start} → {end}（片段長度：{duration}）"
EN_TRIM_TEMPLATE = "Trim range: {start} → {end} (Duration: {duration})"


def test_display_label_uses_extension_and_mode_fallbacks() -> None:
    assert result_display.display_label_for_result("mp3", "song.mp3") == "MP3"
    assert result_display.display_label_for_result("mp4", "movie.mp4") == "MP4"
    assert result_display.display_label_for_result("mp3", "no-extension") == "AUDIO"
    assert result_display.display_label_for_result("mp4", "no-extension") == "VIDEO"
    assert result_display.display_label_for_result("custom", "file.unknown") == "UNKNOWN"


def test_full_result_text_does_not_include_trim() -> None:
    assert result_display.format_result_item_text(
        "mp3",
        "C:/output/full.mp3",
        prefix="",
        skipped=False,
        skipped_label="已跳過",
        time_range=None,
        trim_template=ZH_TRIM_TEMPLATE,
    ) == "MP3: C:/output/full.mp3"


def test_trimmed_result_text_appends_range() -> None:
    assert result_display.format_result_item_text(
        "mp4",
        "C:/output/trimmed.mp4",
        prefix="",
        skipped=False,
        skipped_label="skipped",
        time_range=TimeRange(30, 90),
        trim_template=EN_TRIM_TEMPLATE,
    ) == "MP4: C:/output/trimmed.mp4 | Trim range: 00:30 → 01:30 (Duration: 01:00)"


def test_skipped_batch_result_keeps_prefix_and_label_order() -> None:
    assert result_display.format_result_item_text(
        "mp3",
        "C:/output/skipped.mp3",
        prefix="2. Batch title - ",
        skipped=True,
        skipped_label="已跳過",
        time_range=TimeRange(0, 10),
        trim_template=ZH_TRIM_TEMPLATE,
    ) == "2. Batch title - MP3: C:/output/skipped.mp3 (已跳過) | 裁剪範圍：00:00 → 00:10（片段長度：00:10）"


def test_full_history_text_uses_localized_mode_without_trim() -> None:
    assert result_display.format_history_item_text(
        "2026-08-01 10:00:00",
        "MP3",
        "History title",
        "zh",
        time_range=None,
        trim_template=ZH_TRIM_TEMPLATE,
    ) == "2026-08-01 10:00:00 | 只下載音訊 | History title"


def test_trimmed_history_text_uses_english_mode_and_range() -> None:
    assert result_display.format_history_item_text(
        "2026-08-01 10:00:00",
        "MP4",
        "History title",
        "en",
        time_range=TimeRange(30, 90),
        trim_template=EN_TRIM_TEMPLATE,
    ) == "2026-08-01 10:00:00 | Video only | History title | Trim range: 00:30 → 01:30 (Duration: 01:00)"


def test_local_transcode_mode_remains_unchanged() -> None:
    assert result_display.format_history_item_text(
        "now",
        "Local Transcode",
        "Local file",
        "zh",
        time_range=None,
        trim_template=ZH_TRIM_TEMPLATE,
    ) == "now | Local Transcode | Local file"


def test_app_keeps_result_display_compatibility_bindings() -> None:
    assert app_module.display_label_for_result is result_display.display_label_for_result
    assert app_module.format_trim_range_display is result_display.format_trim_range_display
