@echo off
setlocal

cd /d E:\YouTubeSimpleDownloader

if not exist ".venv\Scripts\python.exe" (
    C:\Windows\py.exe -3.12 -m venv .venv
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
".venv\Scripts\python.exe" -m pip install -e .

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

".venv\Scripts\pyinstaller.exe" ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --name YouTubeSimpleDownloader ^
    --paths src ^
    --collect-all imageio_ffmpeg ^
    --collect-all yt_dlp ^
    --add-binary "ffmpeg\ffmpeg.exe;ffmpeg" ^
    run_app.py

if errorlevel 1 exit /b %errorlevel%

echo.
echo Built: E:\YouTubeSimpleDownloader\dist\YouTubeSimpleDownloader\YouTubeSimpleDownloader.exe
endlocal
