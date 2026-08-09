from __future__ import annotations

import json
from pathlib import Path

import ytsimpledownloader.app as app_module
import ytsimpledownloader.history_store as history_store
from ytsimpledownloader.history_store import load_history, save_history


def test_missing_history_file_returns_empty_list(tmp_path: Path) -> None:
    assert load_history(tmp_path / "missing.json") == []


def test_invalid_json_returns_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    path.write_text("not json", encoding="utf-8")

    assert load_history(path) == []


def test_history_io_error_returns_empty_list(tmp_path: Path) -> None:
    assert load_history(tmp_path) == []


def test_non_list_json_root_returns_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    path.write_text('{"title": "not a history list"}', encoding="utf-8")

    assert load_history(path) == []


def test_valid_history_list_is_loaded(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    records = [{"title": "First"}, {"title": "Second"}]
    path.write_text(json.dumps(records), encoding="utf-8")

    assert load_history(path) == records


def test_save_round_trip_preserves_unicode_text(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    records = [{"title": "繁體中文標題"}, {"title": "English title"}]

    save_history(path, records)

    assert load_history(path) == records
    assert path.read_text(encoding="utf-8") == json.dumps(records, ensure_ascii=False, indent=2)


def test_save_uses_default_limit_of_one_hundred(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    records = [{"index": index} for index in range(105)]

    save_history(path, records)

    assert load_history(path) == records[:100]


def test_save_accepts_an_explicit_limit(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    records = [{"index": index} for index in range(5)]

    save_history(path, records, limit=2)

    assert load_history(path) == records[:2]


def test_app_load_wrapper_uses_current_monkeypatched_history_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "app-history.json"
    records = [{"title": "Isolated"}]
    path.write_text(json.dumps(records), encoding="utf-8")
    monkeypatch.setattr(app_module, "HISTORY_PATH", path)

    assert app_module.load_history() == records


def test_app_save_wrapper_uses_current_monkeypatched_history_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "app-history.json"
    records = [{"title": "Isolated"}]
    monkeypatch.setattr(app_module, "HISTORY_PATH", path)

    app_module.save_history(records)

    assert load_history(path) == records


def test_path_injected_helpers_do_not_use_app_history_path(monkeypatch, tmp_path: Path) -> None:
    app_path = tmp_path / "app-history.json"
    explicit_path = tmp_path / "explicit-history.json"
    records = [{"title": "Explicit"}]
    monkeypatch.setattr(app_module, "HISTORY_PATH", app_path)

    save_history(explicit_path, records)

    assert load_history(explicit_path) == records
    assert app_path.exists() is False


def _temporary_files(path: Path) -> list[Path]:
    return list(path.parent.glob(f".{path.name}.*.tmp"))


def _seed_history(path: Path) -> bytes:
    path.write_text('[{"title": "Original"}]', encoding="utf-8")
    return path.read_bytes()


def test_save_uses_unique_same_directory_temporary_files_and_atomic_replace(
    monkeypatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "history.json"
    real_replace = history_store.os.replace
    replacements = []

    def recording_replace(source, target) -> None:
        source_path = Path(source)
        replacements.append((source_path, Path(target)))
        assert source_path.exists()
        real_replace(source, target)

    monkeypatch.setattr(history_store.os, "replace", recording_replace)

    save_history(path, [{"title": "First"}])
    save_history(path, [{"title": "Second"}])

    assert len(replacements) == 2
    assert replacements[0][0].parent == path.parent
    assert replacements[1][0].parent == path.parent
    assert replacements[0][0].name != replacements[1][0].name
    assert all(target == path for _source, target in replacements)
    assert load_history(path) == [{"title": "Second"}]
    assert _temporary_files(path) == []


def test_save_flushes_and_syncs_before_closing_and_replacing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "history.json"
    events = []
    real_fdopen = history_store.os.fdopen
    real_fsync = history_store.os.fsync
    real_replace = history_store.os.replace

    class RecordingStream:
        def __init__(self, stream) -> None:
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
            self.close()

        def write(self, payload: str) -> int:
            events.append("write")
            return self.stream.write(payload)

        def flush(self) -> None:
            events.append("flush")
            self.stream.flush()

        def fileno(self) -> int:
            return self.stream.fileno()

        def close(self) -> None:
            events.append("close")
            self.stream.close()

    def recording_fdopen(descriptor, *args, **kwargs):
        return RecordingStream(real_fdopen(descriptor, *args, **kwargs))

    def recording_fsync(descriptor) -> None:
        events.append("fsync")
        real_fsync(descriptor)

    def recording_replace(source, target) -> None:
        events.append("replace")
        real_replace(source, target)

    monkeypatch.setattr(history_store.os, "fdopen", recording_fdopen)
    monkeypatch.setattr(history_store.os, "fsync", recording_fsync)
    monkeypatch.setattr(history_store.os, "replace", recording_replace)

    save_history(path, [{"title": "Atomic"}])

    assert events == ["write", "flush", "fsync", "close", "replace"]
    assert load_history(path) == [{"title": "Atomic"}]


def test_serialization_failure_keeps_original_and_creates_no_temp(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    original = _seed_history(path)

    try:
        save_history(path, [{"not_json": object()}])
    except TypeError:
        pass
    else:
        raise AssertionError("Expected JSON serialization to fail")

    assert path.read_bytes() == original
    assert _temporary_files(path) == []


def test_temporary_file_creation_failure_keeps_original(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    original = _seed_history(path)
    monkeypatch.setattr(
        history_store.tempfile,
        "mkstemp",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("temp create failed")),
    )

    try:
        save_history(path, [{"title": "Replacement"}])
    except OSError as exc:
        assert str(exc) == "temp create failed"
    else:
        raise AssertionError("Expected temporary file creation to fail")

    assert path.read_bytes() == original
    assert _temporary_files(path) == []


class _FailingStream:
    def __init__(self, stream, stage: str) -> None:
        self.stream = stream
        self.stage = stage

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        self.close()

    def write(self, payload: str) -> int:
        if self.stage == "write":
            raise OSError("write failed")
        return self.stream.write(payload)

    def flush(self) -> None:
        if self.stage == "flush":
            raise OSError("flush failed")
        self.stream.flush()

    def fileno(self) -> int:
        return self.stream.fileno()

    def close(self) -> None:
        self.stream.close()
        if self.stage == "close":
            raise OSError("close failed")


def test_stream_failure_keeps_original_and_cleans_temp(monkeypatch, tmp_path: Path) -> None:
    real_fdopen = history_store.os.fdopen

    for stage in ("write", "flush", "close"):
        path = tmp_path / f"{stage}-history.json"
        original = _seed_history(path)
        monkeypatch.setattr(
            history_store.os,
            "fdopen",
            lambda descriptor, *args, _stage=stage, **kwargs: _FailingStream(
                real_fdopen(descriptor, *args, **kwargs),
                _stage,
            ),
        )

        try:
            save_history(path, [{"title": "Replacement"}])
        except OSError as exc:
            assert str(exc) == f"{stage} failed"
        else:
            raise AssertionError(f"Expected {stage} to fail")

        assert path.read_bytes() == original
        assert _temporary_files(path) == []


def test_fsync_failure_keeps_original_and_cleans_temp(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    original = _seed_history(path)
    monkeypatch.setattr(
        history_store.os,
        "fsync",
        lambda _descriptor: (_ for _ in ()).throw(OSError("fsync failed")),
    )

    try:
        save_history(path, [{"title": "Replacement"}])
    except OSError as exc:
        assert str(exc) == "fsync failed"
    else:
        raise AssertionError("Expected fsync to fail")

    assert path.read_bytes() == original
    assert _temporary_files(path) == []


def test_replace_failure_keeps_original_and_cleans_temp(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    original = _seed_history(path)
    monkeypatch.setattr(
        history_store.os,
        "replace",
        lambda _source, _target: (_ for _ in ()).throw(OSError("replace failed")),
    )

    try:
        save_history(path, [{"title": "Replacement"}])
    except OSError as exc:
        assert str(exc) == "replace failed"
    else:
        raise AssertionError("Expected replace to fail")

    assert path.read_bytes() == original
    assert _temporary_files(path) == []


def test_cleanup_failure_does_not_hide_save_failure(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    original = _seed_history(path)
    monkeypatch.setattr(
        history_store.os,
        "replace",
        lambda _source, _target: (_ for _ in ()).throw(OSError("replace failed")),
    )
    monkeypatch.setattr(
        history_store.Path,
        "unlink",
        lambda _path: (_ for _ in ()).throw(OSError("cleanup failed")),
    )

    try:
        save_history(path, [{"title": "Replacement"}])
    except OSError as exc:
        assert str(exc) == "replace failed"
    else:
        raise AssertionError("Expected replace to fail")

    assert path.read_bytes() == original
    leftovers = _temporary_files(path)
    assert len(leftovers) == 1
    monkeypatch.undo()
    leftovers[0].unlink()


def test_missing_parent_is_not_created(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "history.json"

    try:
        save_history(path, [{"title": "No parent"}])
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Expected missing parent to fail")

    assert path.parent.exists() is False
