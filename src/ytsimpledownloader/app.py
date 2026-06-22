from __future__ import annotations

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
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .downloader import DownloadCancelled, SingleVideoDownloader, VideoInfo, extract_video_id, is_playlist_url
from .paths import DEFAULT_DOWNLOAD_DIR, PROJECT_DIR, ensure_default_dirs


HISTORY_PATH = PROJECT_DIR / "history.json"
APP_ICON_PATH = Path(__file__).resolve().parent / "assets" / "app_icon.ico"


TEXT = {
    "zh": {
        "app_title": "YouTube 簡易下載器",
        "url": "網址",
        "output_folder": "輸出資料夾",
        "output_folder_error": "無法建立輸出資料夾",
        "browse": "瀏覽",
        "mode": "下載模式",
        "language": "語言",
        "mp3_quality": "MP3 品質",
        "mp4_quality": "MP4 畫質",
        "notify": "下載完成時提示",
        "start": "開始",
        "cancel": "取消",
        "open_output": "開啟輸出資料夾",
        "clear_url": "清空網址",
        "clear_status": "清空狀態",
        "preview": "影片預覽",
        "results": "下載結果",
        "status": "狀態 / 錯誤訊息",
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
    },
    "en": {
        "app_title": "YouTube Simple Downloader",
        "url": "URL(s)",
        "output_folder": "Output Folder",
        "output_folder_error": "Cannot create output folder",
        "browse": "Browse",
        "mode": "Mode",
        "language": "Language",
        "mp3_quality": "MP3 Quality",
        "mp4_quality": "MP4 Quality",
        "notify": "Notify when complete",
        "start": "Start",
        "cancel": "Cancel",
        "open_output": "Open Output Folder",
        "clear_url": "Clear URL",
        "clear_status": "Clear Status",
        "preview": "Video Preview",
        "results": "Download Results",
        "status": "Status / Errors",
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
    },
}


class PreviewWorker(QThread):
    finished_ok = Signal(object, bytes)
    failed = Signal(str)

    def __init__(self, url: str, output_dir: Path) -> None:
        super().__init__()
        self.url = url
        self.output_dir = output_dir

    def run(self) -> None:
        try:
            downloader = SingleVideoDownloader(self.output_dir)
            info = downloader.fetch_video_info(self.url)
            thumbnail = b""
            if info.thumbnail_url:
                with urllib.request.urlopen(info.thumbnail_url, timeout=15) as response:
                    thumbnail = response.read()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(info, thumbnail)


