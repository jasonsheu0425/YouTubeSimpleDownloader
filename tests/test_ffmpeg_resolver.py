from __future__ import annotations

from pathlib import Path

from ytsimpledownloader import ffmpeg_resolver


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

    resolved = Path(ffmpeg_resolver.ensure_ffmpeg_exe())

    assert resolved == target
    assert target.read_bytes() == source.read_bytes()


def test_imageio_fallback_is_reported(tmp_path: Path, monkeypatch) -> None:
    fallback = tmp_path / "imageio-ffmpeg.exe"
    fallback.write_bytes(b"fallback")
    messages: list[str] = []

    monkeypatch.setattr(ffmpeg_resolver, "_bundled_ffmpeg_candidates", list)
    monkeypatch.setattr(ffmpeg_resolver.imageio_ffmpeg, "get_ffmpeg_exe", lambda: str(fallback))

    source, is_fallback = ffmpeg_resolver.resolve_ffmpeg_source(messages.append)

    assert source == fallback
    assert is_fallback is True
    assert messages and "imageio-ffmpeg fallback" in messages[0]
