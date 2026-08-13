from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import tempfile

from .time_range import TimeRange, TimeRangeError


HISTORY_SCHEMA_VERSION = 3


class HistoryLoadStatus(str, Enum):
    OK = "ok"
    MISSING = "missing"
    RECOVERED_CORRUPT = "recovered_corrupt"
    READ_ERROR = "read_error"
    RECOVERY_FAILED = "recovery_failed"


@dataclass(frozen=True)
class HistoryLoadResult:
    items: list[dict]
    status: HistoryLoadStatus
    path: Path
    backup_path: Path | None = None
    corruption_reason: str | None = None
    error: Exception | None = None

    @property
    def safe_to_write(self) -> bool:
        return self.status in {
            HistoryLoadStatus.OK,
            HistoryLoadStatus.MISSING,
            HistoryLoadStatus.RECOVERED_CORRUPT,
        }


def _decode_history(payload: bytes) -> tuple[list[dict] | None, str | None, Exception | None]:
    if not payload:
        return None, "empty_file", None
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, "invalid_utf8", exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, "invalid_json", exc
    if not isinstance(data, list):
        return None, "invalid_root", None
    for item in data:
        if not isinstance(item, dict):
            return None, "invalid_record", None
        paths = item.get("paths")
        if paths is not None and (
            not isinstance(paths, list) or any(not isinstance(path, str) for path in paths)
        ):
            return None, "invalid_paths", None
    return data, None, None


def load_history(path: Path) -> list[dict]:
    try:
        payload = path.read_bytes()
        data = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _recover_corrupt_history(
    path: Path,
    corruption_reason: str,
    corruption_error: Exception | None,
) -> HistoryLoadResult:
    descriptor = -1
    backup_path: Path | None = None
    replaced = False
    try:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        descriptor, backup_name = tempfile.mkstemp(
            prefix=f"{path.name}.corrupt-{timestamp}-",
            suffix=".bak",
            dir=path.parent,
        )
        backup_path = Path(backup_name)
        os.close(descriptor)
        descriptor = -1
        os.replace(path, backup_path)
        replaced = True
    except OSError as exc:
        return HistoryLoadResult(
            items=[],
            status=HistoryLoadStatus.RECOVERY_FAILED,
            path=path,
            backup_path=None,
            corruption_reason=corruption_reason,
            error=exc,
        )
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if backup_path is not None and not replaced:
            try:
                backup_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass

    return HistoryLoadResult(
        items=[],
        status=HistoryLoadStatus.RECOVERED_CORRUPT,
        path=path,
        backup_path=backup_path,
        corruption_reason=corruption_reason,
        error=corruption_error,
    )


def load_history_result(path: Path) -> HistoryLoadResult:
    try:
        path.stat()
    except FileNotFoundError:
        return HistoryLoadResult(items=[], status=HistoryLoadStatus.MISSING, path=path)
    except OSError as exc:
        return HistoryLoadResult(
            items=[],
            status=HistoryLoadStatus.READ_ERROR,
            path=path,
            error=exc,
        )

    try:
        payload = path.read_bytes()
    except OSError as exc:
        return HistoryLoadResult(
            items=[],
            status=HistoryLoadStatus.READ_ERROR,
            path=path,
            error=exc,
        )

    items, corruption_reason, corruption_error = _decode_history(payload)
    if items is not None:
        return HistoryLoadResult(items=items, status=HistoryLoadStatus.OK, path=path)
    return _recover_corrupt_history(
        path,
        corruption_reason or "invalid_history",
        corruption_error,
    )


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
