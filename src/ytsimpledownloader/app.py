from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from threading import Event

from PySide6.QtCore import QSettings, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .downloader import (
    AUDIO_FORMATS,
    VIDEO_FORMATS,
    DownloadCancelled,
    OutputOptions,
    SingleVideoDownloader,
    VideoInfo,
    extract_video_id,
    is_playlist_url,
)
from .paths import DEFAULT_DOWNLOAD_DIR, PROJECT_DIR, ensure_default_dirs
from .media_probe import probe_media
from .transcoder import (
    TranscodeCancelled,
    VideoTranscodeOptions,
    VideoTranscoder,
    encoder_available,
    friendly_transcode_error,
)


HISTORY_PATH = PROJECT_DIR / "history.json"
APP_ICON_PATH = Path(__file__).resolve().parent / "assets" / "app_icon.ico"
SUPPORTED_LOCAL_VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".avi"}


@dataclass
class QueueTask:
    url: str
    title: str = ""
    status: str = "waiting"
    error: str = ""
    attempts: int = 0
    max_retries: int = 0
    last_error: str = ""
    friendly_error: str = ""
    queue_index: int = -1
    playlist_title: str = ""
    playlist_index: int | None = None


TEXT = {
    "zh": {
        "app_title": "YouTube 簡易下載器",
        "url": "網址",
        "output_folder": "輸出資料夾",
        "output_folder_error": "無法建立輸出資料夾",
        "browse": "瀏覽",
        "mode": "下載模式",
        "language": "語言",
        "audio_format": "音訊格式",
        "video_format": "影片格式",
        "mp3_quality": "MP3 品質",
        "embed_audio_thumbnail": "嵌入縮圖作為 MP3 封面",
        "embed_audio_thumbnail_tooltip": "只支援 MP3。會將 YouTube 縮圖嵌入 MP3 作為封面圖。",
        "mp4_quality": "MP4 畫質",
        "video_processing": "影片處理模式",
        "video_processing_keep": "保留下載格式",
        "video_processing_prefer": "優先下載相容格式",
        "video_processing_transcode": "下載後轉檔",
        "video_processing_osu": "osu! 相容影片",
        "video_codec": "視訊編碼",
        "video_codec_copy": "保留原格式",
        "video_codec_h264": "H.264",
        "resolution": "解析度",
        "resolution_original": "保持原始解析度",
        "resolution_custom": "自訂解析度",
        "fps": "幀率",
        "fps_original": "保持原始幀率",
        "quality": "畫質",
        "quality_high": "高畫質",
        "quality_balanced": "平衡",
        "quality_small": "小檔案",
        "quality_custom": "自訂 CRF",
        "crf": "CRF",
        "transcode_speed": "轉檔速度",
        "speed_veryfast": "極快",
        "speed_fast": "快速",
        "speed_medium": "平衡",
        "speed_slow": "高壓縮",
        "video_audio": "影片音訊",
        "video_audio_keep": "保留音訊",
        "video_audio_remove": "移除音訊",
        "keep_original": "保留原始下載檔案",
        "add_local_video": "加入本機影片轉檔",
        "video_output_hint": "MP4 是容器；最大相容性請用 H.264 MP4 / yuv420p。CRF 越低畫質越高、檔案越大。",
        "osu_preset_hint": "osu!: MP4 / H.264 / yuv420p / max 720p / CRF 20 / no audio / faststart",
        "folder_rule": "分類方式",
        "filename_rule": "檔名格式",
        "custom_template": "自訂檔名",
        "folder_none": "不分類",
        "folder_mode": "依下載模式",
        "folder_channel": "依頻道",
        "folder_date": "依日期",
        "folder_playlist": "依播放清單",
        "filename_title": "標題",
        "filename_channel_title": "頻道 - 標題",
        "filename_playlist_index_title": "播放清單序號 - 標題",
        "filename_upload_date_title": "上傳日期 - 標題",
        "filename_custom": "自訂",
        "notify": "下載完成時提示",
        "start": "開始",
        "cancel": "取消",
        "open_output": "開啟輸出資料夾",
        "clear_url": "清空網址",
        "clear_status": "清空狀態",
        "preview": "影片預覽",
        "results": "下載結果",
        "status": "狀態 / 錯誤訊息",
        "queue": "下載佇列",
        "add_queue": "加入佇列",
        "move_up": "上移",
        "move_down": "下移",
        "remove_queue": "移除",
        "clear_queue": "清空佇列",
        "retry_failed": "重試失敗項目",
        "auto_retry": "自動重試",
        "retry_none": "不重試",
        "retry_once": "重試 1 次",
        "retry_twice": "重試 2 次",
        "retry_thrice": "重試 3 次",
        "retry_failed_empty": "目前沒有失敗項目可以重試。",
        "retry_failed_started": "準備重試失敗項目：{count} 個。",
        "retry_attempt": "重試 {attempt}/{max}: {url}",
        "resume_downloads": "保留未完成檔案並嘗試續傳",
        "resume_enabled_status": "續傳已啟用：會保留 .part 暫存檔並盡量續傳；MP3 若已進入 FFmpeg 轉檔階段，可能需要重新處理。",
        "resume_disabled_status": "續傳已停用：如果同一檔案有未完成下載，下次會重新下載。",
        "queue_empty": "佇列是空的。",
        "queue_added": "已加入佇列：{count} 個項目。",
        "queue_no_pending": "目前模式沒有需要下載的新項目。",
        "queue_building": "正在建立下載佇列...",
        "queue_item_failed": "加入佇列失敗",
        "queue_status_waiting": "等待",
        "queue_status_downloading": "下載中",
        "queue_status_completed": "完成",
        "queue_status_failed": "失敗",
        "queue_status_skipped": "略過",
        "queue_status_canceled": "已取消",
        "history": "下載歷史",
        "open_file": "開啟檔案",
        "copy_path": "複製路徑",
        "show_folder": "在資料夾中顯示",
        "clear_history": "清空歷史",
        "no_preview": "尚無預覽",
        "no_thumbnail": "無縮圖",
        "title": "標題",
        "channel": "頻道",
        "duration": "長度",
        "unknown": "未知",
        "fetching_info": "正在讀取影片資訊...",
        "info_loaded": "影片資訊已載入。",
        "preview_error": "預覽錯誤",
        "missing_url_title": "缺少網址",
        "missing_url": "請輸入一個或多個 YouTube 影片網址，每行一個。",
        "cannot_read_title": "無法讀取影片",
        "output_folder_line": "輸出資料夾",
        "done": "完成。",
        "download_completed": "下載完成",
        "download_completed_msg": "下載已完成。",
        "output_file": "輸出檔案",
        "batch_preview": "批量模式：偵測到 {count} 個網址。預覽只會在單一網址時顯示。",
        "batch_item": "批量下載 {current}/{total}",
        "batch_done": "批量下載完成：成功 {success}，失敗 {failed}。",
        "batch_auto_number": "批量模式會自動加編號，避免覆蓋既有檔案。",
        "batch_item_failed": "下載失敗",
        "playlist_preview": "播放清單模式：將在開始下載後讀取並展開影片清單。",
        "fetching_playlist": "正在讀取播放清單：{url}",
        "playlist_loaded": "播放清單「{title}」已載入，共 {count} 部影片。",
        "playlist_empty": "播放清單沒有可下載的公開影片。",
        "skip_downloaded": "略過已下載過的影片",
        "skip_downloaded_status": "已略過下載紀錄中存在的影片：{url}",
        "playlist_skip_summary": "播放清單檢查完成：略過 {skipped} 個已下載項目。",
        "error": "錯誤",
        "cancelling": "正在取消...",
        "cancelled": "下載已取消。",
        "copied_path": "已複製路徑",
        "file_missing_title": "找不到檔案",
        "file_missing": "檔案不存在",
        "exists_title": "檔案已存在",
        "exists_intro": "以下輸出檔案已存在：",
        "exists_choose": "請選擇要怎麼處理。",
        "overwrite": "覆蓋",
        "skip": "跳過",
        "auto_number": "自動加編號",
        "skipped": "已跳過",
        "progress_waiting": "等待下載",
        "history_cleared": "歷史紀錄已清空。",
        "error_unavailable": "影片無法使用，可能是私人影片、已刪除或所在地區無法觀看。",
        "error_login": "這部影片似乎需要登入。第一版尚不支援登入或 Cookie。",
        "error_network": "網路連線失敗或逾時，請檢查網路後再試一次。",
        "error_limited": "YouTube 暫時限制請求，請稍候再試。",
        "error_unsupported": "不支援此網址。請貼上公開 YouTube 影片網址。",
        "error_ffmpeg": "FFmpeg 轉檔或合併失敗，請稍後重試或改用其他格式。",
        "error_webm": "無法輸出 WEBM：目前來源格式或 FFmpeg 合併流程不支援此影片。請改用 MP4 或 MKV。",
        "error_permission": "檔案權限不足，請確認輸出資料夾可以寫入，或改選其他資料夾。",
        "error_path": "檔名或路徑可能太長或無效，請改短輸出路徑後再試。",
        "local_video_error": "請選擇支援的影片檔：mp4, mkv, webm, mov, avi。",
    },
    "en": {
        "app_title": "YouTube Simple Downloader",
        "url": "URL(s)",
        "output_folder": "Output Folder",
        "output_folder_error": "Cannot create output folder",
        "browse": "Browse",
        "mode": "Mode",
        "language": "Language",
        "audio_format": "Audio Format",
        "video_format": "Video Format",
        "mp3_quality": "MP3 Quality",
        "embed_audio_thumbnail": "Embed thumbnail as MP3 cover art",
        "embed_audio_thumbnail_tooltip": "MP3 only. Embeds the YouTube thumbnail in the MP3 as cover art.",
        "mp4_quality": "MP4 Quality",
        "video_processing": "Video Processing",
        "video_processing_keep": "Keep downloaded format",
        "video_processing_prefer": "Prefer compatible format",
        "video_processing_transcode": "Transcode after download",
        "video_processing_osu": "osu! compatible video",
        "video_codec": "Video Codec",
        "video_codec_copy": "Keep original",
        "video_codec_h264": "H.264",
        "resolution": "Resolution",
        "resolution_original": "Original resolution",
        "resolution_custom": "Custom resolution",
        "fps": "FPS",
        "fps_original": "Original FPS",
        "quality": "Quality",
        "quality_high": "High quality",
        "quality_balanced": "Balanced",
        "quality_small": "Small file",
        "quality_custom": "Custom CRF",
        "crf": "CRF",
        "transcode_speed": "Transcode Speed",
        "speed_veryfast": "Very Fast",
        "speed_fast": "Fast",
        "speed_medium": "Balanced",
        "speed_slow": "Smaller File",
        "video_audio": "Video Audio",
        "video_audio_keep": "Keep audio",
        "video_audio_remove": "Remove audio",
        "keep_original": "Keep original downloaded file",
        "add_local_video": "Add Local Video",
        "video_output_hint": "MP4 is a container. For maximum compatibility, use H.264 MP4 / yuv420p. Lower CRF means higher quality and larger files.",
        "osu_preset_hint": "osu!: MP4 / H.264 / yuv420p / max 720p / CRF 20 / no audio / faststart",
        "folder_rule": "Folder Rule",
        "filename_rule": "Filename Format",
        "custom_template": "Custom Filename",
        "folder_none": "No grouping",
        "folder_mode": "By download mode",
        "folder_channel": "By channel",
        "folder_date": "By date",
        "folder_playlist": "By playlist",
        "filename_title": "Title",
        "filename_channel_title": "Channel - Title",
        "filename_playlist_index_title": "Playlist number - Title",
        "filename_upload_date_title": "Upload date - Title",
        "filename_custom": "Custom",
        "notify": "Notify when complete",
        "start": "Start",
        "cancel": "Cancel",
        "open_output": "Open Output Folder",
        "clear_url": "Clear URL",
        "clear_status": "Clear Status",
        "preview": "Video Preview",
        "results": "Download Results",
        "status": "Status / Errors",
        "queue": "Download Queue",
        "add_queue": "Add to Queue",
        "move_up": "Move Up",
        "move_down": "Move Down",
        "remove_queue": "Remove",
        "clear_queue": "Clear Queue",
        "retry_failed": "Retry Failed",
        "auto_retry": "Auto Retry",
        "retry_none": "Do not retry",
        "retry_once": "Retry 1 time",
        "retry_twice": "Retry 2 times",
        "retry_thrice": "Retry 3 times",
        "retry_failed_empty": "There are no failed items to retry.",
        "retry_failed_started": "Retrying {count} failed item(s).",
        "retry_attempt": "Retry {attempt}/{max}: {url}",
        "resume_downloads": "Keep unfinished files and try to resume",
        "resume_enabled_status": "Resume is enabled: .part files are kept and yt-dlp will resume when possible. MP3 post-processing may need to run again after interruption.",
        "resume_disabled_status": "Resume is disabled: unfinished downloads for the same output path will restart.",
        "queue_empty": "The queue is empty.",
        "queue_added": "Added {count} item(s) to the queue.",
        "queue_no_pending": "There are no new items to download for the current mode.",
        "queue_building": "Building download queue...",
        "queue_item_failed": "Failed to add to queue",
        "queue_status_waiting": "Waiting",
        "queue_status_downloading": "Downloading",
        "queue_status_completed": "Completed",
        "queue_status_failed": "Failed",
        "queue_status_skipped": "Skipped",
        "queue_status_canceled": "Canceled",
        "history": "Download History",
        "open_file": "Open File",
        "copy_path": "Copy Path",
        "show_folder": "Show in Folder",
        "clear_history": "Clear History",
        "no_preview": "No preview",
        "no_thumbnail": "No thumbnail",
        "title": "Title",
        "channel": "Channel",
        "duration": "Duration",
        "unknown": "Unknown",
        "fetching_info": "Fetching video info...",
        "info_loaded": "Video info loaded.",
        "preview_error": "Preview error",
        "missing_url_title": "Missing URL",
        "missing_url": "Please enter one or more YouTube video URLs, one per line.",
        "cannot_read_title": "Cannot read video",
        "output_folder_line": "Output folder",
        "done": "Done.",
        "download_completed": "Download completed",
        "download_completed_msg": "Download completed.",
        "output_file": "Output file",
        "batch_preview": "Batch mode: detected {count} URLs. Preview is shown only for a single URL.",
        "batch_item": "Batch download {current}/{total}",
        "batch_done": "Batch completed: {success} succeeded, {failed} failed.",
        "batch_auto_number": "Batch mode uses auto numbering to avoid overwriting existing files.",
        "batch_item_failed": "Download failed",
        "playlist_preview": "Playlist mode: videos will be loaded after starting the download.",
        "fetching_playlist": "Reading playlist: {url}",
        "playlist_loaded": "Playlist \"{title}\" loaded with {count} videos.",
        "playlist_empty": "Playlist does not contain downloadable public videos.",
        "skip_downloaded": "Skip previously downloaded videos",
        "skip_downloaded_status": "Skipped previously downloaded video: {url}",
        "playlist_skip_summary": "Playlist check completed: skipped {skipped} previously downloaded item(s).",
        "error": "Error",
        "cancelling": "Cancelling...",
        "cancelled": "Download cancelled.",
        "copied_path": "Copied path",
        "file_missing_title": "File Missing",
        "file_missing": "File does not exist",
        "exists_title": "File Already Exists",
        "exists_intro": "The following output file already exists:",
        "exists_choose": "Choose what to do.",
        "overwrite": "Overwrite",
        "skip": "Skip",
        "auto_number": "Auto Number",
        "skipped": "skipped",
        "progress_waiting": "Waiting",
        "history_cleared": "History cleared.",
        "error_unavailable": "Video is unavailable, private, deleted, or blocked in this region.",
        "error_login": "This video appears to require sign-in. Version 1 does not support login or cookies yet.",
        "error_network": "Network connection failed or timed out. Please check the connection and try again.",
        "error_limited": "YouTube is temporarily limiting requests. Please wait a bit and try again.",
        "error_unsupported": "Unsupported URL. Please paste public YouTube video URLs.",
        "error_ffmpeg": "FFmpeg conversion or merge failed. Please retry later or try another format.",
        "error_webm": "Cannot output WEBM: this source format or FFmpeg merge flow is not supported for this video. Please use MP4 or MKV.",
        "error_permission": "File permission was denied. Please check the output folder or choose another folder.",
        "error_path": "The filename or path may be too long or invalid. Please try a shorter output folder.",
        "local_video_error": "Please choose supported video files: mp4, mkv, webm, mov, avi.",
    },
}


