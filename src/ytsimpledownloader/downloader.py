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
ProgressCallback = Callable[[str], None]


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


@dataclass(frozen=True)
class PlaylistInfo:
    title: str
    urls: list[str]


PLAYLIST_ID_PREFIXES = ("PL", "UU", "OL", "FL")


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
    ) -> None:
        self.output_dir = Path(output_dir)
        self.progress_callback = progress_callback or (lambda _message: None)
        self.cancel_event = cancel_event
        self.test_seconds = test_seconds
        self.file_exists_action = file_exists_action
        self.mp3_quality = mp3_quality
        self.mp4_quality = mp4_quality
        self.ffmpeg_path = self._ensure_ffmpeg_exe()

    def fetch_video_info(self, url: str) -> VideoInfo:
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
            mp3_path=self.expected_output_path(info, ".mp3"),
            mp4_path=self.expected_output_path(info, ".mp4"),
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

    def download(self, url: str, mode: DownloadMode) -> list[DownloadResult]:
        clean_url = url.strip()
        if not clean_url:
            raise ValueError("URL is required.")

        self.output_dir.mkdir(parents=True, exist_ok=True)

        if mode == "mp3":
            return [self.download_mp3(clean_url)]
        if mode == "mp4":
            return [self.download_mp4(clean_url)]
        if mode == "both":
            return [self.download_mp3(clean_url), self.download_mp4(clean_url)]

        raise ValueError(f"Unsupported download mode: {mode}")

    def download_mp3(self, url: str) -> DownloadResult:
        self._emit("Starting MP3 download...")
        info = self._extract_metadata(url)
        target_path, skipped = self._prepare_target(info, ".mp3")
        if skipped:
            self._emit(f"MP3 skipped, file already exists: {target_path}")
            return DownloadResult("mp3", target_path, skipped=True)

        info = self._run_yt_dlp(
            url,
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": self.mp3_quality,
                    }
                ],
            },
            target_path,
        )
        path = self._expected_path(info, ".mp3")
        self._emit(f"MP3 saved: {path}")
        return DownloadResult("mp3", path)

    def download_mp4(self, url: str) -> DownloadResult:
        self._emit("Starting MP4 download...")
        info = self._extract_metadata(url)
        target_path, skipped = self._prepare_target(info, ".mp4")
        if skipped:
            self._emit(f"MP4 skipped, file already exists: {target_path}")
            return DownloadResult("mp4", target_path, skipped=True)

        info = self._run_yt_dlp(
            url,
            {
                "format": self._mp4_format_selector(),
                "merge_output_format": "mp4",
            },
            target_path,
        )
        path = self._expected_path(info, ".mp4")
        self._emit(f"MP4 saved: {path}")
        return DownloadResult("mp4", path)

    def expected_output_path(self, info: dict, suffix: str) -> Path:
        outtmpl = str(self.output_dir / "%(title).200B [%(id)s].%(ext)s")
        with YoutubeDL({"outtmpl": outtmpl}) as ydl:
            return Path(ydl.prepare_filename(info)).with_suffix(suffix)

    def _extract_metadata(self, url: str) -> dict:
        with YoutubeDL(self._base_opts()) as ydl:
            return ydl.extract_info(url, download=False)

    def _prepare_target(self, info: dict, suffix: str) -> tuple[Path, bool]:
        target_path = self.expected_output_path(info, suffix)
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
        }
        node_path = which("node")
        if node_path:
            opts["js_runtimes"] = {"node": {"path": node_path}}
            opts["remote_components"] = ["ejs:github"]
        if self.test_seconds:
            opts["download_ranges"] = download_range_func(None, [(0, self.test_seconds)])
            opts["force_keyframes_at_cuts"] = True
        return opts

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

    def _expected_path(self, info: dict, suffix: str) -> Path:
        requested_downloads = info.get("requested_downloads") or []
        for item in requested_downloads:
            filepath = item.get("filepath") or item.get("_filename")
            if filepath and Path(filepath).suffix.lower() == suffix:
                return Path(filepath)

        original = Path(YoutubeDL({"outtmpl": str(self.output_dir / "%(title).200B [%(id)s].%(ext)s")}).prepare_filename(info))
        candidate = original.with_suffix(suffix)
        if candidate.exists():
            return candidate

        matches = sorted(self.output_dir.glob(f"*{suffix}"), key=lambda item: item.stat().st_mtime, reverse=True)
        if matches:
            return matches[0]

        return candidate

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
