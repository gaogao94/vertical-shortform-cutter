---
name: vertical-shortform-cutter
description: Cut a long talking-head video into a vertical short-form clip. Use when turning a long video, interview, livestream or presentation into a 20-60s vertical video, or when asked to pick highlight moments, make a video fast-paced, hit 5-second or 15-second retention, cut dead air, tighten pacing, or put captions with key words highlighted on a video. Requires word-level timings, which the calling agent supplies.
---

# Vertical short-form cutter

Turn one long recording into one vertical clip worth posting.

This skill assumes **you already have a transcript with word-level timings**.
Getting those is a separate job: whatever tool you have (an external ASR service,
a local transcriber, a subtitle file) is fine. The work here starts once timings
exist — choosing the cut, controlling pace, and shipping a caption track that
survives a phone screen.

Do not re-transcribe on this machine. It costs minutes on CPU and the caller
already has better timings.

## What "good" looks like at the end

- A vertical MP4 at the source resolution, 30 fps, H.264 + AAC, `+faststart`.
- Integrated loudness near **-16 LUFS**, true peak below -1.5 dBFS.
- Runtime landed in the caller's target window, usually **20-60s**.
- The first 2 seconds state the conflict or the promise; nothing warms up first.
- Captions white, with **only the words that carry the point** coloured.
- Every line fits inside the frame, and no line holds for more than ~2.5s.

## Procedure

The order below is the point of the skill. **Write the script before choosing the
cut.** A cut assembled from timestamps produces a clip that opens on a conclusion
the viewer has no context for; see `references/TRAPS.md` trap 0.

### 1. Read the source facts

Probe the file before deciding anything. You need duration, resolution, frame
rate, and whether an audio stream exists at all.

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 in.mp4
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate -of csv=p=0 in.mp4
ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,channels -of csv=p=0 in.mp4
```

A vertical source (height > width) keeps its framing. A landscape source needs a
crop decision — see `references/SETUP.md`.

Also measure the noise floor, because cut points go in silence and a phone
recording has no true silence:

```bash
ffmpeg -hide_banner -i in.mp4 -af astats=metadata=1:reset=1 -f null NUL
```

### 2. Read the transcript, and write the script

```bash
python scripts/build.py --transcript words.json --out work/ --list-only
```

This prints the transcript with timings and the key terms it derived from the
recording's own vocabulary. Read it as a whole and write the script you want the
viewer to hear — in order, in full sentences, the way it will play.

Two rules for that script:

- **Open on the question, close on the answer.** The most memorable line of a talk
  almost always depends on setup. Starting there confuses; ending there lands.
- **Every line must advance the argument.** If you cannot say what a line adds,
  cut it. Prefer deleting whole lines over trimming inside them.

Then map each line of your script to source seconds. The mapping is the creative
work; `references/PACING.md` covers tempo, hook shape, and what to delete.

### 3. Derive the key terms from the transcript, not from a list

```bash
python scripts/build.py --transcript words.json --out work/ --list-only
```

The `key terms:` line is derived per recording (with `jieba` installed it is real
word segmentation, otherwise character n-grams). **Read it, replace anything
generic, and pass the result explicitly in step 4.** There is deliberately no
built-in domain word list: key words are decided by what a given recording talks
about, so a shipped list would either colour the wrong words or import one
project's subject matter into every other project.

Good key terms are the concepts the recording repeats — four or five of them, each
two to four characters. If the list contains 什么/然后/就是 or a clause fragment,
replace it.

### 4. Build the cut

```bash
python scripts/build.py --transcript words.json --out work/ \
    --beats 4.9:15.18,20.3:24.14,34.84:108.2 \
    --speed 1.0 \
    --keywords 营收,成本,转化,复购 \
    --corrections 布标:部署,复够:复盘
