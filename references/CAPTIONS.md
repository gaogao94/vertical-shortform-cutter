# Captions

Captions decide whether a muted viewer stays. On a vertical frame they are also
the element most likely to ship broken, because a renderer draws whatever it is
given.

## Styling that survives a phone

| Property | Value at 720x1280 | Why |
|---|---|---|
| Font | a CJK-capable UI font (Microsoft YaHei, Noto Sans SC, PingFang SC) | a font without CJK glyphs renders empty boxes, not an error |
| Size | 46 | 11 CJK characters fit inside the frame with side margins |
| Line length | ≤ 11 CJK characters | the hard bound; the font size is chosen to match it |
| Weight | bold | thin strokes vanish over bright footage |
| Text colour | white | maximum contrast on any footage |
| Outline | 3px black, `BorderStyle=3` | a box, so text stays legible over a light background too |
| Bottom margin | ~170px at 1280 tall | clears the platform's own UI overlays |
| Alignment | bottom centre (ASS `Alignment=2`) | the expected position; moving text reads as a mistake |
| Line hold | ≤ 2.5s | longer lines stop feeling like a short |

An ASS style line consistent with the above:

```
Style: Caption,Microsoft YaHei,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,1,0,3,3,0,2,40,40,170,1
```

ASS colours are `&HBBGGRR&` — byte order is reversed from the usual RGB hex. Warm
yellow is `&H00D4FF&`.

## Colouring key words only

The default mode. Text stays white and only the words carrying the point change
colour, which makes a viewer's eye land on them without a moving effect
competing for attention.

Rules:

1. **Colour the concept, not the sentence.** Product, price, promotion, channel —
   the vocabulary the talk is built on. Colouring half a line is the same as
   colouring none of it.
2. **Keep a phrase whole.** Colour a run of consecutive key characters as one
   unit, and never let a line break fall inside it.
3. **One colour.** A second highlight colour implies a second category; a viewer
   will look for a distinction that is not there.
4. **Bound the density.** Roughly one coloured phrase per caption line is the
   ceiling. If most of a line is coloured, the key-word list is too broad.

Keyword matching happens against **merged** text, because a CJK transcript splits
words into single characters — see `TRAPS.md`, trap 1. A keyword list check that
looks correct in the transcript can still match nothing.

## Evidence for the keyword list

A recogniser may mark words the speaker stressed. Where it does, that emphasis is
independent evidence of what the talk treats as important — useful as a cross-check
on a keyword list written from reading the transcript.

Chinese ASR carries no case, so stress marking is unavailable there and the list
must come from reading the transcript. Say which route you used when reporting.

## The three modes

`scripts/render.py --caption-mode` selects one:

- **`key`** (default) — white, key words coloured. Best for talking-head content
  where the argument matters more than the delivery.
- **`karaoke`** — every word lights up in turn for its own duration. Higher energy;
  suits fast list content. Costs more attention, so pair it with a shorter clip.
- **`plain`** — no colour. Use when a house style forbids it or when the transcript
  quality does not justify emphasising specific words.

## Timings and the output timeline

Word timings arrive on the **source** timeline and must be remapped before they
can be burned in. Two failure modes:

- **Stretched captions.** A timestamp falling inside a cut gap, mapped naively,
  produces a line that holds for the whole gap — a caption visible for 29 seconds.
  Map each word independently and keep it only when **both** its start and end land
  inside the same kept range.
- **Fragments.** Captions built per ASR sentence break when a sentence straddles a
  cut, producing headless lines. Build captions per word, then group.

`plan.py` handles both; the check is that no line exceeds ~2.5s and every line
reads as a complete thought.

## Delivery

Burn captions into the video for a feed. Ship the sidecar as well when the caller
may re-edit: `.ass` preserves per-word timing and colours, `.srt` is what most
editors import. `render.py` writes the `.ass` next to the output.

A sidecar also survives a platform's own re-encode better than burned text does
when the viewer turns captions on — but burned text is what shows when they do not.
For social delivery, burn them in.
