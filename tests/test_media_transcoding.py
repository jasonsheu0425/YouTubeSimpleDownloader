from __future__ import annotations

from dataclasses import replace
import hashlib
import subprocess
from pathlib import Path

import pytest

import ytsimpledownloader.transcoder as transcoder_module
from ytsimpledownloader.media_probe import MediaInfo, probe_media
from ytsimpledownloader.transcoder import (
    TranscodeCancelled,
    VideoTranscodeOptions,
    VideoTranscoder,
    ensure_ffmpeg_exe,
    friendly_transcode_error,
)
from ytsimpledownloader.time_range import TimeRange


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


def test_local_clip_outputs_safe_h264_aac_mp4(
    sample_video: Path,
    ffmpeg_path: str,
    tmp_path: Path,
) -> None:
    source_hash = hashlib.sha256(sample_video.read_bytes()).hexdigest()
    time_range = TimeRange(0, 1)
    output_dir = tmp_path / "clips"
    output_dir.mkdir()
    existing = output_dir / "sample_clip_0s-1s.mp4"
    existing.write_bytes(b"existing user output")

    transcoder = VideoTranscoder(ffmpeg_path)
    result = transcoder.transcode(
        sample_video,
        VideoTranscodeOptions.local_clip(time_range),
        output_dir=output_dir,
        file_exists_action="number",
        time_range=time_range,
    )

    assert result.path.name == "sample_clip_0s-1s (2).mp4"
    assert existing.read_bytes() == b"existing user output"
    assert result.path.exists()
    assert result.media_info.video_codec.lower() in {"h264", "avc1"}
    assert result.media_info.has_audio
    assert result.media_info.duration is not None
    assert result.media_info.duration == pytest.approx(1.0, abs=0.25)
    assert hashlib.sha256(sample_video.read_bytes()).hexdigest() == source_hash
    assert not list(output_dir.glob("*.partial-*.mp4"))


def test_local_clip_command_uses_output_seek_and_mp4_muxer(sample_video: Path, ffmpeg_path: str) -> None:
    time_range = TimeRange(30, 90)
    options = VideoTranscodeOptions.local_clip(time_range)
    transcoder = VideoTranscoder(ffmpeg_path)
    command = transcoder.build_command(
        sample_video,
        sample_video.with_name("sample_clip_30s-90s.partial-test.mp4"),
        options,
        time_range=time_range,
    )

    input_index = command.index("-i")
    seek_index = command.index("-ss")
    duration_index = command.index("-t")
    muxer_index = command.index("-f")
    assert input_index < seek_index < duration_index
    assert command[seek_index + 1] == "30"
    assert command[duration_index + 1] == "60"
    assert command[muxer_index + 1] == "mp4"
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-c:a") + 1] == "aac"
    assert command[-1].endswith(".partial-test.mp4")


def test_regular_transcode_command_does_not_add_local_clip_options(
    sample_video: Path,
    ffmpeg_path: str,
) -> None:
    transcoder = VideoTranscoder(ffmpeg_path)
    command = transcoder.build_command(
        sample_video,
        sample_video.with_name("sample_h264.mp4"),
        VideoTranscodeOptions(mode="transcode", container="mp4", suffix="_h264"),
    )

    assert "-ss" not in command
    assert "-t" not in command
    assert command.count("-f") == 0


@pytest.mark.parametrize(
    "options,file_exists_action,error",
    [
        (
            VideoTranscodeOptions(mode="transcode", container="mp4", video_codec="copy"),
            "number",
            "H.264 MP4",
        ),
        (
            replace(VideoTranscodeOptions.local_clip(TimeRange(0, 1)), keep_original=False),
            "number",
            "preserves the source",
        ),
        (VideoTranscodeOptions.local_clip(TimeRange(0, 1)), "overwrite", "numbered output"),
    ],
)
def test_local_clip_rejects_unsafe_contracts(
    sample_video: Path,
    ffmpeg_path: str,
    tmp_path: Path,
    options: VideoTranscodeOptions,
    file_exists_action: str,
    error: str,
) -> None:
    transcoder = VideoTranscoder(ffmpeg_path)

    with pytest.raises(ValueError, match=error):
        transcoder.transcode(
            sample_video,
            options,
            output_dir=tmp_path / "clips",
            file_exists_action=file_exists_action,  # type: ignore[arg-type]
            time_range=TimeRange(0, 1),
        )


