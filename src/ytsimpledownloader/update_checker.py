from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any
from urllib.parse import urlparse


GITHUB_LATEST_RELEASE_API_URL = (
    "https://api.github.com/repos/jasonsheu0425/YouTubeSimpleDownloader/releases/latest"
)
UPDATE_CHECK_INTERVAL = timedelta(hours=24)
_VERSION_PATTERN = re.compile(
    r"^v?(\d+(?:\.\d+){2,})(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?$",
    re.IGNORECASE,
)
_RELEASE_PATH_PREFIX = "/jasonsheu0425/youtubesimpledownloader/releases/tag/"


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    release_url: str


def parse_version_tag(value: object) -> tuple[int, ...] | None:
    if not isinstance(value, str):
        return None
    match = _VERSION_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    parts = tuple(int(part) for part in match.group(1).split("."))
    while len(parts) > 1 and parts[-1] == 0:
        parts = parts[:-1]
    return parts


def is_newer_version(candidate_version: object, current_version: object) -> bool:
    candidate = parse_version_tag(candidate_version)
    current = parse_version_tag(current_version)
    return candidate is not None and current is not None and candidate > current


def should_check_for_updates(
    last_update_check_utc: object,
    now: datetime | None = None,
) -> bool:
    if not isinstance(last_update_check_utc, str) or not last_update_check_utc.strip():
        return True

    try:
        last_check = datetime.fromisoformat(last_update_check_utc.strip().replace("Z", "+00:00"))
    except ValueError:
        return True
    if last_check.tzinfo is None:
        return True

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    else:
        current_time = current_time.astimezone(timezone.utc)
    last_check = last_check.astimezone(timezone.utc)
    if last_check > current_time:
        return True
    return current_time - last_check >= UPDATE_CHECK_INTERVAL


def is_valid_release_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value.strip())
        return (
            parsed.scheme.lower() == "https"
            and parsed.hostname is not None
            and parsed.hostname.lower() == "github.com"
            and parsed.username is None
            and parsed.password is None
            and parsed.port is None
            and parsed.path.lower().startswith(_RELEASE_PATH_PREFIX)
            and len(parsed.path) > len(_RELEASE_PATH_PREFIX)
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        return False


def parse_latest_release_response(payload: object, current_version: str) -> UpdateInfo | None:
    try:
        data: Any
        if isinstance(payload, bytes):
            data = json.loads(payload.decode("utf-8"))
        elif isinstance(payload, str):
            data = json.loads(payload)
        elif isinstance(payload, dict):
            data = payload
        else:
            return None

        if data.get("draft", True) or data.get("prerelease", True):
            return None
        tag_name = data.get("tag_name")
        release_url = data.get("html_url")
        if not is_newer_version(tag_name, current_version) or not is_valid_release_url(release_url):
            return None
        assert isinstance(tag_name, str)
        assert isinstance(release_url, str)
        return UpdateInfo(
            current_version=current_version.removeprefix("v"),
            latest_version=tag_name.removeprefix("v"),
            release_url=release_url,
        )
    except (AttributeError, json.JSONDecodeError, TypeError, UnicodeDecodeError, ValueError):
        return None
