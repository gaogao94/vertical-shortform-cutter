#!/usr/bin/env python3
"""Generate a cover image and a short title card from a video frame.

Why generate rather than hand-paint: the cover must match the burned-in captions
(font, weight, colour, safe margins) or it reads as belonging to a different
video. Drawing it with the same FFmpeg and the same font keeps them consistent,
and keeps this step reproducible instead of a saved Photoshop file.

Two outputs:
  cover.jpg     standalone image for the platform's own thumbnail slot
  titlecard.mp4 ~1.5s lead-in, optional (see --titlecard)

Usage:
  python cover.py --video in.mp4 --at 98 --title "做活动前" \
      --headline "先想清楚这4件事" --subtitle "产品 · 价格 · 促销 · 渠道" \
      --out output/
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# Matches render.py's caption style so the cover looks like the same video.
FONT = "Microsoft YaHei"
ACCENT = "0xD4FF00"      # same warm yellow as the key-word highlight, as BGR-free hex
WHITE = "white"
SHADOW = "black@0.85"


def find_ffmpeg(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    import shutil
    found = shutil.which("ffmpeg")
    if found:
        return found
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "..", "bin", "ffmpeg.exe"),
                 os.path.join(here, "..", "bin", "ffmpeg"),
                 os.path.join(here, "..", "..", "tools", "bin", "ffmpeg.exe")):
        if os.path.isfile(cand):
            return os.path.abspath(cand)
    raise SystemExit("ffmpeg not found: pass --ffmpeg or put it on PATH")


def esc(text: str) -> str:
    """Escape text for a drawtext filter argument.

    A literal colon or backslash inside drawtext's `text=` terminates the option
    early, and an apostrophe would close the quoted string, so both are escaped.
    """
    out = text.replace("\\", r"\\\\").replace(":", r"\:").replace("'", r"\\'")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--at", type=float, default=98.0, help="source second for the backdrop")
    ap.add_argument("--title", default="", help="small kicker line above the headline")
    ap.add_argument("--headline", required=True, help="the one thing the video is about")
    ap.add_argument("--subtitle", default="", help="supporting line, e.g. a list")
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=1280)
    ap.add_argument("--titlecard", action="store_true",
                    help="also render a ~1.5s lead-in clip from the cover")
    ap.add_argument("--ffmpeg")
    args = ap.parse_args()

    ffmpeg = find_ffmpeg(args.ffmpeg)
    os.makedirs(args.out, exist_ok=True)
    cover = os.path.join(args.out, "封面.jpg")

    w, h = args.width, args.height
    # A real vertical gradient, blended once. Layered semi-transparent boxes were
    # the obvious approach and left visible horizontal seams where each box ended -
    # four hard edges across the picture instead of a soft falloff.
    filters = [
        "crop=iw*0.92:ih*0.92",
        f"scale={w}:{h}",
        "eq=brightness=-0.06:saturation=1.05",
        "split=2[bg][fg]",
        f"[fg]format=rgba,geq=r=0:g=0:b=0:a='if(gt(Y,{int(h*0.40)}),"
        f"min(190,(Y-{int(h*0.40)})*190/{int(h*0.60)}),0)'[shade]",
        "[bg][shade]overlay=0:0:format=auto",
    ]

    def text(text: str, size: int, colour: str, y: str, border: int = 6) -> str:
        return (
            f"drawtext=font='{FONT}':text='{esc(text)}':fontsize={size}:"
            f"fontcolor={colour}:borderw={border}:bordercolor={SHADOW}:"
            f"x=(w-text_w)/2:y={y}"
        )

    # Text block sits in the lower third: a feed's own UI (caption, buttons) owns
    # the very bottom, and the subject's face usually owns the top.
    margin = int(w * 0.06)
    if args.title:
        filters.append(text(args.title, 44, WHITE, "h*0.585"))
    filters.append(text(args.headline, 72, ACCENT, "h*0.645" if args.title else "h*0.620"))
    filters.append(
        f"drawbox=x={margin}:y=h*0.745:w={w - margin * 2}:h=5:color={ACCENT}@0.95:t=fill"
    )
    if args.subtitle:
        filters.append(text(args.subtitle, 38, WHITE, "h*0.765"))

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
           "-ss", f"{args.at:.2f}", "-i", args.video, "-frames:v", "1",
           "-vf", ",".join(filters), "-q:v", "2", cover]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0 or not os.path.isfile(cover):
        print("cover FAILED", file=sys.stderr)
        print(proc.stderr[-1200:], file=sys.stderr)
        return 1
    print(f"cover: {cover} ({round(os.path.getsize(cover) / 1024, 1)} KB)")

    if args.titlecard:
        # A lead-in clip, not part of the main render: some platforms let you pick
        # one, and it can be prepended manually when a series needs a consistent
        # open. Kept short because the first two seconds are the hook.
        card = os.path.join(args.out, "封面垫场.mp4")
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
               "-loop", "1", "-t", "1.5", "-i", cover,
               "-f", "lavfi", "-t", "1.5", "-i", "anullsrc=r=44100:cl=mono",
               "-vf", f"fps=30,scale={w}:{h}",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
               "-movflags", "+faststart", card]
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if proc.returncode == 0 and os.path.isfile(card):
            print(f"titlecard: {card} ({round(os.path.getsize(card) / 1024, 1)} KB)")
        else:
            print("titlecard FAILED", file=sys.stderr)
            print(proc.stderr[-600:], file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
