# Pacing

Retention is measured at fixed points. Roughly, a short-form feed judges a clip by
what happens in the first **5 seconds** and again by **15 seconds**. Everything
below serves those two numbers.

## The shape that works

A clip that holds attention has four beats, in this order:

| Beat | Lands by | Job |
|---|---|---|
| Hook | **2s** | State the conflict or the promise. Cold, no preamble. |
| Payoff preview | **5-8s** | The strongest single line, moved up from wherever it sits in the source. |
| Reasoning | 8-20s | Why the payoff is true. One idea per line, each line adding something. |
| Landing | last 2-4s | Close the loop. Often the payoff restated in its conditional form. |

The move that matters most: **the payoff is usually near the end of a source talk
and must be relocated to near the beginning.** A talk builds to its best line
because a room has to be warmed up. A feed does not, so cut the line out and open
with it. Keep it at the end too when it lands differently there.

If the source's strongest line is a question, an accusation, or a number, open on
it verbatim.

## Tempo

Speed up rather than cut more. A talk delivered at conversational pace reads as
slow on a phone, and time-compression keeps the reasoning intact where deletion
destroys it.

| Factor | Effect |
|---|---|
| 1.15x | Relaxed. Slower than the default yet still tighter than the original delivery; use when the content is dense and the viewer has to follow an argument. |
| 1.2x | Barely noticeable; use when the speaker already talks fast. |
| **1.35-1.4x** | The default for a measured speaker. Pitch preserved, still intelligible. |
| 1.5-1.6x | Energetic; use for list-style or high-intensity content. |
| > 1.7x | Words start clipping. Cut content instead. |

Preserve pitch (`atempo`). A raised pitch from naive resampling reads as a defect.

### "Too fast" usually means too little content, not too much speed

Runtime is source length divided by the factor, so **lowering the tempo alone makes
the clip shorter**: the same density is squeezed into less time and the rushed
feeling gets worse. The move that works is the opposite direction — restore
explanatory material that was cut, and lower the tempo at the same time. A 22s
clip at 1.35x becomes a 28s clip at 1.15x with a beat put back, and it reads as
calmer because attention has somewhere to rest.

Diagnose before acting: look for explanatory material in the transcript that was
dropped. If there is none, the content genuinely cannot carry a longer runtime, and
lowering the tempo is the wrong lever.

## Cutting dead air

Aim every cut at a measured quiet run, never at a transcript gap. Transcript gaps
come from the recogniser's segmentation and can sit mid-breath; measured silence
is where nobody is talking. `scripts/build.py --speed` handles tempo, but cut
placement is a decision you make against the audio.

Two rules:

1. **Open and close inside silence.** A clip that starts mid-word feels broken
   regardless of what follows.
2. **Break at a sentence end.** A splice between two half-sentences is audible even
   when both halves are clean.

## What to delete

Delete a line when removing it changes nothing about the argument:

- **Self-repetition.** A speaker often restates a point two or three times. Keep
  the sharpest version.
- **Conversational filler.** Agreement tokens, rhetorical checks, and restarts.
- **Enumerations already stated.** If a list is given twice, keep one.
- **Housekeeping.** Anything about the room, the schedule, or who is speaking next.

Delete whole sentences rather than trimming words inside them. A trimmed sentence
loses its subject or its verb and reads as damaged; a deleted sentence is invisible.

## Runtime

| Target | Source to keep at 1.4x |
|---|---|
| 20-25s | ~30s |
| 30-35s | ~45s |
| 45-60s | ~70-85s |

For 5-second retention, spend the first 2 seconds on the hook and nothing else —
no titles, no context, no introduction of the speaker. For 15-second retention,
make sure a second distinct idea lands between 8s and 15s, so the clip has moved
somewhere rather than repeating its opening.

## Choosing ranges

Ranges are absolute source seconds, in output order. Two patterns:

- **Contiguous plus a hook.** One long range carrying the reasoning, preceded by a
  short range holding the payoff. Two splices, coherent result, safest structure.
- **Framework then application.** A range that states the principle, then a range
  where it is applied to a concrete case. Good when the source teaches a method.

Prefer few splices. Each splice costs continuity; three or four is usually the
limit before a clip feels assembled rather than told.

## Checking the plan

Before rendering, confirm from `build.py` output:

- Hook text is in the first two lines.
- The payoff appears near the end as well as near the start, when it earns it.
- `final_seconds` sits in the caller's window.
- Every dropped line was dropped for one of the reasons above — be able to say
  which.
- Lines read as complete thoughts, with no orphaned fragments.
