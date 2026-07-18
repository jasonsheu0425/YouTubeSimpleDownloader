from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from ytsimpledownloader.update_checker import (
    is_newer_version,
    is_valid_release_url,
    parse_latest_release_response,
    parse_version_tag,
    should_check_for_updates,
)


RELEASE_URL = "https://github.com/jasonsheu0425/YouTubeSimpleDownloader/releases/tag/v0.9.7"


def release_payload(**overrides) -> dict:
    payload = {
        "tag_name": "v0.9.7",
        "html_url": RELEASE_URL,
        "draft": False,
        "prerelease": False,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.9.7", (0, 9, 7)),
        ("v0.9.7", (0, 9, 7)),
        ("v0.9.7-security-fix", (0, 9, 7)),
        ("not-a-version", None),
    ],
)
def test_parse_version_tag(value, expected) -> None:
    assert parse_version_tag(value) == expected


def test_numeric_version_comparison_handles_two_digit_patch() -> None:
    assert is_newer_version("0.9.10", "0.9.7") is True
    assert is_newer_version("0.9.7", "0.9.7") is False
    assert is_newer_version("0.9.6", "0.9.7") is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"draft": True},
        {"prerelease": True},
        {"tag_name": None},
        {"html_url": None},
        {"tag_name": "invalid"},
        {"html_url": "https://example.com/releases/tag/v0.9.7"},
    ],
)
def test_invalid_or_unpublished_release_is_ignored(overrides) -> None:
    assert parse_latest_release_response(release_payload(**overrides), "0.9.6") is None


def test_valid_new_release_is_parsed_from_json() -> None:
    update = parse_latest_release_response(json.dumps(release_payload()), "0.9.6")
    assert update is not None
    assert update.current_version == "0.9.6"
    assert update.latest_version == "0.9.7"
    assert update.release_url == RELEASE_URL


@pytest.mark.parametrize("payload", ["{bad json", b"\xff", [], None])
def test_malformed_release_payload_is_ignored(payload) -> None:
    assert parse_latest_release_response(payload, "0.9.6") is None


def test_release_url_validation_is_restricted_to_project_release_pages() -> None:
    assert is_valid_release_url(RELEASE_URL) is True
    assert is_valid_release_url("http://github.com/jasonsheu0425/YouTubeSimpleDownloader/releases/tag/v0.9.7") is False
    assert is_valid_release_url("https://github.com/another/repository/releases/tag/v0.9.7") is False
    assert is_valid_release_url("https://github.com:bad/invalid") is False


def test_update_check_interval_is_24_hours() -> None:
    now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    assert should_check_for_updates((now - timedelta(hours=23, minutes=59)).isoformat(), now) is False
    assert should_check_for_updates((now - timedelta(hours=24)).isoformat(), now) is True


def test_invalid_or_missing_last_check_time_is_safe() -> None:
    now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    assert should_check_for_updates("", now) is True
    assert should_check_for_updates("not-a-time", now) is True
    assert should_check_for_updates("2026-07-18T11:00:00", now) is True
    assert should_check_for_updates((now + timedelta(hours=1)).isoformat(), now) is True
