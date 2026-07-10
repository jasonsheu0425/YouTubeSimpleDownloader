from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from shutil import copy2
from threading import Event
import subprocess
import time
from typing import Callable, Literal

import imageio_ffmpeg

from .media_probe import MediaInfo, probe_media
from .paths import FFMPEG_DIR


ProgressCallback = Callable[[str], None]
FileExistsAction = Literal["overwrite", "skip", "number"]

VIDEO_PROCESSING_MODES = ("keep", "prefer_compatible", "transcode", "osu")
VIDEO_CODECS = ("copy", "h264", "h265", "av1")
RESOLUTION_RULES = ("original", "2160", "1440", "1080", "720", "480", "custom")
FPS_RULES = ("original", "60", "30", "24", "custom")
QUALITY_RULES = ("high", "balanced", "small", "custom")
SPEED_RULES = ("veryfast", "fast", "medium", "slow")
AUDIO_RULES = ("keep", "remove")

CONTAINER_SUFFIXES = {
    "mp4": ".mp4",
    "mkv": ".mkv",
    "webm": ".webm",
}

CRF_BY_QUALITY = {
    "high": 18,
    "balanced": 20,
    "small": 24,
}

PRESET_BY_SPEED = {
    "veryfast": "veryfast",
    "fast": "fast",
    "medium": "medium",
    "slow": "slow",
}

HEIGHT_BY_RULE = {
    "2160": 2160,
    "1440": 1440,
    "1080": 1080,
    "720": 720,
    "480": 480,
}


class TranscodeCancelled(Exception):
    """Raised when a transcode job is cancelled."""


@dataclass(frozen=True)
class VideoTranscodeOptions:
    mode: str = "keep"
    container: str = "mp4"
    video_codec: str = "h264"
    resolution: str = "original"
    custom_width: int = 1280
    custom_height: int = 720
    fps: str = "original"
    custom_fps: float = 30.0
    quality: str = "balanced"
    crf: int = 20
    speed: str = "medium"
    audio: str = "keep"
    keep_original: bool = True
    suffix: str = "_h264"
    pixel_format: str = "yuv420p"
    faststart: bool = True
    no_upscale: bool = True
    aspect_mode: str = "fit"
    extra_args: tuple[str, ...] = ()

    @classmethod
    def osu(cls, fps: str = "60") -> "VideoTranscodeOptions":
        return cls(
            mode="osu",
            container="mp4",
            video_codec="h264",
            resolution="720",
            fps=fps if fps in {"30", "60"} else "60",
            quality="custom",
            crf=20,
            speed="medium",
            audio="remove",
            keep_original=True,
            suffix="_osu_h264",
            pixel_format="yuv420p",
            faststart=True,
            no_upscale=True,
            aspect_mode="fit",
        )

    def needs_transcode(self) -> bool:
        return self.mode in {"transcode", "osu"}

    def prefer_compatible(self) -> bool:
        return self.mode == "prefer_compatible"

    def effective_crf(self) -> int:
        return self.crf if self.quality == "custom" else CRF_BY_QUALITY.get(self.quality, 20)

    def effective_preset(self) -> str:
        return PRESET_BY_SPEED.get(self.speed, "medium")

    def output_suffix(self) -> str:
        return CONTAINER_SUFFIXES.get(self.container, ".mp4")

    def normalized(self) -> "VideoTranscodeOptions":
        if self.mode == "osu":
            return VideoTranscodeOptions.osu(self.fps)
        container = self.container if self.container in CONTAINER_SUFFIXES else "mp4"
        video_codec = self.video_codec if self.video_codec in VIDEO_CODECS else "h264"
        resolution = self.resolution if self.resolution in RESOLUTION_RULES else "original"
        fps = self.fps if self.fps in FPS_RULES else "original"
        quality = self.quality if self.quality in QUALITY_RULES else "balanced"
        speed = self.speed if self.speed in SPEED_RULES else "medium"
        audio = self.audio if self.audio in AUDIO_RULES else "keep"
        return VideoTranscodeOptions(
            mode=self.mode if self.mode in VIDEO_PROCESSING_MODES else "keep",
            container=container,
            video_codec=video_codec,
            resolution=resolution,
            custom_width=_even(self.custom_width),
            custom_height=_even(self.custom_height),
            fps=fps,
            custom_fps=max(1.0, float(self.custom_fps or 30.0)),
            quality=quality,
            crf=max(0, min(51, int(self.crf))),
            speed=speed,
            audio=audio,
            keep_original=bool(self.keep_original),
            suffix=self.suffix or "_h264",
            pixel_format=self.pixel_format or "yuv420p",
            faststart=bool(self.faststart),
            no_upscale=bool(self.no_upscale),
            aspect_mode=self.aspect_mode or "fit",
            extra_args=tuple(self.extra_args),
        )


@dataclass(frozen=True)
class TranscodeResult:
    path: Path
    source_path: Path
    media_info: MediaInfo
    skipped: bool = False


