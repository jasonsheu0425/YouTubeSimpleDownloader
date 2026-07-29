from __future__ import annotations

from pathlib import Path

import pytest

import ytsimpledownloader.downloader as downloader_module
from ytsimpledownloader.downloader import OutputOptions, SingleVideoDownloader
from ytsimpledownloader.time_range import TimeRange, TimeRangeError


VALID_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
VIDEO_INFO = {
    "title": "Test Video",
    "id": "dQw4w9WgXcQ",
    "uploader": "Test Channel",
    "upload_date": "20260101",
    "ext": "mp4",
}


@pytest.fixture
def downloader_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(SingleVideoDownloader, "_ensure_ffmpeg_exe", lambda self: "ffmpeg.exe")

    def create(**kwargs) -> SingleVideoDownloader:
        return SingleVideoDownloader(tmp_path / "downloads", **kwargs)

    return create


def test_plain_download_keeps_existing_options_and_filename(downloader_factory) -> None:
    downloader = downloader_factory()

    assert "download_ranges" not in downloader._base_opts()
    assert "force_keyframes_at_cuts" not in downloader._base_opts()
    assert downloader._download_range_options() == {}
    assert downloader.expected_output_path(VIDEO_INFO, ".mp4").name == "Test Video [dQw4w9WgXcQ].mp4"


def test_time_range_adds_download_options(
    monkeypatch: pytest.MonkeyPatch,
    downloader_factory,
) -> None:
    sentinel = object()

    def fake_download_range_func(_chapters, ranges):
        assert ranges == [(30, 90)]
        return sentinel

    monkeypatch.setattr(downloader_module, "download_range_func", fake_download_range_func)
    downloader = downloader_factory(time_range=TimeRange(30, 90))

    options = downloader._download_range_options()

    assert options["download_ranges"] is sentinel
    assert options["force_keyframes_at_cuts"] is True


def test_test_seconds_remains_a_time_range_compatibility_shim(downloader_factory) -> None:
    downloader = downloader_factory(test_seconds=10)

    assert downloader.test_seconds == 10
    assert downloader.time_range == TimeRange(0, 10)
    assert "download_ranges" in downloader._download_range_options()
    assert downloader._download_range_options()["force_keyframes_at_cuts"] is True
    assert downloader.expected_output_path(VIDEO_INFO, ".mp4").name.endswith("_trim_0s-10s.mp4")


def test_test_seconds_rejects_non_positive_values(downloader_factory) -> None:
    with pytest.raises(TimeRangeError):
        downloader_factory(test_seconds=0)


def test_test_seconds_and_time_range_cannot_be_combined(downloader_factory) -> None:
    with pytest.raises(ValueError, match="cannot be used together"):
        downloader_factory(test_seconds=10, time_range=TimeRange(30, 90))


def test_time_range_adds_filename_suffix(downloader_factory) -> None:
    downloader = downloader_factory(time_range=TimeRange(30, 90))

    path = downloader.expected_output_path(VIDEO_INFO, ".mp4")

    assert path.name == "Test Video [dQw4w9WgXcQ]_trim_30s-90s.mp4"
    path.resolve().relative_to(downloader.output_dir.resolve())


def test_trimmed_custom_template_stays_in_output_folder(downloader_factory) -> None:
    downloader = downloader_factory(
        time_range=TimeRange(30, 90),
        output_options=OutputOptions(
            filename_rule="custom",
            custom_template="nested/%(title)s.%(ext)s",
        ),
    )

    path = downloader.expected_output_path(VIDEO_INFO, ".mp4")

    assert path.name == "Test Video_trim_30s-90s.mp4"
    assert path.parent.name == "nested"
    path.resolve().relative_to(downloader.output_dir.resolve())


def test_trimmed_custom_template_still_rejects_path_escape(downloader_factory) -> None:
    downloader = downloader_factory(
        time_range=TimeRange(30, 90),
        output_options=OutputOptions(
            filename_rule="custom",
            custom_template=r"..\outside\%(title)s.%(ext)s",
        ),
    )

    with pytest.raises(ValueError, match="output folder"):
        downloader.expected_output_path(VIDEO_INFO, ".mp4")


@pytest.mark.parametrize(
    ("mode", "expected_downloads"),
    [
        ("mp3", 1),
        ("mp4", 1),
        ("both", 2),
    ],
)
def test_trim_range_is_applied_to_each_mode_download(
    monkeypatch: pytest.MonkeyPatch,
    downloader_factory,
    mode: str,
    expected_downloads: int,
) -> None:
    captured_options: list[dict] = []

    class FakeYoutubeDL:
        def __init__(self, options: dict) -> None:
            captured_options.append(options)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            return None

        def extract_info(self, _url: str, download: bool) -> dict:
            assert download is True
            return {}

    downloader = downloader_factory(time_range=TimeRange(30, 90))
    monkeypatch.setattr(downloader_module, "YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(downloader, "_extract_metadata", lambda _url: VIDEO_INFO)
    monkeypatch.setattr(
        downloader,
        "expected_output_path",
        lambda _info, suffix, _playlist_title="", _playlist_index=None: downloader.output_dir / f"target{suffix}",
    )

    results = downloader.download(VALID_URL, mode)  # type: ignore[arg-type]

    assert len(results) == expected_downloads
    assert len(captured_options) == expected_downloads
    assert all("download_ranges" in options for options in captured_options)
    assert all(options["force_keyframes_at_cuts"] is True for options in captured_options)


def test_metadata_options_do_not_apply_download_range(downloader_factory) -> None:
    downloader = downloader_factory(time_range=TimeRange(30, 90))

    options = downloader._base_opts()

    assert "download_ranges" not in options
    assert "force_keyframes_at_cuts" not in options
