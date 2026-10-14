@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "PROJECT_ROOT=%PROJECT_DIR:~0,-1%"
cd /d "%PROJECT_DIR%"
set "PYTHONPATH="
set "PYTHONHOME="
set "PYTHONUSERBASE="
set "PYTHONNOUSERSITE=1"

if exist "build" (
    echo Refusing to overwrite existing build output: %CD%\build
    exit /b 1
)
if exist "dist" (
    echo Refusing to overwrite existing dist output: %CD%\dist
    exit /b 1
)
if exist ".release-venv" (
    echo Refusing to reuse existing release build environment: %CD%\.release-venv
    exit /b 1
)

C:\Windows\py.exe -3.12 -E -s "scripts\release_integrity.py" preflight --project-root "%PROJECT_ROOT%"
if errorlevel 1 exit /b %errorlevel%

C:\Windows\py.exe -3.12 -I -m venv .release-venv
if errorlevel 1 exit /b %errorlevel%

".release-venv\Scripts\python.exe" -I -m pip install --require-hashes -r requirements\bootstrap.lock
if errorlevel 1 exit /b %errorlevel%
".release-venv\Scripts\python.exe" -I -m pip install --require-hashes -r requirements-build.txt
if errorlevel 1 exit /b %errorlevel%
".release-venv\Scripts\python.exe" -I -m pip install --no-deps --no-build-isolation -e .
if errorlevel 1 exit /b %errorlevel%
".release-venv\Scripts\python.exe" -E -s "scripts\check_dependency_locks.py"
if errorlevel 1 exit /b %errorlevel%

".release-venv\Scripts\python.exe" -E -s "scripts\release_integrity.py" preflight --project-root "%PROJECT_ROOT%"
if errorlevel 1 exit /b %errorlevel%

".release-venv\Scripts\python.exe" -E -s "scripts\check_ffmpeg_artifact.py" "ffmpeg\ffmpeg.exe"
if errorlevel 1 exit /b %errorlevel%

".release-venv\Scripts\python.exe" -E -s "scripts\bundle_build_receipt.py" begin --project-root "%PROJECT_ROOT%" --output "build\ytsd-bundle-build-start.json"
if errorlevel 1 exit /b %errorlevel%

echo Restricting PyInstaller PATH to approved Python and Windows runtime directories.
set "PYINSTALLER_PATH="
for /f "delims=" %%P in ('""%PROJECT_DIR%.release-venv\Scripts\python.exe" -E -s "%PROJECT_DIR%scripts\sanitize_pyinstaller_path.py""') do set "PYINSTALLER_PATH=%%P"
if not defined PYINSTALLER_PATH (
    echo Failed to construct a sanitized PyInstaller PATH.
    exit /b 1
)
set "RELEASE_ORIGINAL_PATH=%PATH%"
set "PATH=%PYINSTALLER_PATH%"
set "PYINSTALLER_PATH="

".release-venv\Scripts\python.exe" -I -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --name YouTubeSimpleDownloader ^
    --paths src ^
    --additional-hooks-dir hooks ^
    --icon "src\ytsimpledownloader\assets\app_icon.ico" ^
    --add-data "src\ytsimpledownloader\assets\app_icon.ico;ytsimpledownloader\assets" ^
    --collect-all yt_dlp ^
    --add-binary "ffmpeg\ffmpeg.exe;ffmpeg" ^
    run_app.py

if errorlevel 1 exit /b %errorlevel%

".release-venv\Scripts\python.exe" -E -s "scripts\check_packaged_qt_runtime.py" "dist\YouTubeSimpleDownloader\_internal"
if errorlevel 1 exit /b %errorlevel%

".release-venv\Scripts\python.exe" -E -s "scripts\check_bundle_sources.py" --project-root "%PROJECT_ROOT%" --dist-dir "dist\YouTubeSimpleDownloader" --toc "build\YouTubeSimpleDownloader\COLLECT-00.toc"
if errorlevel 1 exit /b %errorlevel%

set "PATH=%RELEASE_ORIGINAL_PATH%"
set "RELEASE_ORIGINAL_PATH="

powershell.exe -NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "scripts\sign_release_executable.ps1" -Mode Sign -Path "dist\YouTubeSimpleDownloader\YouTubeSimpleDownloader.exe"
if errorlevel 1 exit /b %errorlevel%

".release-venv\Scripts\python.exe" -E -s "scripts\bundle_build_receipt.py" finish --project-root "%PROJECT_ROOT%" --start-record "build\ytsd-bundle-build-start.json" --dist-dir "dist\YouTubeSimpleDownloader" --output "build\ytsd-bundle-build.json"
if errorlevel 1 exit /b %errorlevel%

echo.
echo Built: %CD%\dist\YouTubeSimpleDownloader\YouTubeSimpleDownloader.exe
endlocal
