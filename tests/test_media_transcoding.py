from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ytsimpledownloader.media_probe import probe_media
from ytsimpledownloader.transcoder import (
    VideoTranscodeOptions,
    VideoTranscoder,
    ensure_ffmpeg_exe,
    friendly_transcode_error,
)


@pytest.fixture(scope="session")
def ffmpeg_path() -> str:
    return ensure_ffmpeg_exe()


@pytest.fixture()
def sample_video(tmp_path: Path, ffmpeg_path: str) -> Path:
    target = tmp_path / "sample.mp4"
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=320x180:rate=24",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=1000:sample_rate=44100",
        "-t",
        "2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        str(target),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return target


def test_probe_reads_basic_media_info(sample_video: Path, ffmpeg_path: str) -> None:
    info = probe_media(sample_video, ffmpeg_path)

    assert info.video_codec
    assert info.width == 320
    assert info.height == 180
    assert info.has_audio
    assert info.duration and info.duration > 1


def test_h264_transcode_keeps_audio(sample_video: Path, ffmpeg_path: str, tmp_path: Path) -> None:
    transcoder = VideoTranscoder(ffmpeg_path)
    result = transcoder.transcode(
        sample_video,
        VideoTranscodeOptions(
            mode="transcode",
            container="mp4",
            video_codec="h264",
            resolution="720",
            fps="30",
            quality="custom",
            crf=20,
            speed="medium",
            audio="keep",
            suffix="_h264",
        ),
        output_dir=tmp_path / "out",
        file_exists_action="number",
    )

    assert result.path.exists()
    assert result.path.suffix == ".mp4"
    assert result.media_info.video_codec.lower() in {"h264", "avc1"}
    assert result.media_info.has_audio
    assert result.media_info.height and result.media_info.height <= 720


def test_osu_preset_outputs_h264_mp4_without_audio(sample_video: Path, ffmpeg_path: str, tmp_path: Path) -> None:
    transcoder = VideoTranscoder(ffmpeg_path)
    result = transcoder.transcode(
        sample_video,
        VideoTranscodeOptions.osu("60"),
        output_dir=tmp_path / "osu",
        file_exists_action="number",
    )

    assert result.path.exists()
    assert result.path.name.endswith("_osu_h264.mp4")
    assert result.media_info.video_codec.lower() in {"h264", "avc1"}
    assert not result.media_info.has_audio
    assert result.media_info.height and result.media_info.height <= 720


def test_auto_number_output_path(sample_video: Path, ffmpeg_path: str, tmp_path: Path) -> None:
    transcoder = VideoTranscoder(ffmpeg_path)
    output_dir = tmp_path / "numbered"
    output_dir.mkdir()
    existing = output_dir / "sample_h264.mp4"
    existing.write_bytes(b"already exists")

    path, skipped = transcoder.prepare_output_path(
        sample_video,
        VideoTranscodeOptions(mode="transcode", container="mp4", suffix="_h264"),
        output_dir=output_dir,
        file_exists_action="number",
    )

    assert not skipped
    assert path.name == "sample_h264 (2).mp4"


def test_friendly_transcode_error_messages() -> None:
    assert "不存在" in friendly_transcode_error("No such file or directory")
    assert "權限" in friendly_transcode_error("Permission denied")
    assert "編碼器" in friendly_transcode_error("Unknown encoder 'libx264'")
