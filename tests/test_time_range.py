from __future__ import annotations

import pytest

from ytsimpledownloader.time_range import (
    TimeRange,
    TimeRangeError,
    format_time_value,
    parse_time_range,
    parse_time_value,
    validate_against_duration,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", 0),
        ("59", 59),
        ("90", 90),
        (" 90 ", 90),
        ("01:30", 90),
        ("1:30", 90),
        ("99:59", 5999),
        ("01:02:03", 3723),
        ("1:02:03", 3723),
    ],
)
def test_parse_time_value_accepts_supported_formats(value: str, expected: int) -> None:
    assert parse_time_value(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        " ",
        "-1",
        "+1",
        "1.5",
        "abc",
        "1 0",
        "1:",
        ":30",
        "1::30",
        "1:2:3:4",
        "01:99",
        "01:60",
        "1:60:00",
        "1:00:60",
    ],
)
def test_parse_time_value_rejects_invalid_input(value: str) -> None:
    with pytest.raises(TimeRangeError):
        parse_time_value(value)


def test_parse_time_value_rejects_non_text_input() -> None:
    with pytest.raises(TimeRangeError):
        parse_time_value(None)  # type: ignore[arg-type]


def test_parse_time_value_wraps_integer_conversion_failure() -> None:
    with pytest.raises(TimeRangeError) as exc_info:
        parse_time_value("9" * 10000)

    assert isinstance(exc_info.value.__cause__, ValueError)


def test_parse_time_range_allows_blank_start_as_zero() -> None:
    time_range = parse_time_range("  ", "01:30")

    assert time_range == TimeRange(start_seconds=0, end_seconds=90)
    assert time_range.duration_seconds == 90


def test_parse_time_range_parses_start_and_end() -> None:
    time_range = parse_time_range("00:30", "01:30")

    assert time_range.start_seconds == 30
    assert time_range.end_seconds == 90
    assert time_range.duration_seconds == 60


def test_parse_time_range_rejects_blank_end() -> None:
    with pytest.raises(TimeRangeError):
        parse_time_range("00:30", " ")


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("30", "30"),
        ("31", "30"),
        ("01:00", "00:59"),
    ],
)
def test_parse_time_range_rejects_end_not_greater_than_start(start: str, end: str) -> None:
    with pytest.raises(TimeRangeError):
        parse_time_range(start, end)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (30, 30),
        (-1, 10),
        (0, -1),
        (True, 10),
        (0, False),
        ("0", 10),
        (0, 10.0),
    ],
)
def test_time_range_rejects_invalid_direct_values(start: object, end: object) -> None:
    with pytest.raises(TimeRangeError):
        TimeRange(start_seconds=start, end_seconds=end)  # type: ignore[arg-type]


def test_time_range_allows_valid_direct_values() -> None:
    time_range = TimeRange(start_seconds=0, end_seconds=10)

    assert time_range.start_seconds == 0
    assert time_range.end_seconds == 10
    assert time_range.duration_seconds == 10


def test_identity_key_and_filename_suffix_are_stable() -> None:
    time_range = TimeRange(start_seconds=30, end_seconds=90)

    assert time_range.identity_key() == "trim:30-90"
    assert time_range.filename_suffix() == "_trim_30s-90s"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00"),
        (59, "00:59"),
        (60, "01:00"),
        (3599, "59:59"),
        (3600, "01:00:00"),
        (3723, "01:02:03"),
        (360000, "100:00:00"),
    ],
)
def test_format_time_value(seconds: int, expected: str) -> None:
    assert format_time_value(seconds) == expected


@pytest.mark.parametrize("seconds", [-1, True])
def test_format_time_value_rejects_invalid_seconds(seconds: int) -> None:
    with pytest.raises(TimeRangeError):
        format_time_value(seconds)


def test_duration_validation_allows_unknown_or_exact_duration() -> None:
    time_range = TimeRange(start_seconds=30, end_seconds=90)

    validate_against_duration(time_range, None)
    validate_against_duration(time_range, 90)
    validate_against_duration(time_range, 120)


def test_duration_validation_rejects_range_beyond_video() -> None:
    with pytest.raises(TimeRangeError):
        validate_against_duration(TimeRange(start_seconds=30, end_seconds=91), 90)


@pytest.mark.parametrize("duration", [-1, True])
def test_duration_validation_rejects_invalid_duration(duration: int) -> None:
    with pytest.raises(TimeRangeError):
        validate_against_duration(TimeRange(start_seconds=0, end_seconds=1), duration)
