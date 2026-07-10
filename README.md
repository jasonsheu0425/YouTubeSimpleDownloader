# YouTube Simple Downloader

Download public YouTube video URLs or playlist URLs as audio, video, or both.

## Features

- Single public YouTube video URL, or multiple video URLs pasted one per line.
- Public or unlisted YouTube playlist URLs that do not require login.
- Playlist repeat runs can skip videos that already exist in the local download history, so the app only downloads newly added videos.
- Preview title, channel, duration, thumbnail, and expected audio/video output paths before download when a single URL is entered.
- Download queue supports adding URLs, expanding playlists, moving items up/down, removing items, and clearing the queue before starting.
- Failed queue items can be retried without re-running completed items.
- Optional automatic retries: none, 1, 2, or 3 retries per item.
- Resume setting keeps unfinished `.part` files and lets yt-dlp continue partial downloads when possible.
- Automatic folder grouping: no grouping, by download mode, by channel, by date, or by playlist.
- Playlist grouping creates one folder per playlist, while single videos stay in the selected output folder.
- Filename formats: title, channel - title, playlist number - title, upload date - title, or custom.
- Batch mode downloads multiple URLs sequentially and continues after individual URL failures.
- Playlist mode expands videos into the download queue before downloading.
- Download audio, video, or audio + video.
- Audio formats: MP3, M4A, OPUS, WAV, FLAC.
- Video formats: MP4, MKV, WEBM.
- Video output and transcoding:
  - Prefer downloading compatible H.264 MP4 formats.
  - Convert videos to H.264 MP4 after download.
  - osu! compatible video preset.
  - Resolution, FPS, quality, CRF, transcode speed, and audio removal controls.
  - Batch convert local video files.
  - View real container, codec, resolution, FPS, pixel format, and audio information when probing/transcoding.
- Choose MP3 quality: 128K, 192K, 256K, or 320K.
- Choose MP4 quality: Best, 1080p, 720p, or 480p.
- MP4 remains the recommended default video format; MKV and WEBM are available when needed.
- Shows download percent, speed, ETA, and a progress bar.
- If an output file already exists, choose overwrite, skip, or auto-number.
- Result list supports opening the file, copying the path, and showing the file in Explorer.
- Keeps a local download history.
- Supports Traditional Chinese and English UI.
- Can play a completion notification when downloads finish.
- Includes one-click clear URL and clear status buttons.
- Remembers the last output folder, download mode, audio/video formats, quality settings, output naming settings, auto retry setting, language, notification setting, and window size.
- Uses `imageio-ffmpeg` to provide FFmpeg without a separate external FFmpeg install.

MP4 is a container. A `.mp4` file may contain H.264, H.265, AV1, or other codecs. For maximum compatibility, use H.264 MP4 with `yuv420p`.

Resume note: partial audio/video downloads can usually continue from `.part` files. If an audio download was already in the FFmpeg conversion stage when interrupted, the conversion step may need to run again.

## Setup

```powershell
cd E:\YouTubeSimpleDownloader
C:\Windows\py.exe -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

For local development tests:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

## Run GUI

```powershell
.\.venv\Scripts\python.exe -m ytsimpledownloader.app
```

Paste one video URL to see a preview, add video or playlist URLs to the queue, reorder the queue if needed, then start the download.

## CLI Smoke Test

`smoke_download.py` can test both online YouTube downloads and local FFmpeg-only video conversion.
Commands that pass a YouTube URL require network access and a public video/playlist that does not require login.
Commands that use `--local-video` or `--probe` can run without YouTube access after FFmpeg is available.

```powershell
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode mp3
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode mp4
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode both
```

For a faster technical check, add `--test-seconds 10`.

Output naming smoke options:

```powershell
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/playlist?list=PLAYLIST_ID" --mode mp3 --folder-rule playlist --filename-rule playlist_index_title
```

Disable resume for a smoke test:

```powershell
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode mp3 --no-resume
```

Quality options:

```powershell
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode mp3 --mp3-quality 128
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode mp4 --mp4-quality 720
```

Format options:

```powershell
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode mp3 --audio-format flac
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode mp4 --video-format mkv
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode both --audio-format opus --video-format webm
```

Video transcoding smoke options:

```powershell
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode mp4 --video-processing transcode --video-format mp4 --video-codec h264 --resolution 720 --fps 30 --video-audio remove --test-seconds 5
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode mp4 --video-processing osu --fps 60 --test-seconds 5
.\.venv\Scripts\python.exe tests\smoke_download.py --local-video "C:\path\to\input.mp4" --video-processing transcode --video-format mp4 --video-codec h264
.\.venv\Scripts\python.exe tests\smoke_download.py --probe "C:\path\to\input.mp4"
```

Pytest includes local short-video checks that generate a tiny test file with FFmpeg, then verify media probe, H.264 MP4 conversion, osu! compatible output, auto-number output naming, and friendly transcode error messages.

Default output folder:

```text
%USERPROFILE%\Downloads\YouTubeSimpleDownloader
```

## Build EXE

```powershell
.\build_exe.bat
```

Expected EXE:

```text
E:\YouTubeSimpleDownloader\dist\YouTubeSimpleDownloader\YouTubeSimpleDownloader.exe
```

## Verify Installer SHA-256

After downloading a release installer, compare its SHA-256 with the value published in the GitHub Release notes:

```powershell
Get-FileHash .\YouTubeSimpleDownloader_Setup_v0.9.1-inno-self-signed.exe -Algorithm SHA256
```