def ensure_ffmpeg_exe() -> str:
    source = Path(imageio_ffmpeg.get_ffmpeg_exe())
    target = FFMPEG_DIR / "ffmpeg.exe"
    if not target.exists() or target.stat().st_size != source.stat().st_size:
        target.parent.mkdir(parents=True, exist_ok=True)
        copy2(source, target)
    ffmpeg_dir = str(target.parent)
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    if ffmpeg_dir not in path_entries:
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    return str(target)


def ffmpeg_encoders(ffmpeg_path: str | Path | None = None) -> set[str]:
    ffmpeg = str(ffmpeg_path or ensure_ffmpeg_exe())
    try:
        completed = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=True,
        )
    except Exception:
        return set()

    encoders = set()
    for line in completed.stdout.splitlines():
        bits = line.split()
        if len(bits) >= 2 and bits[0].startswith("V"):
            encoders.add(bits[1])
    return encoders


def encoder_available(codec: str, ffmpeg_path: str | Path | None = None) -> bool:
    encoders = ffmpeg_encoders(ffmpeg_path)
    if codec == "h264":
        return "libx264" in encoders
    if codec == "h265":
        return bool({"libx265", "hevc_nvenc"} & encoders)
    if codec == "av1":
        return bool({"libsvtav1", "libaom-av1", "av1_nvenc"} & encoders)
    if codec == "copy":
        return True
    return False


def friendly_transcode_error(message: str) -> str:
    lower = message.lower()
    if "no such file" in lower or "cannot find" in lower:
        return "輸入檔案不存在。"
    if "permission denied" in lower or "access is denied" in lower:
        return "輸出資料夾沒有寫入權限，或檔案正在被其他程式使用。"
    if "no space" in lower or "not enough space" in lower:
        return "磁碟空間不足。"
    if "unknown encoder" in lower or "encoder" in lower and ("not found" in lower or "not available" in lower):
        return "指定編碼器不可用。"
    if "invalid data" in lower or "could not find codec" in lower:
        return "不支援的影片格式。"
    if "cancel" in lower:
        return "轉檔被取消。"
    if "ffmpeg" in lower:
        return "FFmpeg 轉檔失敗。"
    return "影片轉檔失敗。"