class PreviewWorker(QThread):
    finished_ok = Signal(object, bytes)
    failed = Signal(str)

    def __init__(
        self,
        url: str,
        output_dir: Path,
        output_options: OutputOptions,
        audio_format: str,
        video_format: str,
        video_processing_options: VideoTranscodeOptions,
    ) -> None:
        super().__init__()
        self.url = url
        self.output_dir = output_dir
        self.output_options = output_options
        self.audio_format = audio_format
        self.video_format = video_format
        self.video_processing_options = video_processing_options

    def run(self) -> None:
        try:
            downloader = SingleVideoDownloader(
                self.output_dir,
                output_options=self.output_options,
                audio_format=self.audio_format,
                video_format=self.video_format,
                video_processing_options=self.video_processing_options,
            )
            info = downloader.fetch_video_info(self.url)
            thumbnail = b""
            if info.thumbnail_url:
                with urllib.request.urlopen(info.thumbnail_url, timeout=15) as response:
                    thumbnail = response.read()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(info, thumbnail)


class QueueBuildWorker(QThread):
    status = Signal(str)
    finished_ok = Signal(object, object)

    def __init__(self, urls: list[str], output_dir: Path) -> None:
        super().__init__()
        self.urls = urls
        self.output_dir = output_dir

    def run(self) -> None:
        downloader = SingleVideoDownloader(self.output_dir, progress_callback=self.status.emit)
        tasks = []
        errors = []
        for url in self.urls:
            if is_playlist_url(url):
                self.status.emit(f"Reading playlist: {url}")
                try:
                    playlist = downloader.fetch_playlist_info(url)
                except Exception as exc:
                    errors.append(f"{url}: {exc}")
                    continue
                tasks.extend(
                    QueueTask(
                        url=item_url,
                        title=item_url,
                        playlist_title=playlist.title,
                        playlist_index=index,
                    )
                    for index, item_url in enumerate(playlist.urls, start=1)
                )
                self.status.emit(f"Playlist loaded: {playlist.title} ({len(playlist.urls)} videos)")
            else:
                tasks.append(QueueTask(url=url, title=url))
        self.finished_ok.emit(tasks, errors)


def copy_queue_task(task: QueueTask) -> QueueTask:
    return QueueTask(
        url=task.url,
        title=task.title,
        status=task.status,
        error=task.error,
        attempts=task.attempts,
        max_retries=task.max_retries,
        last_error=task.last_error,
        friendly_error=task.friendly_error,
        queue_index=task.queue_index,
        playlist_title=task.playlist_title,
        playlist_index=task.playlist_index,
    )


class DownloadWorker(QThread):
    status = Signal(str)
    task_updated = Signal(int, str, str, str, int, str)
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        tasks: list[QueueTask],
        output_dir: Path,
        mode: str,
        file_exists_action: str,
        mp3_quality: str,
        mp4_quality: str,
        audio_format: str,
        embed_audio_thumbnail: bool,
        video_format: str,
        video_processing_options: VideoTranscodeOptions,
        output_options: OutputOptions,
        resume_downloads: bool,
        batch_item_template: str,
        batch_failed_label: str,
        fetching_playlist_template: str,
        playlist_loaded_template: str,
        skip_downloaded: bool,
        downloaded_by_video_id: dict[str, dict[str, str]],
        skip_downloaded_template: str,
        playlist_skip_summary_template: str,
        retry_attempt_template: str,
    ) -> None:
        super().__init__()
        self.tasks = [copy_queue_task(task) for task in tasks]
        self.output_dir = output_dir
        self.mode = mode
        self.file_exists_action = file_exists_action
        self.mp3_quality = mp3_quality
        self.mp4_quality = mp4_quality
        self.audio_format = audio_format
        self.embed_audio_thumbnail = embed_audio_thumbnail
        self.video_format = video_format
        self.video_processing_options = video_processing_options
        self.output_options = output_options
        self.resume_downloads = resume_downloads
        self.batch_item_template = batch_item_template
        self.batch_failed_label = batch_failed_label
        self.fetching_playlist_template = fetching_playlist_template
        self.playlist_loaded_template = playlist_loaded_template
        self.skip_downloaded = skip_downloaded
        self.downloaded_by_video_id = {video_id: paths.copy() for video_id, paths in downloaded_by_video_id.items()}
        self.skip_downloaded_template = skip_downloaded_template
        self.playlist_skip_summary_template = playlist_skip_summary_template
        self.retry_attempt_template = retry_attempt_template
        self.cancel_event = Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            downloader = SingleVideoDownloader(
                self.output_dir,
                progress_callback=self.status.emit,
                cancel_event=self.cancel_event,
                file_exists_action=self.file_exists_action,
                mp3_quality=self.mp3_quality,
                mp4_quality=self.mp4_quality,
                audio_format=self.audio_format,
                embed_audio_thumbnail=self.embed_audio_thumbnail,
                video_format=self.video_format,
                video_processing_options=self.video_processing_options,
                output_options=self.output_options,
                resume_downloads=self.resume_downloads,
            )
            entries = []
            task_items = []
            for source_index, task in enumerate(self.tasks, start=1):
                if self.cancel_event.is_set():
                    raise DownloadCancelled("Download cancelled by user.")
                if task.status != "waiting":
                    continue

                url = task.url
                if is_playlist_url(url):
                    self.status.emit(self.fetching_playlist_template.format(url=url))
                    task.attempts += 1
                    queue_index = task.queue_index if task.queue_index >= 0 else source_index - 1
                    self.task_updated.emit(queue_index, "downloading", task.title or url, "", task.attempts, "")
                    try:
                        playlist = downloader.fetch_playlist_info(url)
                    except Exception as exc:
                        error_message = str(exc)
                        error_category = error_key(error_message)
                        self.task_updated.emit(
                            queue_index,
                            "failed",
                            task.title or url,
                            error_message,
                            task.attempts,
                            error_category,
                        )
                        entries.append(
                            {
                                "index": source_index,
                                "url": url,
                                "title": url,
                                "error": error_message,
                                "results": [],
                            }
                        )
                        self.status.emit(f"{self.batch_failed_label}: {url} - {exc}")
                    else:
                        task_items.extend(
                            QueueTask(
                                url=item_url,
                                title=item_url,
                                playlist_title=playlist.title,
                                playlist_index=playlist_index,
                            )
                            for playlist_index, item_url in enumerate(playlist.urls, start=1)
                        )
                        self.status.emit(
                            self.playlist_loaded_template.format(title=playlist.title, count=len(playlist.urls))
                        )
                else:
                    task_items.append(task)

            total = len(task_items)
            history_skipped_count = 0
            for index, task in enumerate(task_items, start=1):
                if self.cancel_event.is_set():
                    raise DownloadCancelled("Download cancelled by user.")

                url = task.url
                queue_index = task.queue_index if task.queue_index >= 0 else index - 1
                if total > 1:
                    self.status.emit(self.batch_item_template.format(current=index, total=total) + f": {url}")

                while True:
                    try:
                        task.attempts += 1
                        self.task_updated.emit(queue_index, "downloading", task.title or url, "", task.attempts, "")
                        video_id = extract_video_id(url)
                        requested_modes = modes_for_download(self.mode)
                        existing = self.downloaded_by_video_id.get(video_id, {}) if self.skip_downloaded and video_id else {}
                        existing_results = []
                        for requested_mode in requested_modes:
                            existing_path = existing.get(download_key_for_mode(
                                requested_mode,
                                self.audio_format,
                                self.video_format,
                            ))
                            if existing_path and Path(existing_path).exists():
                                existing_results.append((requested_mode, existing_path, True))

                        missing_modes = [
                            mode for mode in requested_modes if mode not in {item[0] for item in existing_results}
                        ]
                        if self.skip_downloaded and video_id and not missing_modes:
                            history_skipped_count += 1
                            self.status.emit(self.skip_downloaded_template.format(url=url))
                            self.task_updated.emit(
                                queue_index,
                                "skipped",
                                existing.get("_title") or task.title or url,
                                "",
                                task.attempts,
                                "",
                            )
                            entries.append(
                                {
                                    "index": index,
                                    "url": url,
                                    "title": existing.get("_title") or url,
                                    "info": None,
                                    "error": "",
                                    "results": existing_results,
                                    "skipped_by_history": True,
                                }
                            )
                            break

                        info = downloader.fetch_video_info(url, task.playlist_title, task.playlist_index)
                        self.task_updated.emit(queue_index, "downloading", info.title, "", task.attempts, "")
                        result_items = list(existing_results)
                        download_mode = download_mode_for_missing_modes(missing_modes)
                        if download_mode:
                            results = downloader.download(
                                url,
                                download_mode,
                                task.playlist_title,
                                task.playlist_index,
                            )
                            for result in results:
                                result_items.append((result.mode, str(result.path), result.skipped))
                                if video_id and not result.skipped and result.path.exists():
                                    output_key = download_key_for_mode(
                                        result.mode,
                                        self.audio_format,
                                        self.video_format,
                                    )
                                    self.downloaded_by_video_id.setdefault(video_id, {})[output_key] = str(result.path)
                                    self.downloaded_by_video_id[video_id]["_title"] = info.title
                    except DownloadCancelled:
                        raise
                    except Exception as exc:
                        error_message = str(exc)
                        error_category = error_key(error_message)
                        task.last_error = error_message
                        task.error = error_message
                        task.friendly_error = error_category
                        if task.attempts <= task.max_retries:
                            self.status.emit(
                                self.retry_attempt_template.format(
                                    attempt=task.attempts,
                                    max=task.max_retries,
                                    url=url,
                                )
                            )
                            self.task_updated.emit(
                                queue_index,
                                "downloading",
                                task.title or url,
                                error_message,
                                task.attempts,
                                error_category,
                            )
                            continue

                        self.task_updated.emit(
                            queue_index,
                            "failed",
                            task.title or url,
                            error_message,
                            task.attempts,
                            error_category,
                        )
                        entries.append(
                            {
                                "index": index,
                                "url": url,
                                "title": task.title or url,
                                "error": error_message,
                                "results": [],
                            }
                        )
                        self.status.emit(f"{self.batch_failed_label}: {url} - {exc}")
                        break
                    else:
                        entries.append(
                            {
                                "index": index,
                                "url": url,
                                "title": info.title,
                                "info": info,
                                "error": "",
                                "results": result_items,
                            }
                        )
                        self.task_updated.emit(queue_index, "completed", info.title, "", task.attempts, "")
                        break
            if history_skipped_count:
                self.status.emit(self.playlist_skip_summary_template.format(skipped=history_skipped_count))
        except DownloadCancelled as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(entries)


