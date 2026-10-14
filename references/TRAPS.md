# Traps

Failures that pass a casual look and cost real time to diagnose. Each entry says
what you will observe, why it happens, and the move that fixes it.

Three of these pull against each other around the same mechanism — joining CJK
character tokens, correcting the joined text, and deciding where a caption line
may break. Read #1, #2 and #3 together before changing any of them; each naive fix
reintroduces one of the others.

---

## 0. The clip opens on a conclusion nobody has context for

**Observe.** The strongest line is at position zero, and the result is confusing
rather than gripping. "What is this person talking about?"

**Why.** A talk's best line usually depends on what precedes it. "But I don't have
those people" lands because the speaker just listed everything else that can be
arranged. Lift the line out and it is a fragment of an argument the viewer never
heard — and the first two seconds are the worst place to make someone work.

**Fix.** Write the script before choosing the cut. Read the transcript, decide what
the viewer should hear in what order, and only then pick source seconds for each
line. In practice this means the clip opens on the *question* the talk answers
(what must be decided before a campaign runs) rather than on the answer's punchline,
and reaches the punchline at the end, where it closes the loop.

A hook earns its place by creating a question the next line answers. A conclusion
in the first two seconds creates nothing.

**Tell.** If the resulting script, read aloud on its own, needs an introduction to
make sense, the cut is wrong — no amount of caption polish will repair it.

---

## 1. CJK timings arrive split into single characters

**Observe.** A correction mapping a misheard word onto the right one never applies,
and a keyword search for a word plainly visible in the transcript text finds
nothing.

**Why.** Chinese ASR emits one token per character: `数` and `字`, `渠` and `道`,
`活` and `动`. A whole-word match against those tokens cannot succeed, so both the
correction and the keyword colouring silently do nothing. Nothing errors.

**Fix.** Merge adjacent single-character tokens into the written word first, apply
corrections and keyword matching to that merged text, then re-split it with
proportional timing so per-word highlighting still advances. `scripts/plan.py`
already does this — the point is to keep the order: **merge → correct → re-split**.
Reversing any two of those steps reintroduces the bug.

**Tell.** Coloured-character count of `0` in the plan output while key words are
visibly present in the text.

---

## 2. A merge cap lands inside the term being corrected

**Observe.** Trap #1 is fixed — tokens merge, keyword colouring works — yet one
specific correction still does not apply, and it is inconsistent: some corrections
work, one does not.

**Why.** The fix for trap #1 needs a cap on how many characters may merge, because
a recogniser leaves sub-100ms gaps between *different* words and an unbounded merge
welds a whole clause together. But a character cap is blind to meaning: with a
4-character cap, `手里的数字` splits into `手里的数` + `字卖`, so neither unit
equals `数字` and the correction silently misses. A 3-character cap would split it
differently and still miss.

