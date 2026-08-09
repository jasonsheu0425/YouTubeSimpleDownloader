from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import metadata
import re
from shutil import which
import subprocess


MINIMUM_NODE_VERSION = (22, 0, 0)
NODE_PROBE_TIMEOUT_SECONDS = 2.0
_NODE_VERSION_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")


@dataclass(frozen=True)
class NodeRuntimeDiagnostic:
    found: bool
    path: str
    version: str
    version_tuple: tuple[int, int, int] | None
    supported: bool
    status: str
    reason: str


@dataclass(frozen=True)
class YtDlpRuntimeDiagnostics:
    yt_dlp_version: str
    yt_dlp_version_available: bool
    yt_dlp_version_reason: str
    node: NodeRuntimeDiagnostic


def probe_node_runtime(
    *,
    locate: Callable[[str], str | None] = which,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    timeout: float = NODE_PROBE_TIMEOUT_SECONDS,
) -> NodeRuntimeDiagnostic:
    node_path = locate("node")
    if not node_path:
        return NodeRuntimeDiagnostic(
            found=False,
            path="",
            version="",
            version_tuple=None,
            supported=False,
            status="not_found",
            reason="Node.js was not found on PATH.",
        )

    try:
        completed = run(
            [node_path, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return NodeRuntimeDiagnostic(
            found=True,
            path=node_path,
            version="",
            version_tuple=None,
            supported=False,
            status="probe_timeout",
            reason=f"Node.js version probe timed out after {timeout:g} seconds.",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return NodeRuntimeDiagnostic(
            found=True,
            path=node_path,
            version="",
            version_tuple=None,
            supported=False,
            status="probe_failed",
            reason=f"Node.js version probe failed: {exc}",
        )

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    if completed.returncode != 0:
        return NodeRuntimeDiagnostic(
            found=True,
            path=node_path,
            version="",
            version_tuple=None,
            supported=False,
            status="probe_failed",
            reason=f"Node.js version probe exited with code {completed.returncode}.",
        )

    match = _NODE_VERSION_PATTERN.fullmatch(output)
    if match is None:
        return NodeRuntimeDiagnostic(
            found=True,
            path=node_path,
            version=output,
            version_tuple=None,
            supported=False,
            status="invalid_version",
            reason="Node.js returned an unrecognized version string.",
        )

    version_tuple = tuple(int(part) for part in match.groups())
    version = ".".join(str(part) for part in version_tuple)
    supported = version_tuple >= MINIMUM_NODE_VERSION
    return NodeRuntimeDiagnostic(
        found=True,
        path=node_path,
        version=version,
        version_tuple=version_tuple,
        supported=supported,
        status="supported" if supported else "unsupported_version",
        reason=(
            f"Node.js {version} is supported."
            if supported
            else f"Node.js {version} is below the required minimum 22.0.0."
        ),
    )


def collect_runtime_diagnostics(
    *,
    locate: Callable[[str], str | None] = which,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    version_lookup: Callable[[str], str] = metadata.version,
    timeout: float = NODE_PROBE_TIMEOUT_SECONDS,
) -> YtDlpRuntimeDiagnostics:
    try:
        yt_dlp_version = version_lookup("yt-dlp")
    except Exception as exc:
        yt_dlp_version = ""
        version_available = False
        version_reason = f"Unable to determine yt-dlp version: {exc}"
    else:
        version_available = True
        version_reason = f"yt-dlp {yt_dlp_version} is installed."

    return YtDlpRuntimeDiagnostics(
        yt_dlp_version=yt_dlp_version,
        yt_dlp_version_available=version_available,
        yt_dlp_version_reason=version_reason,
        node=probe_node_runtime(locate=locate, run=run, timeout=timeout),
    )


def javascript_runtime_options(diagnostics: YtDlpRuntimeDiagnostics) -> dict:
    if not diagnostics.node.supported:
        return {}
    return {
        "js_runtimes": {"node": {"path": diagnostics.node.path}},
        "remote_components": ["ejs:github"],
    }