def test_local_clip_rejects_range_past_known_source_duration(
    sample_video: Path,
    ffmpeg_path: str,
    tmp_path: Path,
) -> None:
    transcoder = VideoTranscoder(ffmpeg_path)
    time_range = TimeRange(0, 3)

    with pytest.raises(ValueError, match="greater than the video duration"):
        transcoder.transcode(
            sample_video,
            VideoTranscodeOptions.local_clip(time_range),
            output_dir=tmp_path / "clips",
            file_exists_action="number",
            time_range=time_range,
        )


def test_local_clip_requires_a_known_positive_duration(
    sample_video: Path,
    ffmpeg_path: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    time_range = TimeRange(0, 1)
    transcoder = VideoTranscoder(ffmpeg_path)
    monkeypatch.setattr(
        transcoder_module,
        "probe_media",
        lambda path, _ffmpeg: MediaInfo(path=Path(path), duration=None),
    )

    with pytest.raises(ValueError, match="known positive source duration"):
        transcoder.transcode(
            sample_video,
            VideoTranscodeOptions.local_clip(time_range),
            output_dir=tmp_path / "clips",
            file_exists_action="number",
            time_range=time_range,
        )

    assert not list((tmp_path / "clips").glob("*.partial-*.mp4"))


@pytest.mark.parametrize("failure", [RuntimeError("forced FFmpeg failure"), TranscodeCancelled("cancelled")])
def test_local_clip_failure_or_cancel_removes_only_owned_partial(
    sample_video: Path,
    ffmpeg_path: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    source_hash = hashlib.sha256(sample_video.read_bytes()).hexdigest()
    time_range = TimeRange(0, 1)
    output_dir = tmp_path / "clips"
    transcoder = VideoTranscoder(ffmpeg_path)

    def fail_after_writing_partial(command: list[str], _duration: float | None) -> str:
        partial_path = Path(command[-1])
        assert ".partial-" in partial_path.name
        assert partial_path.suffix == ".mp4"
        partial_path.write_bytes(b"partial output")
        raise failure

    monkeypatch.setattr(transcoder, "_run_ffmpeg", fail_after_writing_partial)

    with pytest.raises(type(failure)):
        transcoder.transcode(
            sample_video,
            VideoTranscodeOptions.local_clip(time_range),
            output_dir=output_dir,
            file_exists_action="number",
            time_range=time_range,
        )

    assert hashlib.sha256(sample_video.read_bytes()).hexdigest() == source_hash
    assert not (output_dir / "sample_clip_0s-1s.mp4").exists()
    assert not list(output_dir.glob("*.partial-*.mp4"))


def test_local_clip_finalization_failure_keeps_existing_output_and_cleans_partial(
    sample_video: Path,
    ffmpeg_path: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_hash = hashlib.sha256(sample_video.read_bytes()).hexdigest()
    time_range = TimeRange(0, 1)
    output_dir = tmp_path / "clips"
    transcoder = VideoTranscoder(ffmpeg_path)

    monkeypatch.setattr(transcoder_module, "encoder_available", lambda *_args: True)
    monkeypatch.setattr(
        transcoder_module,
        "probe_media",
        lambda path, _ffmpeg: MediaInfo(
            path=Path(path),
            video_codec="h264",
            audio_codec="aac",
            duration=2.0,
            has_audio=True,
        ),
    )

    def write_partial(command: list[str], _duration: float | None) -> str:
        Path(command[-1]).write_bytes(b"complete temporary mp4")
        return ""

    def collide(partial_path: Path, output_path: Path) -> None:
        output_path.write_bytes(b"late user output")
        raise FileExistsError("Local Clip output already exists")

    monkeypatch.setattr(transcoder, "_run_ffmpeg", write_partial)
    monkeypatch.setattr(transcoder, "_finalize_local_clip_output", collide)

    with pytest.raises(FileExistsError, match="already exists"):
        transcoder.transcode(
            sample_video,
            VideoTranscodeOptions.local_clip(time_range),
            output_dir=output_dir,
            file_exists_action="number",
            time_range=time_range,
        )

    assert hashlib.sha256(sample_video.read_bytes()).hexdigest() == source_hash
    assert (output_dir / "sample_clip_0s-1s.mp4").read_bytes() == b"late user output"
    assert not list(output_dir.glob("*.partial-*.mp4"))


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
