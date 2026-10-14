# vertical-shortform-cutter

[中文](README.md) · [English](README.en.md)

An **agent skill** that cuts a long talking-head video into a vertical short-form clip.

Give it one long recording — an interview, livestream, presentation, training
session — plus **word-level timings**, and it produces a 20-60s vertical clip whose
captions highlight only the words that carry the point.

**Read [`SKILL.md`](SKILL.md) first** — that is the contract. This file is the signpost.

---

## What it does

| Step | Command | Output |
|---|---|---|
| Read the transcript, derive key terms | `build.py --list-only` | printed transcript + key terms |
| Cut to your script | `build.py --beats ... --phrases ...` | `script.txt`, `plan.json`, `captions.json` |
| Render | `render.py` | vertical MP4, captions burned in, loudness normalised |
| Cover | `cover.py` | cover image |
| Cover as first frame | `add_cover.py` | MP4 with the cover at frame zero |

Trim, tempo change, loudness normalisation and caption burn all happen in **one
FFmpeg pass**. A 30s clip renders in well under a minute on a 2-core CPU; a
frame-by-frame React renderer needs roughly 20 minutes for the same clip — that gap
is why this path exists.

## The method it encodes

The order is the point, and it is counter-intuitive:

1. **Read the transcript as a whole, then write the script you want the viewer to
   hear** — in full, in order, the way it will play.
2. **Only then** choose which source seconds supply each line.
3. **Open on the question the talk answers, not on its punchline.** A talk's best
   line usually depends on setup, so lifting it to position zero makes the clip
   confusing rather than gripping.
4. **Feeling rushed? Restore content and lower the tempo.** Lowering tempo alone
   makes the clip *shorter* (runtime is source length ÷ factor), squeezing the same
   density into less time.

---

## About OpenMontage

**This skill is unrelated to [OpenMontage](https://github.com/calesthio/OpenMontage)
and does not depend on it.** It is a standalone set of scripts that needs only
**ffmpeg + the Python standard library**. You do not need OpenMontage installed.

**Why mention it at all?** Because this workflow grew out of one real production run
with it. Here is what happened, and how this skill handles each case:

| What happened with OpenMontage | How this skill handles it |
|---|---|
| Its pipeline renders captions through **Remotion, frame by frame** — 18.4 minutes for a 55s clip | **One FFmpeg pass**, 0.8 minutes — **22-25x faster** |
| Its `clip-factory` pipeline **transcribes locally** (15.6 minutes for 118s of audio) | **Does not transcribe** — it consumes timings you already have |
| Its `transcriber` uses faster-whisper and depends on `ffprobe` | No transcriber is bundled; for a missing `ffprobe`, see [`references/SETUP.md`](references/SETUP.md) |
| Captions come from React components, broken by character count | Broken at **sentence and word boundaries** — see [`references/TRAPS.md`](references/TRAPS.md) trap 4 |

**They can be used together.** If you already run OpenMontage, the word-level
timings from its `transcriber` tool (faster-whisper) can be fed straight into this
skill, which then skips the expensive rendering path. The expected timing format is
documented in [`references/TIME-BUDGET.md`](references/TIME-BUDGET.md).

Conversely, if all you want is to cut a short from a long video, **this skill is
enough — you do not need OpenMontage**.

---

## Time budget: where the cost actually is

This is the most important section, because **the editing was never the expensive
part**.

Measured on a 2-core / 7.7 GB / no-GPU machine, on 118 seconds of source footage:

| Step | Time | Share |
|---|---|---|
| **Speech transcription** | **15.6 min** | 35% |
| **Frame-by-frame caption render** | **18.4 min** | 41% |
| Everything else (analysis, cut, captions, checks, export) | ~11 min | 24% |
| **Total** | **≈45 min** | 100% |

**Two bottlenecks account for 76%, and both are avoidable:**

1. **Do not transcribe here** — bring word-level timings, save 35%
2. **Do not render frame by frame** — one FFmpeg pass, save 41%

After both: **≈45 min → ≈12 min**.

The gap widens with length. For **30 minutes of source**: roughly **5.6 hours** on
the frame-by-frame path versus **15 minutes** on the single-pass path.

Full measurements, the effect of resolution, and three costs that are easy to
underestimate (disk space, context window, repeated exports) are in
**[`references/TIME-BUDGET.md`](references/TIME-BUDGET.md)**.

---

## Requirements

- **ffmpeg** (with libx264 and the `ass` filter) and **ffprobe**
- **Python 3.10+**, standard library only
- Optional: `jieba` (`pip install jieba`) for better key-term derivation on Chinese
- **Word-level timings** from whatever transcriber you already use — this skill
  does not transcribe

## Verify it works

```bash
python selftest.py
```

Builds a synthetic video and transcript, runs the whole pipeline, and asserts 25
properties — including regressions that shipped and were fixed:

- a correction that survived a merge boundary
- highlights that stayed aligned after a text-length change
- key phrases not cut by a line break
- a frame rate that did not multiply with the tempo
- a silent cover that did not drag loudness down

**No real content is used.**

## Contents

```
SKILL.md                 the contract: procedure, checks, what "good" looks like
scripts/build.py         written-script-driven cut; captions and key-word colouring
scripts/render.py        one-pass render: trim, tempo, loudness, caption burn
scripts/cover.py         cover image generator
scripts/add_cover.py     joins the cover as the video's first frame
references/PACING.md     retention shape, tempo, what to delete
references/CAPTIONS.md   caption styling, key-word colouring, the three modes
references/TRAPS.md      15 failures that are hard to notice and costly to diagnose
references/TIME-BUDGET.md measured timings and optimisations (read this one)
references/SETUP.md      install, and what to do when ffprobe is missing
selftest.py              25 assertions over a synthetic end-to-end run
实测笔记-用AI剪一条竖版短视频.md   a full production post-mortem (Chinese)
```

## License

MIT — use it, fork it, ship it.