class DownloadWorker(QThread):
    status = Signal(str)
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        urls: list[str],
        output_dir: Path,
        mode: str,
        file_exists_action: str,
        mp3_quality: str,
        mp4_quality: str,
        batch_item_template: str,
        batch_failed_label: str,
        fetching_playlist_template: str,
        playlist_loaded_template: str,
        skip_downloaded: bool,
        downloaded_by_video_id: dict[str, dict[str, str]],
        skip_downloaded_template: str,
        playlist_skip_summary_template: str,
    ) -> None:
        super().__init__()
        self.urls = urls
        self.output_dir = output_dir
        self.mode = mode
        self.file_exists_action = file_exists_action
        self.mp3_quality = mp3_quality
        self.mp4_quality = mp4_quality
        self.batch_item_template = batch_item_template
        self.batch_failed_label = batch_failed_label
        self.fetching_playlist_template = fetching_playlist_template
        self.playlist_loaded_template = playlist_loaded_template
        self.skip_downloaded = skip_downloaded
        self.downloaded_by_video_id = {video_id: paths.copy() for video_id, paths in downloaded_by_video_id.items()}
        self.skip_downloaded_template = skip_downloaded_template
        self.playlist_skip_summary_template = playlist_skip_summary_template
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
            )
            entries = []
            task_urls = []
            source_total = len(self.urls)
            for source_index, url in enumerate(self.urls, start=1):
                if self.cancel_event.is_set():
                    raise DownloadCancelled("Download cancelled by user.")

                if is_playlist_url(url):
                    self.status.emit(self.fetching_playlist_template.format(url=url))
                    try:
                        playlist = downloader.fetch_playlist_info(url)
                    except Exception as exc:
                        if source_total == 1:
                            raise
                        entries.append(
                            {
                                "index": source_index,
                                "url": url,
                                "title": url,
                                "error": str(exc),
                                "results": [],
                            }
                        )
                        self.status.emit(f"{self.batch_failed_label}: {url} - {exc}")
                    else:
                        task_urls.extend(playlist.urls)
                        self.status.emit(
                            self.playlist_loaded_template.format(title=playlist.title, count=len(playlist.urls))
                        )
                else:
                    task_urls.append(url)

            total = len(task_urls)
            history_skipped_count = 0
            for index, url in enumerate(task_urls, start=1):
                if self.cancel_event.is_set():
                    raise DownloadCancelled("Download cancelled by user.")

                if total > 1:
                    self.status.emit(self.batch_item_template.format(current=index, total=total) + f": {url}")

                try:
                    video_id = extract_video_id(url)
                    requested_modes = modes_for_download(self.mode)
                    existing = self.downloaded_by_video_id.get(video_id, {}) if self.skip_downloaded and video_id else {}
                    existing_results = []
                    for requested_mode in requested_modes:
                        existing_path = existing.get(requested_mode)
                        if existing_path and Path(existing_path).exists():
                            existing_results.append((requested_mode, existing_path, True))

                    missing_modes = [mode for mode in requested_modes if mode not in {item[0] for item in existing_results}]
                    if self.skip_downloaded and video_id and not missing_modes:
                        history_skipped_count += 1
                        self.status.emit(self.skip_downloaded_template.format(url=url))
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
                        continue

                    info = downloader.fetch_video_info(url)
                    result_items = list(existing_results)
                    download_mode = download_mode_for_missing_modes(missing_modes)
                    if download_mode:
                        results = downloader.download(url, download_mode)
                        for result in results:
                            result_items.append((result.mode, str(result.path), result.skipped))
                            if video_id and not result.skipped and result.path.exists():
                                self.downloaded_by_video_id.setdefault(video_id, {})[result.mode] = str(result.path)
                                self.downloaded_by_video_id[video_id]["_title"] = info.title
                except DownloadCancelled:
                    raise
                except Exception as exc:
                    if total == 1:
                        raise
                    entries.append(
                        {
                            "index": index,
                            "url": url,
                            "title": url,
                            "error": str(exc),
                            "results": [],
                        }
                    )
                    self.status.emit(f"{self.batch_failed_label}: {url} - {exc}")
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
            if history_skipped_count:
                self.status.emit(self.playlist_skip_summary_template.format(skipped=history_skipped_count))
        except DownloadCancelled as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(entries)


def friendly_error(message: str, language: str) -> str:
    lower = message.lower()
    if "video unavailable" in lower or "private video" in lower:
        return TEXT[language]["error_unavailable"]
    if "sign in" in lower or "login" in lower or "cookies" in lower:
        return TEXT[language]["error_login"]
    if "timed out" in lower or "connection" in lower or "network" in lower or "temporary failure" in lower:
        return TEXT[language]["error_network"]
    if "http error 429" in lower or "too many requests" in lower or "temporarily unavailable" in lower:
        return TEXT[language]["error_limited"]
    if "unsupported url" in lower:
        return TEXT[language]["error_unsupported"]
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


