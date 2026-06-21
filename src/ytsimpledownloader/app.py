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
from PySide6.QtGui import QPixmap
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

from .downloader import DownloadCancelled, SingleVideoDownloader, VideoInfo
from .paths import DEFAULT_DOWNLOAD_DIR, PROJECT_DIR, ensure_default_dirs


HISTORY_PATH = PROJECT_DIR / "history.json"


TEXT = {
    "zh": {
        "app_title": "YouTube 簡易下載器",
        "url": "網址",
        "output_folder": "輸出資料夾",
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
        "missing_url": "請輸入單一 YouTube 影片網址。",
        "cannot_read_title": "無法讀取影片",
        "output_folder_line": "輸出資料夾",
        "done": "完成。",
        "download_completed": "下載完成",
        "download_completed_msg": "下載已完成。",
        "output_file": "輸出檔案",
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
        "error_unsupported": "不支援此網址。請貼上單一公開 YouTube 影片網址。",
    },
    "en": {
        "app_title": "YouTube Simple Downloader",
        "url": "URL",
        "output_folder": "Output Folder",
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
        "missing_url": "Please enter a single YouTube video URL.",
        "cannot_read_title": "Cannot read video",
        "output_folder_line": "Output folder",
        "done": "Done.",
        "download_completed": "Download completed",
        "download_completed_msg": "Download completed.",
        "output_file": "Output file",
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
        "error_unsupported": "Unsupported URL. Please paste a single public YouTube video URL.",
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
        url: str,
        output_dir: Path,
        mode: str,
        file_exists_action: str,
        mp3_quality: str,
        mp4_quality: str,
    ) -> None:
        super().__init__()
        self.url = url
        self.output_dir = output_dir
        self.mode = mode
        self.file_exists_action = file_exists_action
        self.mp3_quality = mp3_quality
        self.mp4_quality = mp4_quality
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
            results = downloader.download(self.url, self.mode)
        except DownloadCancelled as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit([(result.mode, str(result.path), result.skipped) for result in results])


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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        ensure_default_dirs()
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

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.url_input.textChanged.connect(self.schedule_preview)

        self.output_input = QLineEdit(str(self.settings.value("output_dir", str(DEFAULT_DOWNLOAD_DIR))))
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

    def schedule_preview(self) -> None:
        self.current_info = None
        self.current_info_url = ""
        url = self.url_input.text().strip()
        if not url:
            self.clear_preview()
            self.preview_timer.stop()
            return
        self.preview_timer.start()

    def start_preview(self) -> None:
        if self.preview_worker and self.preview_worker.isRunning():
            return

        url = self.url_input.text().strip()
        if not url:
            return

        output_dir = Path(self.output_input.text().strip() or DEFAULT_DOWNLOAD_DIR)
        self.append_status(self.t("fetching_info"))
        self.preview_worker = PreviewWorker(url, output_dir)
        self.preview_worker.finished_ok.connect(lambda info, thumbnail: self.preview_finished(url, info, thumbnail))
        self.preview_worker.failed.connect(self.preview_failed)
        self.preview_worker.start()

    def preview_finished(self, url: str, info: VideoInfo, thumbnail: bytes) -> None:
        if url != self.url_input.text().strip():
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

    def start_download(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, self.t("missing_url_title"), self.t("missing_url"))
            return

        output_dir = Path(self.output_input.text().strip() or DEFAULT_DOWNLOAD_DIR)
        mode = self.mode_combo.currentData()
        info = self.video_info_for_start(url, output_dir)
        if info is None:
            return

        file_exists_action = self.ask_file_exists_action(info, mode)
        if file_exists_action is None:
            return

        self.status_box.clear()
        self.result_list.clear()
        self.progress_bar.setValue(0)
        self.progress_label.setText(self.t("progress_waiting"))
        self.append_status(f"{self.t('output_folder_line')}: {output_dir}")
        self.set_running(True)
        self.save_settings()

        self.worker = DownloadWorker(
            url,
            output_dir,
            mode,
            file_exists_action,
            self.mp3_quality_combo.currentData(),
            self.mp4_quality_combo.currentData(),
        )
        self.worker.status.connect(self.append_status)
        self.worker.finished_ok.connect(lambda results: self.download_finished(results, info, url))
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

    def download_finished(self, results: list[tuple[str, str, bool]], info: VideoInfo, url: str) -> None:
        self.progress_bar.setValue(100)
        self.progress_label.setText("100%")
        self.append_status(self.t("done"))
        paths = []
        for mode, path, skipped in results:
            paths.append(path)
            label = f"{mode.upper()}: {path}"
            if skipped:
                label += f" ({self.t('skipped')})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.result_list.addItem(item)
            self.append_status(f"{self.t('output_file')}: {path}")
        if self.result_list.count():
            self.result_list.setCurrentRow(0)

        self.add_history(info, url, paths)
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
                "paths": paths,
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
        output_dir = Path(self.output_input.text().strip() or DEFAULT_DOWNLOAD_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        self.open_folder(output_dir)

    def selected_result_path(self) -> Path | None:
        item = self.result_list.currentItem()
        if item is None:
            return None
        return Path(item.data(Qt.ItemDataRole.UserRole))

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
        enabled = self.result_list.currentItem() is not None
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
        self.browse_button.setEnabled(not running)
        self.mode_combo.setEnabled(not running)
        self.language_combo.setEnabled(not running)
        self.update_quality_controls(not running)

    def save_settings(self) -> None:
        self.settings.setValue("output_dir", self.output_input.text().strip() or str(DEFAULT_DOWNLOAD_DIR))
        self.settings.setValue("mode", self.mode_combo.currentData())
        self.settings.setValue("mp3_quality", self.mp3_quality_combo.currentData())
        self.settings.setValue("mp4_quality", self.mp4_quality_combo.currentData())
        self.settings.setValue("language", self.language)
        self.settings.setValue("notify_complete", "true" if self.notify_checkbox.isChecked() else "false")
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
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
