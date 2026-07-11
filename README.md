# YouTube Simple Downloader

A Windows desktop application for saving public YouTube videos and playlists as audio, video, or both. It is built with PySide6, yt-dlp, imageio-ffmpeg, PyInstaller, and Inno Setup.

## Download the latest release

Download the installer from the [GitHub Releases page](https://github.com/jasonsheu0425/YouTubeSimpleDownloader/releases). The normal installer is:

```text
YouTubeSimpleDownloader_Setup_v0.9.2-inno-self-signed.exe
```

The installer defaults to the per-user location below and shows the destination page on every run. It does not reuse an older install folder automatically.

```text
%LOCALAPPDATA%\Programs\YouTubeSimpleDownloader
```

It creates a Start Menu shortcut and can create a desktop shortcut. No `E:` drive or development checkout is required to run the installed app.

## Features

- Single public YouTube video URL, or multiple video URLs pasted one per line.
- Public or unlisted playlists that do not require login.
- Queue management: add, reorder, remove, clear, retry failed items, and skip completed outputs.
- Resume partially downloaded files when possible.
- Download audio, video, or audio + video.
- Audio formats: MP3, M4A, OPUS, WAV, and FLAC.
- Video formats: MP4, MKV, and WEBM.
- MP3 quality: 128K, 192K, 256K, and 320K.
- Video quality: Best, 1080p, 720p, and 480p.
- Folder grouping and filename formats, including playlist folders.
- Preview title, channel, duration, thumbnail, and expected output paths.
- Download history, result actions, and Traditional Chinese / English UI.
- H.264 MP4 transcoding, an osu! compatible video preset, local video batch conversion, and media probing.

MP4 is a container, not a codec guarantee. A `.mp4` file can contain H.264, H.265, AV1, or another codec. Choose H.264 MP4 with `yuv420p` when maximum compatibility matters.

The osu! preset outputs an MP4 with H.264, `yuv420p`, a maximum height of 720p without upscaling, no audio, `faststart`, and an `_osu_h264` filename suffix.

## Scope and responsible use

Use this application only for public or unlisted videos that you have the right to save. You are responsible for complying with YouTube's terms and applicable law.

The application deliberately does not support:

- Login or cookies.
- Private, paid, members-only, or DRM-protected content.
- Bypassing access restrictions.

## Windows warning and self-signed installer

The release installer is self-signed for testing and friend-to-friend sharing. Windows SmartScreen may show a warning because the project does not use a paid trusted code-signing certificate. The GitHub Release includes a SHA-256 value and the exported public test certificate for verification.

Verify an installer after downloading it:

```powershell
Get-FileHash .\YouTubeSimpleDownloader_Setup_v0.9.2-inno-self-signed.exe -Algorithm SHA256
```

Compare the reported hash with the value in the matching GitHub Release.

## Basic use

1. Paste one video URL to load its preview, or paste multiple URLs one per line.
2. Choose audio, video, or audio + video, then select the desired formats and quality.
3. Select an output folder and choose folder or filename rules if needed.
4. Start downloading. Multiple URLs and playlists are expanded into the queue.
5. Open the file, copy its path, or reveal it in Explorer from the result list.

For a playlist that changes over time, leave **Skip previously downloaded videos** enabled. Later runs check the recorded output formats and download only missing videos or formats.

## Developer setup

Clone the repository instead of relying on a machine-specific path:

```powershell
git clone https://github.com/jasonsheu0425/YouTubeSimpleDownloader.git
cd YouTubeSimpleDownloader
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

Run the GUI:

```powershell
.\.venv\Scripts\python.exe -m ytsimpledownloader.app
```

`requirements.txt` contains runtime dependencies. `requirements-build.txt` contains PyInstaller, and `requirements-dev.txt` contains test-only dependencies.

## Tests

Install development dependencies and run the local regression tests:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m compileall src tests
.\.venv\Scripts\python.exe tests\smoke_download.py --help
```

Pytest creates a short local video with FFmpeg and verifies media probing, H.264 MP4 conversion, the osu! preset, output auto-numbering, and friendly conversion errors. It does not download from YouTube.

`smoke_download.py` supports both local FFmpeg-only checks and online YouTube checks. Commands with URLs require network access and a public video or playlist that does not need login.

```powershell
# Online YouTube checks
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode mp3 --test-seconds 10
.\.venv\Scripts\python.exe tests\smoke_download.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode both --audio-format flac --video-format mkv --test-seconds 10

# Local checks, no YouTube access required
.\.venv\Scripts\python.exe tests\smoke_download.py --probe "C:\path\to\input.mp4"
.\.venv\Scripts\python.exe tests\smoke_download.py --local-video "C:\path\to\input.mp4" --video-processing transcode --video-format mp4 --video-codec h264
.\.venv\Scripts\python.exe tests\smoke_download.py --local-video "C:\path\to\input.mp4" --video-processing osu --fps 60
```

## Build

Build the Windows application bundle:

```powershell
.\build_exe.bat
```

Expected executable:

```text
dist\YouTubeSimpleDownloader\YouTubeSimpleDownloader.exe
```

Build the self-signed Inno Setup installer after the EXE bundle is ready:

```powershell
.\build_inno_installer.ps1
```

Expected installer:

```text
release\YouTubeSimpleDownloader_Setup_v0.9.2-inno-self-signed.exe
```

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and contribution guidance. See [SECURITY.md](SECURITY.md) for how to report a security issue without exposing URLs, cookies, tokens, or other private information.

## License

This project is licensed under the [MIT License](LICENSE).
