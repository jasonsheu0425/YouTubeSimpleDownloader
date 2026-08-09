from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from .time_range import TimeRange, TimeRangeError


HISTORY_SCHEMA_VERSION = 3


def load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def save_history(path: Path, items: list[dict], *, limit: int = 100) -> None:
    payload = json.dumps(items[:limit], ensure_ascii=False, indent=2)
    descriptor = -1
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(temporary_name)
        stream = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = -1
        with stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass


def download_key_for_mode(
    mode: str,
    audio_format: str,
    video_format: str,
    time_range: TimeRange | None = None,
) -> str:
    if mode == "mp3":
        key = f"audio:{audio_format}"
    elif mode == "mp4":
        key = f"video:{video_format}"
    else:
        key = mode
    if time_range is not None:
        key = f"{key}:{time_range.identity_key()}"
    return key


def history_time_range(item: dict) -> TimeRange | None:
    if item.get("trimmed") is not True:
        return None
    try:
        return TimeRange(
            start_seconds=item["trim_start_seconds"],
            end_seconds=item["trim_end_seconds"],
        )
    except (KeyError, TimeRangeError):
        return None


def build_history_record(fields: dict, time_range: TimeRange | None = None) -> dict:
    return {
        **fields,
        "schema_version": HISTORY_SCHEMA_VERSION,
        "trimmed": time_range is not None,
        "trim_start_seconds": time_range.start_seconds if time_range is not None else None,
        "trim_end_seconds": time_range.end_seconds if time_range is not None else None,
        "trim_duration_seconds": time_range.duration_seconds if time_range is not None else None,
    }
