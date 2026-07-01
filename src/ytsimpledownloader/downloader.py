from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from shutil import copy2
from shutil import which
from threading import Event
from typing import Callable, Literal
from urllib.parse import parse_qs, urlparse

import imageio_ffmpeg
from yt_dlp import YoutubeDL
from yt_dlp.utils import download_range_func

from .paths import FFMPEG_DIR


DownloadMode = Literal["mp3", "mp4", "both"]
FileExistsAction = Literal["overwrite", "skip", "number"]
Mp3Quality = Literal["128", "192", "256", "320"]
Mp4Quality = Literal["best", "1080", "720", "480"]
AudioFormat = Literal["mp3", "m4a", "opus", "wav", "flac"]
VideoFormat = Literal["mp4", "mkv", "webm"]
ProgressCallback = Callable[[str], None]

AUDIO_FORMATS: tuple[str, ...] = ("mp3", "m4a", "opus", "wav", "flac")
VIDEO_FORMATS: tuple[str, ...] = ("mp4", "mkv", "webm")


@dataclass(frozen=True)
class OutputOptions:
    folder_rule: str = "none"
    filename_rule: str = "title"
    custom_template: str = ""


DEFAULT_OUTPUT_OPTIONS = OutputOptions()


class YtDlpLogger:
    def __init__(self, emit: ProgressCallback) -> None:
        self.emit = emit

    def debug(self, message: str) -> None:
        return

    def warning(self, message: str) -> None:
        self.emit(f"Warning: {message}")

    def error(self, message: str) -> None:
        self.emit(f"Error: {message}")


class DownloadCancelled(Exception):
    """Raised when the user cancels an active download."""


@dataclass(frozen=True)
class DownloadResult:
    mode: Literal["mp3", "mp4"]
    path: Path
    skipped: bool = False


@dataclass(frozen=True)
class VideoInfo:
    title: str
    uploader: str
    duration: int | None
    thumbnail_url: str
    webpage_url: str
    mp3_path: Path
    mp4_path: Path
    audio_format: str = "mp3"
    video_format: str = "mp4"


@dataclass(frozen=True)
class PlaylistInfo:
    title: str
    urls: list[str]


PLAYLIST_ID_PREFIXES = ("PL", "UU", "OL", "FL")


