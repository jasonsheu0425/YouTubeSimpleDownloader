from __future__ import annotations

import json
from pathlib import Path

import ytsimpledownloader.app as app_module
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
