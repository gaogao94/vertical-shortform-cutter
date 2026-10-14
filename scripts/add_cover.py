#!/usr/bin/env python3
"""Prepend a cover as the video's first frame.

A feed shows the first frame immediately, so when a cover is wanted as frame zero
it has to be inside the video, not uploaded separately. This converts the cover
image to a short clip and joins it ahead of the cut.

The join is a filter concat with a re-encode, not a stream copy: the still and the
cut come from different sources with different encoders, and exporting both through
the same settings keeps the whole file uniform (a stream copy can produce a file
whose parameters change mid-stream, which some players and platforms mishandle).

Usage:
  python add_cover.py --video cut.mp4 --cover cover.jpg --output final.mp4
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--cover", required=True, help="cover image, or a short clip")
    ap.add_argument("--output", required=True)
    ap.add_argument("--seconds", type=float, default=2.0,
                    help="how long the cover holds; 1.5-2s reads as a title, "
                         "longer spends the hook on a static frame")
    ap.add_argument("--loudness", type=float, default=-16.0,
                    help="integrated loudness target for the joined file, in LUFS")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--font", default="Microsoft YaHei")
    ap.add_argument("--caption", default="",
                    help="optional caption burned over the cover frame")
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--ffmpeg")
    args = ap.parse_args()

    ffmpeg = find_ffmpeg(args.ffmpeg)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    is_image = os.path.splitext(args.cover)[1].lower() in (
        ".jpg", ".jpeg", ".png", ".webp", ".bmp")

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    if is_image:
        cmd += ["-loop", "1", "-t", f"{args.seconds:.3f}", "-i", args.cover]
    else:
        cmd += ["-i", args.cover]
    cmd += ["-i", args.video]

    cover_filter = f"[0:v]fps={args.fps},scale=720:1280,setsar=1"
    if args.caption:
        text = args.caption.replace("\\", r"\\\\").replace(":", r"\:").replace("'", r"\'")
        cover_filter += (
            f",drawtext=font='{args.font}':text='{text}':fontsize=38:"
            f"fontcolor=white:borderw=4:bordercolor=black@0.85:"
            f"x=(w-text_w)/2:y=h-160"
        )
    cover_filter += ",format=yuv420p[cv]"

    filters = [
        cover_filter,
        # The cut may carry no audio if it was built from a silent source, so
        # synthesise a silent track for the cover and let concat match them.
        f"anullsrc=r=44100:cl=stereo,atrim=0:{args.seconds:.3f},asetpts=PTS-STARTPTS[ca]",
        f"[1:v]fps={args.fps},scale=720:1280,setsar=1,format=yuv420p[bv]",
        "[cv][ca][bv][1:a]concat=n=2:v=1:a=1[vcat][acat]",
        # Normalise the joined track, not just the cut. The cover holds silence and
        # silence drags the average of the whole file down, so a clip that measured
        # correctly on its own reads several dB quieter once the cover is attached.
        # loudnorm belongs inside the filtergraph: -af cannot be combined with
        # -filter_complex for the same stream.
        f"[acat]loudnorm=I={args.loudness}:TP=-1.5:LRA=11[aout]",
    ]

    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", "[vcat]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(args.crf),
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", args.output,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0 or not os.path.isfile(args.output):
        print("FAILED", file=sys.stderr)
        print(proc.stderr[-1500:], file=sys.stderr)
        return 1

    import shutil
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        info = json.loads(subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format",
             "-show_streams", args.output],
            capture_output=True, text=True, errors="replace").stdout or "{}")
        fmt = info.get("format", {})
        vid = next((s for s in info.get("streams", [])
                    if s["codec_type"] == "video"), {})
        print(f"{args.output}")
        print(f"  {round(os.path.getsize(args.output) / 1048576, 2)} MB | "
              f"{fmt.get('duration')}s | {vid.get('width')}x{vid.get('height')} "
              f"@ {vid.get('r_frame_rate')}")
    else:
        print(f"{args.output} ({round(os.path.getsize(args.output) / 1048576, 2)} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
