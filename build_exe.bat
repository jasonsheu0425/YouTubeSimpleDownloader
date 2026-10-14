@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
cd /d "%PROJECT_DIR%"

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

C:\Windows\py.exe -3.12 "scripts\release_integrity.py" preflight --project-root "%PROJECT_DIR%"
if errorlevel 1 exit /b %errorlevel%

C:\Windows\py.exe -3.12 -m venv .release-venv
if errorlevel 1 exit /b %errorlevel%

".release-venv\Scripts\python.exe" -m pip install --require-hashes -r requirements\bootstrap.lock
if errorlevel 1 exit /b %errorlevel%
".release-venv\Scripts\python.exe" -m pip install --require-hashes -r requirements-build.txt
if errorlevel 1 exit /b %errorlevel%
".release-venv\Scripts\python.exe" -m pip install --no-deps --no-build-isolation -e .
if errorlevel 1 exit /b %errorlevel%
".release-venv\Scripts\python.exe" "scripts\check_dependency_locks.py"
if errorlevel 1 exit /b %errorlevel%

".release-venv\Scripts\python.exe" "scripts\release_integrity.py" preflight --project-root "%PROJECT_DIR%"
if errorlevel 1 exit /b %errorlevel%

".release-venv\Scripts\python.exe" "scripts\check_ffmpeg_artifact.py" "ffmpeg\ffmpeg.exe"
if errorlevel 1 exit /b %errorlevel%

echo Sanitizing PyInstaller PATH: excluding ambient Codex and Poppler runtimes.
set "PYINSTALLER_PATH="
for /f "delims=" %%P in ('""%PROJECT_DIR%.release-venv\Scripts\python.exe" "%PROJECT_DIR%scripts\sanitize_pyinstaller_path.py""') do set "PYINSTALLER_PATH=%%P"
if not defined PYINSTALLER_PATH (
    echo Failed to construct a sanitized PyInstaller PATH.
    exit /b 1
)
set "PATH=%PYINSTALLER_PATH%"
set "PYINSTALLER_PATH="

".release-venv\Scripts\pyinstaller.exe" ^
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

".release-venv\Scripts\python.exe" "scripts\check_packaged_qt_runtime.py" "dist\YouTubeSimpleDownloader\_internal"
if errorlevel 1 exit /b %errorlevel%

echo.
echo Built: %CD%\dist\YouTubeSimpleDownloader\YouTubeSimpleDownloader.exe
endlocal
