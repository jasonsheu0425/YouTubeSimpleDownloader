from __future__ import annotations

from urllib.parse import parse_qs, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
}
YOUTUBE_SHORT_HOSTS = {"youtu.be"}
THUMBNAIL_HOSTS = {"i.ytimg.com", "img.youtube.com", "yt3.ggpht.com"}
THUMBNAIL_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_THUMBNAIL_BYTES = 5 * 1024 * 1024
THUMBNAIL_TIMEOUT_SECONDS = 15


class ThumbnailSecurityError(ValueError):
    """Raised when a preview thumbnail violates the network policy."""


def _validated_https_url(value: str, allowed_hosts: set[str], label: str) -> tuple[str, object]:
    clean = str(value or "").strip()
    if not clean:
        raise ValueError(f"{label} URL is required.")

    try:
        parsed = urlparse(clean)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"Invalid {label} URL.") from exc

    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() != "https":
        raise ValueError(f"{label} URL must use HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{label} URL must not contain embedded credentials.")
    if port is not None:
        raise ValueError(f"{label} URL must not specify a custom port.")
    if not host or host not in allowed_hosts:
        raise ValueError(f"Unsupported {label} host.")
    return clean, parsed


def validate_youtube_url(value: str) -> str:
    clean = str(value or "").strip()
    parsed_host = (urlparse(clean).hostname or "").lower().rstrip(".")
    allowed_hosts = YOUTUBE_HOSTS | YOUTUBE_SHORT_HOSTS
    clean, parsed = _validated_https_url(clean, allowed_hosts, "YouTube")
    host = (parsed.hostname or "").lower().rstrip(".")
    path_parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)

    if host in YOUTUBE_SHORT_HOSTS:
        if len(path_parts) == 1:
            return clean
        raise ValueError("Unsupported YouTube URL. A video ID is required.")

    path = parsed.path.rstrip("/") or "/"
    if path == "/watch" and (query.get("v") or [""])[0].strip():
        return clean
    if path == "/playlist" and (query.get("list") or [""])[0].strip():
        return clean
    if len(path_parts) == 2 and path_parts[0] == "shorts" and path_parts[1].strip():
        return clean

    raise ValueError(f"Unsupported YouTube URL path on {parsed_host or host}.")


def validate_thumbnail_url(value: str) -> str:
    try:
        clean, _parsed = _validated_https_url(value, THUMBNAIL_HOSTS, "thumbnail")
    except ValueError as exc:
        raise ThumbnailSecurityError(str(exc)) from exc
    return clean


class SafeThumbnailRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_thumbnail_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_thumbnail_bytes(
    url: str,
    *,
    timeout: int = THUMBNAIL_TIMEOUT_SECONDS,
    max_bytes: int = MAX_THUMBNAIL_BYTES,
    opener=None,
) -> bytes:
    clean_url = validate_thumbnail_url(url)
    safe_opener = opener or build_opener(SafeThumbnailRedirectHandler())
    request = Request(clean_url, headers={"User-Agent": "YouTubeSimpleDownloader/preview"})

    with safe_opener.open(request, timeout=timeout) as response:
        validate_thumbnail_url(response.geturl())
        headers = response.headers
        if hasattr(headers, "get_content_type"):
            content_type = headers.get_content_type().lower()
        else:
            content_type = str(headers.get("Content-Type", "")).split(";", 1)[0].strip().lower()
        if content_type not in THUMBNAIL_CONTENT_TYPES:
            raise ThumbnailSecurityError(f"Unsupported thumbnail content type: {content_type or 'missing'}.")

        content_length = headers.get("Content-Length")
        if content_length:
            try:
                declared_size = int(content_length)
            except (TypeError, ValueError) as exc:
                raise ThumbnailSecurityError("Invalid thumbnail Content-Length.") from exc
            if declared_size < 0 or declared_size > max_bytes:
                raise ThumbnailSecurityError("Thumbnail response is too large.")

        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ThumbnailSecurityError("Thumbnail response is too large.")
        return data
