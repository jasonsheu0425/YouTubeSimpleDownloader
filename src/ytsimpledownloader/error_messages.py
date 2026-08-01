from __future__ import annotations

from .ui_text import TEXT


def error_key(message: str) -> str:
    lower = message.lower()
    if (
        "video unavailable" in lower
        or "private video" in lower
        or "not available" in lower
        or "this video is unavailable" in lower
        or "blocked in your country" in lower
        or "region" in lower
        or "geo" in lower
        or "removed" in lower
        or "deleted" in lower
    ):
        return "error_unavailable"
    if "sign in" in lower or "login" in lower or "cookies" in lower or "confirm your age" in lower:
        return "error_login"
    if (
        "timed out" in lower
        or "connection" in lower
        or "network" in lower
        or "temporary failure" in lower
        or "name resolution" in lower
        or "remote end closed connection" in lower
        or "connection reset" in lower
    ):
        return "error_network"
    if (
        "http error 429" in lower
        or "too many requests" in lower
        or "temporarily unavailable" in lower
        or "try again later" in lower
        or "confirm you are not a bot" in lower
    ):
        return "error_limited"
    if "unsupported url" in lower:
        return "error_unsupported"
    if "webm" in lower and (
        "requested format is not available" in lower
        or "merge" in lower
        or "ffmpeg" in lower
        or "not available" in lower
    ):
        return "error_webm"
    if "ffmpeg" in lower or "postprocessing" in lower or "conversion failed" in lower or "merge" in lower:
        return "error_ffmpeg"
    if (
        "permission denied" in lower
        or "access is denied" in lower
        or "winerror 5" in lower
        or "operation not permitted" in lower
    ):
        return "error_permission"
    if (
        "file name too long" in lower
        or "filename too long" in lower
        or "path too long" in lower
        or "winerror 3" in lower
        or "winerror 123" in lower
        or "invalid argument" in lower
        or "invalid path" in lower
    ):
        return "error_path"
    return ""


def friendly_error(message: str, language: str, category: str = "") -> str:
    key = category or error_key(message)
    if key:
        return TEXT[language][key]
    return message
