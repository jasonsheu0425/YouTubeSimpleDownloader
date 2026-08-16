from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pytest

import ytsimpledownloader.app as app_module
from ytsimpledownloader import media_probe
from ytsimpledownloader.downloader import OutputOptions, SingleVideoDownloader, VideoInfo
from ytsimpledownloader.download_errors import DownloadErrorInfo, DownloadErrorKind
from ytsimpledownloader.network_security import (
    MAX_THUMBNAIL_BYTES,
    SafeThumbnailRedirectHandler,
    ThumbnailSecurityError,
    fetch_thumbnail_bytes,
    validate_thumbnail_url,
    validate_youtube_url,
)
from ytsimpledownloader.transcoder import VideoTranscodeOptions


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "https://youtube.com/watch?v=jNQXAC9IVRw",
        "https://m.youtube.com/watch?v=jNQXAC9IVRw",
        "https://music.youtube.com/watch?v=jNQXAC9IVRw",
        "https://www.youtube.com/shorts/jNQXAC9IVRw",
        "https://youtu.be/jNQXAC9IVRw",
        "https://www.youtube.com/playlist?list=PL1234567890",
    ],
)
def test_supported_youtube_urls_are_accepted(url: str) -> None:
    assert validate_youtube_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://www.youtube.com/watch?v=jNQXAC9IVRw",
        "file:///C:/Windows/win.ini",
        "ftp://youtube.com/video",
        "https://example.com/watch?v=jNQXAC9IVRw",
        "https://youtube.com.example.com/watch?v=jNQXAC9IVRw",
        "https://localhost/watch?v=jNQXAC9IVRw",
        "https://127.0.0.1/watch?v=jNQXAC9IVRw",
        "https://192.168.1.1/watch?v=jNQXAC9IVRw",
        "https://user:password@www.youtube.com/watch?v=jNQXAC9IVRw",
        "https://youtu.be/video/extra-path",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/playlist",
        "not a URL",
    ],
)
def test_unsafe_or_unsupported_youtube_urls_are_rejected(url: str) -> None:
    with pytest.raises(ValueError):
        validate_youtube_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://i.ytimg.com/vi/jNQXAC9IVRw/hqdefault.jpg",
        "https://img.youtube.com/vi/jNQXAC9IVRw/0.jpg",
        "https://yt3.ggpht.com/example=s88-c-k-c0x00ffffff-no-rj",
    ],
)
def test_supported_thumbnail_urls_are_accepted(url: str) -> None:
    assert validate_thumbnail_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://i.ytimg.com/vi/id/hqdefault.jpg",
        "https://example.com/image.jpg",
        "https://localhost/image.jpg",
        "https://127.0.0.1/image.jpg",
        "https://user:password@i.ytimg.com/image.jpg",
    ],
)
def test_unsafe_thumbnail_urls_are_rejected(url: str) -> None:
    with pytest.raises(ThumbnailSecurityError):
        validate_thumbnail_url(url)


class _FakeHeaders(dict):
    def get_content_type(self) -> str:
        return str(self.get("Content-Type", "")).split(";", 1)[0]


class _FakeResponse:
    def __init__(self, data: bytes, url: str, headers: dict[str, str]) -> None:
        self._stream = io.BytesIO(data)
        self._url = url
        self.headers = _FakeHeaders(headers)

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


class _FakeOpener:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.timeout = None

    def open(self, _request, timeout: int):
        self.timeout = timeout
        return self.response


def test_thumbnail_fetch_accepts_small_image_and_uses_timeout() -> None:
    response = _FakeResponse(
        b"image-data",
        "https://i.ytimg.com/vi/id/hqdefault.jpg",
        {"Content-Type": "image/jpeg", "Content-Length": "10"},
    )
    opener = _FakeOpener(response)

    assert fetch_thumbnail_bytes(response.geturl(), opener=opener, timeout=7) == b"image-data"
    assert opener.timeout == 7


def test_thumbnail_fetch_rejects_oversized_content_length() -> None:
    response = _FakeResponse(
        b"small",
        "https://i.ytimg.com/vi/id/hqdefault.jpg",
        {"Content-Type": "image/jpeg", "Content-Length": str(MAX_THUMBNAIL_BYTES + 1)},
    )

    with pytest.raises(ThumbnailSecurityError, match="too large"):
        fetch_thumbnail_bytes(response.geturl(), opener=_FakeOpener(response))


def test_thumbnail_fetch_rejects_oversized_body_without_content_length() -> None:
    response = _FakeResponse(
        b"x" * (MAX_THUMBNAIL_BYTES + 1),
        "https://i.ytimg.com/vi/id/hqdefault.jpg",
        {"Content-Type": "image/webp"},
    )

    with pytest.raises(ThumbnailSecurityError, match="too large"):
        fetch_thumbnail_bytes(response.geturl(), opener=_FakeOpener(response))


def test_thumbnail_fetch_rejects_non_image_content() -> None:
    response = _FakeResponse(
        b"not-an-image",
        "https://i.ytimg.com/vi/id/hqdefault.jpg",
        {"Content-Type": "text/html"},
    )

    with pytest.raises(ThumbnailSecurityError, match="content type"):
        fetch_thumbnail_bytes(response.geturl(), opener=_FakeOpener(response))


