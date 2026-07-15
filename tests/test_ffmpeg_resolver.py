from __future__ import annotations

from pathlib import Path

import pytest

from ytsimpledownloader import ffmpeg_resolver


def test_bundled_minimum_version_is_accepted(tmp_path: Path, monkeypatch) -> None:
    bundled = tmp_path / "bundled" / "ffmpeg.exe"
    bundled.parent.mkdir()
    bundled.write_bytes(b"fixed-ffmpeg-binary")

    monkeypatch.setattr(ffmpeg_resolver, "_bundled_ffmpeg_candidates", lambda: [bundled])
    monkeypatch.setattr(ffmpeg_resolver, "_read_ffmpeg_version", lambda _path: ((8, 1, 2), "8.1.2"))

    source, is_fallback = ffmpeg_resolver.resolve_ffmpeg_source()

    assert source == bundled
    assert is_fallback is False


def test_runtime_copy_is_synchronized_by_content(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "bundled" / "ffmpeg.exe"
    source.parent.mkdir()
    source.write_bytes(b"fixed-ffmpeg-binary")
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    target = runtime_dir / "ffmpeg.exe"
    target.write_bytes(b"old-ffmpeg-binary!!")

    monkeypatch.setattr(ffmpeg_resolver, "FFMPEG_DIR", runtime_dir)
    monkeypatch.setattr(ffmpeg_resolver, "_bundled_ffmpeg_candidates", lambda: [source])
    monkeypatch.setattr(ffmpeg_resolver, "_read_ffmpeg_version", lambda _path: ((8, 1, 2), "8.1.2"))

    resolved = Path(ffmpeg_resolver.ensure_ffmpeg_exe())

    assert resolved == target
    assert target.read_bytes() == source.read_bytes()


def test_imageio_fallback_below_minimum_is_rejected(tmp_path: Path, monkeypatch) -> None:
    fallback = tmp_path / "imageio-ffmpeg.exe"
    fallback.write_bytes(b"fallback")
    messages: list[str] = []

    monkeypatch.setattr(ffmpeg_resolver, "_bundled_ffmpeg_candidates", list)
    monkeypatch.setattr(ffmpeg_resolver.imageio_ffmpeg, "get_ffmpeg_exe", lambda: str(fallback))
    monkeypatch.setattr(ffmpeg_resolver, "_read_ffmpeg_version", lambda _path: ((7, 1, 0), "7.1.0"))

    with pytest.raises(RuntimeError, match=r"imageio-ffmpeg fallback.*7\.1\.0.*8\.1\.2"):
        ffmpeg_resolver.resolve_ffmpeg_source(messages.append)

    assert any("checking imageio-ffmpeg fallback" in message for message in messages)
    assert any("required minimum 8.1.2" in message for message in messages)