This is the two traps pulling against each other: merge too little and whole-word
matching fails (#1); merge too much and distinct words fuse. **No cap value fixes
both**, because the problem is that corrections are being applied at the wrong
level.

**Fix.** Apply corrections to the **assembled caption line**, not to individual
merged units. The line always contains the complete term regardless of how the
merge happened to split. Re-derive the highlight positions from character indices
afterwards, so a replacement of a different length keeps the colour on the right
characters.

Keep the merge cap for keyword matching, where a split term merely misses one
highlight. Reserve line-level application for corrections, where a miss ships a
wrong word to the viewer.

**Tell.** A correction works in a printed transcript but not in the rendered
caption, in the same run. Print the merged units around the term: if the term is
split across two of them, this is the bug.

---

## 3. Caption text runs past the frame edge

**Observe.** On a phone the caption is cut off at both sides. Every command in the
pipeline reports success.

**Why.** A vertical frame is narrow. At font size 60 with a 40px side margin, a
720px-wide frame holds roughly 11 CJK characters; a 16-character line overflows.
The subtitle renderer does not wrap or shrink, it just draws.

**Fix.** Two bounds together: cap the line at ~11 characters **and** keep the font
size modest (46 works at 720px wide). Both, not either — a long line at a small
font is unreadable, a short line at a large font still overflows.

**Verify.** Extract a frame from the longest caption line and look at it. This is
the only check that catches it.

---

## 4. Caption lines join two clauses, or split one word

**Observe.** A caption reads *"the end of one sentence the start of the next"* with
no break where the speaker clearly paused, and elsewhere a word appears cut in half
across two lines (渠道 becoming 渠 / 道).

Both symptoms look like a line-break bug. Neither is fixed by tuning the width.

**Why.** There is nothing to break on. A recogniser emits word timings with **no
punctuation**, and continuous speech has **almost no internal silence** — measured
on one recording, most sentences contained no pause of 120ms or longer. So the only
honest break points available are the recogniser's own sentence boundaries. A line
built by counting characters ignores those boundaries, joins the tail of one clause
to the head of the next, and — because the character stream has had its word
boundaries flattened — slices words in half.

Two tempting fixes that do **not** work, both tried:

- **Detecting pauses as punctuation.** No pauses exist to detect.
- **Deriving break points from word timings.** Timing drifts and stretches; short
  phrases computed out to several seconds.

**Fix.** Two mechanisms, in order of reliability:

1. **One caption line per recogniser sentence**, broken further only at a **word
   boundary** when a sentence cannot fit. Measure line width over joined words, not
   over a flat character stream — the recogniser emits single characters for CJK,
   so a width check on raw tokens lands between 渠 and 道.
2. **A punctuated script from the caller** (`--phrases`). This is the only route to
   clause-accurate breaks, because the caller knows where the punctuation belongs.

Size the line to the frame: at 720px wide, 17 CJK characters at font size 38 fills
the width exactly.

---

## 5. A line break splits a coloured phrase

**Observe.** A key phrase lands in yellow but the colour stops mid-phrase, so
`转化方案` renders as `转化方` on one line and `案` on the next, both yellow.

**Why.** The line-break rule counts characters and breaks on the limit. A key word
is several characters, so the limit lands inside it.

**Fix.** Treat a run of consecutive key characters as **atomic** when measuring a
line: the whole phrase moves to the next line or the current line stays short.
Rejoining single-character tokens before measuring (see #4) removes most of these
cases at the source; the atomic rule catches the rest.

---

## 6. Output frame rate multiplies with tempo

**Observe.** You sped a 30fps clip to 1.4x and the export reports `42/1`.

**Why.** `setpts=PTS/1.4` retimes the presentation timestamps but leaves the
sample interval at 1/30s, so the stream is simply described as 42fps. The duration
is correct and playback looks right, but 42 is a non-standard rate: platforms
re-process it, and some editors misread it.

**Fix.** Follow `setpts` with an explicit `fps=` filter at the intended rate
(`setpts=PTS/1.4,fps=30`). Tempo changes speed; the `fps` filter decides the grid.

**Verify.** `ffprobe ... -show_entries stream=r_frame_rate` returns `30/1`, not
`source_fps × speed`.

---

## 7. Loudness silently reverts

**Observe.** An earlier export sounded right; a later one is barely audible, and
the console shows nothing unusual.

**Why.** `loudnorm` sits in the audio chain, so it is easy to drop when the filter
graph is rewritten — for example when adding tempo, or when moving from a
two-pass to a one-pass render. A phone recording peaks near -27 dBFS, so without
normalisation the export lands near **-35 LUFS**, roughly 19 dB below everything
else on a feed.

**Fix.** Treat `loudnorm=I=-16:TP=-1.5:LRA=11` as part of the export definition,
not an optional polish step. Re-measure every export rather than assuming.

**Verify.** `ebur128=peak=true` reports integrated loudness near the target. Read
the `I:` line specifically; the true-peak line can look healthy while loudness is
far off.

---

## 8. A silent cover drags the whole file's loudness down

**Observe.** The cut measured correctly on its own. After a cover image was joined
to the front, the same measurement on the joined file reports several dB quieter —
even though the speech itself is untouched.

**Why.** Two causes stacked:

1. The cover holds **silence**, and silence is included in the measurement, pulling
   the average of the whole file down. Two seconds of silence in a 54-second clip
   is roughly 3 dB.
2. The join re-encodes the file, so any normalisation applied to the cut is not
   carried forward automatically.

**Fix.** Normalise **after** joining, on the concatenated track, so the cover's
silence and the speech share one gain. Put `loudnorm` **inside** the filtergraph:
`-af` cannot be combined with `-filter_complex` for the same stream, and the error
(`Simple and complex filtering cannot be used together`) names the constraint
without naming the fix.

**Verify.** Measure the joined file, not the cut. Expect a true peak under -1 dBFS.

---

## 9. Loudness measured with the wrong tool reports a false failure

**Observe.** The export sounds correct on a phone, but the check reports roughly
-18 dBFS where -15 was expected.

**Why.** `astats` reports **RMS across the entire measured window**, including
silence. EBU R128 (`ebur128`) applies a gate that excludes silence before
integrating. On a file with a leading cover — or simply leading and trailing
silence — the two disagree by several dB, and only the gated figure corresponds to
how loud the speech actually sounds.

**Fix.** Use `ebur128` for the acceptance check and read the gated figure, or
measure the speech region only (`-ss` past the cover). Treat `astats` RMS as a
signal-presence check ("is there audio at all, is it clipping"), not a loudness
check.

**Tell.** The two measurements disagree by more than ~1 dB and the file contains
silence at either end.

---

## 10. Editing non-ASCII source through a shell corrupts it

**Observe.** A Python file that ran a minute ago now fails to parse, with
`unterminated string literal` pointing at a line of CJK text that looks fine in the
editor. String literals have become mojibake (`"浠€涔?`).

**Why.** A PowerShell round trip — read the file as text, replace a substring,
write it back — decodes with the console's OEM codepage and re-encodes as UTF-8.
The CJK bytes are reinterpreted on the way in, and the file is destroyed. The
damage is not reversible: the wrong decoding can produce characters that do not map
back.

**Fix.** Edit source files with a tool that reads and writes UTF-8 explicitly
(Python with `encoding="utf-8"`, or an editor), and never route source text through
shell string operations. If a shell edit is unavoidable, keep the replacement
ASCII-only and verify afterwards:

```bash
python -c "import ast; ast.parse(open('file.py', encoding='utf-8').read()); print('ok')"
```

Also watch for a **BOM** added by a shell write: a UTF-8 BOM makes Python fail on
line 1 with `invalid non-printable character U+FEFF`.

---

## 11. Windows: batch files and non-ASCII paths

**Observe.** A launcher works in one folder and produces nonsense errors in
another: fragments of English words reported as "not recognized as an internal or
external command".

**Why.** `cmd.exe` parses batch files in the OEM codepage. A non-ASCII byte in the
file — a Chinese project path, for instance — is decoded into different characters
and the parser reads fragments of the following lines as commands.

**Fix.** Keep batch files 100% ASCII and pass non-ASCII paths through a runtime
variable with delayed expansion:

```bat
setlocal enabledelayedexpansion
for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0paths.txt") do (
  if /i "%%A"=="PY" set "PYV=%%B"
)
call "!PYV!" "!IMPLV!" %*
```

The paths file itself is UTF-8 with a BOM so `cmd.exe` and Python agree on it.
ASCII paths everywhere are simpler when you get the choice.

---

## 12. Windows: Python subprocesses decode output as GBK

**Observe.** A tool's availability check crashes with
`UnicodeDecodeError: 'gbk' codec can't decode byte ...`, or a tool that works by
hand reports itself unavailable when called from code.

**Why.** On a Chinese Windows install, a child process writing UTF-8 into a pipe
is decoded by the parent using the OEM codepage. Output containing non-ASCII bytes
then raises inside the reader thread, which often surfaces as a status check
failing rather than as a decode error.

**Fix.** Set `PYTHONUTF8=1` for the process doing the spawning. This is a
prerequisite, not a preference: several tool availability checks report
`unavailable` without it.

---

## 13. A tool is missing one binary, and the source is slow

**Observe.** `ffmpeg` exists but `ffprobe` does not, and downloading a full
Windows build crawls at a few KB/s from the usual hosts.

**Why.** Some distributions ship `ffmpeg` alone. Many pipelines shell out to
`ffprobe` for metadata, so the gap is fatal while looking trivial.

**Fix.** `imageio-ffmpeg` on PyPI ships a complete `ffmpeg` binary and installs in
seconds from a nearby mirror. If `ffprobe` is genuinely needed, a shim can
reproduce the subset of its interface actually used — `-print_format json`,
`-show_entries` (with `:` separating sections and `,` separating fields of one
section), `-select_streams`, and the `default`/`csv`/`flat` writers — implemented
on top of `ffmpeg -i`.

Budget the shim honestly: it is a compatibility layer, worth it when the real
binary is unreachable, and worth removing the moment it is not.

---

## 14. Transcribing here, to save a download

**Observe.** Hours disappear on a clip that should have taken minutes. The machine
is pegged the whole time and the run is no better for it.

**Why.** Two costs get underestimated because they look like one small step:

1. **The transcription itself.** On a 2-core CPU with no GPU, 118 seconds of audio
   takes **15.6 minutes** — about 8x realtime, and 35% of the whole job. A larger
   model is several times slower again and wants more RAM than a small machine has.
2. **The model download.** Whisper `large-v3` is ~3 GB. On a machine with 3.4 GB
   free that fails part way through with `No space left on device` — after spending
   the download time. Model caches also default to the system drive, which is
   usually the smallest one.

**Fix.** Treat transcription as out of scope: consume word-level timings from
whatever tool the caller already uses. That removes the entire cost rather than
optimising it, and external timings are usually more accurate anyway.

When transcription genuinely cannot be avoided, decide it deliberately:

- Check **free disk space and RAM first**, and point the model cache at a large
  drive (`HF_HOME=/path/to/big/drive`).
- Match the model to the hardware. Under 8 GB of RAM, a smaller model beats a
  failed large one.
- Budget it honestly: roughly **0.13 × audio minutes** of CPU time on a 2-core box,
  which is minutes for a short clip and an hour for a long recording.

**Tell.** If the plan starts with "first, transcribe the video", the expensive
decision has already been made. See [`TIME-BUDGET.md`](TIME-BUDGET.md) for the full
measured breakdown.
