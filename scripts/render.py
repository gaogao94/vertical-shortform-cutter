#!/usr/bin/env python3
"""Render the planned cut: trim, retime, normalise loudness, burn captions.

One FFmpeg pass does all of it, so nothing is encoded twice. For a ~30s vertical
clip this runs in well under a minute on a 2-core CPU; a frame-by-frame React
renderer of the same clip takes ~20 minutes, which is why this path exists.

Reads plan.json + captions.json from plan.py.

Usage:
  python render.py --video in.mp4 --plan work/plan.json \
      --captions work/captions.json --output out/short.mp4

Options that matter:
  --font-size      caption size; 46 fits 11 CJK chars inside a 720px frame
  --margin-v       bottom inset; keep clear of the platform UI overlays
  --key-colour     ASS colour for key words, &HBBGGRR& (default warm yellow)
  --loudness       integrated loudness target; -16 suits mobile playback
  --caption-mode   key | karaoke | plain
                     key     - white text, only key words coloured (default)
                     karaoke - per-word sweep, every word lights up in turn
                     plain   - no colour at all
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from typing import Any


def find_ffmpeg(explicit: str | None = None) -> str:
    """Locate ffmpeg: explicit path, then PATH, then the local tools/bin layout."""
    if explicit:
        return explicit
    import shutil
    found = shutil.which("ffmpeg")
    if found:
        return found
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (
        os.path.join(here, "..", "bin", "ffmpeg.exe"),
        os.path.join(here, "..", "bin", "ffmpeg"),
        os.path.join(here, "..", "..", "tools", "bin", "ffmpeg.exe"),
    ):
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    raise SystemExit("ffmpeg not found: pass --ffmpeg or put it on PATH")


HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,1,0,3,3,0,2,{margin_h},{margin_h},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def build_ass(caps: dict[str, Any], width: int, height: int, font: str, size: int,
              margin_v: int, margin_h: int, key_colour: str, mode: str) -> tuple[str, int]:
    """Return (ASS text, number of coloured runs)."""
    out = [HEADER.format(width=width, height=height, font=font, size=size,
                         margin_v=margin_v, margin_h=margin_h)]
    white = r"\c&HFFFFFF&"
    colour = 0
    for cap in caps["segments"]:
        parts, open_colour = [], False
        if mode == "karaoke":
            # Sweep: each word lights up for its own duration, in centiseconds.
            for word in cap["words"]:
                span = max(1, int(round((word["end"] - word["start"]) * 100)))
                parts.append(r"{\k%d}%s" % (span, word["word"]))
                colour += 1
        else:
            for word in cap["words"]:
                is_key = bool(word.get("key")) and mode == "key"
                if is_key and not open_colour:
                    parts.append("{" + key_colour + "}")
                    open_colour = True
                elif not is_key and open_colour:
                    parts.append("{" + white + "}")
                    open_colour = False
                if is_key:
                    colour += 1
                parts.append(word["word"])
            if open_colour:
                parts.append("{" + white + "}")
        out.append(f"Dialogue: 0,{ass_time(cap['start'])},{ass_time(cap['end'])},"
                   f"Caption,,0,0,0,,{''.join(parts)}")
    return "\n".join(out) + "\n", colour


def probe(path: str, ffmpeg: str) -> dict:
    """Read output metadata. Prefers ffprobe, falls back to parsing `ffmpeg -i`.

    ffprobe is absent from some builds (and from the imageio-ffmpeg wheel), so a
    missing prober must not fail a render that actually succeeded.
    """
    import shutil
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        for cand in (os.path.join(os.path.dirname(ffmpeg), "ffprobe"),
                     os.path.join(os.path.dirname(ffmpeg), "ffprobe.exe")):
            if os.path.isfile(cand):
                ffprobe = cand
                break
    if ffprobe:
        proc = subprocess.run([ffprobe, "-v", "quiet", "-print_format", "json",
                               "-show_format", "-show_streams", path],
                              capture_output=True, text=True, errors="replace")
        try:
            data = json.loads(proc.stdout or "{}")
            if data.get("streams"):
                return data
        except json.JSONDecodeError:
            pass

    proc = subprocess.run([ffmpeg, "-hide_banner", "-i", path],
                          capture_output=True, text=True, errors="replace")
    report = proc.stderr or ""
    info: dict = {"format": {}, "streams": []}
    for line in report.splitlines():
        stripped = line.strip()
        found = re.search(r"Duration:\s*([\d:.]+)", stripped)
        if found:
            info["format"]["duration"] = found.group(1)
        dims = re.search(r"(\d{2,5})x(\d{2,5})", stripped)
        if dims and "Video:" in stripped:
            stream = {"codec_type": "video", "width": int(dims.group(1)),
                      "height": int(dims.group(2))}
            fps = re.search(r"([\d.]+)\s*fps", stripped)
            if fps:
                stream["r_frame_rate"] = f"{round(float(fps.group(1)))}/1"
            info["streams"].append(stream)
        elif "Audio:" in stripped:
            info["streams"].append({"codec_type": "audio"})
    return info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--captions", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=1280)
    ap.add_argument("--fps", type=int, default=30,
                    help="output frame rate; setpts alone yields source_fps * speed")
    ap.add_argument("--font", default="Microsoft YaHei")
    ap.add_argument("--font-size", type=int, default=38)
    ap.add_argument("--margin-v", type=int, default=170)
    ap.add_argument("--margin-h", type=int, default=40)
    ap.add_argument("--key-colour", default=r"\c&H00D4FF&",
                    help="ASS colour for key words, &HBBGGRR&")
    ap.add_argument("--loudness", type=float, default=-16.0,
                    help="integrated loudness target in LUFS")
    ap.add_argument("--caption-mode", choices=("key", "karaoke", "plain"), default="key")
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--ffmpeg")
    args = ap.parse_args()

    with open(args.plan, encoding="utf-8") as fh:
        plan = json.load(fh)
    with open(args.captions, encoding="utf-8") as fh:
        caps = json.load(fh)

    ffmpeg = find_ffmpeg(args.ffmpeg)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    ass_path = os.path.splitext(args.output)[0] + ".ass"
    ass_text, colour_runs = build_ass(caps, args.width, args.height, args.font,
                                     args.font_size, args.margin_v, args.margin_h,
                                     args.key_colour, args.caption_mode)
    with open(ass_path, "w", encoding="utf-8") as fh:
        fh.write(ass_text)
    print(f"captions: {len(caps['segments'])} lines, {colour_runs} coloured runs "
          f"({args.caption_mode} mode) -> {ass_path}")

    speed = plan["speed"]
    ranges = plan["ranges"]

    # trim + concat + retime + caption burn, single pass over the source.
    filters: list[str] = []
    labels: list[str] = []
    for idx, (_name, lo, hi) in enumerate(ranges):
        filters.append(f"[0:v]trim=start={lo:.3f}:end={hi:.3f},setpts=PTS-STARTPTS[v{idx}]")
        filters.append(f"[0:a]atrim=start={lo:.3f}:end={hi:.3f},asetpts=PTS-STARTPTS[a{idx}]")
        labels.append(f"[v{idx}][a{idx}]")
    filters.append("".join(labels) + f"concat=n={len(ranges)}:v=1:a=1[cv][ca]")
    filters.append(f"[cv]setpts=PTS/{speed},fps={args.fps}[sv]")
    # loudnorm is not optional: phone recordings land near -35 LUFS, which is
    # inaudible next to anything else on a feed.
    filters.append(f"[ca]atempo={speed},loudnorm=I={args.loudness}:TP=-1.5:LRA=11[sa]")
    ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")
    filters.append(f"[sv]ass='{ass_escaped}'[vout]")

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", args.video,
           "-filter_complex", ";".join(filters),
           "-map", "[vout]", "-map", "[sa]",
           "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", args.output]
    print("rendering...")
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    elapsed = round(time.time() - started, 1)
    if proc.returncode != 0 or not os.path.isfile(args.output):
        print(f"render FAILED after {elapsed}s", file=sys.stderr)
        print(proc.stderr[-1500:], file=sys.stderr)
        return 1

    info = probe(args.output, ffmpeg)
    fmt = info.get("format", {})
    vid = next((s for s in info.get("streams", []) if s["codec_type"] == "video"), {})
    duration = fmt.get("duration", "?")
    try:  # ffprobe gives seconds, the ffmpeg fallback gives a timestamp
        duration = f"{float(duration):.2f}"
    except (TypeError, ValueError):
        pass
    print(f"done in {elapsed}s")
    print(f"  {args.output}")
    print(f"  {round(os.path.getsize(args.output) / 1048576, 2)} MB | "
          f"{duration}s | {vid.get('width')}x{vid.get('height')} "
          f"@ {vid.get('r_frame_rate')} | {vid.get('codec_name')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
