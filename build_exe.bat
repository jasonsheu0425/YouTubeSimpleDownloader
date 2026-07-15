@echo off
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

if not exist ".venv\Scripts\python.exe" (
    C:\Windows\py.exe -3.12 -m venv .venv
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
".venv\Scripts\python.exe" -m pip install -e .

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

".venv\Scripts\pyinstaller.exe" ^
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

echo.
echo Built: %CD%\dist\YouTubeSimpleDownloader\YouTubeSimpleDownloader.exe
endlocal
