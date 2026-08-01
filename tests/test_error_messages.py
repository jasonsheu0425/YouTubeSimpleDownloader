from __future__ import annotations

import pytest

import ytsimpledownloader.app as app_module
import ytsimpledownloader.error_messages as error_messages
from ytsimpledownloader.ui_text import TEXT


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("VIDEO UNAVAILABLE", "error_unavailable"),
        ("Sign in to confirm your age", "error_login"),
        ("Connection reset by peer", "error_network"),
        ("HTTP Error 429: Too Many Requests", "error_limited"),
        ("Unsupported URL", "error_unsupported"),
        ("WEBM merge failed", "error_webm"),
        ("FFmpeg postprocessing conversion failed", "error_ffmpeg"),
        ("Permission denied", "error_permission"),
        ("File name too long", "error_path"),
    ],
)
def test_error_key_classifies_known_messages_case_insensitively(message: str, expected: str) -> None:
    assert error_messages.error_key(message) == expected


def test_error_key_preserves_classification_order() -> None:
    assert error_messages.error_key("WEBM FFmpeg merge failed") == "error_webm"
    assert error_messages.error_key("Video unavailable: sign in") == "error_unavailable"


@pytest.mark.parametrize("language", ["zh", "en"])
def test_friendly_error_uses_existing_localized_text(language: str) -> None:
    assert error_messages.friendly_error("Connection timed out", language) == TEXT[language]["error_network"]
    assert error_messages.friendly_error("raw failure", language, "error_permission") == TEXT[language][
        "error_permission"
    ]


def test_unknown_and_empty_messages_are_returned_unchanged() -> None:
    assert error_messages.error_key("unexpected failure") == ""
    assert error_messages.friendly_error("unexpected failure", "en") == "unexpected failure"
    assert error_messages.friendly_error("", "zh") == ""


def test_none_keeps_existing_invalid_input_behavior() -> None:
    with pytest.raises(AttributeError):
        error_messages.error_key(None)  # type: ignore[arg-type]


def test_app_keeps_error_message_compatibility_bindings() -> None:
    assert app_module.error_key is error_messages.error_key
    assert app_module.friendly_error is error_messages.friendly_error