```

`--beats` are **absolute source seconds, in playback order** — reordering is how
you move a line earlier or later. The script prints the resulting script beat by
beat, and writes `script.txt`, `plan.json` and `captions.json`, the latter already
remapped onto the **output** timeline.

Read the printed script top to bottom before rendering. This is the last moment a
logic break is cheap to fix.

Confirm before moving on: the opening line creates a question rather than stating
a conclusion, the payoff appears near the end, `final_seconds` sits in the
caller's window, coloured characters are more than zero, and every dropped line
has a stated reason.

**Caption line breaks.** By default each caption line is one recogniser sentence,
and a sentence that cannot fit is broken at a **word boundary**. That default is
deliberate: continuous speech has almost no internal silence to detect and a
transcript normally has no punctuation, so anything finer is guesswork. When the
caller can supply a punctuated script, `--phrases` cuts lines at punctuation
instead, which is the only way to get clause-accurate breaks:

```bash
python scripts/build.py ... --phrases script.txt
```

Two rules that keep lines readable, both enforced by the script:

- Break **between words**, never inside one. A recogniser emits single characters
  for CJK, so adjacency is rejoined before line width is measured — otherwise 渠道
  renders as 渠 on one line and 道 on the next.
- Size the line to the frame. At 720px wide, 17 CJK characters at font size 38
  fills the width; a longer line or a larger font overflows and is clipped.

### 5. Render

```bash
python scripts/render.py --video in.mp4 --plan work/plan.json \
    --captions work/captions.json --output out/short.mp4
```

Trim, tempo, loudness and caption burn all happen in one pass. For a ~25s clip
this takes under a minute on a 2-core CPU.

Caption appearance and the alternative caption modes are in
`references/CAPTIONS.md`.

### 6. Make the cover

The cover is a separate image, and optionally the video's first frame. A feed shows
the first frame instantly, so a cover that appears there buys scroll-stopping power
at the cost of the hook; a standalone image costs nothing. Ask which the caller
wants — both are one command.

```bash
# the image, for the platform's thumbnail slot
python scripts/cover.py --video in.mp4 --out out/ --at 98 \
    --title "做活动前" --headline "先想清楚这4件事" \
    --subtitle "产品 · 价格 · 促销 · 渠道"

# optional: put that cover at frame zero
python scripts/add_cover.py --video out/cut.mp4 --cover out/封面.jpg \
    --output out/final.mp4 --seconds 2
```

`--at` picks the backdrop frame, so choose a second where the subject is mid-
gesture and clearly lit — a cover is a promise about the video, and a flat frame
promises nothing. Keep the headline to what the video actually answers.

**Placement.** Text goes in the lower half. A feed's own UI (caption, buttons,
progress) owns the very bottom, and the subject's face usually owns the top, so
the lower-middle band is the only region clear of both. Darken it with a single
blended gradient, not stacked translucent boxes — stacked boxes leave visible
horizontal seams across the picture.

`add_cover.py` normalises loudness on the joined file, because the cover holds
silence and silence drags the average down: a cut that measured correctly on its
own reads several dB quieter once a silent cover is attached.

### 7. Verify the export, then report

Three failures are invisible in the console and obvious on a phone. Check all
three:

```bash
# loudness: gated EBU R128, integrated near -16 LUFS, true peak under -1.5 dBFS.
# Use ebur128, not astats: astats averages silence in and reads several dB low on
# any file with silence at the ends (a cover image, for instance).
ffmpeg -hide_banner -i out/final.mp4 -vn -filter_complex ebur128=peak=true -f null NUL

# frame rate: expect a clean 30/1, not source_fps x speed
ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 out/final.mp4
```

Then extract frames from the longest caption line **and from any line containing a
corrected word**, and look at them. Text running past the frame edge, and a
correction that failed to apply, both pass every command above and still ship
broken. Look at the cover too, and at frame zero if the cover was joined there.

Report: output path, duration, resolution, frame rate, loudness, the script you
built and why, and which lines you dropped as filler with the reason for each.

## Traps that cost real time

`references/TRAPS.md` holds 14 failures that are hard to notice and expensive to
diagnose. Three of them fight over one mechanism — joining CJK character tokens,
correcting the joined text, and choosing where a caption line may break — so read
those together before changing any of them; a naive fix for one reintroduces
another. The rest cover hooks that open on an unexplained conclusion, caption
overflow, frame rates that multiply with tempo, loudness that reverts or is
mis-measured, covers that drag loudness down, source files corrupted by editing
them through a shell, and the Windows path-encoding faults that break `ffprobe`.
