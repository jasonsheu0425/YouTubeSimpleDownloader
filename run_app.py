from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from ytsimpledownloader.downloader import SingleVideoDownloader
from ytsimpledownloader.paths import DEFAULT_DOWNLOAD_DIR, ensure_default_dirs


def smoke_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-url", required=True)
    parser.add_argument("--mode", choices=["mp3", "mp4", "both"], default="mp3")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DOWNLOAD_DIR)
    parser.add_argument("--test-seconds", type=int)
    parser.add_argument("--smoke-log", type=Path)
    parser.add_argument("--mp3-quality", choices=["128", "192", "256", "320"], default="192")
    parser.add_argument("--mp4-quality", choices=["best", "1080", "720", "480"], default="best")
    args = parser.parse_args(argv)

    def log(message: str) -> None:
        if args.smoke_log:
            args.smoke_log.parent.mkdir(parents=True, exist_ok=True)
            with args.smoke_log.open("a", encoding="utf-8") as handle:
                handle.write(message + "\n")

    try:
        ensure_default_dirs()
        log(f"Starting smoke: mode={args.mode} output_dir={args.output_dir}")
        downloader = SingleVideoDownloader(
            args.output_dir,
            progress_callback=log,
            test_seconds=args.test_seconds,
            mp3_quality=args.mp3_quality,
            mp4_quality=args.mp4_quality,
        )
        log(f"FFmpeg: {downloader.ffmpeg_path}")
        results = downloader.download(args.smoke_url, args.mode)
        for result in results:
            log(f"Result: {result.mode} {result.path} exists={result.path.exists()}")
        return 0 if all(result.path.exists() for result in results) else 1
    except Exception:
        log(traceback.format_exc())
        return 1


if __name__ == "__main__":
    if "--smoke-url" in sys.argv:
        raise SystemExit(smoke_main(sys.argv[1:]))

    from ytsimpledownloader.app import main

    raise SystemExit(main())
