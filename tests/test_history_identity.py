from __future__ import annotations

import json
from pathlib import Path

import pytest

import ytsimpledownloader.app as app_module
from ytsimpledownloader.app import (
    QueueTask,
    build_history_record,
    download_key_for_mode,
    history_downloads_by_video_id,
    history_time_range,
    task_has_downloaded_modes,
)
from ytsimpledownloader.time_range import TimeRange


VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
VIDEO_ID = "dQw4w9WgXcQ"


def _write_history(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, records: list[dict]) -> None:
    history_path = tmp_path / "history.json"
    history_path.write_text(json.dumps(records), encoding="utf-8")
    monkeypatch.setattr(app_module, "HISTORY_PATH", history_path)


def _record(path: Path, time_range: TimeRange | None = None, *, schema_version: int = 3) -> dict:
    fields = {
        "schema_version": schema_version,
        "title": "Test Video",
        "url": VIDEO_URL,
        "video_id": VIDEO_ID,
        "paths": [str(path)],
        "audio_format": "mp3",
        "video_format": "mp4",
    }
    if schema_version < 3:
        return fields
    return build_history_record(fields, time_range)


def test_download_identity_is_trim_aware() -> None:
    first_trim = TimeRange(30, 90)
    second_trim = TimeRange(60, 120)

    assert download_key_for_mode("mp3", "mp3", "mp4") == "audio:mp3"
    assert download_key_for_mode("mp4", "mp3", "mp4") == "video:mp4"
    assert download_key_for_mode("mp3", "mp3", "mp4", first_trim) == "audio:mp3:trim:30-90"
    assert download_key_for_mode("mp4", "mp3", "mp4", first_trim) == "video:mp4:trim:30-90"
    assert download_key_for_mode("mp3", "mp3", "mp4", second_trim) == "audio:mp3:trim:60-120"


def test_schema_v3_record_contains_trim_metadata() -> None:
    record = build_history_record({"title": "Test"}, TimeRange(30, 90))

    assert record["schema_version"] == 3
    assert record["trimmed"] is True
    assert record["trim_start_seconds"] == 30
    assert record["trim_end_seconds"] == 90
    assert record["trim_duration_seconds"] == 60


def test_schema_v3_full_record_preserves_full_download_identity() -> None:
    record = build_history_record({"title": "Test"})

    assert record["schema_version"] == 3
    assert record["trimmed"] is False
    assert record["trim_start_seconds"] is None
    assert record["trim_end_seconds"] is None
    assert record["trim_duration_seconds"] is None
    assert history_time_range(record) is None


def test_schema_v2_record_without_trim_fields_remains_readable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "legacy.mp3"
    audio_path.write_bytes(b"legacy")
    _write_history(monkeypatch, tmp_path, [_record(audio_path, schema_version=2)])

    downloads = history_downloads_by_video_id()

    assert downloads[VIDEO_ID]["audio:mp3"] == str(audio_path)


def test_missing_trim_fields_do_not_crash_or_create_a_false_skip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "malformed.mp3"
    audio_path.write_bytes(b"malformed")
    malformed = _record(audio_path)
    malformed["trimmed"] = True
    malformed.pop("trim_end_seconds")
    _write_history(monkeypatch, tmp_path, [malformed])

    assert history_time_range(malformed) is None
    assert VIDEO_ID in history_downloads_by_video_id()
    assert "audio:mp3" not in history_downloads_by_video_id()[VIDEO_ID]


def test_full_and_trim_downloads_do_not_skip_each_other(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    full_path = tmp_path / "full.mp3"
    trim_path = tmp_path / "trim.mp3"
    full_path.write_bytes(b"full")
    trim_path.write_bytes(b"trim")
    trim = TimeRange(30, 90)
    task = QueueTask(url=VIDEO_URL)

    _write_history(monkeypatch, tmp_path, [_record(full_path)])
    full_downloads = history_downloads_by_video_id()
    assert task_has_downloaded_modes(task, "mp3", full_downloads, "mp3", "mp4")
    assert not task_has_downloaded_modes(task, "mp3", full_downloads, "mp3", "mp4", trim)

    _write_history(monkeypatch, tmp_path, [_record(trim_path, trim)])
    trim_downloads = history_downloads_by_video_id()
    assert task_has_downloaded_modes(task, "mp3", trim_downloads, "mp3", "mp4", trim)
    assert not task_has_downloaded_modes(task, "mp3", trim_downloads, "mp3", "mp4")
    assert not task_has_downloaded_modes(
        task,
        "mp3",
        trim_downloads,
        "mp3",
        "mp4",
        TimeRange(60, 120),
    )


def test_different_trim_ranges_have_separate_skip_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.mp4"
    first_path.write_bytes(b"first")
    first_trim = TimeRange(30, 90)
    second_trim = TimeRange(60, 120)
    _write_history(monkeypatch, tmp_path, [_record(first_path, first_trim)])

    downloads = history_downloads_by_video_id()
    task = QueueTask(url=VIDEO_URL)

    assert task_has_downloaded_modes(task, "mp4", downloads, "mp3", "mp4", first_trim)
    assert not task_has_downloaded_modes(
        task,
        "mp4",
        downloads,
        "mp3",
        "mp4",
        second_trim,
    )


def test_both_mode_requires_matching_trimmed_audio_and_video(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "trim.mp3"
    video_path = tmp_path / "trim.mp4"
    audio_path.write_bytes(b"audio")
    video_path.write_bytes(b"video")
    trim = TimeRange(30, 90)
    audio_record = _record(audio_path, trim)
    video_record = _record(video_path, trim)
    _write_history(monkeypatch, tmp_path, [audio_record, video_record])

    downloads = history_downloads_by_video_id()

    assert task_has_downloaded_modes(
        QueueTask(url=VIDEO_URL),
        "both",
        downloads,
        "mp3",
        "mp4",
        trim,
    )
