from __future__ import annotations

import re
from dataclasses import dataclass


class TimeRangeError(ValueError):
    """Raised when a trim time value or range is invalid."""


def _require_nonnegative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TimeRangeError(f"{field_name} must be an integer number of seconds.")
    if value < 0:
        raise TimeRangeError(f"{field_name} cannot be negative.")


@dataclass(frozen=True)
class TimeRange:
    start_seconds: int
    end_seconds: int

    def __post_init__(self) -> None:
        _require_nonnegative_integer(self.start_seconds, "Start time")
        _require_nonnegative_integer(self.end_seconds, "End time")
        if self.end_seconds <= self.start_seconds:
            raise TimeRangeError("End time must be greater than start time.")

    @property
    def duration_seconds(self) -> int:
        return self.end_seconds - self.start_seconds

    def identity_key(self) -> str:
        return f"trim:{self.start_seconds}-{self.end_seconds}"

    def filename_suffix(self) -> str:
        return f"_trim_{self.start_seconds}s-{self.end_seconds}s"


def parse_time_value(value: str) -> int:
    if not isinstance(value, str):
        raise TimeRangeError("Time value must be text.")

    text = value.strip()
    if not text:
        raise TimeRangeError("Time value cannot be empty.")

    parts = text.split(":")
    if len(parts) not in (1, 2, 3) or any(not re.fullmatch(r"[0-9]+", part) for part in parts):
        raise TimeRangeError("Use seconds, MM:SS, or HH:MM:SS.")

    try:
        numbers = [int(part) for part in parts]
    except ValueError as exc:
        raise TimeRangeError("Time value is too large to parse.") from exc
    if len(numbers) == 1:
        return numbers[0]

    if len(numbers) == 2:
        minutes, seconds = numbers
        if seconds > 59:
            raise TimeRangeError("Seconds must be between 0 and 59.")
        return minutes * 60 + seconds

    hours, minutes, seconds = numbers
    if minutes > 59:
        raise TimeRangeError("Minutes must be between 0 and 59 in HH:MM:SS.")
    if seconds > 59:
        raise TimeRangeError("Seconds must be between 0 and 59.")
    return hours * 3600 + minutes * 60 + seconds


def parse_time_range(start: str, end: str) -> TimeRange:
    start_seconds = 0 if isinstance(start, str) and not start.strip() else parse_time_value(start)
    if not isinstance(end, str) or not end.strip():
        raise TimeRangeError("End time cannot be empty.")
    return TimeRange(start_seconds=start_seconds, end_seconds=parse_time_value(end))


def format_time_value(seconds: int) -> str:
    _require_nonnegative_integer(seconds, "Time")
    hours, remainder = divmod(seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"
    return f"{minutes:02d}:{remaining_seconds:02d}"


def validate_against_duration(time_range: TimeRange, duration_seconds: int | None) -> None:
    if duration_seconds is None:
        return
    _require_nonnegative_integer(duration_seconds, "Video duration")
    if time_range.end_seconds > duration_seconds:
        raise TimeRangeError("End time cannot be greater than the video duration.")
