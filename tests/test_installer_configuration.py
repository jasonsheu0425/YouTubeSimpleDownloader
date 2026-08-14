from __future__ import annotations

from pathlib import Path


INSTALLER_SCRIPT = Path(__file__).resolve().parents[1] / "installer" / "YouTubeSimpleDownloader.iss"
INSTALLER_BUILD_SCRIPT = Path(__file__).resolve().parents[1] / "build_inno_installer.ps1"


def installer_sources() -> list[list[str]]:
    return [
        path.read_text(encoding="utf-8-sig").splitlines()
        for path in (INSTALLER_SCRIPT, INSTALLER_BUILD_SCRIPT)
    ]


def test_installer_remains_a_per_user_install() -> None:
    installer_lines, build_lines = installer_sources()

    assert "PrivilegesRequired=lowest" in installer_lines
    assert "PrivilegesRequired=lowest" in build_lines
    assert r"DefaultDirName={localappdata}\Programs\YouTubeSimpleDownloader" in installer_lines
    assert r"DefaultDirName={localappdata}\Programs\$AppName" in build_lines


def test_desktop_shortcut_is_optional_and_uses_current_user_desktop() -> None:
    for lines in installer_sources():
        task_line = next(line for line in lines if line.startswith('Name: "desktopicon";'))
        shortcut_line = next(line for line in lines if "Tasks: desktopicon" in line)

        assert "Flags: unchecked" in task_line
        assert r'Name: "{userdesktop}\{#MyAppName}"' in shortcut_line
        assert "{commondesktop}" not in shortcut_line


def test_start_menu_shortcut_is_unchanged() -> None:
    for lines in installer_sources():
        assert (
            r'Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"'
            in lines
        )
