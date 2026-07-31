from __future__ import annotations

from pathlib import Path

from .time_range import TimeRange, format_time_value
from .ui_text import download_mode_text


def display_label_for_result(mode: str, path: str) -> str:
    suffix = Path(str(path)).suffix.lower().lstrip(".")
    if suffix:
        return suffix.upper()
    if mode == "mp3":
        return "AUDIO"
    if mode == "mp4":
        return "VIDEO"
    return mode.upper()


def format_trim_range_display(time_range: TimeRange, template: str) -> str:
    return template.format(
        start=format_time_value(time_range.start_seconds),
        end=format_time_value(time_range.end_seconds),
        duration=format_time_value(time_range.duration_seconds),
    )


def format_result_item_text(
    mode: str,
    path: str,
    *,
    prefix: str,
    skipped: bool,
    skipped_label: str,
    time_range: TimeRange | None,
    trim_template: str,
) -> str:
    text = f"{prefix}{display_label_for_result(mode, path)}: {path}"
    if skipped:
        text += f" ({skipped_label})"
    if time_range is not None:
        text += f" | {format_trim_range_display(time_range, trim_template)}"
    return text


def format_history_item_text(
    timestamp: object,
    mode: object,
    title: object,
    language: str,
    *,
    time_range: TimeRange | None,
    trim_template: str,
) -> str:
    mode_text = download_mode_text(mode, language)
    text = f"{timestamp} | {mode_text} | {title}"
    if time_range is not None:
        text += f" | {format_trim_range_display(time_range, trim_template)}"
    return text
