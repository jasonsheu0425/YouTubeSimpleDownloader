from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

import ytsimpledownloader.downloader as downloader_module
from ytsimpledownloader.downloader import SingleVideoDownloader
from ytsimpledownloader.yt_dlp_runtime import (
    NodeRuntimeDiagnostic,
    YtDlpRuntimeDiagnostics,
    collect_runtime_diagnostics,
    javascript_runtime_options,
    probe_node_runtime,
)


NODE_PATH = r"C:\Program Files\nodejs\node.exe"


def completed_process(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([NODE_PATH, "--version"], returncode, stdout, stderr)


def test_supported_node_is_reported_with_structured_diagnostics() -> None:
    diagnostic = probe_node_runtime(
        locate=lambda _name: NODE_PATH,
        run=lambda *_args, **_kwargs: completed_process("v22.17.1\n"),
    )

    assert diagnostic == NodeRuntimeDiagnostic(
        found=True,
        path=NODE_PATH,
        version="22.17.1",
        version_tuple=(22, 17, 1),
        supported=True,
        status="supported",
        reason="Node.js 22.17.1 is supported.",
    )


def test_node_probe_uses_argument_list_and_short_timeout() -> None:
    calls = []

    def capture_run(command, **kwargs):
        calls.append((command, kwargs))
        return completed_process("v22.0.0\n")

    diagnostic = probe_node_runtime(
        locate=lambda _name: NODE_PATH,
        run=capture_run,
        timeout=1.5,
    )

    assert diagnostic.supported is True
    assert calls == [
        (
            [NODE_PATH, "--version"],
            {
                "capture_output": True,
                "text": True,
                "timeout": 1.5,
                "check": False,
                "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
            },
        )
    ]


def test_missing_node_is_non_fatal() -> None:
    diagnostic = probe_node_runtime(locate=lambda _name: None)

    assert diagnostic.found is False
    assert diagnostic.supported is False
    assert diagnostic.status == "not_found"
    assert diagnostic.path == ""


def test_old_node_is_not_supported() -> None:
    diagnostic = probe_node_runtime(
        locate=lambda _name: NODE_PATH,
        run=lambda *_args, **_kwargs: completed_process("v21.7.3\n"),
    )

    assert diagnostic.found is True
    assert diagnostic.version_tuple == (21, 7, 3)
    assert diagnostic.supported is False
    assert diagnostic.status == "unsupported_version"


def test_node_probe_nonzero_exit_is_non_fatal() -> None:
    diagnostic = probe_node_runtime(
        locate=lambda _name: NODE_PATH,
        run=lambda *_args, **_kwargs: completed_process("", returncode=1, stderr="failed"),
    )

    assert diagnostic.found is True
    assert diagnostic.supported is False
    assert diagnostic.status == "probe_failed"
    assert "code 1" in diagnostic.reason


def test_node_probe_os_error_is_non_fatal() -> None:
    def failed_run(*_args, **_kwargs):
        raise OSError("cannot execute")

    diagnostic = probe_node_runtime(locate=lambda _name: NODE_PATH, run=failed_run)

    assert diagnostic.found is True
    assert diagnostic.supported is False
    assert diagnostic.status == "probe_failed"
    assert "cannot execute" in diagnostic.reason


def test_node_probe_timeout_is_non_fatal() -> None:
    def timeout_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired([NODE_PATH, "--version"], 2)

    diagnostic = probe_node_runtime(locate=lambda _name: NODE_PATH, run=timeout_run, timeout=2)

    assert diagnostic.found is True
    assert diagnostic.supported is False
    assert diagnostic.status == "probe_timeout"
    assert "2 seconds" in diagnostic.reason


@pytest.mark.parametrize("output", ["", "22.17.1", "node v22.17.1", "v22", "unexpected output"])
def test_malformed_node_version_is_not_supported(output: str) -> None:
    diagnostic = probe_node_runtime(
        locate=lambda _name: NODE_PATH,
        run=lambda *_args, **_kwargs: completed_process(output),
    )

    assert diagnostic.found is True
    assert diagnostic.supported is False
    assert diagnostic.status == "invalid_version"


def test_yt_dlp_version_lookup_is_included() -> None:
    diagnostics = collect_runtime_diagnostics(
        locate=lambda _name: None,
        version_lookup=lambda package: "2026.6.9" if package == "yt-dlp" else "",
    )

    assert diagnostics.yt_dlp_version == "2026.6.9"
    assert diagnostics.yt_dlp_version_available is True
    assert diagnostics.yt_dlp_version_reason == "yt-dlp 2026.6.9 is installed."


def test_yt_dlp_version_lookup_failure_is_non_fatal() -> None:
    def failed_lookup(_package: str) -> str:
        raise RuntimeError("metadata unavailable")

    diagnostics = collect_runtime_diagnostics(locate=lambda _name: None, version_lookup=failed_lookup)

    assert diagnostics.yt_dlp_version == ""
    assert diagnostics.yt_dlp_version_available is False
    assert "metadata unavailable" in diagnostics.yt_dlp_version_reason
    assert diagnostics.node.status == "not_found"


def runtime_diagnostics(node: NodeRuntimeDiagnostic) -> YtDlpRuntimeDiagnostics:
    return YtDlpRuntimeDiagnostics(
        yt_dlp_version="2026.6.9",
        yt_dlp_version_available=True,
        yt_dlp_version_reason="yt-dlp 2026.6.9 is installed.",
        node=node,
    )


def supported_node() -> NodeRuntimeDiagnostic:
    return NodeRuntimeDiagnostic(
        found=True,
        path=NODE_PATH,
        version="22.17.1",
        version_tuple=(22, 17, 1),
        supported=True,
        status="supported",
        reason="Node.js 22.17.1 is supported.",
    )


def test_supported_node_builds_existing_yt_dlp_options() -> None:
    assert javascript_runtime_options(runtime_diagnostics(supported_node())) == {
        "js_runtimes": {"node": {"path": NODE_PATH}},
        "remote_components": ["ejs:github"],
    }


@pytest.mark.parametrize(
    "node",
    [
        NodeRuntimeDiagnostic(False, "", "", None, False, "not_found", "missing"),
        NodeRuntimeDiagnostic(True, NODE_PATH, "21.7.3", (21, 7, 3), False, "unsupported_version", "old"),
        NodeRuntimeDiagnostic(True, NODE_PATH, "", None, False, "probe_failed", "failed"),
        NodeRuntimeDiagnostic(True, NODE_PATH, "", None, False, "probe_timeout", "timeout"),
        NodeRuntimeDiagnostic(True, NODE_PATH, "bad", None, False, "invalid_version", "invalid"),
    ],
)
def test_invalid_or_missing_node_leaves_yt_dlp_fallback_unconfigured(node: NodeRuntimeDiagnostic) -> None:
    assert javascript_runtime_options(runtime_diagnostics(node)) == {}


def test_downloader_base_options_use_supported_node(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    diagnostics = runtime_diagnostics(supported_node())
    monkeypatch.setattr(SingleVideoDownloader, "_ensure_ffmpeg_exe", lambda self: "ffmpeg.exe")
    monkeypatch.setattr(downloader_module, "collect_runtime_diagnostics", lambda: diagnostics)

    downloader = SingleVideoDownloader(tmp_path)
    options = downloader._base_opts()

    assert downloader.runtime_diagnostics is diagnostics
    assert options["js_runtimes"] == {"node": {"path": NODE_PATH}}
    assert options["remote_components"] == ["ejs:github"]


@pytest.mark.parametrize(
    "node",
    [
        NodeRuntimeDiagnostic(False, "", "", None, False, "not_found", "missing"),
        NodeRuntimeDiagnostic(True, NODE_PATH, "21.7.3", (21, 7, 3), False, "unsupported_version", "old"),
        NodeRuntimeDiagnostic(True, NODE_PATH, "", None, False, "probe_failed", "failed"),
        NodeRuntimeDiagnostic(True, NODE_PATH, "", None, False, "probe_timeout", "timeout"),
        NodeRuntimeDiagnostic(True, NODE_PATH, "bad", None, False, "invalid_version", "invalid"),
    ],
)
def test_downloader_base_options_leave_fallback_to_yt_dlp_when_node_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    node: NodeRuntimeDiagnostic,
) -> None:
    monkeypatch.setattr(SingleVideoDownloader, "_ensure_ffmpeg_exe", lambda self: "ffmpeg.exe")
    monkeypatch.setattr(downloader_module, "collect_runtime_diagnostics", lambda: runtime_diagnostics(node))

    options = SingleVideoDownloader(tmp_path)._base_opts()

    assert "js_runtimes" not in options
    assert "remote_components" not in options
