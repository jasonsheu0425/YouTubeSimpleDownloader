from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QByteArray, QObject, QSettings, Signal
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtWidgets import QApplication

import ytsimpledownloader.app as app_module
from ytsimpledownloader import __version__


def next_patch_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) < 3 or any(not part.isdecimal() for part in parts):
        raise ValueError("version must contain at least three numeric release segments")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("0.10.1", "0.10.2"),
        ("0.10.1.1", "0.10.1.2"),
    ],
)
def test_next_patch_version_increments_final_release_segment(version, expected) -> None:
    assert next_patch_version(version) == expected


LATEST_VERSION = next_patch_version(__version__)
RELEASE_URL = (
    "https://github.com/jasonsheu0425/YouTubeSimpleDownloader/releases/tag/"
    f"v{LATEST_VERSION}"
)


class FakeReply(QObject):
    finished = Signal()

    def __init__(self, payload: bytes = b"", error=QNetworkReply.NetworkError.NoError) -> None:
        super().__init__()
        self.payload = payload
        self.network_error = error
        self.aborted = False
        self.deleted = False

    def error(self):
        return self.network_error

    def readAll(self):  # noqa: N802
        return QByteArray(self.payload)

    def abort(self) -> None:
        self.aborted = True

    def deleteLater(self) -> None:  # noqa: N802
        self.deleted = True


@pytest.fixture
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> QSettings:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.SystemScope, str(tmp_path))
    settings = QSettings("YouTubeSimpleDownloader", "YouTubeSimpleDownloader")
    settings.clear()
    settings.sync()
    monkeypatch.setattr(app_module, "ensure_default_dirs", lambda: None)
    monkeypatch.setattr(app_module, "HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(app_module, "DEFAULT_DOWNLOAD_DIR", tmp_path)
    return settings


def update_payload() -> bytes:
    return json.dumps(
        {
            "tag_name": f"v{LATEST_VERSION}",
            "html_url": RELEASE_URL,
            "draft": False,
            "prerelease": False,
        }
    ).encode("utf-8")


def test_main_window_construction_does_not_start_network_request(qapp, isolated_settings, monkeypatch) -> None:
    requests = []
    monkeypatch.setattr(app_module.MainWindow, "_send_update_request", lambda self, request: requests.append(request))
    window = app_module.MainWindow()
    try:
        qapp.processEvents()
        assert requests == []
    finally:
        window.close()


def test_disabled_automatic_check_does_not_create_request(qapp, isolated_settings, monkeypatch) -> None:
    isolated_settings.setValue("check_updates_automatically", "false")
    isolated_settings.sync()
    window = app_module.MainWindow()
    requests = []
    monkeypatch.setattr(window, "_send_update_request", lambda request: requests.append(request))
    try:
        window.maybe_check_for_updates()
        assert requests == []
    finally:
        window.close()


def test_due_check_creates_request_and_records_attempt(qapp, isolated_settings, monkeypatch) -> None:
    window = app_module.MainWindow()
    reply = FakeReply()
    requests = []

    def send(request):
        requests.append(request)
        return reply

    monkeypatch.setattr(window, "_send_update_request", send)
    try:
        window.maybe_check_for_updates()
        assert len(requests) == 1
        assert requests[0].url().toString() == app_module.GITHUB_LATEST_RELEASE_API_URL
        assert isolated_settings.value("last_update_check_utc")
    finally:
        window.close()
        assert reply.aborted is True


def test_network_failure_is_silent(qapp, isolated_settings, monkeypatch) -> None:
    window = app_module.MainWindow()
    reply = FakeReply(error=QNetworkReply.NetworkError.ConnectionRefusedError)
    monkeypatch.setattr(window, "_send_update_request", lambda request: reply)
    try:
        window.maybe_check_for_updates()
        reply.finished.emit()
        qapp.processEvents()
        assert window.update_banner.isHidden() is True
        assert window.update_reply is None
    finally:
        window.close()


def test_new_version_banner_actions_and_language(qapp, isolated_settings, monkeypatch) -> None:
    window = app_module.MainWindow()
    reply = FakeReply(update_payload())
    opened_urls = []

    class FakeDesktopServices:
        @staticmethod
        def openUrl(url):  # noqa: N802
            opened_urls.append(url.toString())
            return True

    monkeypatch.setattr(window, "_send_update_request", lambda request: reply)
    monkeypatch.setattr(app_module, "QDesktopServices", FakeDesktopServices)
    try:
        window.maybe_check_for_updates()
        reply.finished.emit()
        qapp.processEvents()

        assert window.update_banner.isHidden() is False
        assert __version__ in window.update_banner_label.text()
        assert LATEST_VERSION in window.update_banner_label.text()
        window.open_update_button.click()
        assert opened_urls == [RELEASE_URL]

        english_index = window.language_combo.findData("en")
        window.language_combo.setCurrentIndex(english_index)
        assert window.update_check_checkbox.text() == "Check for updates automatically"
        assert "A new version is available" in window.update_banner_label.text()

        window.dismiss_update_button.click()
        assert window.update_banner.isHidden() is True
    finally:
        window.close()


def test_update_checkbox_persists_and_aborts_pending_reply(qapp, isolated_settings, monkeypatch) -> None:
    window = app_module.MainWindow()
    reply = FakeReply()
    monkeypatch.setattr(window, "_send_update_request", lambda request: reply)
    try:
        window.maybe_check_for_updates()
        window.update_check_checkbox.setChecked(False)
        isolated_settings.sync()
        assert str(isolated_settings.value("check_updates_automatically")).lower() == "false"
        assert reply.aborted is True
        assert window.update_reply is None
    finally:
        window.close()


def test_close_aborts_pending_update_reply(qapp, isolated_settings, monkeypatch) -> None:
    window = app_module.MainWindow()
    reply = FakeReply()
    monkeypatch.setattr(window, "_send_update_request", lambda request: reply)
    window.maybe_check_for_updates()
    window.close()
    assert reply.aborted is True
    assert window.update_reply is None
