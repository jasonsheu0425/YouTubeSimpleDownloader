from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(PROJECT_SRC))

from ytsimpledownloader.downloader import AUDIO_FORMATS, VIDEO_FORMATS, OutputOptions, SingleVideoDownloader, is_playlist_url
from ytsimpledownloader.paths import DEFAULT_DOWNLOAD_DIR, ensure_default_dirs


def safe_print(message: object = "") -> None:
    text = str(message)
    encoding = sys.stdout.encoding or "utf-8"
    print(text.encode(encoding, errors="replace").decode(encoding))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test one or more YouTube URL downloads.")
    parser.add_argument("urls", nargs="+", help="One or more public YouTube video URLs")
    parser.add_argument("--mode", choices=["mp3", "mp4", "both"], default="mp3")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DOWNLOAD_DIR)
    parser.add_argument("--test-seconds", type=int, help="Download only the first N seconds for a faster smoke test.")
    parser.add_argument("--audio-format", choices=AUDIO_FORMATS, default="mp3")
    parser.add_argument("--video-format", choices=VIDEO_FORMATS, default="mp4")
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


def main() -> int:
    args = parse_args()
    ensure_default_dirs()

    downloader = SingleVideoDownloader(
        args.output_dir,
        progress_callback=safe_print,
        test_seconds=args.test_seconds,
        audio_format=args.audio_format,
        video_format=args.video_format,
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
