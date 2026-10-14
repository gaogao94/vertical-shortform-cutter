# Setup

## Required

| Tool | Purpose | Notes |
|---|---|---|
| **ffmpeg** | trim, tempo, loudness, caption burn, all in one pass | must include libx264 and the `ass` filter |
| **ffprobe** | reading source facts, verifying exports | ships with most ffmpeg builds, but not all |
| Python 3.10+ | the two scripts in `scripts/` | standard library only, no packages to install |

Both scripts locate ffmpeg themselves: `PATH` first, then a sibling `bin/`
directory. Pass `--ffmpeg /path/to/ffmpeg` when neither applies.

## Verifying an install

```bash
ffmpeg -hide_banner -encoders | grep -E 'libx264|aac'
ffmpeg -hide_banner -filters  | grep -E 'ass|loudnorm|atempo'
ffprobe -v error -show_entries format=duration -of csv=p=0 some.mp4
```

If the `ass` filter is missing, the build lacks libass and captions cannot be
burned; use a full build.

## When ffprobe is missing

Some distributions ship `ffmpeg` alone, or reach the network so slowly that
fetching a full Windows build is impractical. The fast route to a working
`ffmpeg` from PyPI:

```bash
pip install imageio-ffmpeg
python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
```

That binary is a complete essentials build — `libx264`, `libx265`, `nvenc`, and
the `subtitles`/`drawtext`/`ass` filters included — and installs in seconds from a
nearby mirror. It carries no `ffprobe`, so writes that need metadata must either
call `ffmpeg -i` directly or reproduce the ffprobe subset in use.

## Windows specifics

Three things break on a Chinese-locale Windows install that work everywhere else.
All three are documented in `TRAPS.md`; the fixes, in order of how often they bite:

1. **`PYTHONUTF8=1`** — without it, subprocess output decoded as GBK raises inside
   a reader thread, and tool availability checks report `unavailable`.
2. **ASCII batch files** — `cmd.exe` parses batch files in the OEM codepage, so a
   non-ASCII path inside one becomes garbage commands. Pass such paths through a
   runtime variable with delayed expansion.
3. **A UTF-8 BOM on config files** read by both `cmd.exe` and Python, so the two
   agree on the encoding.

Keep the working tree on a drive with room. A 4K source plus intermediates eats
tens of gigabytes, and a model download can fill a small system drive mid-run —
`No space left on device` in the middle of a render is that, not a bug.

## Input expectations

`scripts/plan.py` accepts either of these shapes, and any key spelling in the
`segments` / `words` / `start` / `end` / `word` / `text` family:

```json
{
  "segments": [
    {
      "start": 0.0,
      "end": 3.2,
      "text": "…",
      "words": [{"word": "…", "start": 0.0, "end": 0.3}]
    }
  ]
}
```

Word-level timings are what the captions are built from. Sentence-level timings
still produce a clip, but each caption then changes as a whole line and key-word
colouring cannot be placed inside it — say so when reporting, rather than shipping
captions that silently lost their emphasis.
