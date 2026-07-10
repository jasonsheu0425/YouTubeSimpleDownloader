from __future__ import annotations

from dataclasses import dataclass
import json
import re
import subprocess
from pathlib import Path
from shutil import which


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    container: str = ""
    video_codec: str = ""
    audio_codec: str = ""
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    bitrate: int | None = None
    duration: float | None = None
    size_bytes: int = 0
    pixel_format: str = ""
    has_audio: bool = False
    error: str = ""

    def summary(self) -> str:
        parts = []
        if self.container:
            parts.append(f"container={self.container}")
        if self.video_codec:
            parts.append(f"video={self.video_codec}")
        if self.audio_codec:
            parts.append(f"audio={self.audio_codec}")
        if self.width and self.height:
            parts.append(f"{self.width}x{self.height}")
        if self.fps:
            parts.append(f"{self.fps:g}fps")
        if self.pixel_format:
            parts.append(self.pixel_format)
        if self.duration:
            parts.append(f"{self.duration:.1f}s")
        if self.size_bytes:
            parts.append(f"{self.size_bytes / 1024 / 1024:.2f}MB")
        if self.error:
            parts.append(f"error={self.error}")
        return " | ".join(parts) if parts else "No media details available"


def find_ffprobe(ffmpeg_path: str | Path | None = None) -> str:
    candidates: list[Path] = []
    if ffmpeg_path:
        ffmpeg = Path(ffmpeg_path)
        candidates.append(ffmpeg.with_name("ffprobe.exe"))
        candidates.append(ffmpeg.with_name("ffprobe"))

    for name in ("ffprobe.exe", "ffprobe"):
        found = which(name)
        if found:
            candidates.append(Path(found))

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


def probe_media(path: str | Path, ffmpeg_path: str | Path | None = None) -> MediaInfo:
    source = Path(path)
    size = source.stat().st_size if source.exists() else 0
    if not source.exists():
        return MediaInfo(path=source, size_bytes=size, error="Input file does not exist.")

    ffprobe = find_ffprobe(ffmpeg_path)
    if ffprobe:
        try:
            return _probe_with_ffprobe(source, ffprobe, size)
        except Exception as exc:
            ffprobe_error = str(exc)
    else:
        ffprobe_error = "ffprobe not found"

    if ffmpeg_path:
        try:
            return _probe_with_ffmpeg_i(source, str(ffmpeg_path), size, ffprobe_error)
        except Exception as exc:
            return MediaInfo(path=source, size_bytes=size, error=f"{ffprobe_error}; ffmpeg probe failed: {exc}")

    return MediaInfo(path=source, size_bytes=size, error=ffprobe_error)


def _probe_with_ffprobe(source: Path, ffprobe: str, size: int) -> MediaInfo:
    command = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(source),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    data = json.loads(completed.stdout or "{}")
    format_info = data.get("format") or {}
    streams = data.get("streams") or []
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})

    return MediaInfo(
        path=source,
        container=str(format_info.get("format_name") or ""),
        video_codec=str(video_stream.get("codec_name") or ""),
        audio_codec=str(audio_stream.get("codec_name") or ""),
        width=_int_or_none(video_stream.get("width")),
        height=_int_or_none(video_stream.get("height")),
        fps=_fps_from_stream(video_stream),
        bitrate=_int_or_none(format_info.get("bit_rate") or video_stream.get("bit_rate")),
        duration=_float_or_none(format_info.get("duration") or video_stream.get("duration")),
        size_bytes=size,
        pixel_format=_clean_pixel_format(str(video_stream.get("pix_fmt") or "")),
        has_audio=bool(audio_stream),
    )


def _probe_with_ffmpeg_i(source: Path, ffmpeg: str, size: int, prior_error: str) -> MediaInfo:
    command = [ffmpeg, "-hide_banner", "-i", str(source)]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = (completed.stderr or "") + "\n" + (completed.stdout or "")

    duration = None
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if duration_match:
        hours, minutes, seconds = duration_match.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    video_match = re.search(r"Video:\s*([^,\s]+).*?(\d{2,5})x(\d{2,5}).*?(?:(\d+(?:\.\d+)?)\s*fps)?", text)
    audio_match = re.search(r"Audio:\s*([^,\s]+)", text)
    pixel_match = re.search(r"Video:[^\n,]+,\s*([^,\s]+)", text)
    container_match = re.search(r"Input #0,\s*([^,]+),", text)

    return MediaInfo(
        path=source,
        container=container_match.group(1).strip() if container_match else "",
        video_codec=video_match.group(1) if video_match else "",
        audio_codec=audio_match.group(1) if audio_match else "",
        width=int(video_match.group(2)) if video_match else None,
        height=int(video_match.group(3)) if video_match else None,
        fps=float(video_match.group(4)) if video_match and video_match.group(4) else None,
        duration=duration,
        size_bytes=size,
        pixel_format=_clean_pixel_format(pixel_match.group(1) if pixel_match else ""),
        has_audio=bool(audio_match),
        error=f"ffprobe unavailable: {prior_error}",
    )


def _fps_from_stream(stream: dict) -> float | None:
    for key in ("avg_frame_rate", "r_frame_rate"):
        value = stream.get(key)
        if not value or value == "0/0":
            continue
        if isinstance(value, str) and "/" in value:
            numerator, denominator = value.split("/", 1)
            denominator_float = float(denominator)
            if denominator_float:
                return round(float(numerator) / denominator_float, 3)
        return _float_or_none(value)
    return None


def _int_or_none(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None


def _clean_pixel_format(value: str) -> str:
    return value.split("(", 1)[0].split(",", 1)[0].strip()
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
