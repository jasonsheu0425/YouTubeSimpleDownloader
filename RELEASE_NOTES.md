# YouTube Simple Downloader v0.3.0

Feature release adding YouTube playlist URL support.

## Features

- Added playlist URL support for public or unlisted YouTube playlists that do not require login.
- Playlist URLs are expanded into individual video downloads and processed through the existing batch queue.
- Private playlists and login/cookie-only playlists remain unsupported.

## v0.2.1 Fixes

- Fixed startup failure on computers that do not have an `E:` drive.
- Moved app data, history, and FFmpeg cache to the user's local app data folder.
- Changed the default download folder to the user's Downloads folder.

## v0.2.0 Features

- Added multi-URL batch mode. Paste multiple YouTube video URLs, one per line, and download them sequentially.
- Batch mode continues after individual URL failures and records failed items in the result list.
- Batch mode auto-numbers existing output files to avoid overwriting earlier downloads.

## v0.1.1 Fixes

- Fixed a crash that could happen after pressing Cancel while a download worker was still shutting down.

## v0.1.0 Features

- Single public YouTube video URL download.
- MP3, MP4, or MP3 + MP4 modes.
- MP3 quality: 128K, 192K, 256K, 320K.
- MP4 quality: Best, 1080p, 720p, 480p.
- Video preview with title, channel, duration, thumbnail, and expected output paths.
- Traditional Chinese and English UI.
- Download progress, ETA, result actions, and history.
- Inno Setup installer with selectable install location, optional desktop shortcut, Start Menu shortcut, and uninstall entry.

## Notes

This release is self-signed for testing and friend-to-friend sharing. Windows may still show SmartScreen or trust warnings because this is not a paid trusted code-signing certificate.
