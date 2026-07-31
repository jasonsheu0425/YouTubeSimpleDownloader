from __future__ import annotations

from dataclasses import dataclass


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
