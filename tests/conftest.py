from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    application = QApplication.instance() or QApplication([])
    yield application
    application.closeAllWindows()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()
    application.quit()


@pytest.fixture(autouse=True)
def cleanup_qt_widgets():
    yield
    application = QApplication.instance()
    if application is None:
        return
    for widget in application.topLevelWidgets():
        preview_timer = getattr(widget, "preview_timer", None)
        if preview_timer is not None:
            preview_timer.stop()
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()