def test_thumbnail_fetch_rejects_unsafe_final_redirect_url() -> None:
    response = _FakeResponse(
        b"image-data",
        "https://example.com/stolen.jpg",
        {"Content-Type": "image/jpeg"},
    )

    with pytest.raises(ThumbnailSecurityError):
        fetch_thumbnail_bytes(
            "https://i.ytimg.com/vi/id/hqdefault.jpg",
            opener=_FakeOpener(response),
        )


def test_thumbnail_redirect_handler_rejects_unknown_domain() -> None:
    handler = SafeThumbnailRedirectHandler()

    with pytest.raises(ThumbnailSecurityError):
        handler.redirect_request(None, None, 302, "Found", {}, "https://example.com/image.jpg")


def test_invalid_thumbnail_does_not_fail_video_metadata_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = VideoInfo(
        title="Safe title",
        uploader="Safe channel",
        duration=10,
        thumbnail_url="https://example.com/image.jpg",
        webpage_url="https://www.youtube.com/watch?v=jNQXAC9IVRw",
        mp3_path=tmp_path / "safe.mp3",
        mp4_path=tmp_path / "safe.mp4",
    )

    class FakeDownloader:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def fetch_video_info(self, _url: str) -> VideoInfo:
            return info

    monkeypatch.setattr(app_module, "SingleVideoDownloader", FakeDownloader)
    monkeypatch.setattr(
        app_module,
        "fetch_thumbnail_bytes",
        lambda _url: (_ for _ in ()).throw(ThumbnailSecurityError("rejected")),
    )
    completed = []
    failed = []
    worker = app_module.PreviewWorker(
        info.webpage_url,
        tmp_path,
        OutputOptions(),
        "mp3",
        "mp4",
        VideoTranscodeOptions(),
    )
    worker.finished_ok.connect(lambda metadata, thumbnail: completed.append((metadata, thumbnail)))
    worker.failed.connect(failed.append)

    worker.run()

    assert completed == [(info, b"")]
    assert failed == []


def test_queue_build_reports_invalid_url_without_dropping_valid_items(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDownloader:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

    monkeypatch.setattr(app_module, "SingleVideoDownloader", FakeDownloader)
    completed = []
    worker = app_module.QueueBuildWorker(
        [
            "https://www.youtube.com/watch?v=jNQXAC9IVRw",
            "https://example.com/watch?v=unsafe",
        ],
        tmp_path,
    )
    worker.finished_ok.connect(lambda tasks, errors: completed.append((tasks, errors)))

    worker.run()

    tasks, errors = completed[0]
    assert [task.url for task in tasks] == ["https://www.youtube.com/watch?v=jNQXAC9IVRw"]
    assert errors == [DownloadErrorInfo(DownloadErrorKind.INVALID_INPUT, "error_unsupported")]


def test_path_ffprobe_is_never_selected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = tmp_path / "ffprobe.exe"
    fake.write_bytes(b"untrusted")
    monkeypatch.setenv("PATH", str(tmp_path))

    assert media_probe.find_ffprobe(tmp_path / "ffmpeg.exe") == ""


def test_ffmpeg_probe_timeout_returns_friendly_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"sample")

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("ffmpeg", 15)

    monkeypatch.setattr(media_probe.subprocess, "run", timeout)
    result = media_probe.probe_media(source, "verified-ffmpeg.exe")

    assert "timed out" in result.error.lower()


@pytest.fixture
def downloader_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(SingleVideoDownloader, "_ensure_ffmpeg_exe", lambda self: "ffmpeg.exe")

    def create(template: str) -> SingleVideoDownloader:
        return SingleVideoDownloader(
            tmp_path / "downloads",
            output_options=OutputOptions(filename_rule="custom", custom_template=template),
        )

    return create


@pytest.mark.parametrize(
    "template",
    [
        r"..\outside\%(title)s.%(ext)s",
        r"C:\Temp\%(title)s.%(ext)s",
        "/tmp/%(title)s.%(ext)s",
        r"\\server\share\%(title)s.%(ext)s",
    ],
)
def test_custom_filename_template_rejects_path_escape(downloader_factory, template: str) -> None:
    downloader = downloader_factory(template)

    with pytest.raises(ValueError, match="output folder"):
        downloader.expected_output_path({"title": "safe", "id": "id"}, ".mp4")


def test_valid_nested_custom_filename_stays_in_output_folder(downloader_factory) -> None:
    downloader = downloader_factory("music/%(title)s [%(id)s].%(ext)s")

    path = downloader.expected_output_path({"title": "safe", "id": "id"}, ".mp4")

    path.resolve().relative_to(downloader.output_dir.resolve())
    assert path.parent.name == "music"


def test_requested_download_path_outside_output_folder_is_rejected(downloader_factory, tmp_path: Path) -> None:
    downloader = downloader_factory("%(title)s.%(ext)s")
    target = downloader.output_dir / "safe.mp4"
    malicious = tmp_path / "outside.mp4"

    with pytest.raises(ValueError, match="output folder"):
        downloader._expected_path(
            {"requested_downloads": [{"filepath": str(malicious)}]},
            ".mp4",
            target,
        )
