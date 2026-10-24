from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ytsimpledownloader.app as app_module


def test_thumbnail_setting_defaults_off_and_is_saved(qapp, isolated_settings, isolated_settings_factory) -> None:
    window = app_module.MainWindow()
    try:
        checkbox = window.embed_audio_thumbnail_checkbox
        assert checkbox.isChecked() is False
        assert checkbox.isEnabled() is True

        checkbox.setChecked(True)
        isolated_settings.sync()
        reloaded = isolated_settings_factory()
        assert str(reloaded.value("embed_audio_thumbnail", "false")).lower() == "true"
    finally:
        window.close()


def test_thumbnail_setting_is_loaded_and_only_enabled_for_mp3(qapp, isolated_settings) -> None:
    isolated_settings.setValue("embed_audio_thumbnail", "true")
    isolated_settings.sync()
    window = app_module.MainWindow()
    try:
        checkbox = window.embed_audio_thumbnail_checkbox
        assert checkbox.isChecked() is True

        window.audio_format_combo.setCurrentIndex(window.audio_format_combo.findData("m4a"))
        assert checkbox.isEnabled() is False

        window.audio_format_combo.setCurrentIndex(window.audio_format_combo.findData("mp3"))
        assert checkbox.isEnabled() is True

        window.mode_combo.setCurrentIndex(window.mode_combo.findData("mp4"))
        assert checkbox.isEnabled() is False

        window.mode_combo.setCurrentIndex(window.mode_combo.findData("both"))
        assert checkbox.isEnabled() is True
    finally:
        window.close()
