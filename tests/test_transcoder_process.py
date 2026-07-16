from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread, Timer
import time

import pytest

from ytsimpledownloader.transcoder import TranscodeCancelled, VideoTranscoder


def _python_command(script: str, *arguments: Path) -> list[str]:
    return [sys.executable, "-u", "-c", script, *(str(argument) for argument in arguments)]


def _assert_reader_threads_stopped() -> None:
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        readers = [thread for thread in _live_threads() if thread.name.startswith("ffmpeg-")]
        if not readers:
            return
        time.sleep(0.01)
    assert not [thread for thread in _live_threads() if thread.name.startswith("ffmpeg-")]


def _live_threads() -> list[Thread]:
    from threading import enumerate as enumerate_threads

    return enumerate_threads()


def test_ffmpeg_like_process_preserves_progress_and_stderr() -> None:
    messages: list[str] = []
    transcoder = VideoTranscoder(
        sys.executable,
        progress_callback=messages.append,
        inactivity_timeout=2.0,
        terminate_timeout=0.5,
    )
    command = _python_command(
        "import sys\n"
        "print('out_time_ms=500000', flush=True)\n"
        "print('speed=1.25x', flush=True)\n"
        "print('diagnostic-line', file=sys.stderr, flush=True)\n"
        "print('progress=end', flush=True)\n"
    )

    stderr_tail = transcoder._run_ffmpeg(command, duration=1.0)

    assert stderr_tail == "diagnostic-line"
    assert any("50.0%" in message for message in messages)
    assert "Transcode speed: 1.25x" in messages
    assert "Transcoding: 100%" in messages
    _assert_reader_threads_stopped()


def test_large_stdout_and_stderr_are_drained_without_deadlock() -> None:
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(project_root / "src"), existing_pythonpath) if part
    )
    child_script = (
        "import sys\n"
        "for index in range(1024):\n"
        "    print(f'stderr-{index}-' + 'e' * 1024, file=sys.stderr)\n"
        "sys.stderr.flush()\n"
        "for index in range(1024):\n"
        "    print(f'stdout-{index}-' + 'o' * 1024)\n"
        "print('progress=end')\n"
        "sys.stdout.flush()\n"
    )
    harness = (
        "import sys\n"
        "from ytsimpledownloader.transcoder import VideoTranscoder\n"
        f"child_script = {child_script!r}\n"
        "transcoder = VideoTranscoder(sys.executable, inactivity_timeout=2.0, terminate_timeout=0.5)\n"
        "tail = transcoder._run_ffmpeg([sys.executable, '-u', '-c', child_script], None)\n"
        "assert 'stderr-1023-' in tail\n"
    )

    try:
        completed = subprocess.run(
            [sys.executable, "-u", "-c", harness],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("FFmpeg-like subprocess deadlocked while both pipes were under pressure")

    assert completed.returncode == 0, completed.stderr


def test_cancel_event_terminates_running_process(tmp_path: Path) -> None:
    cancel_event = Event()
    completed_marker = tmp_path / "completed.txt"
    transcoder = VideoTranscoder(
        sys.executable,
        cancel_event=cancel_event,
        inactivity_timeout=5.0,
        terminate_timeout=0.5,
    )
    command = _python_command(
        "from pathlib import Path\n"
        "import sys, time\n"
        "print('progress=continue', flush=True)\n"
        "time.sleep(30)\n"
        "Path(sys.argv[1]).write_text('finished', encoding='utf-8')\n",
        completed_marker,
    )
    timer = Timer(0.25, cancel_event.set)
    timer.start()
    started = time.monotonic()

    try:
        with pytest.raises(TranscodeCancelled, match="cancelled by user"):
            transcoder._run_ffmpeg(command, duration=None)
    finally:
        timer.cancel()

    assert time.monotonic() - started < 3.0
    time.sleep(0.1)
    assert not completed_marker.exists()
    _assert_reader_threads_stopped()


def test_inactivity_timeout_stops_and_cleans_up_process(tmp_path: Path) -> None:
    completed_marker = tmp_path / "completed.txt"
    transcoder = VideoTranscoder(
        sys.executable,
        inactivity_timeout=0.3,
        terminate_timeout=0.5,
    )
    command = _python_command(
        "from pathlib import Path\n"
        "import sys, time\n"
        "time.sleep(30)\n"
        "Path(sys.argv[1]).write_text('finished', encoding='utf-8')\n",
        completed_marker,
    )
    started = time.monotonic()

    with pytest.raises(RuntimeError, match="produced no output for 0.3 seconds"):
        transcoder._run_ffmpeg(command, duration=None)

    assert time.monotonic() - started < 3.0
    time.sleep(0.1)
    assert not completed_marker.exists()
    _assert_reader_threads_stopped()


def test_nonzero_return_code_preserves_stderr_error() -> None:
    transcoder = VideoTranscoder(
        sys.executable,
        inactivity_timeout=2.0,
        terminate_timeout=0.5,
    )
    command = _python_command(
        "import sys\n"
        "print('specific ffmpeg failure', file=sys.stderr, flush=True)\n"
        "raise SystemExit(7)\n"
    )

    with pytest.raises(RuntimeError, match="specific ffmpeg failure"):
        transcoder._run_ffmpeg(command, duration=None)


def test_terminate_escalates_to_kill_after_grace_period() -> None:
    class StubbornProcess:
        def __init__(self) -> None:
            self.terminated = False
            self.killed = False
            self.wait_calls = 0

        def poll(self) -> int | None:
            return 0 if self.killed else None

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

        def wait(self, timeout: float | None = None) -> int:
            self.wait_calls += 1
            if not self.killed:
                raise subprocess.TimeoutExpired(cmd="fake-ffmpeg", timeout=timeout)
            return 0

    process = StubbornProcess()
    transcoder = VideoTranscoder(
        sys.executable,
        inactivity_timeout=2.0,
        terminate_timeout=0.01,
    )

    transcoder._terminate_process(process)  # type: ignore[arg-type]

    assert process.terminated
    assert process.killed
    assert process.wait_calls == 2