def modes_for_paths(paths: list[str]) -> list[str]:
    modes = []
    for raw_path in paths:
        suffix = Path(str(raw_path)).suffix.lower()
        if suffix == ".mp3" and "mp3" not in modes:
            modes.append("mp3")
        elif suffix == ".mp4" and "mp4" not in modes:
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

        for raw_path in item.get("paths") or []:
            path = Path(str(raw_path))
            if not path.exists():
                continue
            if path.suffix.lower() == ".mp3":
                bucket["mp3"] = str(path)
            elif path.suffix.lower() == ".mp4":
                bucket["mp4"] = str(path)
    return downloads


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        ensure_default_dirs()
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.settings = QSettings("YouTubeSimpleDownloader", "YouTubeSimpleDownloader")
        self.language = str(self.settings.value("language", "zh"))
        if self.language not in TEXT:
            self.language = "zh"

        self.worker: DownloadWorker | None = None
        self.preview_worker: PreviewWorker | None = None
        self.current_info: VideoInfo | None = None
        self.current_info_url = ""

        self.resize(self.settings.value("window_size", self.size()))

        self.url_label = QLabel()
        self.output_label = QLabel()
        self.mode_label = QLabel()
        self.language_label = QLabel()
        self.mp3_quality_label = QLabel()
        self.mp4_quality_label = QLabel()
        self.preview_header = QLabel()
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

        self.mp3_quality_combo = QComboBox()
        for value in ("128", "192", "256", "320"):
            self.mp3_quality_combo.addItem(f"{value}K", value)
        saved_mp3 = self.settings.value("mp3_quality", "192")
        mp3_index = self.mp3_quality_combo.findData(saved_mp3)
        if mp3_index >= 0:
            self.mp3_quality_combo.setCurrentIndex(mp3_index)

        self.mp4_quality_combo = QComboBox()
        for label, value in (("Best", "best"), ("1080p", "1080"), ("720p", "720"), ("480p", "480")):
            self.mp4_quality_combo.addItem(label, value)
        saved_mp4 = self.settings.value("mp4_quality", "best")
        mp4_index = self.mp4_quality_combo.findData(saved_mp4)
        if mp4_index >= 0:
            self.mp4_quality_combo.setCurrentIndex(mp4_index)
        self.mode_combo.currentIndexChanged.connect(self.handle_mode_changed)

        self.notify_checkbox = QCheckBox()
        self.notify_checkbox.setChecked(str(self.settings.value("notify_complete", "true")).lower() != "false")
        self.skip_downloaded_checkbox = QCheckBox()
        self.skip_downloaded_checkbox.setChecked(str(self.settings.value("skip_downloaded", "true")).lower() != "false")
        self.skip_downloaded_checkbox.stateChanged.connect(lambda _state: self.save_settings())

        self.start_button = QPushButton()
        self.start_button.clicked.connect(self.start_download)
        self.cancel_button = QPushButton()
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_download)
        self.open_button = QPushButton()
        self.open_button.clicked.connect(self.open_output_folder)
        self.clear_url_button = QPushButton()
        self.clear_url_button.clicked.connect(self.url_input.clear)
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

        self.history_list = QListWidget()
        self.history_list.itemDoubleClicked.connect(self.open_selected_history_file)

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

        self._build_layout()
        self.update_language()
        self.update_result_buttons()
        self.update_quality_controls()
        self.refresh_history()

    def t(self, key: str) -> str:
        return TEXT[self.language][key]

    def _build_layout(self) -> None:
        form = QGridLayout()
        form.addWidget(self.url_label, 0, 0)
        form.addWidget(self.url_input, 0, 1, 1, 4)
        form.addWidget(self.clear_url_button, 0, 5)
        form.addWidget(self.output_label, 1, 0)
        form.addWidget(self.output_input, 1, 1, 1, 4)
        form.addWidget(self.browse_button, 1, 5)
        form.addWidget(self.mode_label, 2, 0)
        form.addWidget(self.mode_combo, 2, 1)
        form.addWidget(self.mp3_quality_label, 2, 2)
        form.addWidget(self.mp3_quality_combo, 2, 3)
        form.addWidget(self.mp4_quality_label, 2, 4)
        form.addWidget(self.mp4_quality_combo, 2, 5)
        form.addWidget(self.language_label, 3, 0)
        form.addWidget(self.language_combo, 3, 1)
        form.addWidget(self.notify_checkbox, 3, 2, 1, 2)
        form.addWidget(self.skip_downloaded_checkbox, 3, 4, 1, 2)

        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.open_button)
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
        preview_layout.addWidget(self.thumbnail_label)
        preview_layout.addLayout(preview_details, 1)

        progress_layout = QHBoxLayout()
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_label, 1)

        result_buttons = QHBoxLayout()
        result_buttons.addWidget(self.open_file_button)
        result_buttons.addWidget(self.copy_path_button)
        result_buttons.addWidget(self.show_file_button)
        result_buttons.addStretch(1)

        history_buttons = QHBoxLayout()
        history_buttons.addWidget(self.clear_history_button)
        history_buttons.addStretch(1)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.preview_header)
        layout.addLayout(preview_layout)
        layout.addLayout(buttons)
        layout.addLayout(progress_layout)
        layout.addWidget(self.results_header)
        layout.addWidget(self.result_list)
        layout.addLayout(result_buttons)
        layout.addWidget(self.history_header)
        layout.addWidget(self.history_list)
        layout.addLayout(history_buttons)
        layout.addWidget(self.status_header)
        layout.addWidget(self.status_box, 1)

        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)

    def update_language(self) -> None:
        self.setWindowTitle(self.t("app_title"))
        self.url_label.setText(self.t("url"))
        self.output_label.setText(self.t("output_folder"))
        self.mode_label.setText(self.t("mode"))
        self.language_label.setText(self.t("language"))
        self.mp3_quality_label.setText(self.t("mp3_quality"))
        self.mp4_quality_label.setText(self.t("mp4_quality"))
        self.browse_button.setText(self.t("browse"))
        self.notify_checkbox.setText(self.t("notify"))
        self.skip_downloaded_checkbox.setText(self.t("skip_downloaded"))
        self.start_button.setText(self.t("start"))
        self.cancel_button.setText(self.t("cancel"))
        self.open_button.setText(self.t("open_output"))
        self.clear_url_button.setText(self.t("clear_url"))
        self.clear_status_button.setText(self.t("clear_status"))
        self.preview_header.setText(self.t("preview"))
        self.results_header.setText(self.t("results"))
        self.history_header.setText(self.t("history"))
        self.status_header.setText(self.t("status"))
        self.open_file_button.setText(self.t("open_file"))
        self.copy_path_button.setText(self.t("copy_path"))
        self.show_file_button.setText(self.t("show_folder"))
        self.clear_history_button.setText(self.t("clear_history"))
        self.clear_preview()
        self.progress_label.setText(self.t("progress_waiting"))
        self.refresh_history()

    def change_language(self) -> None:
        self.language = self.language_combo.currentData()
        self.save_settings()
        self.update_language()

    def handle_mode_changed(self) -> None:
        self.update_quality_controls()
        self.save_settings()

    def update_quality_controls(self, base_enabled: bool | None = None) -> None:
        if base_enabled is None:
            base_enabled = self.mode_combo.isEnabled()

        mode = self.mode_combo.currentData()
        mp3_enabled = base_enabled and mode in ("mp3", "both")
        mp4_enabled = base_enabled and mode in ("mp4", "both")

        self.mp3_quality_label.setEnabled(mp3_enabled)
        self.mp3_quality_combo.setEnabled(mp3_enabled)
        self.mp4_quality_label.setEnabled(mp4_enabled)
        self.mp4_quality_combo.setEnabled(mp4_enabled)

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
        self.append_status(self.t("fetching_info"))
        self.preview_worker = PreviewWorker(url, output_dir)
        self.preview_worker.finished_ok.connect(lambda info, thumbnail: self.preview_finished(url, info, thumbnail))
        self.preview_worker.failed.connect(self.preview_failed)
        self.preview_worker.start()

    def preview_finished(self, url: str, info: VideoInfo, thumbnail: bytes) -> None:
        if self.parse_urls() != [url]:
            return

        self.current_info = info
        self.current_info_url = url
        self.title_label.setText(f"{self.t('title')}: {info.title}")
        self.channel_label.setText(f"{self.t('channel')}: {info.uploader}")
        self.duration_label.setText(f"{self.t('duration')}: {format_duration(info.duration, self.t('unknown'))}")
        self.mp3_path_label.setText(f"MP3: {info.mp3_path}")
        self.mp4_path_label.setText(f"MP4: {info.mp4_path}")

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
        self.mp3_path_label.setText("MP3: -")
        self.mp4_path_label.setText("MP4: -")

    def show_batch_preview(self, count: int) -> None:
        self.thumbnail_label.clear()
        self.thumbnail_label.setText(self.t("no_preview"))
        self.title_label.setText(self.t("batch_preview").format(count=count))
        self.channel_label.setText(f"{self.t('channel')}: -")
        self.duration_label.setText(f"{self.t('duration')}: -")
        self.mp3_path_label.setText("MP3: -")
        self.mp4_path_label.setText("MP4: -")

    def show_playlist_preview(self) -> None:
        self.thumbnail_label.clear()
        self.thumbnail_label.setText(self.t("no_preview"))
        self.title_label.setText(self.t("playlist_preview"))
        self.channel_label.setText(f"{self.t('channel')}: -")
        self.duration_label.setText(f"{self.t('duration')}: -")
        self.mp3_path_label.setText("MP3: -")
        self.mp4_path_label.setText("MP4: -")

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

    def start_download(self) -> None:
        urls = self.parse_urls()
        if not urls:
            QMessageBox.warning(self, self.t("missing_url_title"), self.t("missing_url"))
            return

        output_dir = self.selected_output_dir_or_warn()
        if output_dir is None:
            return
        mode = self.mode_combo.currentData()
        has_playlist = any(is_playlist_url(url) for url in urls)
        if len(urls) == 1 and not is_playlist_url(urls[0]):
            info = self.video_info_for_start(urls[0], output_dir)
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
        if len(urls) > 1 or has_playlist:
            self.append_status(self.t("batch_auto_number"))
        self.set_running(True)
        self.save_settings()

        self.worker = DownloadWorker(
            urls,
            output_dir,
            mode,
            file_exists_action,
            self.mp3_quality_combo.currentData(),
            self.mp4_quality_combo.currentData(),
            self.t("batch_item"),
            self.t("batch_item_failed"),
            self.t("fetching_playlist"),
            self.t("playlist_loaded"),
            self.skip_downloaded_checkbox.isChecked(),
            history_downloads_by_video_id(),
            self.t("skip_downloaded_status"),
            self.t("playlist_skip_summary"),
        )
        self.worker.status.connect(self.append_status)
        self.worker.finished_ok.connect(self.download_finished)
        self.worker.failed.connect(self.download_failed)
        self.worker.finished.connect(lambda worker=self.worker: self.cleanup_worker(worker))
        self.worker.start()

    def video_info_for_start(self, url: str, output_dir: Path) -> VideoInfo | None:
        if self.current_info and self.current_info_url == url:
            return self.current_info

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            info = SingleVideoDownloader(output_dir).fetch_video_info(url)
        except Exception as exc:
            QMessageBox.warning(self, self.t("cannot_read_title"), friendly_error(str(exc), self.language))
            return None
        finally:
            QApplication.restoreOverrideCursor()

        self.preview_finished(url, info, b"")
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
                label = f"{prefix}{mode.upper()}: {path}"
                if skipped:
                    label += f" ({self.t('skipped')})"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, path)
                self.result_list.addItem(item)
                self.append_status(f"{self.t('output_file')}: {path}")

            info = entry.get("info")
            url = entry.get("url") or ""
            if info and paths:
                self.add_history(info, url, paths)

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
            self.append_status(self.t("cancelled"))
            self.progress_label.setText(self.t("cancelled"))
            self.set_running(False)
            return

        self.append_status(f"{self.t('error')}: {friendly_error(message, self.language)}")
        self.set_running(False)

    def cleanup_worker(self, worker: DownloadWorker) -> None:
        if self.worker is worker:
            self.worker = None
        worker.deleteLater()

    def add_history(self, info: VideoInfo, url: str, paths: list[str]) -> None:
        items = load_history()
        items.insert(
            0,
            {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "title": info.title,
                "url": url,
                "video_id": extract_video_id(url),
                "paths": paths,
                "download_modes": modes_for_paths(paths),
                "mode": self.mode_combo.currentText(),
                "mp3_quality": self.mp3_quality_combo.currentText(),
                "mp4_quality": self.mp4_quality_combo.currentText(),
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
        if message.startswith("Downloading:"):
            self.update_progress(message)
            return
        self.status_box.append(message)

    def update_progress(self, message: str) -> None:
        match = re.search(r"(\d+(?:\.\d+)?)%", message)
        if match:
            value = int(float(match.group(1)))
            self.progress_bar.setValue(max(0, min(100, value)))
        self.progress_label.setText(message.replace("Downloading: ", ""))

    def status_box_clear(self) -> None:
        self.status_box.clear()
        self.progress_bar.setValue(0)
        self.progress_label.setText(self.t("progress_waiting"))

    def set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.url_input.setEnabled(not running)
        self.browse_button.setEnabled(not running)
        self.mode_combo.setEnabled(not running)
        self.language_combo.setEnabled(not running)
        self.skip_downloaded_checkbox.setEnabled(not running)
        self.update_quality_controls(not running)

    def save_settings(self) -> None:
        self.settings.setValue("output_dir", str(self.current_output_dir()))
        self.settings.setValue("mode", self.mode_combo.currentData())
        self.settings.setValue("mp3_quality", self.mp3_quality_combo.currentData())
        self.settings.setValue("mp4_quality", self.mp4_quality_combo.currentData())
        self.settings.setValue("language", self.language)
        self.settings.setValue("notify_complete", "true" if self.notify_checkbox.isChecked() else "false")
        self.settings.setValue("skip_downloaded", "true" if self.skip_downloaded_checkbox.isChecked() else "false")
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
