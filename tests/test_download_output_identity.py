from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import ytsimpledownloader.downloader as downloader_module
from ytsimpledownloader.downloader import SingleVideoDownloader
from ytsimpledownloader.transcoder import VideoTranscodeOptions


@pytest.fixture
def downloader(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SingleVideoDownloader:
    monkeypatch.setattr(SingleVideoDownloader, "_ensure_ffmpeg_exe", lambda self: "unused-ffmpeg.exe")
    monkeypatch.setattr(downloader_module, "collect_runtime_diagnostics", lambda: None)
    return SingleVideoDownloader(tmp_path, video_processing_options=VideoTranscodeOptions(
        mode="transcode", keep_original=False,
    ))


@pytest.mark.parametrize("suffix", [".mp3", ".m4a", ".opus", ".wav", ".flac", ".mp4", ".mkv", ".webm"])
def test_expected_output_is_accepted(downloader: SingleVideoDownloader, tmp_path: Path, suffix: str) -> None:
    target = tmp_path / f"download{suffix}"
    target.write_bytes(b"identified output")

    assert downloader._expected_path({}, suffix, target) == target


@pytest.mark.parametrize("key", ["filepath", "_filename"])
def test_existing_reported_target_is_accepted(
    downloader: SingleVideoDownloader, tmp_path: Path, key: str,
) -> None:
    reported = tmp_path / "expected.mp4"
    reported.write_bytes(b"identified output")

    assert downloader._expected_path(
        {"requested_downloads": [{key: str(reported)}]}, ".mp4", reported,
    ) == reported


@pytest.mark.parametrize("key", ["filepath", "_filename"])
def test_unrelated_reported_file_is_never_selected(
    downloader: SingleVideoDownloader, tmp_path: Path, key: str,
) -> None:
    unrelated = tmp_path / "existing.mp4"
    unrelated.write_bytes(b"existing user file fixture")
    target = tmp_path / "expected.mp4"

    with pytest.raises(FileNotFoundError, match="identifiable output"):
        downloader._expected_path({"requested_downloads": [{key: str(unrelated)}]}, ".mp4", target)

    assert unrelated.read_bytes() == b"existing user file fixture"


def test_unrelated_reported_file_does_not_override_expected_output(
    downloader: SingleVideoDownloader, tmp_path: Path,
) -> None:
    unrelated = tmp_path / "existing.mp4"
    unrelated.write_bytes(b"existing user file fixture")
    target = tmp_path / "expected.mp4"
    target.write_bytes(b"new download fixture")

    assert downloader._expected_path(
        {"requested_downloads": [{"filepath": str(unrelated)}]}, ".mp4", target,
    ) == target
    assert unrelated.read_bytes() == b"existing user file fixture"


@pytest.mark.parametrize("action", ["skip", "number", "overwrite"])
def test_target_collision_behavior_is_preserved(
    downloader: SingleVideoDownloader, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, action: str,
) -> None:
    target = tmp_path / "existing.mp4"
    target.write_bytes(b"existing user file fixture")
    downloader.file_exists_action = action
    monkeypatch.setattr(downloader, "expected_output_path", lambda *_args: target)

    selected, skipped = downloader._prepare_target({}, ".mp4")

    if action == "skip":
        assert skipped and selected == target
        assert target.read_bytes() == b"existing user file fixture"
    elif action == "number":
        assert not skipped and selected == tmp_path / "existing (2).mp4"
        assert target.read_bytes() == b"existing user file fixture"
    else:
        assert not skipped and selected == target
        assert not target.exists()


@pytest.mark.parametrize("suffix", [".mp3", ".m4a", ".opus", ".wav", ".flac", ".mp4", ".mkv", ".webm"])
def test_missing_output_never_selects_unrelated_file(
    downloader: SingleVideoDownloader, tmp_path: Path, suffix: str,
) -> None:
    unrelated = tmp_path / f"unrelated{suffix}"
    unrelated.write_bytes(b"existing user file fixture")
    original = hashlib.sha256(unrelated.read_bytes()).digest()

    with pytest.raises(FileNotFoundError, match="identifiable output"):
        downloader._expected_path({}, suffix, tmp_path / f"missing{suffix}")

    assert hashlib.sha256(unrelated.read_bytes()).digest() == original


def test_missing_reported_output_falls_back_only_to_expected_file(
    downloader: SingleVideoDownloader, tmp_path: Path,
) -> None:
    target = tmp_path / "expected.mp3"
    target.write_bytes(b"postprocessed audio")

    assert downloader._expected_path(
        {"requested_downloads": [{"filepath": str(tmp_path / "missing.mp3")}]}, ".mp3", target,
    ) == target


def test_missing_reported_and_expected_files_fail_closed(
    downloader: SingleVideoDownloader, tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError, match="identifiable output"):
        downloader._expected_path(
            {"requested_downloads": [{"filepath": str(tmp_path / "missing-reported.mp4")}]},
            ".mp4", tmp_path / "missing-expected.mp4",
        )


def test_directory_is_not_a_download_output(downloader: SingleVideoDownloader, tmp_path: Path) -> None:
    target = tmp_path / "directory.mp4"
    target.mkdir()

    with pytest.raises(FileNotFoundError, match="identifiable output"):
        downloader._expected_path({}, ".mp4", target)


def test_reported_output_outside_selected_folder_still_fails(
    downloader: SingleVideoDownloader, tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="output folder"):
        downloader._expected_path(
            {"requested_downloads": [{"filepath": str(tmp_path.parent / "outside.mp4")}]},
            ".mp4", tmp_path / "expected.mp4",
        )


@pytest.mark.parametrize("mode", ["mp3", "mp4"])
@pytest.mark.parametrize("report_unrelated", [False, True])
def test_unidentified_download_does_not_reach_transcoder_or_report_success(
    downloader: SingleVideoDownloader, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str,
    report_unrelated: bool,
) -> None:
    unrelated = tmp_path / f"unrelated.{mode}"
    unrelated.write_bytes(b"existing user file fixture")
    original = unrelated.read_bytes()
    initial_entries = set(tmp_path.iterdir())
    monkeypatch.setattr(downloader, "_extract_metadata", lambda _url: {})
    monkeypatch.setattr(downloader, "_prepare_target", lambda *_args: (tmp_path / f"missing.{mode}", False))
    info = {"requested_downloads": [{"filepath": str(unrelated)}]} if report_unrelated else {}
    monkeypatch.setattr(downloader, "_run_yt_dlp", lambda *_args: info)
    monkeypatch.setattr(
        downloader_module, "VideoTranscoder",
        lambda *_args, **_kwargs: pytest.fail("Unidentified output must never reach transcoding"),
    )

    with pytest.raises(FileNotFoundError, match="identifiable output"):
        getattr(downloader, f"download_{mode}")("https://www.youtube.com/watch?v=offline-fixture")

    assert unrelated.read_bytes() == original
    assert set(tmp_path.iterdir()) == initial_entries
