from __future__ import annotations

from pathlib import Path


INSTALLER_SCRIPT = Path(__file__).resolve().parents[1] / "installer" / "YouTubeSimpleDownloader.iss"
INSTALLER_BUILD_SCRIPT = Path(__file__).resolve().parents[1] / "build_inno_installer.ps1"


def installer_template_lines() -> list[str]:
    return INSTALLER_SCRIPT.read_text(encoding="utf-8-sig").splitlines()


def installer_builder_text() -> str:
    return INSTALLER_BUILD_SCRIPT.read_text(encoding="utf-8-sig")


def test_installer_remains_a_per_user_install() -> None:
    installer_lines = installer_template_lines()

    assert "PrivilegesRequired=lowest" in installer_lines
    assert r"DefaultDirName={localappdata}\Programs\YouTubeSimpleDownloader" in installer_lines
    assert "OutputBaseFilename=YouTubeSimpleDownloader_Setup_v{#MyAppVersion}-inno-self-signed" in installer_lines


def test_desktop_shortcut_is_optional_and_uses_current_user_desktop() -> None:
    lines = installer_template_lines()
    task_line = next(line for line in lines if line.startswith('Name: "desktopicon";'))
    shortcut_line = next(line for line in lines if "Tasks: desktopicon" in line)

    assert "Flags: unchecked" in task_line
    assert r'Name: "{userdesktop}\{#MyAppName}"' in shortcut_line
    assert "{commondesktop}" not in shortcut_line


def test_start_menu_shortcut_is_unchanged() -> None:
    assert (
        r'Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"'
        in installer_template_lines()
    )


def test_installer_builder_expands_a_staged_template_without_mutating_it() -> None:
    template = installer_template_lines()
    builder = installer_builder_text()

    assert any(r'Source: "{#MyPayloadDir}\*"' in line for line in template)
    assert '$PayloadDir = Join-Path $StagingRoot "payload"' in builder
    assert '$template = $template.Replace("@PAYLOAD_DIR@", $PayloadDir)' in builder
    assert '$template = Get-Content -Raw -LiteralPath $TemplatePath' in builder
    assert '$StagedIss = Join-Path $StagingRoot' in builder
    assert 'Set-Content -LiteralPath $StagedIss' in builder
    assert 'Set-Content -LiteralPath $TemplatePath' not in builder
    assert 'inventory-hash --dist-dir $PayloadDir' in builder
