from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(PROJECT_SRC))

from ytsimpledownloader.downloader import AUDIO_FORMATS, VIDEO_FORMATS, OutputOptions, SingleVideoDownloader, is_playlist_url
from ytsimpledownloader.media_probe import probe_media
from ytsimpledownloader.paths import DEFAULT_DOWNLOAD_DIR, ensure_default_dirs
from ytsimpledownloader.transcoder import VideoTranscodeOptions, VideoTranscoder


def safe_print(message: object = "") -> None:
    text = str(message)
    encoding = sys.stdout.encoding or "utf-8"
    print(text.encode(encoding, errors="replace").decode(encoding))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test one or more YouTube URL downloads.")
    parser.add_argument("urls", nargs="*", help="One or more public YouTube video URLs")
    parser.add_argument("--mode", choices=["mp3", "mp4", "both"], default="mp3")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DOWNLOAD_DIR)
    parser.add_argument("--test-seconds", type=int, help="Download only the first N seconds for a faster smoke test.")
    parser.add_argument("--audio-format", choices=AUDIO_FORMATS, default="mp3")
    parser.add_argument("--video-format", choices=VIDEO_FORMATS, default="mp4")
    parser.add_argument(
        "--video-processing",
        choices=["keep", "prefer_compatible", "transcode", "osu"],
        default="keep",
    )
    parser.add_argument("--video-codec", choices=["copy", "h264"], default="h264")
    parser.add_argument("--resolution", choices=["original", "2160", "1440", "1080", "720", "480"], default="original")
    parser.add_argument("--fps", choices=["original", "60", "30", "24"], default="original")
    parser.add_argument("--quality", choices=["high", "balanced", "small", "custom"], default="balanced")
    parser.add_argument("--crf", type=int, default=20)
    parser.add_argument("--transcode-speed", choices=["veryfast", "fast", "medium", "slow"], default="medium")
    parser.add_argument("--video-audio", choices=["keep", "remove"], default="keep")
    parser.add_argument("--local-video", action="append", type=Path, default=[], help="Transcode a local video file.")
    parser.add_argument("--probe", type=Path, help="Probe a local media file and print real format details.")
    parser.add_argument("--mp3-quality", choices=["128", "192", "256", "320"], default="192")
    parser.add_argument("--mp4-quality", choices=["best", "1080", "720", "480"], default="best")
    parser.add_argument("--folder-rule", choices=["none", "mode", "channel", "date", "playlist"], default="none")
    parser.add_argument(
        "--filename-rule",
        choices=["title", "channel_title", "playlist_index_title", "upload_date_title", "custom"],
        default="title",
    )
    parser.add_argument("--custom-template", default="")
    parser.add_argument("--no-resume", action="store_true", help="Disable yt-dlp resume/continue behavior.")
    return parser.parse_args()


def video_options_from_args(args: argparse.Namespace) -> VideoTranscodeOptions:
    if args.video_processing == "osu":
        return VideoTranscodeOptions.osu(args.fps if args.fps in {"30", "60"} else "60")
    return VideoTranscodeOptions(
        mode=args.video_processing,
        container=args.video_format,
        video_codec=args.video_codec,
        resolution=args.resolution,
        fps=args.fps,
        quality=args.quality,
        crf=args.crf,
        speed=args.transcode_speed,
        audio=args.video_audio,
        keep_original=True,
        suffix="_h264",
    ).normalized()


def main() -> int:
    args = parse_args()
    ensure_default_dirs()

    if args.probe:
        info = probe_media(args.probe, VideoTranscoder().ffmpeg_path)
        safe_print(info.summary())
        return 1 if info.error and not info.video_codec else 0

    if args.local_video:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        transcoder = VideoTranscoder(progress_callback=safe_print)
        failures = []
        results = []
        for path in args.local_video:
            try:
                result = transcoder.transcode(
                    path,
                    video_options_from_args(args),
                    output_dir=args.output_dir,
                    file_exists_action="number",
                )
            except Exception as exc:
                failures.append((path, exc))
                safe_print(f"Failed: {path}")
                safe_print(exc)
            else:
                results.append(result.path)
                safe_print(f"Output: {result.path}")
                safe_print(result.media_info.summary())
        missing = [path for path in results if not path.exists()]
        return 1 if failures or missing else 0

    if not args.urls:
        safe_print("At least one URL is required unless --local-video or --probe is used.")
        return 2

    downloader = SingleVideoDownloader(
        args.output_dir,
        progress_callback=safe_print,
        test_seconds=args.test_seconds,
        audio_format=args.audio_format,
        video_format=args.video_format,
        video_processing_options=video_options_from_args(args),
        mp3_quality=args.mp3_quality,
        mp4_quality=args.mp4_quality,
        output_options=OutputOptions(args.folder_rule, args.filename_rule, args.custom_template),
        resume_downloads=not args.no_resume,
    )
    all_results = []
    failures = []
    expanded_urls = []
    for url in args.urls:
        if is_playlist_url(url):
            safe_print(f"Reading playlist: {url}")
            try:
                playlist = downloader.fetch_playlist_info(url)
            except Exception as exc:
                failures.append((url, exc))
                safe_print(f"Failed: {url}")
                safe_print(exc)
            else:
                safe_print(f"Playlist loaded: {playlist.title} ({len(playlist.urls)} videos)")
                expanded_urls.extend((item_url, playlist.title, index) for index, item_url in enumerate(playlist.urls, 1))
        else:
            expanded_urls.append((url, "", None))

    for index, (url, playlist_title, playlist_index) in enumerate(expanded_urls, start=1):
        safe_print(f"Downloading {index}/{len(expanded_urls)}: {url}")
        try:
            all_results.extend(downloader.download(url, args.mode, playlist_title, playlist_index))
        except Exception as exc:
            failures.append((url, exc))
            safe_print(f"Failed: {url}")
            safe_print(exc)

    safe_print()
    safe_print("Output files:")
    for result in all_results:
        exists = "exists" if result.path.exists() else "missing"
        label = result.path.suffix.lower().lstrip(".").upper() or result.mode.upper()
        safe_print(f"- {label}: {result.path} [{exists}]")

    missing = [result.path for result in all_results if not result.path.exists()]
    wrong_suffixes = []
    expected_audio_suffix = f".{args.audio_format}"
    expected_video_suffix = f".{args.video_format}"
    for result in all_results:
        expected_suffix = expected_audio_suffix if result.mode == "mp3" else expected_video_suffix
        if result.path.suffix.lower() != expected_suffix:
            wrong_suffixes.append((result.path, expected_suffix))
    if failures:
        safe_print()
        safe_print("Failures:")
        for url, exc in failures:
            safe_print(f"- {url}: {exc}")
    if wrong_suffixes:
        safe_print()
        safe_print("Unexpected suffixes:")
        for path, expected_suffix in wrong_suffixes:
            safe_print(f"- {path} expected {expected_suffix}")
    return 1 if missing or failures or wrong_suffixes else 0


if __name__ == "__main__":
    raise SystemExit(main())
