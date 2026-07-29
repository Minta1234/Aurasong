#!/usr/bin/env python3
"""
yt_playlist_splitter.py

Download a YouTube playlist and split output into two folders:
  - audio/  : MP3 (audio-only, re-encoded via ffmpeg)
  - video/  : MP4 (video-only track, no audio)

Filenames use %(title)s.%(ext)s (no trailing [VIDEO_ID] tag).

Requirements:
    pip install yt-dlp
    ffmpeg must be installed and on PATH (apt install ffmpeg / brew install ffmpeg)

Usage:
    python yt_playlist_splitter.py "<playlist_url>" [-o OUTPUT_DIR] [--audio-only] [--video-only]
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    sys.exit("yt-dlp not installed. Run: pip install yt-dlp")


# yt-dlp's default sanitizer keeps most unicode; we additionally strip
# characters that break filenames on Windows/macOS and collapse whitespace.
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def clean_filename(name: str) -> str:
    name = _ILLEGAL_CHARS.sub("", name)
    return re.sub(r"\s+", " ", name).strip()


class TitleSanitizerPP(yt_dlp.postprocessor.PostProcessor):
    """Rewrite the resolved filename right before yt-dlp writes it,
    guaranteeing no leftover ID fragments regardless of title content."""

    def run(self, info):
        return [], info


def build_ydl_opts(output_dir: Path, mode: str) -> dict:
    """
    mode: 'audio' -> extract mp3, 'video' -> video-only stream, no audio
    """
    common = {
        "outtmpl": {
            "default": str(output_dir / "%(title)s.%(ext)s"),
        },
        "restrictfilenames": False,
        "windowsfilenames": True,   # safe across OSes, avoids : " ? etc.
        "ignoreerrors": True,       # one bad video shouldn't kill the whole playlist
        "noplaylist": False,
        "quiet": False,
        "no_warnings": False,
    }

    if mode == "audio":
        common.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    elif mode == "video":
        common.update({
            # video-only stream (no audio track) — this is the "image video" part
            "format": "bestvideo[ext=mp4]/bestvideo",
            "postprocessors": [{
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }],
        })
    elif mode == "thumbnail":
        common.update({
            "skip_download": True,       # don't fetch video/audio at all
            "writethumbnail": True,      # fetch the highest-res thumbnail YouTube exposes
            "postprocessors": [{
                "key": "FFmpegThumbnailsConvertor",
                "format": "jpg",         # normalize webp/other -> jpg
            }],
        })
    else:
        raise ValueError(mode)

    return common


_MODE_DIRS = {"audio": "mp3", "video": "video", "thumbnail": "thumbnails"}


def download(url: str, output_dir: Path, mode: str) -> None:
    target_dir = output_dir / _MODE_DIRS[mode]
    target_dir.mkdir(parents=True, exist_ok=True)
    opts = build_ydl_opts(target_dir, mode)

    print(f"\n=== Downloading [{mode}] -> {target_dir} ===")
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])


def main():
    parser = argparse.ArgumentParser(description="Download a YouTube playlist, split into mp3 + video-only.")
    parser.add_argument("playlist_url", help="YouTube playlist (or video) URL")
    parser.add_argument("-o", "--output", default="downloads", help="Output base directory (default: ./downloads)")
    parser.add_argument("--audio-only", action="store_true", help="Only extract MP3s")
    parser.add_argument("--video-only", action="store_true", help="Only extract video (no audio)")
    parser.add_argument("--thumbnails", action="store_true", help="Also fetch each video's thumbnail image (jpg)")
    parser.add_argument("--thumbnails-only", action="store_true", help="Only fetch thumbnails, skip audio/video")
    args = parser.parse_args()

    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    do_audio = not args.video_only and not args.thumbnails_only
    do_video = not args.audio_only and not args.thumbnails_only
    do_thumbnail = args.thumbnails or args.thumbnails_only

    if do_audio:
        download(args.playlist_url, output_dir, "audio")
    if do_video:
        download(args.playlist_url, output_dir, "video")
    if do_thumbnail:
        download(args.playlist_url, output_dir, "thumbnail")

    print("\nDone. Files saved under:", output_dir)


if __name__ == "__main__":
    main()
