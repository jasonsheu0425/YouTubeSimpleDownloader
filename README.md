# YouTube Simple Downloader

Download one or more public YouTube video URLs as MP3, MP4, or both.

## Features

- Single public YouTube video URL, or multiple video URLs pasted one per line.
- Preview title, channel, duration, thumbnail, and expected MP3/MP4 paths before download when a single URL is entered.
- Batch mode downloads multiple URLs sequentially and continues after individual URL failures.
- Download MP3, MP4, or MP3 + MP4.
- Choose MP3 quality: 128K, 192K, 256K, or 320K.
- Choose MP4 quality: Best, 1080p, 720p, or 480p.
- MP4 is merged to an `.mp4` output when needed.
- Shows download percent, speed, ETA, and a progress bar.
- If an output file already exists, choose overwrite, skip, or auto-number.
- Result list supports opening the file, copying the path, and showing the file in Explorer.
- Keeps a local download history.
- Supports Traditional Chinese and English UI.
- Can play a completion notification when downloads finish.
- Includes one-click clear URL and clear status buttons.
- Remembers the last output folder, download mode, quality settings, language, notification setting, and window size.
- Uses `imageio-ffmpeg` to provide FFmpeg without a separate external FFmpeg install.

## Setup

```powershell
cd E:\YouTubeSimpleDownloader
C:\Windows\py.exe -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

## Run GUI

```powershell
.\.venv\Scripts\python.exe -m ytsimpledownloader.app
```

Paste one URL to see a preview, or paste multiple URLs one per line for batch download.

## CLI Smoke Test

```powershell
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode mp3
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode mp4
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode both
```

For a faster technical check, add `--test-seconds 10`.

Quality options:

```powershell
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode mp3 --mp3-quality 128
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode mp4 --mp4-quality 720
```

Default output folder:

```text
E:\YouTubeSimpleDownloader\downloads
```

## Build EXE

```powershell
.\build_exe.bat
```

Expected EXE:

```text
E:\YouTubeSimpleDownloader\dist\YouTubeSimpleDownloader\YouTubeSimpleDownloader.exe
```
