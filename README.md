# vertical-shortform-cutter

An agent skill for cutting a long talking-head video into a vertical short-form clip.

Give it one long recording — an interview, livestream, presentation, training
session — and word-level timings, and it produces a 20-60s vertical clip with
captions that highlight only the words that carry the point.

**Read [`SKILL.md`](SKILL.md) first.** It is the contract; this file is just the
signpost.

## What it does

| Step | Command | Output |
|---|---|---|
| Read the transcript, derive key terms | `build.py --list-only` | printed transcript + key terms |
| Cut to your script | `build.py --beats ... --phrases ...` | `script.txt`, `plan.json`, `captions.json` |
| Render | `render.py` | vertical MP4, captions burned in, loudness normalised |
| Cover | `cover.py` | cover image |
| Cover as first frame | `add_cover.py` | MP4 with the cover at frame zero |

Trim, tempo change, loudness normalisation and caption burn all happen in one
FFmpeg pass. A ~30s clip renders in well under a minute on a 2-core CPU; a
frame-by-frame React renderer needs roughly 20 minutes for the same clip, which is
why this path exists.

## The method it encodes

The order is the point, and it is counter-intuitive:

1. **Read the transcript as a whole, then write the script you want the viewer to
   hear** — in full, in order, the way it will play.
2. **Only then** choose which source seconds supply each line.
3. Open on the question the talk answers, not on its punchline. A talk's best line
   usually depends on setup, so lifting it to position zero makes the clip
   confusing rather than gripping.
4. Restore content and lower the tempo when pacing feels rushed. Lowering tempo
   alone makes the clip *shorter* (runtime is source length ÷ factor), squeezing the
   same density into less time.

## Requirements

- **ffmpeg** (with libx264 and the `ass` filter) and **ffprobe**
- **Python 3.10+**, standard library only
- Optional: `jieba` (`pip install jieba`) for better key-term derivation on Chinese
- Word-level timings from whatever transcriber you already use — this skill does
  not transcribe

## Verify it works

```bash
python selftest.py
```

Builds a synthetic video and transcript, runs the whole pipeline, and asserts 25
properties — including the regressions that shipped and were fixed: corrections
that survived a merge boundary, highlights that stayed aligned after a
text-length change, key phrases that were not cut by a line break, and a frame
rate that did not multiply with the tempo. No real content is used.

## What is in here

```
SKILL.md                 the contract: procedure, checks, what "good" looks like
scripts/build.py         written-script-driven cut; captions and key words
scripts/render.py        one-pass render: trim, tempo, loudness, caption burn
scripts/cover.py         cover image generator
scripts/add_cover.py     joins the cover as the video's first frame
references/PACING.md     retention shape, tempo, what to delete
references/CAPTIONS.md   caption styling, key-word colouring, the three modes
references/TRAPS.md      14 failures that are hard to notice and costly to diagnose
references/SETUP.md      install, and what to do when ffprobe is missing
selftest.py              25 assertions over a synthetic end-to-end run
```

## License

MIT — use it, fork it, ship it.
