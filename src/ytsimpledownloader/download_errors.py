from __future__ import annotations

import errno
from dataclasses import dataclass
from enum import Enum
from urllib.error import URLError

from yt_dlp.utils import (
    DownloadError,
    ExtractorError,
    GeoRestrictedError,
    PostProcessingError,
    UnsupportedError,
)


class DownloadErrorKind(str, Enum):
    CANCELLED = "cancelled"
    INVALID_INPUT = "invalid_input"
    UNSUPPORTED_URL = "unsupported_url"
    TIMEOUT = "timeout"
    NETWORK = "network"
    UNAVAILABLE = "unavailable"
    ACCESS_REQUIRED = "access_required"
    EXTRACTOR = "extractor"
    POSTPROCESSOR = "postprocessor"
    FILESYSTEM = "filesystem"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DownloadErrorInfo:
    kind: DownloadErrorKind
    message_key: str | None = None


def cancelled_download_error() -> DownloadErrorInfo:
    return DownloadErrorInfo(DownloadErrorKind.CANCELLED)


def classify_download_error(
    exc: BaseException,
    *,
    cancellation_types: tuple[type[BaseException], ...] = (),
) -> DownloadErrorInfo:
    """Classify a download failure without retaining exception details.

    The classifier intentionally relies on typed evidence first. Message matching
    is limited to narrow, long-standing user-facing yt-dlp/validation signatures.
    """

    if cancellation_types and isinstance(exc, cancellation_types):
        return cancelled_download_error()

    direct = _classify_typed_exception(exc, direct=True)
    if direct is not None:
        return direct

    preserved_cause = _preserved_cause(exc)
    if preserved_cause is not None:
        cause_result = _classify_typed_exception(preserved_cause, direct=False)
        if cause_result is not None:
            return cause_result

    return _classify_narrow_message(str(exc))


def _classify_typed_exception(exc: BaseException, *, direct: bool) -> DownloadErrorInfo | None:
    if isinstance(exc, TimeoutError):
        return DownloadErrorInfo(DownloadErrorKind.TIMEOUT, "error_network")
    if isinstance(exc, PermissionError):
        return DownloadErrorInfo(DownloadErrorKind.FILESYSTEM, "error_permission")
    if direct and isinstance(exc, OSError) and exc.errno in {
        errno.EACCES,
        errno.EPERM,
        errno.ENAMETOOLONG,
        errno.ENOSPC,
        errno.EROFS,
    }:
        return DownloadErrorInfo(DownloadErrorKind.FILESYSTEM)
    if isinstance(exc, (ConnectionError, URLError)):
        return DownloadErrorInfo(DownloadErrorKind.NETWORK, "error_network")

    if isinstance(exc, UnsupportedError):
        return DownloadErrorInfo(DownloadErrorKind.UNSUPPORTED_URL, "error_unsupported")
    if isinstance(exc, GeoRestrictedError):
        return DownloadErrorInfo(DownloadErrorKind.UNAVAILABLE, "error_unavailable")
    if isinstance(exc, PostProcessingError):
        return DownloadErrorInfo(DownloadErrorKind.POSTPROCESSOR)
    if isinstance(exc, ExtractorError):
        cause = _preserved_cause(exc)
        if cause is not None:
            cause_result = _classify_typed_exception(cause, direct=False)
            if cause_result is not None:
                return cause_result
        return DownloadErrorInfo(DownloadErrorKind.EXTRACTOR)
    if isinstance(exc, DownloadError):
        return None
    return None


def _preserved_cause(exc: BaseException) -> BaseException | None:
    """Read optional public exception context defensively.

    yt-dlp may retain the original exception in ``DownloadError.exc_info``. That
    field is optional, so it only improves a classification when its shape is
    usable; it is never required for a result.
    """

    if isinstance(exc, DownloadError):
        exc_info = getattr(exc, "exc_info", None)
        if isinstance(exc_info, tuple) and len(exc_info) == 3 and isinstance(exc_info[1], BaseException):
            return exc_info[1]

    cause = getattr(exc, "cause", None)
    if isinstance(cause, BaseException):
        return cause
    if isinstance(exc.__cause__, BaseException):
        return exc.__cause__
    return None


def _classify_narrow_message(message: str) -> DownloadErrorInfo:
    lower = message.lower()
    if (
        "youtube url" in lower
        or "youtube host" in lower
        or "youtube url path" in lower
        or "url must use https" in lower
        or "url is required" in lower
    ):
        return DownloadErrorInfo(DownloadErrorKind.INVALID_INPUT, "error_unsupported")
    if "unsupported url" in lower:
        return DownloadErrorInfo(DownloadErrorKind.UNSUPPORTED_URL, "error_unsupported")
    if "video unavailable" in lower or "this video is unavailable" in lower:
        return DownloadErrorInfo(DownloadErrorKind.UNAVAILABLE, "error_unavailable")
    if "private video" in lower or "sign in to confirm your age" in lower:
        return DownloadErrorInfo(DownloadErrorKind.ACCESS_REQUIRED, "error_login")
    return DownloadErrorInfo(DownloadErrorKind.UNKNOWN)