class VideoTranscoder:
    def __init__(
        self,
        ffmpeg_path: str | Path | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> None:
        self.ffmpeg_path = str(ffmpeg_path or ensure_ffmpeg_exe())
        self.progress_callback = progress_callback or (lambda _message: None)
        self.cancel_event = cancel_event

    def transcode(
        self,
        source_path: str | Path,
        options: VideoTranscodeOptions,
        output_dir: str | Path | None = None,
        file_exists_action: FileExistsAction = "number",
    ) -> TranscodeResult:
        options = options.normalized()
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(str(source))
        if options.video_codec != "copy" and not encoder_available(options.video_codec, self.ffmpeg_path):
            raise RuntimeError(f"Encoder not available: {options.video_codec}")

        output_path, skipped = self.prepare_output_path(source, options, output_dir, file_exists_action)
        if skipped:
            info = probe_media(output_path, self.ffmpeg_path)
            return TranscodeResult(output_path, source, info, skipped=True)

        command = self.build_command(source, output_path, options)
        source_info = probe_media(source, self.ffmpeg_path)
        self._emit(f"Transcoding: {source.name}")
        stderr_tail = self._run_ffmpeg(command, source_info.duration)
        if self.cancel_event and self.cancel_event.is_set():
            if output_path.exists():
                try:
                    output_path.unlink()
                except OSError:
                    pass
            raise TranscodeCancelled("Transcode cancelled by user.")
        if not output_path.exists():
            raise RuntimeError(stderr_tail or "FFmpeg did not create an output file.")

        if not options.keep_original and source.exists() and source.resolve() != output_path.resolve():
            source.unlink()

        info = probe_media(output_path, self.ffmpeg_path)
        self._emit(f"Transcoded: {output_path}")
        if info.error:
            self._emit(f"Media info note: {info.error}")
        self._emit(f"Media info: {info.summary()}")
        return TranscodeResult(output_path, source, info)

    def prepare_output_path(
        self,
        source: Path,
        options: VideoTranscodeOptions,
        output_dir: str | Path | None = None,
        file_exists_action: FileExistsAction = "number",
    ) -> tuple[Path, bool]:
        folder = Path(output_dir) if output_dir else source.parent
        folder.mkdir(parents=True, exist_ok=True)
        suffix = options.output_suffix()
        base_name = f"{source.stem}{options.suffix or ''}{suffix}"
        target = folder / base_name

        if target.resolve() == source.resolve():
            target = folder / f"{source.stem}_converted{suffix}"

        if not target.exists():
            return target, False
        if file_exists_action == "skip":
            return target, True
        if file_exists_action == "overwrite":
            target.unlink()
            return target, False
        return _numbered_path(target), False

    def build_command(self, source: Path, output: Path, options: VideoTranscodeOptions) -> list[str]:
        video_filters = self._video_filters(options)
        command = [
            self.ffmpeg_path,
            "-hide_banner",
            "-y",
            "-i",
            str(source),
        ]
        if video_filters:
            command.extend(["-vf", ",".join(video_filters)])

        command.extend(self._video_args(options))
        command.extend(self._audio_args(options))

        if options.faststart and options.container == "mp4":
            command.extend(["-movflags", "+faststart"])
        if options.extra_args:
            command.extend(options.extra_args)

        command.extend(["-progress", "pipe:1", "-nostats", str(output)])
        return command

    def _video_args(self, options: VideoTranscodeOptions) -> list[str]:
        if options.video_codec == "copy":
            return ["-c:v", "copy"]
        if options.video_codec == "h265":
            encoder = "libx265" if "libx265" in ffmpeg_encoders(self.ffmpeg_path) else "hevc_nvenc"
        elif options.video_codec == "av1":
            encoders = ffmpeg_encoders(self.ffmpeg_path)
            if "libsvtav1" in encoders:
                encoder = "libsvtav1"
            elif "libaom-av1" in encoders:
                encoder = "libaom-av1"
            else:
                encoder = "av1_nvenc"
        else:
            encoder = "libx264"

        args = ["-c:v", encoder, "-crf", str(options.effective_crf()), "-preset", options.effective_preset()]
        if options.pixel_format:
            args.extend(["-pix_fmt", options.pixel_format])
        return args

    def _audio_args(self, options: VideoTranscodeOptions) -> list[str]:
        if options.audio == "remove":
            return ["-an"]
        if options.container == "mp4":
            return ["-c:a", "aac", "-b:a", "192k"]
        return ["-c:a", "copy"]

    def _video_filters(self, options: VideoTranscodeOptions) -> list[str]:
        filters = []
        scale_filter = self._scale_filter(options)
        if scale_filter:
            filters.append(scale_filter)
        fps_value = self._fps_value(options)
        if fps_value:
            filters.append(f"fps={fps_value:g}")
        return filters

    def _scale_filter(self, options: VideoTranscodeOptions) -> str:
        if options.resolution == "original":
            return ""
        if options.resolution == "custom":
            width = _even(options.custom_width)
            height = _even(options.custom_height)
            if options.aspect_mode == "crop":
                return f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
            if options.aspect_mode == "pad":
                return (
                    f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
                )
            return f"scale={width}:{height}:force_original_aspect_ratio=decrease"

        height = HEIGHT_BY_RULE.get(options.resolution)
        if not height:
            return ""
        if options.no_upscale:
            return f"scale='if(gt(ih,{height}),-2,iw)':'if(gt(ih,{height}),{height},ih)'"
        return f"scale=-2:{height}"

    def _fps_value(self, options: VideoTranscodeOptions) -> float | None:
        if options.fps == "original":
            return None
        if options.fps == "custom":
            return options.custom_fps
        try:
            return float(options.fps)
        except ValueError:
            return None

    def _run_ffmpeg(self, command: list[str], duration: float | None) -> str:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        start = time.monotonic()
        stderr_lines: list[str] = []
        assert process.stdout is not None
        assert process.stderr is not None

        try:
            while True:
                if self.cancel_event and self.cancel_event.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise TranscodeCancelled("Transcode cancelled by user.")

                line = process.stdout.readline()
                if line:
                    self._handle_progress_line(line.strip(), duration, start)

                stderr_line = process.stderr.readline()
                if stderr_line:
                    stderr_lines.append(stderr_line.strip())
                    stderr_lines = stderr_lines[-25:]

                if not line and not stderr_line and process.poll() is not None:
                    break
        finally:
            if process.poll() is None:
                process.terminate()

        return_code = process.wait()
        stderr_tail = "\n".join(stderr_lines)
        if return_code != 0:
            raise RuntimeError(stderr_tail or f"FFmpeg exited with code {return_code}")
        return stderr_tail

    def _handle_progress_line(self, line: str, duration: float | None, start: float) -> None:
        if not line or "=" not in line:
            return
        key, value = line.split("=", 1)
        if key == "out_time_ms" and duration:
            try:
                seconds = int(value) / 1_000_000
            except ValueError:
                return
            percent = min(100.0, max(0.0, seconds / duration * 100))
            elapsed = time.monotonic() - start
            eta = (elapsed / percent * (100 - percent)) if percent > 0 else 0
            self._emit(f"Transcoding: {percent:.1f}% | {seconds:.1f}/{duration:.1f}s | ETA {eta:.0f}s")
        elif key == "speed" and value:
            self._emit(f"Transcode speed: {value}")
        elif key == "progress" and value == "end":
            self._emit("Transcoding: 100%")

    def _emit(self, message: str) -> None:
        self.progress_callback(message)


def _numbered_path(path: Path) -> Path:
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _even(value: int) -> int:
    normalized = max(2, int(value or 2))
    return normalized if normalized % 2 == 0 else normalized - 1
