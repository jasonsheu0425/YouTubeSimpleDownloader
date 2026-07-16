from __future__ import annotations

from pathlib import Path

import pytest

from ytsimpledownloader.downloader import SingleVideoDownloader
from ytsimpledownloader.transcoder import VideoTranscodeOptions


@pytest.fixture
def downloader_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(SingleVideoDownloader, "_ensure_ffmpeg_exe", lambda self: "ffmpeg.exe")

    def create(**kwargs) -> SingleVideoDownloader:
        return SingleVideoDownloader(tmp_path, **kwargs)

    return create


def test_audio_options_do_not_embed_thumbnail_by_default(downloader_factory) -> None:
    options = downloader_factory(audio_format="mp3")._audio_options()

    assert "writethumbnail" not in options
    assert [processor["key"] for processor in options["postprocessors"]] == ["FFmpegExtractAudio"]


def test_mp3_thumbnail_embedding_follows_audio_extraction(downloader_factory) -> None:
    options = downloader_factory(audio_format="mp3", embed_audio_thumbnail=True)._audio_options()

    assert options["writethumbnail"] is True
    assert [processor["key"] for processor in options["postprocessors"]] == [
        "FFmpegExtractAudio",
        "EmbedThumbnail",
    ]
    assert options["postprocessors"][1]["already_have_thumbnail"] is False


@pytest.mark.parametrize("audio_format", ["m4a", "opus", "wav", "flac"])
def test_thumbnail_embedding_is_not_enabled_for_other_audio_formats(
    downloader_factory,
    audio_format: str,
) -> None:
    options = downloader_factory(
        audio_format=audio_format,
        embed_audio_thumbnail=True,
    )._audio_options()

    assert "writethumbnail" not in options
    assert [processor["key"] for processor in options["postprocessors"]] == ["FFmpegExtractAudio"]


def test_thumbnail_setting_does_not_change_base_video_or_osu_options(downloader_factory) -> None:
    standard = downloader_factory(embed_audio_thumbnail=True)
    osu = downloader_factory(
        embed_audio_thumbnail=True,
        video_processing_options=VideoTranscodeOptions(mode="osu"),
    )

    assert "writethumbnail" not in standard._base_opts()
    assert "writethumbnail" not in osu._base_opts()
    assert standard._mp4_format_selector() == downloader_factory()._mp4_format_selector()
    normalized_osu = osu.video_processing_options.normalized()
    assert normalized_osu.mode == "osu"
    assert normalized_osu.container == "mp4"
    assert normalized_osu.video_codec == "h264"
