from __future__ import annotations

from dataclasses import fields

import ytsimpledownloader.app as app_module
import ytsimpledownloader.queue_models as queue_models


EXPECTED_FIELD_NAMES = [
    "url",
    "title",
    "status",
    "error",
    "attempts",
    "max_retries",
    "last_error",
    "friendly_error",
    "queue_index",
    "playlist_title",
    "playlist_index",
]


def test_queue_task_fields_and_defaults_are_unchanged() -> None:
    task = queue_models.QueueTask(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert [field.name for field in fields(queue_models.QueueTask)] == EXPECTED_FIELD_NAMES
    assert task == queue_models.QueueTask(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        title="",
        status="waiting",
        error="",
        attempts=0,
        max_retries=0,
        last_error="",
        friendly_error="",
        queue_index=-1,
        playlist_title="",
        playlist_index=None,
    )


def test_copy_queue_task_preserves_every_field_in_an_independent_instance() -> None:
    original = queue_models.QueueTask(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        title="Test title",
        status="failed",
        error="raw error",
        attempts=2,
        max_retries=3,
        last_error="last error",
        friendly_error="error_network",
        queue_index=4,
        playlist_title="Test playlist",
        playlist_index=5,
    )

    copied = queue_models.copy_queue_task(original)

    assert copied == original
    assert copied is not original
    copied.title = "Changed title"
    copied.attempts = 99
    assert original.title == "Test title"
    assert original.attempts == 2


def test_app_keeps_queue_model_compatibility_bindings() -> None:
    assert app_module.QueueTask is queue_models.QueueTask
    assert app_module.copy_queue_task is queue_models.copy_queue_task
