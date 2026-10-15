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
    assert builder.count('$ReceiptScript verify --project-root $ProjectDir --dist-dir $PayloadDir') >= 2


def test_bundle_receipt_and_signing_order_is_fixed() -> None:
    batch = (INSTALLER_BUILD_SCRIPT.parent / "build_exe.bat").read_text(encoding="utf-8")
    builder = installer_builder_text()
    assert 'set "PYTHONPATH="' in batch
    assert 'set "PYTHONHOME="' in batch
    assert 'set "PYTHONNOUSERSITE=1"' in batch
    begin = batch.index('bundle_build_receipt.py" begin')
    save_path = batch.index('set "RELEASE_ORIGINAL_PATH=%PATH%"')
    sanitize_path = batch.index('set "PATH=%PYINSTALLER_PATH%"')
    pyinstaller = batch.index('-m PyInstaller')
    qt_gate = batch.index(r'scripts\check_packaged_qt_runtime.py')
    native_gate = batch.index(r'scripts\check_bundle_sources.py')
    restore_path = batch.index('set "PATH=%RELEASE_ORIGINAL_PATH%"')
    sign = batch.index('sign_release_executable.ps1" -Mode Sign')
    finish = batch.index('bundle_build_receipt.py" finish')
    assert begin < save_path < sanitize_path < pyinstaller < qt_gate < native_gate < restore_path < sign < finish
    assert builder.index('$ReceiptScript verify --project-root $ProjectDir --dist-dir $DistDir') < builder.index('Get-ChildItem -LiteralPath $DistDir -Force')
    assert builder.index('$ReceiptScript verify --project-root $ProjectDir --dist-dir $PayloadDir') < builder.index('$compilerProcess.Start()')
    assert builder.index('$null = Assert-ValidSignature (Join-Path $PayloadDir "$AppName.exe")') < builder.index('$compilerProcess.Start()')
    assert builder.count('Set-AuthenticodeSignature') == 1
    assert 'Set-AuthenticodeSignature -LiteralPath $StagedInstaller' in builder
    assert 'Get-AuthenticodeSignature -LiteralPath $Path' in builder
    signer = (INSTALLER_BUILD_SCRIPT.parent / "scripts/sign_release_executable.ps1").read_text(encoding="utf-8")
    assert 'Set-AuthenticodeSignature -LiteralPath $resolved' in signer
    assert 'Get-AuthenticodeSignature -LiteralPath $resolved' in signer
    assert '$SignerScript -Mode Verify -Path $AppExe' in builder
    assert '$null = Assert-ValidSignature (Join-Path $PayloadDir "$AppName.exe")' in builder
