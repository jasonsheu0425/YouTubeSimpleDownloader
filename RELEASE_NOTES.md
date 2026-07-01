# YouTube Simple Downloader v0.8.0

## v0.8.0 - Configurable Audio and Video Formats

- Added audio format selection: MP3, M4A, OPUS, WAV, and FLAC.
- Added video format selection: MP4, MKV, and WEBM.
- Preview output paths now follow the selected audio/video formats.
- Download history records selected audio/video formats and skip logic checks the exact requested format.
- Result rows display the real output format based on the generated file extension.
- Smoke test CLI now supports `--audio-format` and `--video-format`.

## v0.6.2 - UI and Queue Flow

Patch release improving the desktop interface and correcting direct-download and queue behavior.

## Changes

- Reorganized the interface into numbered sections for input, settings, preview, queue, progress, and results/history/errors.
- Added a dark desktop theme, clearer primary actions, result tabs, a URL paste button, and a version/status footer.
- A single video URL now downloads directly without being inserted into the queue.
- Multiple URLs still create a download queue automatically.
- Duplicate videos are no longer added to the queue more than once.
- Pressing Start again no longer resets completed queue items back to Waiting when the requested output already exists.
- Changing from MP3 to MP4, or requesting a missing format in MP3 + MP4 mode, queues only the missing output.
- Completed items are filtered before the worker starts, avoiding unnecessary repeated checks and numbered duplicate files.

## v0.6.1 Features

Patch release adding an explicit resume setting.

## Features

- Added a setting to keep unfinished files and let yt-dlp resume downloads when possible.
- The downloader now explicitly enables yt-dlp continue mode and `.part` temporary files when resume is enabled.
- Cancelling a download leaves the queue item as Canceled, so the same task can be run again with the same output template.
- The status area explains the limitation: MP3 audio download can often resume, but FFmpeg post-processing may need to run again after interruption.
- CLI smoke test now supports `--no-resume`.

## v0.6.0 Features

- Added folder grouping options: no grouping, by download mode, by channel, by date, or by playlist.
- Playlist grouping creates a folder named after the playlist and stores that playlist's downloads inside it.
- Single video downloads stay in the selected output folder when playlist grouping is selected.
- Added filename format options: title, channel - title, playlist number - title, upload date - title, and custom.
- Previewed MP3/MP4 output paths now use the same output template as the actual download path.
- CLI smoke test now supports folder and filename rule options.

## v0.5.1 Features

- Added Retry Failed for queue items that end in the Failed state.
- Added an Auto Retry setting: do not retry, retry 1 time, retry 2 times, or retry 3 times.
- Queue tasks now track attempts, max retries, last error, and friendly error category.
- Failed downloads stay in the queue as Failed instead of only being listed in the result area.
- Expanded friendly error categories for unavailable/region-blocked videos, sign-in required, network errors, YouTube temporary limits, FFmpeg failures, file permission errors, and filename/path problems.

## v0.5.0 Features

- Added a visible download queue.
- Added Add to Queue, Move Up, Move Down, Remove, and Clear Queue actions.
- Playlist URLs can be expanded into queue items before downloading.
- Queue items update status while downloading: Waiting, Downloading, Completed, Failed, Skipped, or Canceled.

## v0.4.1 Features

- Added a custom application icon for the EXE, GUI window, installer, Start Menu shortcut, and optional desktop shortcut.

## v0.4.0 Features

- Added a "skip previously downloaded videos" option, enabled by default.
- Playlist repeat runs now compare video IDs against local download history and only download missing MP3/MP4 formats.
- If a video already has MP3 but not MP4, MP3 + MP4 mode only downloads the missing MP4.

## v0.3.0 Features

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