def extract_video_id(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    if "youtu.be" in host and path_parts:
        return path_parts[0]

    query = parse_qs(parsed.query)
    video_ids = query.get("v") or []
    if video_ids:
        return video_ids[0]

    if path_parts and path_parts[0] in {"embed", "shorts", "live"} and len(path_parts) > 1:
        return path_parts[1]

    return ""


def is_playlist_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    if "youtube.com" not in host and "youtu.be" not in host:
        return False

    query = parse_qs(parsed.query)
    playlist_ids = query.get("list") or []
    if not playlist_ids:
        return False

    if parsed.path.rstrip("/") == "/playlist":
        return True

    playlist_id = playlist_ids[0]
    return parsed.path.rstrip("/") == "/watch" and playlist_id.startswith(PLAYLIST_ID_PREFIXES)


class SingleVideoDownloader:
    def __init__(
        self,
        output_dir: Path,
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
        test_seconds: int | None = None,
        file_exists_action: FileExistsAction = "number",
        mp3_quality: Mp3Quality = "192",
        mp4_quality: Mp4Quality = "best",
        audio_format: AudioFormat = "mp3",
        video_format: VideoFormat = "mp4",
        output_options: OutputOptions | None = None,
        resume_downloads: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.progress_callback = progress_callback or (lambda _message: None)
        self.cancel_event = cancel_event
        self.test_seconds = test_seconds
        self.file_exists_action = file_exists_action
        self.mp3_quality = mp3_quality
        self.mp4_quality = mp4_quality
        self.audio_format = self._validate_audio_format(audio_format)
        self.video_format = self._validate_video_format(video_format)
        self.output_options = output_options or DEFAULT_OUTPUT_OPTIONS
        self.resume_downloads = resume_downloads
        self.ffmpeg_path = self._ensure_ffmpeg_exe()

    def fetch_video_info(
        self,
        url: str,
        playlist_title: str = "",
        playlist_index: int | None = None,
    ) -> VideoInfo:
        clean_url = url.strip()
        if not clean_url:
            raise ValueError("URL is required.")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        with YoutubeDL(self._base_opts()) as ydl:
            info = ydl.extract_info(clean_url, download=False)

        return VideoInfo(
            title=info.get("title") or "(unknown title)",
            uploader=info.get("uploader") or info.get("channel") or "(unknown channel)",
            duration=info.get("duration"),
            thumbnail_url=info.get("thumbnail") or "",
            webpage_url=info.get("webpage_url") or clean_url,
            mp3_path=self.expected_output_path(info, self._audio_suffix(), playlist_title, playlist_index),
            mp4_path=self.expected_output_path(info, self._video_suffix(), playlist_title, playlist_index),
            audio_format=self.audio_format,
            video_format=self.video_format,
        )

    def fetch_playlist_info(self, url: str) -> PlaylistInfo:
        clean_url = url.strip()
        if not clean_url:
            raise ValueError("URL is required.")

        opts = self._base_opts()
        opts["noplaylist"] = False
        opts["extract_flat"] = "in_playlist"
        opts["ignoreerrors"] = True

        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)

        entries = info.get("entries") or []
        urls = []
        for entry in entries:
            if not entry:
                continue
            webpage_url = entry.get("webpage_url")
            if webpage_url:
                urls.append(webpage_url)
                continue
            video_id = entry.get("id") or entry.get("url")
            if video_id:
                urls.append(f"https://www.youtube.com/watch?v={video_id}")

        if not urls:
            raise ValueError("Playlist does not contain downloadable public videos.")

        return PlaylistInfo(
            title=info.get("title") or "YouTube playlist",
            urls=urls,
        )

    def download(
        self,
        url: str,
        mode: DownloadMode,
        playlist_title: str = "",
        playlist_index: int | None = None,
    ) -> list[DownloadResult]:
        clean_url = url.strip()
        if not clean_url:
            raise ValueError("URL is required.")

        self.output_dir.mkdir(parents=True, exist_ok=True)

        if mode == "mp3":
            return [self.download_mp3(clean_url, playlist_title, playlist_index)]
        if mode == "mp4":
            return [self.download_mp4(clean_url, playlist_title, playlist_index)]
        if mode == "both":
            return [
                self.download_mp3(clean_url, playlist_title, playlist_index),
                self.download_mp4(clean_url, playlist_title, playlist_index),
            ]

        raise ValueError(f"Unsupported download mode: {mode}")

    def download_mp3(
        self,
        url: str,
        playlist_title: str = "",
        playlist_index: int | None = None,
    ) -> DownloadResult:
        label = self.audio_format.upper()
        self._emit(f"Starting {label} audio download...")
        info = self._extract_metadata(url)
        suffix = self._audio_suffix()
        target_path, skipped = self._prepare_target(info, suffix, playlist_title, playlist_index)
        if skipped:
            self._emit(f"{label} skipped, file already exists: {target_path}")
            return DownloadResult("mp3", target_path, skipped=True)

        info = self._run_yt_dlp(
            url,
            self._audio_options(),
            target_path,
        )
        path = self._expected_path(info, suffix, target_path)
        self._emit(f"{label} saved: {path}")
        return DownloadResult("mp3", path)

    def download_mp4(
        self,
        url: str,
        playlist_title: str = "",
        playlist_index: int | None = None,
    ) -> DownloadResult:
        label = self.video_format.upper()
        self._emit(f"Starting {label} video download...")
        info = self._extract_metadata(url)
        suffix = self._video_suffix()
        target_path, skipped = self._prepare_target(info, suffix, playlist_title, playlist_index)
        if skipped:
            self._emit(f"{label} skipped, file already exists: {target_path}")
            return DownloadResult("mp4", target_path, skipped=True)

        info = self._run_yt_dlp(
            url,
            {
                "format": self._video_format_selector(),
                "merge_output_format": self.video_format,
            },
            target_path,
        )
        path = self._expected_path(info, suffix, target_path)
        self._emit(f"{label} saved: {path}")
        return DownloadResult("mp4", path)

    def expected_output_path(
        self,
        info: dict,
        suffix: str,
        playlist_title: str = "",
        playlist_index: int | None = None,
    ) -> Path:
        prepared_info = self._info_with_context(info, playlist_title, playlist_index)
        outtmpl = self._output_template(suffix, playlist_title, playlist_index)
        with YoutubeDL({"outtmpl": outtmpl, "windowsfilenames": True, "restrictfilenames": False}) as ydl:
            return Path(ydl.prepare_filename(prepared_info)).with_suffix(suffix)

    def _extract_metadata(self, url: str) -> dict:
        with YoutubeDL(self._base_opts()) as ydl:
            return ydl.extract_info(url, download=False)

    def _prepare_target(
        self,
        info: dict,
        suffix: str,
        playlist_title: str = "",
        playlist_index: int | None = None,
    ) -> tuple[Path, bool]:
        target_path = self.expected_output_path(info, suffix, playlist_title, playlist_index)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if not target_path.exists():
            return target_path, False

        if self.file_exists_action == "skip":
            return target_path, True
        if self.file_exists_action == "overwrite":
            target_path.unlink()
            return target_path, False

        return self._numbered_path(target_path), False

    def _numbered_path(self, path: Path) -> Path:
        counter = 2
        while True:
            candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def _run_yt_dlp(self, url: str, mode_options: dict, target_path: Path) -> dict:
        opts = self._base_opts()
        opts["outtmpl"] = str(target_path.with_suffix(".%(ext)s"))
        opts["progress_hooks"] = [self._progress_hook]
        opts.update(mode_options)

        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)

    def _base_opts(self) -> dict:
        opts = {
            "outtmpl": str(self.output_dir / "%(title).200B [%(id)s].%(ext)s"),
            "ffmpeg_location": self.ffmpeg_path,
            "noplaylist": True,
            "windowsfilenames": True,
            "restrictfilenames": False,
            "quiet": True,
            "noprogress": True,
            "no_warnings": False,
            "continuedl": self.resume_downloads,
            "nopart": False,
            "logger": YtDlpLogger(self._emit),
        }
        node_path = which("node")
        if node_path:
            opts["js_runtimes"] = {"node": {"path": node_path}}
            opts["remote_components"] = ["ejs:github"]
        if self.test_seconds:
            opts["download_ranges"] = download_range_func(None, [(0, self.test_seconds)])
            opts["force_keyframes_at_cuts"] = True
        return opts

    def _audio_options(self) -> dict:
        postprocessor = {
            "key": "FFmpegExtractAudio",
            "preferredcodec": self.audio_format,
        }
        if self.audio_format == "mp3":
            postprocessor["preferredquality"] = self.mp3_quality

        if self.audio_format == "m4a":
            audio_selector = "bestaudio[ext=m4a]/bestaudio/best"
        elif self.audio_format == "opus":
            audio_selector = "bestaudio[acodec=opus]/bestaudio[ext=webm]/bestaudio/best"
        else:
            audio_selector = "bestaudio/best"

        return {
            "format": audio_selector,
            "postprocessors": [postprocessor],
        }

    def _video_format_selector(self) -> str:
        if self.video_format == "mp4":
            return self._mp4_format_selector()
        if self.video_format == "webm":
            return self._webm_format_selector()
        return self._generic_video_format_selector()

    def _mp4_format_selector(self) -> str:
        if self.mp4_quality == "best":
            return "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/best"

        height = int(self.mp4_quality)
        return (
            f"bv*[ext=mp4][height<={height}]+ba[ext=m4a]/"
            f"b[ext=mp4][height<={height}]/"
            f"bv*[height<={height}]+ba/"
            "best"
        )

    def _generic_video_format_selector(self) -> str:
        if self.mp4_quality == "best":
            return "bv*+ba/best"

        height = int(self.mp4_quality)
        return f"bv*[height<={height}]+ba/b[height<={height}]/best[height<={height}]/best"

    def _webm_format_selector(self) -> str:
        if self.mp4_quality == "best":
            return "bv*[ext=webm]+ba[ext=webm]/b[ext=webm]"

        height = int(self.mp4_quality)
        return f"bv*[ext=webm][height<={height}]+ba[ext=webm]/b[ext=webm][height<={height}]"

    def _progress_hook(self, data: dict) -> None:
        if self.cancel_event and self.cancel_event.is_set():
            raise DownloadCancelled("Download cancelled by user.")

        status = data.get("status")
        filename = data.get("filename")

        if status == "downloading":
            percent = data.get("_percent_str", "").strip()
            speed = data.get("_speed_str", "").strip()
            eta = data.get("_eta_str", "").strip()
            downloaded = data.get("_downloaded_bytes_str", "").strip()
            total = data.get("_total_bytes_str") or data.get("_total_bytes_estimate_str") or ""
            total = str(total).strip()
            bits = [part for part in (percent, speed, f"ETA {eta}" if eta else "") if part]
            if bits:
                size_part = f" | {downloaded}/{total}" if downloaded and total else ""
                self._emit("Downloading: " + " | ".join(bits) + size_part)
        elif status == "finished" and filename:
            self._emit(f"Downloaded: {filename}")

    def _expected_path(self, info: dict, suffix: str, target_path: Path) -> Path:
        requested_downloads = info.get("requested_downloads") or []
        for item in requested_downloads:
            filepath = item.get("filepath") or item.get("_filename")
            if filepath and Path(filepath).suffix.lower() == suffix:
                return Path(filepath)

        if target_path.exists():
            return target_path

        matches = sorted(target_path.parent.glob(f"*{suffix}"), key=lambda item: item.stat().st_mtime, reverse=True)
        if matches:
            return matches[0]

        return target_path

    def _info_with_context(self, info: dict, playlist_title: str, playlist_index: int | None) -> dict:
        prepared = dict(info)
        if playlist_title:
            prepared["playlist_title"] = playlist_title
        if playlist_index is not None:
            prepared["playlist_index"] = playlist_index
        return prepared

    def _output_template(
        self,
        suffix: str,
        playlist_title: str = "",
        playlist_index: int | None = None,
    ) -> str:
        filename = self._filename_template(playlist_index)
        folder = self._folder_template(suffix, playlist_title)
        if folder:
            return str(self.output_dir / folder / filename)
        return str(self.output_dir / filename)

    def _folder_template(self, suffix: str, playlist_title: str = "") -> str:
        rule = self.output_options.folder_rule
        if rule == "mode":
            return self.audio_format.upper() if suffix.lstrip(".") in AUDIO_FORMATS else self.video_format.upper()
        if rule == "channel":
            return "%(uploader).100B"
        if rule == "date":
            return "%(upload_date)s"
        if rule == "playlist" and playlist_title:
            return "%(playlist_title).120B"
        return ""

    def _filename_template(self, playlist_index: int | None = None) -> str:
        rule = self.output_options.filename_rule
        if rule == "channel_title":
            return "%(uploader).80B - %(title).160B [%(id)s].%(ext)s"
        if rule == "playlist_index_title" and playlist_index is not None:
            return "%(playlist_index)03d - %(title).180B [%(id)s].%(ext)s"
        if rule == "upload_date_title":
            return "%(upload_date)s - %(title).180B [%(id)s].%(ext)s"
        if rule == "custom":
            template = self.output_options.custom_template.strip()
            if template:
                if "%(ext)" not in template:
                    template += ".%(ext)s"
                return template
        return "%(title).200B [%(id)s].%(ext)s"

    def _audio_suffix(self) -> str:
        return f".{self.audio_format}"

    def _video_suffix(self) -> str:
        return f".{self.video_format}"

    def _validate_audio_format(self, value: str) -> AudioFormat:
        normalized = str(value).lower()
        if normalized not in AUDIO_FORMATS:
            raise ValueError(f"Unsupported audio format: {value}")
        return normalized  # type: ignore[return-value]

    def _validate_video_format(self, value: str) -> VideoFormat:
        normalized = str(value).lower()
        if normalized not in VIDEO_FORMATS:
            raise ValueError(f"Unsupported video format: {value}")
        return normalized  # type: ignore[return-value]

    def _emit(self, message: str) -> None:
        self.progress_callback(message)

    def _ensure_ffmpeg_exe(self) -> str:
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
