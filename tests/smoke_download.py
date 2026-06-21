from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(PROJECT_SRC))

from ytsimpledownloader.downloader import SingleVideoDownloader
from ytsimpledownloader.paths import DEFAULT_DOWNLOAD_DIR, ensure_default_dirs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test one or more YouTube URL downloads.")
    parser.add_argument("urls", nargs="+", help="One or more public YouTube video URLs")
    parser.add_argument("--mode", choices=["mp3", "mp4", "both"], default="mp3")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DOWNLOAD_DIR)
    parser.add_argument("--test-seconds", type=int, help="Download only the first N seconds for a faster smoke test.")
    parser.add_argument("--mp3-quality", choices=["128", "192", "256", "320"], default="192")
    parser.add_argument("--mp4-quality", choices=["best", "1080", "720", "480"], default="best")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_default_dirs()

    downloader = SingleVideoDownloader(
        args.output_dir,
        progress_callback=print,
        test_seconds=args.test_seconds,
        mp3_quality=args.mp3_quality,
        mp4_quality=args.mp4_quality,
    )
    all_results = []
    failures = []
    for index, url in enumerate(args.urls, start=1):
        print(f"Downloading {index}/{len(args.urls)}: {url}")
        try:
            all_results.extend(downloader.download(url, args.mode))
        except Exception as exc:
            failures.append((url, exc))
            print(f"Failed: {url}")
            print(exc)

    print()
    print("Output files:")
    for result in all_results:
        exists = "exists" if result.path.exists() else "missing"
        print(f"- {result.mode.upper()}: {result.path} [{exists}]")

    missing = [result.path for result in all_results if not result.path.exists()]
    if failures:
        print()
        print("Failures:")
        for url, exc in failures:
            print(f"- {url}: {exc}")
    return 1 if missing or failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
