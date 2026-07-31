from __future__ import annotations

import ytsimpledownloader.app as app_module
import ytsimpledownloader.history_store as history_store
from ytsimpledownloader.time_range import TimeRange


def test_history_schema_version_remains_three() -> None:
    assert history_store.HISTORY_SCHEMA_VERSION == 3


def test_full_download_keys_keep_audio_and_video_formats() -> None:
    assert history_store.download_key_for_mode("mp3", "mp3", "mp4") == "audio:mp3"
    assert history_store.download_key_for_mode("mp4", "mp3", "mp4") == "video:mp4"


def test_trimmed_download_keys_append_range_identity() -> None:
    time_range = TimeRange(30, 90)

    assert history_store.download_key_for_mode("mp3", "mp3", "mp4", time_range) == "audio:mp3:trim:30-90"
    assert history_store.download_key_for_mode("mp4", "mp3", "mp4", time_range) == "video:mp4:trim:30-90"


def test_different_ranges_produce_different_keys() -> None:
    first = history_store.download_key_for_mode("mp3", "mp3", "mp4", TimeRange(30, 90))
    second = history_store.download_key_for_mode("mp3", "mp3", "mp4", TimeRange(60, 120))

    assert first != second


def test_full_history_record_has_empty_trim_metadata() -> None:
    record = history_store.build_history_record({"title": "Full"})

    assert record == {
        "title": "Full",
        "schema_version": 3,
        "trimmed": False,
        "trim_start_seconds": None,
        "trim_end_seconds": None,
        "trim_duration_seconds": None,
    }


def test_trimmed_history_record_contains_range_metadata() -> None:
    record = history_store.build_history_record({"title": "Trimmed"}, TimeRange(30, 90))

    assert record["schema_version"] == 3
    assert record["trimmed"] is True
    assert record["trim_start_seconds"] == 30
    assert record["trim_end_seconds"] == 90
    assert record["trim_duration_seconds"] == 60


def test_history_time_range_returns_valid_trim_range() -> None:
    record = history_store.build_history_record({"title": "Trimmed"}, TimeRange(30, 90))

    assert history_store.history_time_range(record) == TimeRange(30, 90)


def test_history_time_range_ignores_full_and_legacy_records() -> None:
    assert history_store.history_time_range({"trimmed": False}) is None
    assert history_store.history_time_range({"schema_version": 2}) is None


def test_history_time_range_rejects_missing_trim_fields() -> None:
    assert history_store.history_time_range({"trimmed": True, "trim_start_seconds": 30}) is None


def test_history_time_range_rejects_malformed_trim_fields() -> None:
    assert history_store.history_time_range(
        {"trimmed": True, "trim_start_seconds": 90, "trim_end_seconds": 30}
    ) is None
    assert history_store.history_time_range(
        {"trimmed": True, "trim_start_seconds": "30", "trim_end_seconds": 90}
    ) is None


def test_history_time_range_uses_start_and_end_instead_of_stored_duration() -> None:
    record = {
        "trimmed": True,
        "trim_start_seconds": 30,
        "trim_end_seconds": 90,
        "trim_duration_seconds": 999,
    }

    assert history_store.history_time_range(record) == TimeRange(30, 90)
    assert history_store.history_time_range(record).duration_seconds == 60


def test_app_keeps_history_store_compatibility_bindings() -> None:
    assert app_module.HISTORY_SCHEMA_VERSION == history_store.HISTORY_SCHEMA_VERSION
    assert app_module.download_key_for_mode is history_store.download_key_for_mode
    assert app_module.history_time_range is history_store.history_time_range
    assert app_module.build_history_record is history_store.build_history_record