class LocalTranscodeWorker(QThread):
    status = Signal(str)
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        paths: list[str],
        output_dir: Path,
        options: VideoTranscodeOptions,
        file_exists_action: str,
    ) -> None:
        super().__init__()
        self.paths = [str(Path(path)) for path in paths]
        self.output_dir = output_dir
        self.options = options
        self.file_exists_action = file_exists_action
        self.cancel_event = Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        entries = []
        try:
            transcoder = VideoTranscoder(progress_callback=self.status.emit, cancel_event=self.cancel_event)
            total = len(self.paths)
            for index, raw_path in enumerate(self.paths, start=1):
                if self.cancel_event.is_set():
                    raise TranscodeCancelled("Transcode cancelled by user.")
                source = Path(raw_path)
                self.status.emit(f"Local transcode {index}/{total}: {source}")
                try:
                    source_info = probe_media(source, transcoder.ffmpeg_path)
                    self.status.emit(f"Source media: {source_info.summary()}")
                    result = transcoder.transcode(
                        source,
                        self.options,
                        output_dir=self.output_dir if str(self.output_dir) else None,
                        file_exists_action=self.file_exists_action,
                    )
                except TranscodeCancelled:
                    raise
                except Exception as exc:
                    entries.append(
                        {
                            "index": index,
                            "url": "",
                            "title": source.name,
                            "source_path": str(source),
                            "error": str(exc),
                            "results": [],
                        }
                    )
                    self.status.emit(f"Local transcode failed: {source} - {exc}")
                else:
                    entries.append(
                        {
                            "index": index,
                            "url": "",
                            "title": source.stem,
                            "source_path": str(source),
                            "source_media_info": source_info,
                            "media_info": result.media_info,
                            "error": "",
                            "results": [("mp4", str(result.path), result.skipped)],
                            "transcode": True,
                        }
                    )
        except TranscodeCancelled as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(entries)


def error_key(message: str) -> str:
    lower = message.lower()
    if (
        "video unavailable" in lower
        or "private video" in lower
        or "not available" in lower
        or "this video is unavailable" in lower
        or "blocked in your country" in lower
        or "region" in lower
        or "geo" in lower
        or "removed" in lower
        or "deleted" in lower
    ):
        return "error_unavailable"
    if "sign in" in lower or "login" in lower or "cookies" in lower or "confirm your age" in lower:
        return "error_login"
    if (
        "timed out" in lower
        or "connection" in lower
        or "network" in lower
        or "temporary failure" in lower
        or "name resolution" in lower
        or "remote end closed connection" in lower
        or "connection reset" in lower
    ):
        return "error_network"
    if (
        "http error 429" in lower
        or "too many requests" in lower
        or "temporarily unavailable" in lower
        or "try again later" in lower
        or "confirm you are not a bot" in lower
    ):
        return "error_limited"
    if "unsupported url" in lower:
        return "error_unsupported"
    if "webm" in lower and (
        "requested format is not available" in lower
        or "merge" in lower
        or "ffmpeg" in lower
        or "not available" in lower
    ):
        return "error_webm"
    if "ffmpeg" in lower or "postprocessing" in lower or "conversion failed" in lower or "merge" in lower:
        return "error_ffmpeg"
    if (
        "permission denied" in lower
        or "access is denied" in lower
        or "winerror 5" in lower
        or "operation not permitted" in lower
    ):
        return "error_permission"
    if (
        "file name too long" in lower
        or "filename too long" in lower
        or "path too long" in lower
        or "winerror 3" in lower
        or "winerror 123" in lower
        or "invalid argument" in lower
        or "invalid path" in lower
    ):
        return "error_path"
    return ""


def friendly_error(message: str, language: str, category: str = "") -> str:
    key = category or error_key(message)
    if key:
        return TEXT[language][key]
    return message


def format_duration(seconds: int | None, unknown: str) -> str:
    if seconds is None:
        return unknown
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def modes_for_download(mode: str) -> list[str]:
    if mode == "both":
        return ["mp3", "mp4"]
    return [mode]


def download_mode_for_missing_modes(missing_modes: list[str]) -> str:
    if missing_modes == ["mp3", "mp4"]:
        return "both"
    if missing_modes == ["mp3"]:
        return "mp3"
    if missing_modes == ["mp4"]:
        return "mp4"
    return ""


def download_key_for_mode(mode: str, audio_format: str, video_format: str) -> str:
    if mode == "mp3":
        return f"audio:{audio_format}"
    if mode == "mp4":
        return f"video:{video_format}"
    return mode


def display_label_for_result(mode: str, path: str) -> str:
    suffix = Path(str(path)).suffix.lower().lstrip(".")
    if suffix:
        return suffix.upper()
    if mode == "mp3":
        return "AUDIO"
    if mode == "mp4":
        return "VIDEO"
    return mode.upper()


def modes_for_paths(paths: list[str]) -> list[str]:
    modes = []
    for raw_path in paths:
        suffix = Path(str(raw_path)).suffix.lower().lstrip(".")
        if suffix in AUDIO_FORMATS and "mp3" not in modes:
            modes.append("mp3")
        elif suffix in VIDEO_FORMATS and "mp4" not in modes:
            modes.append("mp4")
    return modes


def load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def save_history(items: list[dict]) -> None:
    HISTORY_PATH.write_text(json.dumps(items[:100], ensure_ascii=False, indent=2), encoding="utf-8")


def history_downloads_by_video_id() -> dict[str, dict[str, str]]:
    downloads: dict[str, dict[str, str]] = {}
    for item in load_history():
        video_id = str(item.get("video_id") or extract_video_id(str(item.get("url") or "")))
        if not video_id:
            continue

        bucket = downloads.setdefault(video_id, {})
        title = str(item.get("title") or "")
        if title and "_title" not in bucket:
            bucket["_title"] = title

        item_audio_format = str(item.get("audio_format") or "").lower()
        item_video_format = str(item.get("video_format") or "").lower()

        for raw_path in item.get("paths") or []:
            path = Path(str(raw_path))
            if not path.exists():
                continue
            suffix = path.suffix.lower().lstrip(".")
            if suffix in AUDIO_FORMATS:
                audio_format = item_audio_format if item_audio_format in AUDIO_FORMATS else suffix
                bucket[f"audio:{audio_format}"] = str(path)
            elif suffix in VIDEO_FORMATS:
                video_format = item_video_format if item_video_format in VIDEO_FORMATS else suffix
                bucket[f"video:{video_format}"] = str(path)
    return downloads


def queue_task_key(url: str) -> str:
    video_id = extract_video_id(url)
    return f"video:{video_id}" if video_id else f"url:{url.strip()}"


def task_has_downloaded_modes(
    task: QueueTask,
    mode: str,
    downloaded_by_video_id: dict[str, dict[str, str]],
    audio_format: str,
    video_format: str,
) -> bool:
    video_id = extract_video_id(task.url)
    if not video_id:
        return False
    existing = downloaded_by_video_id.get(video_id, {})
    return all(
        bool(existing.get(download_key_for_mode(requested_mode, audio_format, video_format)))
        and Path(existing[download_key_for_mode(requested_mode, audio_format, video_format)]).exists()
        for requested_mode in modes_for_download(mode)
    )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        ensure_default_dirs()
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.settings = QSettings("YouTubeSimpleDownloader", "YouTubeSimpleDownloader")
        self.language = str(self.settings.value("language", "zh"))
        if self.language not in TEXT:
            self.language = "zh"

        self.worker: DownloadWorker | LocalTranscodeWorker | None = None
        self.preview_worker: PreviewWorker | None = None
        self.queue_worker: QueueBuildWorker | None = None
        self.download_queue: list[QueueTask] = []
        self.current_info: VideoInfo | None = None
        self.current_info_url = ""
        self.current_info_key = ""

        self.resize(self.settings.value("window_size", self.size()))

        self.url_label = QLabel()
        self.output_label = QLabel()
        self.mode_label = QLabel()
        self.language_label = QLabel()
        self.audio_format_label = QLabel()
        self.video_format_label = QLabel()
        self.mp3_quality_label = QLabel()
        self.mp4_quality_label = QLabel()
        self.video_processing_label = QLabel()
        self.video_codec_label = QLabel()
        self.resolution_label = QLabel()
        self.fps_label = QLabel()
        self.quality_label = QLabel()
        self.crf_label = QLabel()
        self.transcode_speed_label = QLabel()
        self.video_audio_label = QLabel()
        self.folder_rule_label = QLabel()
        self.filename_rule_label = QLabel()
        self.custom_template_label = QLabel()
        self.retry_label = QLabel()
        self.preview_header = QLabel()
        self.queue_header = QLabel()
        self.results_header = QLabel()
        self.history_header = QLabel()
        self.status_header = QLabel()

        self.url_input = QTextEdit()
        self.url_input.setAcceptRichText(False)
        self.url_input.setFixedHeight(78)
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=...\nhttps://www.youtube.com/watch?v=...")
        self.url_input.textChanged.connect(self.schedule_preview)

        self.output_input = QLineEdit(str(self.saved_output_dir()))
        self.output_input.textChanged.connect(self.schedule_preview)
        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self.choose_output_dir)

        self.language_combo = QComboBox()
        self.language_combo.addItem("繁體中文", "zh")
        self.language_combo.addItem("English", "en")
        language_index = self.language_combo.findData(self.language)
        if language_index >= 0:
            self.language_combo.setCurrentIndex(language_index)
        self.language_combo.currentIndexChanged.connect(self.change_language)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("MP3", "mp3")
        self.mode_combo.addItem("MP4", "mp4")
        self.mode_combo.addItem("MP3 + MP4", "both")
        saved_mode = self.settings.value("mode", "mp3")
        saved_index = self.mode_combo.findData(saved_mode)
        if saved_index >= 0:
            self.mode_combo.setCurrentIndex(saved_index)

        self.audio_format_combo = QComboBox()
        for value in AUDIO_FORMATS:
            self.audio_format_combo.addItem(value.upper(), value)
        saved_audio_format = str(self.settings.value("audio_format", "mp3")).lower()
        audio_format_index = self.audio_format_combo.findData(saved_audio_format)
        if audio_format_index >= 0:
            self.audio_format_combo.setCurrentIndex(audio_format_index)

        self.mp3_quality_combo = QComboBox()
        for value in ("128", "192", "256", "320"):
            self.mp3_quality_combo.addItem(f"{value}K", value)
        saved_mp3 = self.settings.value("mp3_quality", "192")
        mp3_index = self.mp3_quality_combo.findData(saved_mp3)
        if mp3_index >= 0:
            self.mp3_quality_combo.setCurrentIndex(mp3_index)

        self.embed_audio_thumbnail_checkbox = QCheckBox()
        self.embed_audio_thumbnail_checkbox.setChecked(
            str(self.settings.value("embed_audio_thumbnail", "false")).lower() == "true"
        )
        self.embed_audio_thumbnail_checkbox.stateChanged.connect(lambda _state: self.save_settings())

        self.video_format_combo = QComboBox()
        for value in VIDEO_FORMATS:
            self.video_format_combo.addItem(value.upper(), value)
        saved_video_format = str(self.settings.value("video_format", "mp4")).lower()
        video_format_index = self.video_format_combo.findData(saved_video_format)
        if video_format_index >= 0:
            self.video_format_combo.setCurrentIndex(video_format_index)

        self.mp4_quality_combo = QComboBox()
        for label, value in (("Best", "best"), ("1080p", "1080"), ("720p", "720"), ("480p", "480")):
            self.mp4_quality_combo.addItem(label, value)
        saved_mp4 = self.settings.value("mp4_quality", "best")
        mp4_index = self.mp4_quality_combo.findData(saved_mp4)
        if mp4_index >= 0:
            self.mp4_quality_combo.setCurrentIndex(mp4_index)
        self.mode_combo.currentIndexChanged.connect(self.handle_mode_changed)
        self.audio_format_combo.currentIndexChanged.connect(self.handle_format_changed)
        self.video_format_combo.currentIndexChanged.connect(self.handle_format_changed)

        self.video_processing_combo = QComboBox()
        for value in ("keep", "prefer_compatible", "transcode", "osu"):
            self.video_processing_combo.addItem("", value)
        saved_video_processing = str(self.settings.value("video_processing_mode", "keep"))
        video_processing_index = self.video_processing_combo.findData(saved_video_processing)
        if video_processing_index >= 0:
            self.video_processing_combo.setCurrentIndex(video_processing_index)

        self.video_codec_combo = QComboBox()
        self.video_codec_combo.addItem("", "copy")
        self.video_codec_combo.addItem("", "h264")
        saved_video_codec = str(self.settings.value("video_codec", "h264"))
        video_codec_index = self.video_codec_combo.findData(saved_video_codec)
        if video_codec_index >= 0:
            self.video_codec_combo.setCurrentIndex(video_codec_index)

        self.resolution_combo = QComboBox()
        for value in ("original", "2160", "1440", "1080", "720", "480"):
            self.resolution_combo.addItem("", value)
        saved_resolution = str(self.settings.value("video_resolution", "original"))
        resolution_index = self.resolution_combo.findData(saved_resolution)
        if resolution_index >= 0:
            self.resolution_combo.setCurrentIndex(resolution_index)

        self.fps_combo = QComboBox()
        for value in ("original", "60", "30", "24"):
            self.fps_combo.addItem("", value)
        saved_fps = str(self.settings.value("video_fps", "original"))
        fps_index = self.fps_combo.findData(saved_fps)
        if fps_index >= 0:
            self.fps_combo.setCurrentIndex(fps_index)

        self.quality_combo = QComboBox()
        for value in ("high", "balanced", "small", "custom"):
            self.quality_combo.addItem("", value)
        saved_quality = str(self.settings.value("video_quality", "balanced"))
        quality_index = self.quality_combo.findData(saved_quality)
        if quality_index >= 0:
            self.quality_combo.setCurrentIndex(quality_index)

        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(0, 51)
        self.crf_spin.setValue(int(str(self.settings.value("video_crf", "20"))))

        self.transcode_speed_combo = QComboBox()
        for value in ("veryfast", "fast", "medium", "slow"):
            self.transcode_speed_combo.addItem("", value)
        saved_speed = str(self.settings.value("video_transcode_speed", "medium"))
        speed_index = self.transcode_speed_combo.findData(saved_speed)
        if speed_index >= 0:
            self.transcode_speed_combo.setCurrentIndex(speed_index)

        self.video_audio_combo = QComboBox()
        for value in ("keep", "remove"):
            self.video_audio_combo.addItem("", value)
        saved_video_audio = str(self.settings.value("video_audio_mode", "keep"))
        video_audio_index = self.video_audio_combo.findData(saved_video_audio)
        if video_audio_index >= 0:
            self.video_audio_combo.setCurrentIndex(video_audio_index)

        self.keep_original_checkbox = QCheckBox()
        self.keep_original_checkbox.setChecked(str(self.settings.value("video_keep_original", "true")).lower() != "false")
        self.video_output_hint_label = QLabel()
        self.video_output_hint_label.setWordWrap(True)

        for widget in (
            self.video_processing_combo,
            self.video_codec_combo,
            self.resolution_combo,
            self.fps_combo,
            self.quality_combo,
            self.crf_spin,
            self.transcode_speed_combo,
            self.video_audio_combo,
        ):
            if isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self.handle_video_processing_changed)
            else:
                widget.currentIndexChanged.connect(self.handle_video_processing_changed)
        self.keep_original_checkbox.stateChanged.connect(lambda _state: self.save_settings())

        self.folder_rule_combo = QComboBox()
        for value in ("none", "mode", "channel", "date", "playlist"):
            self.folder_rule_combo.addItem("", value)
        saved_folder_rule = self.settings.value("folder_rule", "none")
        folder_rule_index = self.folder_rule_combo.findData(saved_folder_rule)
        if folder_rule_index >= 0:
            self.folder_rule_combo.setCurrentIndex(folder_rule_index)
        self.folder_rule_combo.currentIndexChanged.connect(self.handle_output_options_changed)

        self.filename_rule_combo = QComboBox()
        for value in ("title", "channel_title", "playlist_index_title", "upload_date_title", "custom"):
            self.filename_rule_combo.addItem("", value)
        saved_filename_rule = self.settings.value("filename_rule", "title")
        filename_rule_index = self.filename_rule_combo.findData(saved_filename_rule)
        if filename_rule_index >= 0:
            self.filename_rule_combo.setCurrentIndex(filename_rule_index)
        self.filename_rule_combo.currentIndexChanged.connect(self.handle_output_options_changed)

        self.custom_template_input = QLineEdit(str(self.settings.value("custom_template", "")))
        self.custom_template_input.setPlaceholderText("%(title).200B [%(id)s].%(ext)s")
        self.custom_template_input.textChanged.connect(self.handle_output_options_changed)

        self.notify_checkbox = QCheckBox()
        self.notify_checkbox.setChecked(str(self.settings.value("notify_complete", "true")).lower() != "false")
        self.skip_downloaded_checkbox = QCheckBox()
        self.skip_downloaded_checkbox.setChecked(str(self.settings.value("skip_downloaded", "true")).lower() != "false")
        self.skip_downloaded_checkbox.stateChanged.connect(lambda _state: self.save_settings())
        self.resume_checkbox = QCheckBox()
        self.resume_checkbox.setChecked(str(self.settings.value("resume_downloads", "true")).lower() != "false")
        self.resume_checkbox.stateChanged.connect(lambda _state: self.save_settings())

        self.retry_combo = QComboBox()
        self.retry_combo.addItem("", 0)
        self.retry_combo.addItem("", 1)
        self.retry_combo.addItem("", 2)
        self.retry_combo.addItem("", 3)
        saved_retries = int(str(self.settings.value("max_retries", "0")))
        retry_index = self.retry_combo.findData(max(0, min(3, saved_retries)))
        if retry_index >= 0:
            self.retry_combo.setCurrentIndex(retry_index)
        self.retry_combo.currentIndexChanged.connect(lambda _index: self.save_settings())

        self.start_button = QPushButton()
        self.start_button.clicked.connect(self.start_download)
        self.add_queue_button = QPushButton()
        self.add_queue_button.clicked.connect(self.add_urls_to_queue)
        self.cancel_button = QPushButton()
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_download)
        self.open_button = QPushButton()
        self.open_button.clicked.connect(self.open_output_folder)
        self.add_local_video_button = QPushButton()
        self.add_local_video_button.clicked.connect(self.choose_local_videos)
        self.clear_url_button = QPushButton()
        self.clear_url_button.clicked.connect(self.url_input.clear)
        self.paste_url_button = QPushButton()
        self.paste_url_button.clicked.connect(self.paste_urls)
        self.clear_status_button = QPushButton()
        self.clear_status_button.clicked.connect(self.status_box_clear)

        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(900)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.start_preview)

        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setFixedSize(180, 102)
        self.thumbnail_label.setStyleSheet("border: 1px solid #bbb; background: #f6f6f6; color: #666;")

        self.title_label = QLabel()
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.channel_label = QLabel()
        self.channel_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.duration_label = QLabel()
        self.mp3_path_label = QLabel()
        self.mp3_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.mp4_path_label = QLabel()
        self.mp4_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_label = QLabel()

        self.result_list = QListWidget()
        self.result_list.itemDoubleClicked.connect(self.open_selected_file)
        self.result_list.currentItemChanged.connect(lambda _current, _previous: self.update_result_buttons())

        self.queue_list = QListWidget()
        self.queue_list.currentItemChanged.connect(lambda _current, _previous: self.update_queue_buttons())

        self.history_list = QListWidget()
        self.history_list.itemDoubleClicked.connect(self.open_selected_history_file)

        self.move_up_button = QPushButton()
        self.move_up_button.clicked.connect(lambda: self.move_queue_item(-1))
        self.move_down_button = QPushButton()
        self.move_down_button.clicked.connect(lambda: self.move_queue_item(1))
        self.remove_queue_button = QPushButton()
        self.remove_queue_button.clicked.connect(self.remove_selected_queue_item)
        self.clear_queue_button = QPushButton()
        self.clear_queue_button.clicked.connect(self.clear_queue)
        self.retry_failed_button = QPushButton()
        self.retry_failed_button.clicked.connect(self.retry_failed_downloads)

        self.open_file_button = QPushButton()
        self.open_file_button.clicked.connect(self.open_selected_file)
        self.copy_path_button = QPushButton()
        self.copy_path_button.clicked.connect(self.copy_selected_path)
        self.show_file_button = QPushButton()
        self.show_file_button.clicked.connect(self.show_selected_in_folder)
        self.clear_history_button = QPushButton()
        self.clear_history_button.clicked.connect(self.clear_history)

        self.status_box = QTextEdit()
        self.status_box.setReadOnly(True)

        self.result_tabs: QTabWidget | None = None

        self._build_layout()
        self.update_language()
        self.update_result_buttons()
        self.update_queue_buttons()
        self.update_quality_controls()
        self.refresh_history()

    def t(self, key: str) -> str:
        return TEXT[self.language][key]

    def _section_header(self, number: int) -> tuple[QHBoxLayout, QLabel]:
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 2)
        header.setSpacing(7)
        badge = QLabel(str(number))
        badge.setObjectName("sectionBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(20, 20)
        title = QLabel()
        title.setObjectName("sectionTitle")
        header.addWidget(badge)
        header.addWidget(title)
        header.addStretch(1)
        return header, title

    def _build_layout(self) -> None:
        self.setMinimumSize(1260, 780)
        if not self.settings.contains("window_size"):
            self.resize(1400, 880)

        self.input_group = QGroupBox()
        input_group_layout = QVBoxLayout(self.input_group)
        input_group_layout.setContentsMargins(12, 10, 12, 12)
        input_group_layout.setSpacing(8)
        input_header, self.input_title_label = self._section_header(1)
        input_group_layout.addLayout(input_header)
        input_layout = QHBoxLayout()
        input_layout.setSpacing(14)

        url_panel = QVBoxLayout()
        url_panel.setSpacing(6)
        url_panel.addWidget(self.url_label)
        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        self.url_input.setFixedHeight(86)
        url_row.addWidget(self.url_input, 1)
        url_buttons = QVBoxLayout()
        url_buttons.setSpacing(8)
        url_buttons.addWidget(self.paste_url_button)
        url_buttons.addWidget(self.clear_url_button)
        url_buttons.addStretch(1)
        url_row.addLayout(url_buttons)
        url_panel.addLayout(url_row)

        output_panel = QVBoxLayout()
        output_panel.setSpacing(6)
        output_panel.addWidget(self.output_label)
        output_row = QHBoxLayout()
        output_row.setSpacing(8)
        output_row.addWidget(self.output_input, 1)
        output_row.addWidget(self.browse_button)
        output_panel.addLayout(output_row)
        output_panel.addStretch(1)

        input_layout.addLayout(url_panel, 3)
        input_layout.addLayout(output_panel, 2)
        input_group_layout.addLayout(input_layout)

        self.settings_group = QGroupBox()
        settings_group_layout = QVBoxLayout(self.settings_group)
        settings_group_layout.setContentsMargins(12, 10, 12, 12)
        settings_group_layout.setSpacing(8)
        settings_header, self.settings_title_label = self._section_header(2)
        settings_group_layout.addLayout(settings_header)
        settings_layout = QGridLayout()
        settings_layout.setHorizontalSpacing(16)
        settings_layout.setVerticalSpacing(10)
        settings_layout.addWidget(self.mode_label, 0, 0)
        settings_layout.addWidget(self.mode_combo, 1, 0)
        settings_layout.addWidget(self.audio_format_label, 0, 1)
        settings_layout.addWidget(self.audio_format_combo, 1, 1)
        settings_layout.addWidget(self.mp3_quality_label, 0, 2)
        settings_layout.addWidget(self.mp3_quality_combo, 1, 2)
        settings_layout.addWidget(self.video_format_label, 0, 3)
        settings_layout.addWidget(self.video_format_combo, 1, 3)
        settings_layout.addWidget(self.mp4_quality_label, 0, 4)
        settings_layout.addWidget(self.mp4_quality_combo, 1, 4)
        settings_layout.addWidget(self.embed_audio_thumbnail_checkbox, 1, 5, 1, 2)
        settings_layout.addWidget(self.folder_rule_label, 2, 0)
        settings_layout.addWidget(self.folder_rule_combo, 3, 0)
        settings_layout.addWidget(self.filename_rule_label, 2, 1)
        settings_layout.addWidget(self.filename_rule_combo, 3, 1)
        settings_layout.addWidget(self.custom_template_label, 2, 2, 1, 5)
        settings_layout.addWidget(self.custom_template_input, 3, 2, 1, 5)
        settings_layout.addWidget(self.language_label, 4, 0)
        settings_layout.addWidget(self.language_combo, 5, 0)
        settings_layout.addWidget(self.retry_label, 4, 1)
        settings_layout.addWidget(self.retry_combo, 5, 1)
        settings_layout.addWidget(self.notify_checkbox, 5, 2)
        settings_layout.addWidget(self.skip_downloaded_checkbox, 5, 3)
        settings_layout.addWidget(self.resume_checkbox, 5, 4, 1, 3)
        settings_layout.addWidget(self.video_processing_label, 6, 0)
        settings_layout.addWidget(self.video_processing_combo, 7, 0)
        settings_layout.addWidget(self.video_codec_label, 6, 1)
        settings_layout.addWidget(self.video_codec_combo, 7, 1)
        settings_layout.addWidget(self.resolution_label, 6, 2)
        settings_layout.addWidget(self.resolution_combo, 7, 2)
        settings_layout.addWidget(self.fps_label, 6, 3)
        settings_layout.addWidget(self.fps_combo, 7, 3)
        settings_layout.addWidget(self.quality_label, 6, 4)
        settings_layout.addWidget(self.quality_combo, 7, 4)
        settings_layout.addWidget(self.crf_label, 6, 5)
        settings_layout.addWidget(self.crf_spin, 7, 5)
        settings_layout.addWidget(self.transcode_speed_label, 6, 6)
        settings_layout.addWidget(self.transcode_speed_combo, 7, 6)
        settings_layout.addWidget(self.video_audio_label, 8, 0)
        settings_layout.addWidget(self.video_audio_combo, 9, 0)
        settings_layout.addWidget(self.keep_original_checkbox, 9, 1, 1, 2)
        settings_layout.addWidget(self.video_output_hint_label, 8, 3, 2, 4)
        for column in range(7):
            settings_layout.setColumnMinimumWidth(column, 116)
        settings_layout.setColumnStretch(6, 2)
        settings_group_layout.addLayout(settings_layout)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        buttons.addWidget(self.add_queue_button)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.add_local_video_button)
        buttons.addWidget(self.clear_status_button)
        buttons.addStretch(1)

        preview_details = QVBoxLayout()
        preview_details.addWidget(self.title_label)
        preview_details.addWidget(self.channel_label)
        preview_details.addWidget(self.duration_label)
        preview_details.addWidget(self.mp3_path_label)
        preview_details.addWidget(self.mp4_path_label)
        preview_details.addStretch(1)

        preview_layout = QHBoxLayout()
        preview_layout.setSpacing(12)
        preview_layout.addWidget(self.thumbnail_label)
        preview_layout.addLayout(preview_details, 1)

        self.preview_group = QGroupBox()
        preview_group_layout = QVBoxLayout(self.preview_group)
        preview_group_layout.setContentsMargins(10, 10, 10, 10)
        preview_group_layout.setSpacing(8)
        preview_header, self.preview_title_label = self._section_header(3)
        preview_group_layout.addLayout(preview_header)
        preview_group_layout.addLayout(preview_layout)

        progress_layout = QHBoxLayout()
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_label, 1)

        queue_buttons = QHBoxLayout()
        queue_buttons.addWidget(self.move_up_button)
        queue_buttons.addWidget(self.move_down_button)
        queue_buttons.addWidget(self.remove_queue_button)
        queue_buttons.addWidget(self.clear_queue_button)
        queue_buttons.addWidget(self.retry_failed_button)
        queue_buttons.addStretch(1)

        self.queue_group = QGroupBox()
        self.queue_list.setMinimumHeight(156)
        queue_group_layout = QVBoxLayout(self.queue_group)
        queue_group_layout.setContentsMargins(10, 10, 10, 10)
        queue_group_layout.setSpacing(8)
        queue_header, self.queue_title_label = self._section_header(4)
        queue_group_layout.addLayout(queue_header)
        queue_group_layout.addWidget(self.queue_list, 1)
        queue_group_layout.addLayout(queue_buttons)

        result_buttons = QHBoxLayout()
        result_buttons.addWidget(self.open_file_button)
        result_buttons.addWidget(self.copy_path_button)
        result_buttons.addWidget(self.show_file_button)
        result_buttons.addStretch(1)

        history_buttons = QHBoxLayout()
        history_buttons.addWidget(self.clear_history_button)
        history_buttons.addStretch(1)

        result_page = QWidget()
        result_page_layout = QVBoxLayout(result_page)
        result_page_layout.setContentsMargins(0, 0, 0, 0)
        result_page_layout.addWidget(self.result_list)
        result_page_layout.addLayout(result_buttons)

        history_page = QWidget()
        history_page_layout = QVBoxLayout(history_page)
        history_page_layout.setContentsMargins(0, 0, 0, 0)
        history_page_layout.addWidget(self.history_list)
        history_page_layout.addLayout(history_buttons)

        log_page = QWidget()
        log_page_layout = QVBoxLayout(log_page)
        log_page_layout.setContentsMargins(0, 0, 0, 0)
        log_page_layout.addWidget(self.status_box)

        self.result_tabs = QTabWidget()
        self.result_tabs.addTab(result_page, "")
        self.result_tabs.addTab(history_page, "")
        self.result_tabs.addTab(log_page, "")

        self.progress_group = QGroupBox()
        progress_group_layout = QVBoxLayout(self.progress_group)
        progress_group_layout.setContentsMargins(10, 10, 10, 10)
        progress_group_layout.setSpacing(8)
        progress_header, self.progress_title_label = self._section_header(5)
        progress_group_layout.addLayout(progress_header)
        progress_group_layout.addLayout(progress_layout)

        self.results_group = QGroupBox()
        self.results_group.setMinimumHeight(185)
        results_group_layout = QVBoxLayout(self.results_group)
        results_group_layout.setContentsMargins(10, 10, 10, 10)
        results_group_layout.setSpacing(8)
        results_header, self.results_title_label = self._section_header(6)
        results_group_layout.addLayout(results_header)
        results_group_layout.addWidget(self.result_tabs)

        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(12)
        middle_layout.addWidget(self.preview_group, 2)
        middle_layout.addWidget(self.queue_group, 3)

        footer = QHBoxLayout()
        footer.setSpacing(12)
        self.health_label = QLabel()
        self.version_footer_label = QLabel()
        self.log_folder_button = QPushButton()
        self.log_folder_button.clicked.connect(lambda: self.open_folder(PROJECT_DIR))
        footer.addWidget(self.health_label)
        footer.addStretch(1)
        footer.addWidget(self.version_footer_label)
        footer.addWidget(self.log_folder_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self.input_group)
        layout.addWidget(self.settings_group)
        layout.addLayout(buttons)
        layout.addLayout(middle_layout, 2)
        layout.addWidget(self.progress_group)
        layout.addWidget(self.results_group, 2)
        layout.addLayout(footer)

        root = QWidget()
        root.setLayout(layout)
        root.setMinimumHeight(layout.sizeHint().height())
        self.content_scroll = QScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setWidget(root)
        self.setCentralWidget(self.content_scroll)
        self.start_button.setObjectName("primaryButton")
        self.add_queue_button.setObjectName("accentButton")
        self.health_label.setObjectName("healthLabel")
        self.version_footer_label.setObjectName("mutedLabel")
        self.apply_theme()

    def apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #151719;
                color: #e8eaed;
                font-family: "Microsoft JhengHei UI", "Microsoft JhengHei", "Segoe UI";
                font-size: 10.5pt;
            }
            QGroupBox {
                background: #1b1f23;
                border: 1px solid #30363d;
                border-radius: 8px;
                margin-top: 0;
            }
            QLabel {
                color: #f1f3f4;
                background: transparent;
            }
            QLabel#sectionBadge {
                background: #2f81f7;
                color: white;
                border-radius: 5px;
                font-weight: 700;
                font-size: 9pt;
            }
            QLabel#sectionTitle {
                color: #f1f3f4;
                font-weight: 700;
            }
            QLabel#mutedLabel {
                color: #aeb6bf;
            }
            QLabel#healthLabel {
                color: #7ee787;
                font-weight: 600;
            }
            QLineEdit, QTextEdit, QListWidget, QComboBox {
                background: #22272e;
                color: #f1f3f4;
                border: 1px solid #3a424c;
                border-radius: 6px;
                padding: 6px;
                selection-background-color: #2f81f7;
            }
            QTextEdit {
                padding: 8px;
            }
            QListWidget {
                alternate-background-color: #1f242a;
            }
            QPushButton {
                background: #24292f;
                color: #f1f3f4;
                border: 1px solid #3a424c;
                border-radius: 6px;
                padding: 7px 14px;
                min-height: 22px;
            }
            QPushButton:hover {
                background: #2d333b;
                border-color: #586069;
            }
            QPushButton:disabled {
                color: #7d8590;
                background: #202428;
                border-color: #30363d;
            }
            QPushButton#primaryButton {
                background: #2ea043;
                border-color: #3fb950;
                color: white;
                font-weight: 700;
                min-width: 130px;
            }
            QPushButton#primaryButton:hover {
                background: #3fb950;
            }
            QPushButton#accentButton {
                min-width: 120px;
            }
            QCheckBox {
                spacing: 7px;
                color: #f1f3f4;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QComboBox::drop-down {
                width: 24px;
                border-left: 1px solid #3a424c;
            }
            QProgressBar {
                background: #24292f;
                border: 1px solid #30363d;
                border-radius: 6px;
                color: #f1f3f4;
                text-align: center;
                min-height: 16px;
            }
            QProgressBar::chunk {
                background: #2f81f7;
                border-radius: 5px;
            }
            QTabWidget::pane {
                border: 1px solid #30363d;
                border-radius: 6px;
                top: -1px;
            }
            QTabBar::tab {
                background: #202428;
                color: #c9d1d9;
                border: 1px solid #30363d;
                border-bottom: none;
                padding: 7px 16px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background: #2d333b;
                color: #f1f3f4;
            }
            """
        )

    def update_language(self) -> None:
        self.setWindowTitle(self.t("app_title"))
        self.url_label.setText(self.t("url"))
        self.output_label.setText(self.t("output_folder"))
        self.mode_label.setText(self.t("mode"))
        self.language_label.setText(self.t("language"))
        self.audio_format_label.setText(self.t("audio_format"))
        self.video_format_label.setText(self.t("video_format"))
        self.mp3_quality_label.setText(self.t("mp3_quality"))
        self.embed_audio_thumbnail_checkbox.setText(self.t("embed_audio_thumbnail"))
        self.embed_audio_thumbnail_checkbox.setToolTip(self.t("embed_audio_thumbnail_tooltip"))
        self.mp4_quality_label.setText(self.t("mp4_quality"))
        self.video_processing_label.setText(self.t("video_processing"))
        for index, key in enumerate(
            (
                "video_processing_keep",
                "video_processing_prefer",
                "video_processing_transcode",
                "video_processing_osu",
            )
        ):
            self.video_processing_combo.setItemText(index, self.t(key))
        self.video_codec_label.setText(self.t("video_codec"))
        self.video_codec_combo.setItemText(0, self.t("video_codec_copy"))
        self.video_codec_combo.setItemText(1, self.t("video_codec_h264"))
        self.resolution_label.setText(self.t("resolution"))
        self.resolution_combo.setItemText(0, self.t("resolution_original"))
        for index, value in enumerate(("2160p", "1440p", "1080p", "720p", "480p"), start=1):
            self.resolution_combo.setItemText(index, value)
        self.fps_label.setText(self.t("fps"))
        self.fps_combo.setItemText(0, self.t("fps_original"))
        for index, value in enumerate(("60 FPS", "30 FPS", "24 FPS"), start=1):
            self.fps_combo.setItemText(index, value)
        self.quality_label.setText(self.t("quality"))
        for index, key in enumerate(("quality_high", "quality_balanced", "quality_small", "quality_custom")):
            self.quality_combo.setItemText(index, self.t(key))
        self.crf_label.setText(self.t("crf"))
        self.transcode_speed_label.setText(self.t("transcode_speed"))
        for index, key in enumerate(("speed_veryfast", "speed_fast", "speed_medium", "speed_slow")):
            self.transcode_speed_combo.setItemText(index, self.t(key))
        self.video_audio_label.setText(self.t("video_audio"))
        self.video_audio_combo.setItemText(0, self.t("video_audio_keep"))
        self.video_audio_combo.setItemText(1, self.t("video_audio_remove"))
        self.keep_original_checkbox.setText(self.t("keep_original"))
        self.video_output_hint_label.setText(
            self.t("osu_preset_hint") if self.video_processing_combo.currentData() == "osu" else self.t("video_output_hint")
        )
        self.folder_rule_label.setText(self.t("folder_rule"))
        self.filename_rule_label.setText(self.t("filename_rule"))
        self.custom_template_label.setText(self.t("custom_template"))
        for index, key in enumerate(("folder_none", "folder_mode", "folder_channel", "folder_date", "folder_playlist")):
            self.folder_rule_combo.setItemText(index, self.t(key))
        for index, key in enumerate(
            (
                "filename_title",
                "filename_channel_title",
                "filename_playlist_index_title",
                "filename_upload_date_title",
                "filename_custom",
            )
        ):
            self.filename_rule_combo.setItemText(index, self.t(key))
        self.retry_label.setText(self.t("auto_retry"))
        self.retry_combo.setItemText(0, self.t("retry_none"))
        self.retry_combo.setItemText(1, self.t("retry_once"))
        self.retry_combo.setItemText(2, self.t("retry_twice"))
        self.retry_combo.setItemText(3, self.t("retry_thrice"))
        self.browse_button.setText(self.t("browse"))
        self.notify_checkbox.setText(self.t("notify"))
        self.skip_downloaded_checkbox.setText(self.t("skip_downloaded"))
        self.resume_checkbox.setText(self.t("resume_downloads"))
        self.paste_url_button.setText("貼上" if self.language == "zh" else "Paste")
        self.add_queue_button.setText(self.t("add_queue"))
        self.start_button.setText(self.t("start"))
        self.cancel_button.setText(self.t("cancel"))
        self.open_button.setText(self.t("open_output"))
        self.add_local_video_button.setText(self.t("add_local_video"))
        self.clear_url_button.setText(self.t("clear_url"))
        self.clear_status_button.setText(self.t("clear_status"))
        self.preview_header.setText(self.t("preview"))
        self.queue_header.setText(self.t("queue"))
        self.move_up_button.setText(self.t("move_up"))
        self.move_down_button.setText(self.t("move_down"))
        self.remove_queue_button.setText(self.t("remove_queue"))
        self.clear_queue_button.setText(self.t("clear_queue"))
        self.retry_failed_button.setText(self.t("retry_failed"))
        self.results_header.setText(self.t("results"))
        self.history_header.setText(self.t("history"))
        self.status_header.setText(self.t("status"))
        self.open_file_button.setText(self.t("open_file"))
        self.copy_path_button.setText(self.t("copy_path"))
        self.show_file_button.setText(self.t("show_folder"))
        self.clear_history_button.setText(self.t("clear_history"))
        if hasattr(self, "input_group"):
            self.input_title_label.setText("輸入" if self.language == "zh" else "Input")
            self.settings_title_label.setText("下載設定" if self.language == "zh" else "Download Settings")
            self.preview_title_label.setText("影片預覽（單一 URL）" if self.language == "zh" else "Preview (Single URL)")
            self.queue_title_label.setText("下載佇列" if self.language == "zh" else "Download Queue")
            self.progress_title_label.setText("目前下載進度" if self.language == "zh" else "Current Progress")
            self.results_title_label.setText("結果 / 歷史紀錄 / 錯誤訊息" if self.language == "zh" else "Results / History / Log")
            self.health_label.setText("● yt-dlp: OK    ● FFmpeg: OK    ● 輸出資料夾可寫入" if self.language == "zh" else "● yt-dlp: OK    ● FFmpeg: OK    ● Output folder writable")
            self.version_footer_label.setText(f"版本：{__version__}" if self.language == "zh" else f"Version: {__version__}")
            self.log_folder_button.setText("開啟 Log 資料夾" if self.language == "zh" else "Open Log Folder")
        if self.result_tabs:
            self.result_tabs.setTabText(0, self.t("results"))
            self.result_tabs.setTabText(1, self.t("history"))
            self.result_tabs.setTabText(2, self.t("status"))
        self.clear_preview()
        self.progress_label.setText(self.t("progress_waiting"))
        self.refresh_queue()
        self.refresh_history()
        self.update_custom_template_controls()
        self.update_video_processing_controls()

    def change_language(self) -> None:
        self.language = self.language_combo.currentData()
        self.save_settings()
        self.update_language()

    def handle_mode_changed(self) -> None:
        self.update_quality_controls()
        self.update_video_processing_controls()
        self.save_settings()
        self.schedule_preview()

    def handle_format_changed(self) -> None:
        self.current_info = None
        self.current_info_key = ""
        self.update_quality_controls()
        self.save_settings()
        self.schedule_preview()

    def handle_video_processing_changed(self) -> None:
        mode = self.video_processing_combo.currentData()
        if mode == "osu":
            self.video_format_combo.setCurrentIndex(max(0, self.video_format_combo.findData("mp4")))
            self.video_codec_combo.setCurrentIndex(max(0, self.video_codec_combo.findData("h264")))
            self.resolution_combo.setCurrentIndex(max(0, self.resolution_combo.findData("720")))
            if self.fps_combo.currentData() not in ("30", "60"):
                self.fps_combo.setCurrentIndex(max(0, self.fps_combo.findData("60")))
            self.quality_combo.setCurrentIndex(max(0, self.quality_combo.findData("custom")))
            self.crf_spin.setValue(20)
            self.transcode_speed_combo.setCurrentIndex(max(0, self.transcode_speed_combo.findData("medium")))
            self.video_audio_combo.setCurrentIndex(max(0, self.video_audio_combo.findData("remove")))
            self.keep_original_checkbox.setChecked(True)
        self.update_video_processing_controls()
        self.save_settings()
        self.schedule_preview()

    def handle_output_options_changed(self, *_args) -> None:
        self.update_custom_template_controls()
        self.save_settings()
        self.schedule_preview()

    def update_custom_template_controls(self) -> None:
        enabled = self.filename_rule_combo.currentData() == "custom" and self.filename_rule_combo.isEnabled()
        self.custom_template_label.setEnabled(enabled)
        self.custom_template_input.setEnabled(enabled)

    def update_quality_controls(self, base_enabled: bool | None = None) -> None:
        if base_enabled is None:
            base_enabled = self.mode_combo.isEnabled()

        mode = self.mode_combo.currentData()
        audio_enabled = base_enabled and mode in ("mp3", "both")
        video_enabled = base_enabled and mode in ("mp4", "both")
        mp3_enabled = audio_enabled and self.audio_format_combo.currentData() == "mp3"
        mp4_enabled = video_enabled

        self.audio_format_label.setEnabled(audio_enabled)
        self.audio_format_combo.setEnabled(audio_enabled)
        self.mp3_quality_label.setEnabled(mp3_enabled)
        self.mp3_quality_combo.setEnabled(mp3_enabled)
        self.embed_audio_thumbnail_checkbox.setEnabled(mp3_enabled)
        self.video_format_label.setEnabled(video_enabled)
        self.video_format_combo.setEnabled(video_enabled)
        self.mp4_quality_label.setEnabled(mp4_enabled)
        self.mp4_quality_combo.setEnabled(mp4_enabled)

    def update_video_processing_controls(self, base_enabled: bool | None = None) -> None:
        if base_enabled is None:
            base_enabled = self.mode_combo.isEnabled()
        video_mode = self.mode_combo.currentData() in ("mp4", "both")
        enabled = base_enabled and video_mode
        processing = self.video_processing_combo.currentData()
        needs_settings = enabled and processing != "keep"
        force_osu = processing == "osu"

        self.video_processing_label.setEnabled(enabled)
        self.video_processing_combo.setEnabled(enabled)
        for widget in (
            self.video_codec_label,
            self.video_codec_combo,
            self.resolution_label,
            self.resolution_combo,
            self.fps_label,
            self.fps_combo,
            self.quality_label,
            self.quality_combo,
            self.crf_label,
            self.crf_spin,
            self.transcode_speed_label,
            self.transcode_speed_combo,
            self.video_audio_label,
            self.video_audio_combo,
            self.keep_original_checkbox,
            self.video_output_hint_label,
        ):
            widget.setEnabled(needs_settings)
        if force_osu:
            self.video_format_combo.setEnabled(False)
            self.video_audio_combo.setEnabled(False)
        self.crf_spin.setEnabled(needs_settings and self.quality_combo.currentData() == "custom")
        self.video_output_hint_label.setText(
            self.t("osu_preset_hint") if force_osu else self.t("video_output_hint")
        )

    def choose_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self.t("output_folder"), self.output_input.text())
        if folder:
            self.output_input.setText(folder)

    def saved_output_dir(self) -> Path:
        saved = Path(str(self.settings.value("output_dir", str(DEFAULT_DOWNLOAD_DIR)))).expanduser()
        if self.can_create_dir(saved):
            return saved
        return DEFAULT_DOWNLOAD_DIR

    def current_output_dir(self) -> Path:
        return Path(self.output_input.text().strip() or DEFAULT_DOWNLOAD_DIR).expanduser()

    def current_audio_format(self) -> str:
        return str(self.audio_format_combo.currentData() or "mp3")

    def current_video_format(self) -> str:
        return str(self.video_format_combo.currentData() or "mp4")

    def current_video_transcode_options(self) -> VideoTranscodeOptions:
        mode = str(self.video_processing_combo.currentData() or "keep")
        if mode == "osu":
            return VideoTranscodeOptions.osu(str(self.fps_combo.currentData() or "60"))
        return VideoTranscodeOptions(
            mode=mode,
            container=self.current_video_format(),
            video_codec=str(self.video_codec_combo.currentData() or "h264"),
            resolution=str(self.resolution_combo.currentData() or "original"),
            fps=str(self.fps_combo.currentData() or "original"),
            quality=str(self.quality_combo.currentData() or "balanced"),
            crf=int(self.crf_spin.value()),
            speed=str(self.transcode_speed_combo.currentData() or "medium"),
            audio=str(self.video_audio_combo.currentData() or "keep"),
            keep_original=self.keep_original_checkbox.isChecked(),
            suffix="_h264" if mode != "osu" else "_osu_h264",
            pixel_format="yuv420p",
            faststart=True,
            no_upscale=True,
            aspect_mode="fit",
        ).normalized()

    def preview_context_key(self, url: str, output_dir: Path) -> str:
        options = self.output_options()
        return "|".join(
            (
                url.strip(),
                str(output_dir),
                options.folder_rule,
                options.filename_rule,
                options.custom_template,
                self.current_audio_format(),
                self.current_video_format(),
                self.current_video_transcode_options().mode,
                self.current_video_transcode_options().suffix,
                self.current_video_transcode_options().container,
                self.current_video_transcode_options().video_codec,
                self.current_video_transcode_options().resolution,
                self.current_video_transcode_options().fps,
            )
        )

    def can_create_dir(self, path: Path) -> bool:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        return True

    def selected_output_dir_or_warn(self) -> Path | None:
        output_dir = self.current_output_dir()
        if self.can_create_dir(output_dir):
            return output_dir
        QMessageBox.warning(self, self.t("output_folder_error"), f"{self.t('output_folder_error')}:\n{output_dir}")
        return None

    def schedule_preview(self) -> None:
        self.current_info = None
        self.current_info_url = ""
        urls = self.parse_urls()
        if not urls:
            self.clear_preview()
            self.preview_timer.stop()
            return
        if len(urls) > 1:
            self.preview_timer.stop()
            self.show_batch_preview(len(urls))
            return
        if is_playlist_url(urls[0]):
            self.preview_timer.stop()
            self.show_playlist_preview()
            return
        self.preview_timer.start()

    def start_preview(self) -> None:
        if self.preview_worker and self.preview_worker.isRunning():
            return

        urls = self.parse_urls()
        if len(urls) != 1:
            return
        url = urls[0]

        output_dir = self.current_output_dir()
        request_key = self.preview_context_key(url, output_dir)
        self.append_status(self.t("fetching_info"))
        self.preview_worker = PreviewWorker(
            url,
            output_dir,
            self.output_options(),
            self.current_audio_format(),
            self.current_video_format(),
            self.current_video_transcode_options(),
        )
        self.preview_worker.finished_ok.connect(
            lambda info, thumbnail: self.preview_finished(url, info, thumbnail, request_key)
        )
        self.preview_worker.failed.connect(self.preview_failed)
        self.preview_worker.start()

    def preview_finished(self, url: str, info: VideoInfo, thumbnail: bytes, request_key: str = "") -> None:
        current_key = self.preview_context_key(url, self.current_output_dir())
        if self.parse_urls() != [url] or (request_key and request_key != current_key):
            self.schedule_preview()
            return

        self.current_info = info
        self.current_info_url = url
        self.current_info_key = current_key
        self.title_label.setText(f"{self.t('title')}: {info.title}")
        self.channel_label.setText(f"{self.t('channel')}: {info.uploader}")
        self.duration_label.setText(f"{self.t('duration')}: {format_duration(info.duration, self.t('unknown'))}")
        self.mp3_path_label.setText(f"{info.audio_format.upper()}: {info.mp3_path}")
        self.mp4_path_label.setText(f"{info.video_format.upper()}: {info.mp4_path}")

        pixmap = QPixmap()
        if thumbnail and pixmap.loadFromData(thumbnail):
            scaled = pixmap.scaled(
                self.thumbnail_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.thumbnail_label.setPixmap(scaled)
        else:
            self.thumbnail_label.setText(self.t("no_thumbnail"))
        self.append_status(self.t("info_loaded"))

    def preview_failed(self, message: str) -> None:
        self.clear_preview()
        self.append_status(f"{self.t('preview_error')}: {friendly_error(message, self.language)}")

    def clear_preview(self) -> None:
        self.thumbnail_label.clear()
        self.thumbnail_label.setText(self.t("no_preview"))
        self.title_label.setText(f"{self.t('title')}: -")
        self.channel_label.setText(f"{self.t('channel')}: -")
        self.duration_label.setText(f"{self.t('duration')}: -")
        self.mp3_path_label.setText(f"{self.current_audio_format().upper()}: -")
        self.mp4_path_label.setText(f"{self.current_video_format().upper()}: -")

    def show_batch_preview(self, count: int) -> None:
        self.thumbnail_label.clear()
        self.thumbnail_label.setText(self.t("no_preview"))
        self.title_label.setText(self.t("batch_preview").format(count=count))
        self.channel_label.setText(f"{self.t('channel')}: -")
        self.duration_label.setText(f"{self.t('duration')}: -")
        self.mp3_path_label.setText(f"{self.current_audio_format().upper()}: -")
        self.mp4_path_label.setText(f"{self.current_video_format().upper()}: -")

    def show_playlist_preview(self) -> None:
        self.thumbnail_label.clear()
        self.thumbnail_label.setText(self.t("no_preview"))
        self.title_label.setText(self.t("playlist_preview"))
        self.channel_label.setText(f"{self.t('channel')}: -")
        self.duration_label.setText(f"{self.t('duration')}: -")
        self.mp3_path_label.setText(f"{self.current_audio_format().upper()}: -")
        self.mp4_path_label.setText(f"{self.current_video_format().upper()}: -")

    def paste_urls(self) -> None:
        text = QApplication.clipboard().text().strip()
        if not text:
            return
        current = self.url_input.toPlainText().strip()
        self.url_input.setPlainText(f"{current}\n{text}" if current else text)

    def parse_urls(self) -> list[str]:
        urls = []
        for raw_line in self.url_input.toPlainText().splitlines():
            line = raw_line.strip()
            if not line:
                continue
            matches = re.findall(r"https?://\S+", line)
            if matches:
                urls.extend(match.rstrip(",;") for match in matches)
            else:
                urls.append(line)
        return urls

    def status_label(self, status: str) -> str:
        return self.t(f"queue_status_{status}") if f"queue_status_{status}" in TEXT[self.language] else status

    def refresh_queue(self) -> None:
        if not hasattr(self, "queue_list"):
            return
        selected = self.selected_queue_index()
        self.queue_list.clear()
        for index, task in enumerate(self.download_queue, start=1):
            title = task.title or task.url
            label = f"{index}. [{self.status_label(task.status)}] {title}"
            if task.attempts:
                label += f" ({task.attempts}/{task.max_retries + 1})"
            if task.last_error or task.error:
                label += f" - {friendly_error(task.last_error or task.error, self.language, task.friendly_error)}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, index - 1)
            self.queue_list.addItem(item)
        if self.download_queue:
            self.queue_list.setCurrentRow(min(selected if selected is not None else 0, len(self.download_queue) - 1))
        self.update_queue_buttons()

    def selected_queue_index(self) -> int | None:
        if not hasattr(self, "queue_list"):
            return None
        item = self.queue_list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def update_queue_buttons(self) -> None:
        running = bool(self.worker and self.worker.isRunning())
        index = self.selected_queue_index()
        has_selection = index is not None
        can_edit = not running
        self.move_up_button.setEnabled(can_edit and has_selection and index > 0)
        self.move_down_button.setEnabled(can_edit and has_selection and index < len(self.download_queue) - 1)
        self.remove_queue_button.setEnabled(can_edit and has_selection)
        self.clear_queue_button.setEnabled(can_edit and bool(self.download_queue))
        self.retry_failed_button.setEnabled(can_edit and any(task.status == "failed" for task in self.download_queue))

    def move_queue_item(self, delta: int) -> None:
        index = self.selected_queue_index()
        if index is None:
            return
        new_index = index + delta
        if new_index < 0 or new_index >= len(self.download_queue):
            return
        self.download_queue[index], self.download_queue[new_index] = self.download_queue[new_index], self.download_queue[index]
        self.refresh_queue()
        self.queue_list.setCurrentRow(new_index)

    def remove_selected_queue_item(self) -> None:
        index = self.selected_queue_index()
        if index is None:
            return
        del self.download_queue[index]
        self.refresh_queue()

    def clear_queue(self) -> None:
        self.download_queue.clear()
        self.refresh_queue()

    def current_max_retries(self) -> int:
        return int(self.retry_combo.currentData() or 0)

    def output_options(self) -> OutputOptions:
        return OutputOptions(
            folder_rule=str(self.folder_rule_combo.currentData() or "none"),
            filename_rule=str(self.filename_rule_combo.currentData() or "title"),
            custom_template=self.custom_template_input.text().strip(),
        )

    def reset_task_for_run(self, task: QueueTask, index: int, status: str = "waiting") -> None:
        task.status = status
        task.error = ""
        task.last_error = ""
        task.friendly_error = ""
        task.attempts = 0
        task.max_retries = self.current_max_retries()
        task.queue_index = index

    def add_urls_to_queue(self) -> None:
        urls = self.parse_urls()
        if not urls:
            QMessageBox.warning(self, self.t("missing_url_title"), self.t("missing_url"))
            return
        output_dir = self.selected_output_dir_or_warn()
        if output_dir is None:
            return
        if self.queue_worker and self.queue_worker.isRunning():
            return
        self.append_status(self.t("queue_building"))
        self.add_queue_button.setEnabled(False)
        self.queue_worker = QueueBuildWorker(urls, output_dir)
        self.queue_worker.status.connect(self.append_status)
        self.queue_worker.finished_ok.connect(self.queue_build_finished)
        self.queue_worker.finished.connect(self.queue_build_cleanup)
        self.queue_worker.start()

    def queue_build_finished(self, tasks: list[QueueTask], errors: list[str]) -> None:
        existing_keys = {queue_task_key(task.url) for task in self.download_queue}
        new_tasks = []
        for task in tasks:
            key = queue_task_key(task.url)
            if key in existing_keys:
                continue
            existing_keys.add(key)
            new_tasks.append(task)
        self.download_queue.extend(new_tasks)
        if new_tasks:
            self.append_status(self.t("queue_added").format(count=len(new_tasks)))
        for error in errors:
            self.append_status(f"{self.t('queue_item_failed')}: {friendly_error(error, self.language)}")
        self.refresh_queue()

    def queue_build_cleanup(self) -> None:
        if self.queue_worker:
            self.queue_worker.deleteLater()
            self.queue_worker = None
        self.add_queue_button.setEnabled(not bool(self.worker and self.worker.isRunning()))

    def update_queue_task(
        self,
        index: int,
        status: str,
        title: str,
        error: str,
        attempts: int,
        friendly_error_key: str,
    ) -> None:
        if index < 0 or index >= len(self.download_queue):
            return
        task = self.download_queue[index]
        task.status = status
        if title:
            task.title = title
        task.error = error
        task.last_error = error
        task.friendly_error = friendly_error_key
        task.attempts = attempts
        self.refresh_queue()

    def retry_failed_downloads(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        failed_indexes = [index for index, task in enumerate(self.download_queue) if task.status == "failed"]
        if not failed_indexes:
            self.append_status(self.t("retry_failed_empty"))
            return
        for index, task in enumerate(self.download_queue):
            task.queue_index = index
            task.max_retries = self.current_max_retries()
            if index in failed_indexes:
                self.reset_task_for_run(task, index)
        self.append_status(self.t("retry_failed_started").format(count=len(failed_indexes)))
        self.start_download(retry_failed_only=True)

    def start_download(self, retry_failed_only: bool = False) -> None:
        mode = str(self.mode_combo.currentData())
        audio_format = self.current_audio_format()
        video_format = self.current_video_format()
        downloaded_by_video_id = history_downloads_by_video_id()
        skip_downloaded = self.skip_downloaded_checkbox.isChecked()

        if isinstance(retry_failed_only, bool) and retry_failed_only:
            tasks = [copy_queue_task(task) for task in self.download_queue]
        elif self.download_queue:
            for index, task in enumerate(self.download_queue):
                has_requested_outputs = task_has_downloaded_modes(
                    task,
                    mode,
                    downloaded_by_video_id,
                    audio_format,
                    video_format,
                )
                keep_completed = task.status in ("completed", "skipped") and has_requested_outputs
                if keep_completed or (skip_downloaded and has_requested_outputs):
                    task.status = "completed"
                    task.error = ""
                    task.last_error = ""
                    task.friendly_error = ""
                    task.queue_index = index
                    continue
                self.reset_task_for_run(task, index)
            tasks = [copy_queue_task(task) for task in self.download_queue]
            if not any(task.status == "waiting" for task in tasks):
                self.refresh_queue()
                self.append_status(self.t("queue_no_pending"))
                return
        else:
            urls = self.parse_urls()
            if not urls:
                QMessageBox.warning(self, self.t("missing_url_title"), self.t("missing_url"))
                return

            if len(urls) == 1 and not is_playlist_url(urls[0]):
                direct_task = QueueTask(url=urls[0])
                if skip_downloaded and task_has_downloaded_modes(
                    direct_task,
                    mode,
                    downloaded_by_video_id,
                    audio_format,
                    video_format,
                ):
                    self.append_status(self.t("queue_no_pending"))
                    return
                self.reset_task_for_run(direct_task, -1)
                tasks = [direct_task]
            else:
                unique_urls = list(dict.fromkeys(urls))
                self.download_queue = [QueueTask(url=url) for url in unique_urls]
                for index, task in enumerate(self.download_queue):
                    if skip_downloaded and task_has_downloaded_modes(
                        task,
                        mode,
                        downloaded_by_video_id,
                        audio_format,
                        video_format,
                    ):
                        task.status = "completed"
                        task.queue_index = index
                    else:
                        self.reset_task_for_run(task, index)
                tasks = [copy_queue_task(task) for task in self.download_queue]
                self.refresh_queue()
                if not any(task.status == "waiting" for task in tasks):
                    self.append_status(self.t("queue_no_pending"))
                    return
        if not tasks:
            QMessageBox.warning(self, self.t("missing_url_title"), self.t("missing_url"))
            return

        output_dir = self.selected_output_dir_or_warn()
        if output_dir is None:
            return
        has_playlist = any(is_playlist_url(task.url) for task in tasks)
        if len(tasks) == 1 and not is_playlist_url(tasks[0].url):
            info = self.video_info_for_start(tasks[0].url, output_dir)
            if info is None:
                return

            file_exists_action = self.ask_file_exists_action(info, mode)
            if file_exists_action is None:
                return
        else:
            file_exists_action = "number"

        self.status_box.clear()
        self.result_list.clear()
        self.progress_bar.setValue(0)
        self.progress_label.setText(self.t("progress_waiting"))
        self.append_status(f"{self.t('output_folder_line')}: {output_dir}")
        self.append_status(self.t("resume_enabled_status") if self.resume_checkbox.isChecked() else self.t("resume_disabled_status"))
        if len(tasks) > 1 or has_playlist:
            self.append_status(self.t("batch_auto_number"))
        if self.download_queue:
            self.refresh_queue()
        self.set_running(True)
        self.save_settings()

        self.worker = DownloadWorker(
            tasks,
            output_dir,
            mode,
            file_exists_action,
            self.mp3_quality_combo.currentData(),
            self.mp4_quality_combo.currentData(),
            audio_format,
            self.embed_audio_thumbnail_checkbox.isChecked(),
            video_format,
            self.current_video_transcode_options(),
            self.output_options(),
            self.resume_checkbox.isChecked(),
            self.t("batch_item"),
            self.t("batch_item_failed"),
            self.t("fetching_playlist"),
            self.t("playlist_loaded"),
            skip_downloaded,
            downloaded_by_video_id,
            self.t("skip_downloaded_status"),
            self.t("playlist_skip_summary"),
            self.t("retry_attempt"),
        )
        self.worker.status.connect(self.append_status)
        self.worker.task_updated.connect(self.update_queue_task)
        self.worker.finished_ok.connect(self.download_finished)
        self.worker.failed.connect(self.download_failed)
        self.worker.finished.connect(lambda worker=self.worker: self.cleanup_worker(worker))
        self.worker.start()

    def video_info_for_start(self, url: str, output_dir: Path) -> VideoInfo | None:
        request_key = self.preview_context_key(url, output_dir)
        if self.current_info and self.current_info_url == url and self.current_info_key == request_key:
            return self.current_info

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            info = SingleVideoDownloader(
                output_dir,
                output_options=self.output_options(),
                audio_format=self.current_audio_format(),
                video_format=self.current_video_format(),
                video_processing_options=self.current_video_transcode_options(),
            ).fetch_video_info(url)
        except Exception as exc:
            QMessageBox.warning(self, self.t("cannot_read_title"), friendly_error(str(exc), self.language))
            return None
        finally:
            QApplication.restoreOverrideCursor()

        self.preview_finished(url, info, b"", request_key)
        return info

    def ask_file_exists_action(self, info: VideoInfo, mode: str) -> str | None:
        paths = []
        if mode in ("mp3", "both") and info.mp3_path.exists():
            paths.append(info.mp3_path)
        if mode in ("mp4", "both") and info.mp4_path.exists():
            paths.append(info.mp4_path)
        if not paths:
            return "number"

        message = f"{self.t('exists_intro')}\n\n"
        message += "\n".join(str(path) for path in paths)
        message += f"\n\n{self.t('exists_choose')}"
        box = QMessageBox(self)
        box.setWindowTitle(self.t("exists_title"))
        box.setText(message)
        overwrite = box.addButton(self.t("overwrite"), QMessageBox.ButtonRole.DestructiveRole)
        skip = box.addButton(self.t("skip"), QMessageBox.ButtonRole.AcceptRole)
        number = box.addButton(self.t("auto_number"), QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton(self.t("cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(number)
        box.exec()

        clicked = box.clickedButton()
        if clicked == overwrite:
            return "overwrite"
        if clicked == skip:
            return "skip"
        if clicked == number:
            return "number"
        if clicked == cancel:
            return None
        return None

    def cancel_download(self) -> None:
        if self.worker:
            self.append_status(self.t("cancelling"))
            self.cancel_button.setEnabled(False)
            self.worker.cancel()

    def choose_local_videos(self) -> None:
        files, _selected_filter = QFileDialog.getOpenFileNames(
            self,
            self.t("add_local_video"),
            str(Path.home()),
            "Videos (*.mp4 *.mkv *.webm *.mov *.avi)",
        )
        if files:
            self.start_local_transcode(files)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        videos = [path for path in paths if Path(path).suffix.lower() in SUPPORTED_LOCAL_VIDEO_SUFFIXES]
        if not videos:
            QMessageBox.warning(self, self.t("error"), self.t("local_video_error"))
            return
        self.start_local_transcode(videos)

    def start_local_transcode(self, paths: list[str]) -> None:
        if self.worker and self.worker.isRunning():
            return
        videos = [str(Path(path)) for path in paths if Path(path).suffix.lower() in SUPPORTED_LOCAL_VIDEO_SUFFIXES]
        if not videos:
            QMessageBox.warning(self, self.t("error"), self.t("local_video_error"))
            return
        output_dir = Path("")

        options = self.current_video_transcode_options()
        if options.mode == "keep":
            options = VideoTranscodeOptions(
                mode="transcode",
                container=self.current_video_format(),
                video_codec="h264",
                resolution="original",
                fps="original",
                quality="balanced",
                crf=20,
                speed="medium",
                audio="keep",
                keep_original=True,
                suffix="_h264",
            )
        elif options.mode == "prefer_compatible":
            options = VideoTranscodeOptions(
                mode="transcode",
                container=options.container,
                video_codec=options.video_codec,
                resolution=options.resolution,
                fps=options.fps,
                quality=options.quality,
                crf=options.crf,
                speed=options.speed,
                audio=options.audio,
                keep_original=True,
                suffix=options.suffix,
                pixel_format=options.pixel_format,
                faststart=options.faststart,
                no_upscale=options.no_upscale,
                aspect_mode=options.aspect_mode,
            )

        self.status_box.clear()
        self.result_list.clear()
        self.progress_bar.setValue(0)
        self.progress_label.setText(self.t("progress_waiting"))
        self.append_status(
            f"{self.t('output_folder_line')}: "
            + ("原影片所在資料夾" if self.language == "zh" else "Source video folder")
        )
        self.set_running(True)
        self.save_settings()

        self.worker = LocalTranscodeWorker(videos, output_dir, options, "number")
        self.worker.status.connect(self.append_status)
        self.worker.finished_ok.connect(self.download_finished)
        self.worker.failed.connect(self.download_failed)
        self.worker.finished.connect(lambda worker=self.worker: self.cleanup_worker(worker))
        self.worker.start()

    def download_finished(self, entries: list[dict]) -> None:
        self.progress_bar.setValue(100)
        self.progress_label.setText("100%")

        success_count = 0
        failed_count = 0
        is_batch = len(entries) > 1
        for entry in entries:
            title = entry.get("title") or entry.get("url") or ""
            error = entry.get("error") or ""
            if error:
                failed_count += 1
                label = f"{entry.get('index', '')}. {self.t('batch_item_failed')}: {title} - {friendly_error(error, self.language)}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, "")
                self.result_list.addItem(item)
                continue

            results = entry.get("results") or []
            if results:
                success_count += 1

            paths = []
            for mode, path, skipped in results:
                paths.append(path)
                prefix = f"{entry.get('index')}. {title} - " if is_batch else ""
                label = f"{prefix}{display_label_for_result(mode, path)}: {path}"
                if skipped:
                    label += f" ({self.t('skipped')})"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, path)
                self.result_list.addItem(item)
                self.append_status(f"{self.t('output_file')}: {path}")

            info = entry.get("info")
            url = entry.get("url") or ""
            if info and paths:
                self.add_history(info, url, paths, entry)
            elif paths and entry.get("source_path"):
                self.add_local_history(entry, paths)

        if is_batch:
            self.append_status(self.t("batch_done").format(success=success_count, failed=failed_count))
        else:
            self.append_status(self.t("done"))

        if self.result_list.count():
            self.result_list.setCurrentRow(0)

        self.set_running(False)

        if self.notify_checkbox.isChecked():
            QApplication.beep()
            QMessageBox.information(self, self.t("download_completed"), self.t("download_completed_msg"))

    def download_failed(self, message: str) -> None:
        if "cancelled" in message.lower() or "canceled" in message.lower():
            for task in self.download_queue:
                if task.status in ("waiting", "downloading"):
                    task.status = "canceled"
            self.refresh_queue()
            self.append_status(self.t("cancelled"))
            self.progress_label.setText(self.t("cancelled"))
            self.set_running(False)
            return

        friendly = friendly_error(message, self.language)
        if friendly == message:
            friendly = friendly_transcode_error(message)
        self.append_status(f"{self.t('error')}: {friendly}")
        self.set_running(False)

    def cleanup_worker(self, worker: DownloadWorker | LocalTranscodeWorker) -> None:
        if self.worker is worker:
            self.worker = None
        self.update_queue_buttons()
        worker.deleteLater()

    def add_history(self, info: VideoInfo, url: str, paths: list[str], entry: dict | None = None) -> None:
        video_options = self.current_video_transcode_options()
        items = load_history()
        items.insert(
            0,
            {
                "schema_version": 2,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "title": info.title,
                "url": url,
                "video_id": extract_video_id(url),
                "paths": paths,
                "download_modes": modes_for_paths(paths),
                "mode": self.mode_combo.currentText(),
                "audio_format": self.current_audio_format(),
                "video_format": self.current_video_format(),
                "mp3_quality": self.mp3_quality_combo.currentText(),
                "mp4_quality": self.mp4_quality_combo.currentText(),
                "source_path": str(entry.get("source_path") or "") if entry else "",
                "converted_paths": paths if video_options.mode in {"prefer_compatible", "transcode", "osu"} else [],
                "video_processing_mode": video_options.mode,
                "video_codec": video_options.video_codec,
                "resolution": video_options.resolution,
                "fps": video_options.fps,
                "crf": video_options.effective_crf(),
                "preset": video_options.effective_preset(),
                "remove_audio": video_options.audio == "remove",
                "osu_compatible": video_options.mode == "osu",
                "media_info": entry.get("media_info").summary() if entry and entry.get("media_info") else "",
            },
        )
        save_history(items)
        self.refresh_history()

    def add_local_history(self, entry: dict, paths: list[str]) -> None:
        video_options = self.current_video_transcode_options()
        items = load_history()
        items.insert(
            0,
            {
                "schema_version": 2,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "title": entry.get("title") or Path(str(entry.get("source_path") or "")).stem,
                "url": "",
                "video_id": "",
                "source_path": entry.get("source_path") or "",
                "paths": paths,
                "converted_paths": paths,
                "download_modes": ["mp4"],
                "mode": "Local Transcode",
                "video_format": video_options.container,
                "video_processing_mode": video_options.mode,
                "video_codec": video_options.video_codec,
                "resolution": video_options.resolution,
                "fps": video_options.fps,
                "crf": video_options.effective_crf(),
                "preset": video_options.effective_preset(),
                "remove_audio": video_options.audio == "remove",
                "osu_compatible": video_options.mode == "osu",
                "source_media_info": entry.get("source_media_info").summary()
                if entry.get("source_media_info")
                else "",
                "media_info": entry.get("media_info").summary() if entry.get("media_info") else "",
            },
        )
        save_history(items)
        self.refresh_history()

    def refresh_history(self) -> None:
        if not hasattr(self, "history_list"):
            return
        self.history_list.clear()
        for item in load_history()[:50]:
            paths = item.get("paths") or []
            path = paths[0] if paths else ""
            text = f"{item.get('time', '')} | {item.get('mode', '')} | {item.get('title', '')}"
            row = QListWidgetItem(text)
            row.setData(Qt.ItemDataRole.UserRole, path)
            self.history_list.addItem(row)

    def clear_history(self) -> None:
        save_history([])
        self.refresh_history()
        self.append_status(self.t("history_cleared"))

    def open_selected_history_file(self, *_args) -> None:
        item = self.history_list.currentItem()
        if item is None:
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        if path.exists():
            self.open_path(path)

    def open_output_folder(self) -> None:
        output_dir = self.selected_output_dir_or_warn()
        if output_dir is None:
            return
        self.open_folder(output_dir)

    def selected_result_path(self) -> Path | None:
        item = self.result_list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        if not value:
            return None
        return Path(value)

    def open_selected_file(self, *_args) -> None:
        path = self.selected_result_path()
        if not path:
            return
        if path.exists():
            self.open_path(path)
        else:
            QMessageBox.warning(self, self.t("file_missing_title"), f"{self.t('file_missing')}:\n{path}")

    def copy_selected_path(self) -> None:
        path = self.selected_result_path()
        if path:
            QApplication.clipboard().setText(str(path))
            self.append_status(f"{self.t('copied_path')}: {path}")

    def show_selected_in_folder(self) -> None:
        path = self.selected_result_path()
        if not path:
            return
        if sys.platform == "win32" and path.exists():
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            self.open_folder(path.parent)

    def update_result_buttons(self) -> None:
        enabled = self.selected_result_path() is not None
        self.open_file_button.setEnabled(enabled)
        self.copy_path_button.setEnabled(enabled)
        self.show_file_button.setEnabled(enabled)

    def open_folder(self, folder: Path) -> None:
        if sys.platform == "win32":
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(folder)])

    def open_path(self, path: Path) -> None:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])

    def append_status(self, message: str) -> None:
        if message.startswith("Downloading:") or message.startswith("Transcoding:"):
            self.update_progress(message)
            return
        self.status_box.append(message)

    def update_progress(self, message: str) -> None:
        match = re.search(r"(\d+(?:\.\d+)?)%", message)
        if match:
            value = int(float(match.group(1)))
            self.progress_bar.setValue(max(0, min(100, value)))
        self.progress_label.setText(message.replace("Downloading: ", "").replace("Transcoding: ", ""))

    def status_box_clear(self) -> None:
        self.status_box.clear()
        self.progress_bar.setValue(0)
        self.progress_label.setText(self.t("progress_waiting"))

    def set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.add_queue_button.setEnabled(not running)
        self.add_local_video_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.url_input.setEnabled(not running)
        self.browse_button.setEnabled(not running)
        self.mode_combo.setEnabled(not running)
        self.folder_rule_combo.setEnabled(not running)
        self.filename_rule_combo.setEnabled(not running)
        self.language_combo.setEnabled(not running)
        self.skip_downloaded_checkbox.setEnabled(not running)
        self.resume_checkbox.setEnabled(not running)
        self.retry_combo.setEnabled(not running)
        self.update_quality_controls(not running)
        self.update_video_processing_controls(not running)
        self.update_custom_template_controls()
        self.update_queue_buttons()

    def save_settings(self) -> None:
        self.settings.setValue("output_dir", str(self.current_output_dir()))
        self.settings.setValue("mode", self.mode_combo.currentData())
        self.settings.setValue("audio_format", self.current_audio_format())
        self.settings.setValue("video_format", self.current_video_format())
        self.settings.setValue("mp3_quality", self.mp3_quality_combo.currentData())
        self.settings.setValue(
            "embed_audio_thumbnail",
            "true" if self.embed_audio_thumbnail_checkbox.isChecked() else "false",
        )
        self.settings.setValue("mp4_quality", self.mp4_quality_combo.currentData())
        video_options = self.current_video_transcode_options()
        self.settings.setValue("video_processing_mode", video_options.mode)
        self.settings.setValue("video_codec", video_options.video_codec)
        self.settings.setValue("video_resolution", video_options.resolution)
        self.settings.setValue("video_fps", video_options.fps)
        self.settings.setValue("video_quality", video_options.quality)
        self.settings.setValue("video_crf", video_options.crf)
        self.settings.setValue("video_transcode_speed", video_options.speed)
        self.settings.setValue("video_audio_mode", video_options.audio)
        self.settings.setValue("video_keep_original", "true" if video_options.keep_original else "false")
        self.settings.setValue("folder_rule", self.folder_rule_combo.currentData())
        self.settings.setValue("filename_rule", self.filename_rule_combo.currentData())
        self.settings.setValue("custom_template", self.custom_template_input.text().strip())
        self.settings.setValue("language", self.language)
        self.settings.setValue("notify_complete", "true" if self.notify_checkbox.isChecked() else "false")
        self.settings.setValue("skip_downloaded", "true" if self.skip_downloaded_checkbox.isChecked() else "false")
        self.settings.setValue("resume_downloads", "true" if self.resume_checkbox.isChecked() else "false")
        self.settings.setValue("max_retries", self.current_max_retries())
        self.settings.setValue("window_size", self.size())

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.worker and self.worker.isRunning():
            self.cancel_download()
            event.ignore()
            return
        self.save_settings()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    if APP_ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
