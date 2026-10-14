#!/usr/bin/env python3
"""Build a short-form cut from a written script, not from timestamps.

The order matters and is the whole point of this module: read the transcript,
write the script you actually want the viewer to hear, and only then decide which
source seconds supply each line. Cutting first and narrating afterwards produces
clips that open on a conclusion the viewer has no context for.

Two caption modes:

  default    word timings are grouped by pause and character count. Works with no
             extra input, but most recognisers emit no punctuation, so a line can
             glue the end of one clause to the start of the next.
  --phrases  the caller supplies the script WITH punctuation, as text or a file.
             Lines are then cut at punctuation, giving complete clauses and whole
             phrases. This is the mode to reach for when a caption reads wrong.

Usage:
  # 1. read the transcript and the derived key terms
  python build.py --transcript words.json --out work/ --list-only

  # 2. cut, with a punctuated script controlling caption line breaks
  python build.py --transcript words.json --out work/ \
      --beats 4.9:15.18,20.3:24.14,34.84:108.2 --speed 1.0 \
      --phrases script.txt --corrections 数字:产品

  --list-only          print the merged transcript and stop (write the script first)
  --keywords auto      derive from the transcript (default)
  --keywords a,b,c     supply explicitly, e.g. from a domain glossary
  --keywords none      no colouring; white captions only
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from typing import Any

MAX_LINE_CHARS = 17
MAX_LINE_SECONDS = 3.2
MAX_WORD_GAP = 0.12
# Cap on how many characters one merge may join. A CJK recogniser emits single
# characters and often leaves sub-100ms gaps between *different* words, so an
# unbounded merge welds a whole clause into one unit and whole-word matching then
# fails. 4 covers normal Chinese terms while keeping distinct words apart.
MAX_MERGE_CHARS = 4
PAUSE_BREAK = 0.45

# Very common words carry no emphasis, so they are poor key terms even when they
# are frequent. This is a stoplist, not a domain list: it stays valid for any
# transcript.
STOPWORDS = {
    "这个", "那个", "我们", "你们", "他们", "什么", "就是", "然后", "但是",
    "因为", "所以", "如果", "可以", "没有", "一个", "这些", "那些", "这样",
    "那样", "现在", "时候", "问题", "东西", "对", "吧", "是不是", "对吧",
    "知道", "觉得", "应该", "可能", "还是", "或者", "而且", "自己", "一样",
    "出来", "起来", "下去", "一下", "一定", "其实", "真的", "非常", "特别",
}


def load_transcript(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    segments = data.get("segments") if isinstance(data, dict) else data
    if not segments:
        raise SystemExit(f"no segments in {path}")
    out = []
    for seg in segments:
        words = []
        for word in seg.get("words") or []:
            token = (word.get("word") or word.get("text") or "").strip()
            if not token:
                continue
            words.append({"word": token,
                          "start": float(word.get("start") or 0.0),
                          "end": float(word.get("end") or 0.0)})
        start = seg.get("start")
        end = seg.get("end")
        if start is None and words:
            start = words[0]["start"]
        if end is None and words:
            end = words[-1]["end"]
        out.append({"start": float(start or 0.0), "end": float(end or 0.0),
                    "words": words, "text": seg.get("text") or ""})
    return out


def merge_tokens(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge per-character CJK tokens into written words, keeping the timeline."""
    merged: list[dict[str, Any]] = []
    for seg in segments:
        words = seg["words"]
        i = 0
        while i < len(words):
            run = [words[i]]
            j = i + 1
            while (j < len(words)
                   and words[j]["start"] - run[-1]["end"] < MAX_WORD_GAP
                   and len(words[j]["word"]) == 1 and len(run[-1]["word"]) == 1
                   and sum(len(w["word"]) for w in run) < MAX_MERGE_CHARS):
                run.append(words[j])
                j += 1
            merged.append({"word": "".join(w["word"] for w in run),
                           "start": run[0]["start"], "end": run[-1]["end"]})
            i = j
    return merged


def derive_keywords(segments: list[dict[str, Any]], top: int = 10,
                    min_count: int = 2) -> list[str]:
    """Derive the terms a talk is built on, without a domain word list.

    Two strategies, best first:

    1. **jieba**, when installed. Real word segmentation, so the ranking lands on
       the concepts the talk repeats and skips clause fragments. ``pip install
       jieba``; pure Python and quick.
    2. **character n-grams**, when it is not. Scores 2-4 character sequences by
       occurrence, which surfaces repeated vocabulary but also admits fragments
       that pass the stoplist.

    Either way the output is a suggestion. Read it, and pass --keywords explicitly
    when you know the subject: a wrong key-word list colours the wrong words, and
    that is invisible until someone watches the clip.
    """
    corpus = "".join(w["word"] for seg in segments for w in seg["words"])

    try:
        import logging

        import jieba  # type: ignore

        logging.getLogger("jieba").setLevel(logging.ERROR)
        counts: Counter[str] = Counter()
        for token in jieba.cut(corpus):
            token = token.strip()
            if (len(token) >= 2 and token not in STOPWORDS
                    and re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]+", token)):
                counts[token] += 1
        return [t for t, n in counts.most_common() if n >= min_count][:top]
    except ImportError:
        pass

    counts = Counter()
    for size in (2, 3, 4):
        for start in range(len(corpus) - size + 1):
            gram = corpus[start:start + size]
            if re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]+", gram):
                counts[gram] += 1

    ranked = sorted(counts.items(), key=lambda kv: (kv[1] * len(kv[0]), len(kv[0])),
                    reverse=True)
    chosen: list[str] = []
    for gram, count in ranked:
        if count < min_count or gram in STOPWORDS:
            continue
        if any(gram in existing for existing in chosen):
            continue          # subsumed by a longer term already taken
        chosen.append(gram)
        if len(chosen) >= top:
            break
    return chosen


def _split_phrase(group: list[dict[str, Any]], keywords: list[str],
                  max_chars: int) -> list[list[dict[str, Any]]]:
    """Break one phrase into displayable lines without cutting a key word."""
    text = "".join(c["char"] for c in group)
    if len(text) <= max_chars:
        return [group]
    protected: set[int] = set()
    for kw in keywords:
        at = text.find(kw)
        while at != -1:
            protected.update(range(at, at + len(kw)))
            at = text.find(kw, at + 1)
    pieces, start = [], 0
    while start < len(group):
        end = min(start + max_chars, len(group))
        # Back off so the break does not land inside a key word.
        while end < len(group) and (end - 1) in protected and end in protected:
            end -= 1
        if end <= start:
            end = min(start + max_chars, len(group))
        pieces.append(group[start:end])
        start = end
    return pieces


def _piece_to_caption(piece: list[dict[str, Any]], keywords: list[str]) -> dict[str, Any]:
    text = "".join(c["char"] for c in piece)
    flags = [False] * len(text)
    for kw in keywords:
        at = text.find(kw)
        while at != -1:
            for k in range(at, at + len(kw)):
                flags[k] = True
            at = text.find(kw, at + 1)
    return {
        "start": round(piece[0]["start"], 3),
        "end": round(piece[-1]["end"], 3),
        "text": text,
        "range": piece[0].get("range"),
        "words": [{"word": c["char"], "start": round(c["start"], 3),
                   "end": round(c["end"], 3), "key": flags[i]}
                  for i, c in enumerate(piece)],
    }


def build_phrase_captions(tokens: list[dict[str, Any]], phrase_text: str,
                          keywords: list[str], max_chars: int = MAX_LINE_CHARS,
                          corrections: list[tuple[str, str]] | None = None,
                          beat_order: list[str] | None = None
                          ) -> list[dict[str, Any]]:
    """Caption lines split at punctuation the caller supplied.

    Most recognisers emit no punctuation, so a transcript cannot say where one
    clause ends and the next begins. Splitting by character count then glues them
    together - the tail of one clause plus the head of the next. Rather than guess,
    take the caller's punctuated text: split on punctuation and line breaks, and
    give each phrase the timing of its own characters by walking the word timings
    in order.

    Matching is done **per beat**, one script line per beat, for two reasons: a
    global walk drifts as soon as the wording diverges and collapses every caption
    onto one timestamp, and per-beat alignment keeps the timing bounded by the
    source range the line actually came from.
    """
    corrections = corrections or []

    def split_punctuation(text: str) -> list[str]:
        out = []
        for chunk in re.split(r"[，。、！？；：,.!?;:]\s*", text):
            chunk = chunk.strip()
            if chunk:
                out.append(chunk)
        return out

    raw_lines = [line.strip() for line in phrase_text.splitlines()]
    raw_lines = [line for line in raw_lines if line and not line.startswith("#")]

    # Group the script into beats. One line per beat is the intended shape; if the
    # caller writes several lines for one beat, they are joined so the grouping
    # still lines up 1:1 with the ranges.
    if beat_order and len(raw_lines) > len(beat_order):
        per_beat = max(1, len(raw_lines) // len(beat_order))
        groups = ["".join(raw_lines[i * per_beat:(i + 1) * per_beat])
                  for i in range(len(beat_order))]
        leftovers = raw_lines[per_beat * len(beat_order):]
        if leftovers:
            groups[-1] += "".join(leftovers)
    else:
        groups = raw_lines

    # Flatten the source words to characters, applying corrections first so a
    # deliberate wording change in the script still matches the source stream.
    chars: list[dict[str, Any]] = []
    for tok in tokens:
        word = tok["word"]
        for wrong, right in corrections:
            if word == wrong:
                word = right
        span = max(tok["end"] - tok["start"], 0.01)
        step = span / max(len(word), 1)
        cursor = tok["start"]
        for ch in word:
            chars.append({"char": ch, "start": cursor, "end": cursor + step,
                          "range": tok["range"]})
            cursor += step

    captions: list[dict[str, Any]] = []
    for gi, group_text in enumerate(groups):
        phrases = split_punctuation(group_text)
        if not phrases:
            continue
        # Restrict matching to this beat's characters; fall back to all of them if
        # the grouping and the ranges disagree.
        want_beat = beat_order[gi] if beat_order and gi < len(beat_order) else None
        pool = [c for c in chars if want_beat is None or c["range"] == want_beat]
        if not pool:
            pool = chars
        wanted = [c for phrase in phrases for c in phrase]
        assigned: list[dict[str, Any]] = []
        cursor = 0
        for want in wanted:
            found = cursor
            while found < len(pool) and pool[found]["char"] != want:
                found += 1
            if found >= len(pool):
                # Keep the walk local rather than snapping to the end of the pool,
                # which would collapse every remaining caption onto one timestamp.
                src = pool[min(cursor, len(pool) - 1)]
            else:
                src = pool[found]
                cursor = found + 1
            assigned.append({"char": want, "start": src["start"], "end": src["end"],
                             "range": src["range"]})
        pos = 0
        for phrase in phrases:
            piece = assigned[pos:pos + len(phrase)]
            pos += len(phrase)
            if not piece:
                continue
            for sub in _split_phrase(piece, keywords, max_chars):
                captions.append(_piece_to_caption(sub, keywords))
    return captions


def _split_evenly(text: str, start: float, end: float,
                  keys: set[int] | None = None) -> list[dict[str, Any]]:
    """Split text across a time span, one entry per character."""
    keys = keys or set()
    chars = list(text) or [" "]
    span = max(end - start, 0.05)
    step = span / len(chars)
    out, cursor = [], start
    for idx, ch in enumerate(chars):
        out.append({"word": ch, "start": round(cursor, 3),
                    "end": round(cursor + step, 3), "key": idx in keys})
        cursor += step
    return out


def _apply_corrections(captions: list[dict[str, Any]],
                       corrections: list[tuple[str, str]]) -> int:
    """Apply word corrections to assembled caption lines, preserving highlights.

    A correction cannot be applied per merged token: the cap on how far tokens
    merge (needed to keep distinct words apart) can fall inside the term being
    corrected, so a term becomes two units and neither matches. The assembled line
    always contains the whole term. Highlight positions are re-derived from
    character indices, so a replacement of a different length keeps the colour on
    the right characters.
    """
    changed = 0
    for cap in captions:
        before = cap["text"]
        after = before
        for wrong, right in corrections:
            after = after.replace(wrong, right)
        if after == before:
            continue
        keys: set[int] = set()
        pos = 0
        for word in cap["words"]:
            if word.get("key"):
                keys.update(range(pos, pos + len(word["word"])))
            pos += len(word["word"])
        cap["text"] = after
        cap["words"] = _split_evenly(after, cap["start"], cap["end"], keys)
        changed += 1
    return changed


def _emit(args, captions: list[dict[str, Any]], beats, raw_total: float,
          final_seconds: float, tokens: list[dict[str, Any]], keywords: list[str],
          corrections, corrected_lines: int) -> int:
    """Write the artifacts and print the script for human review."""
    beat_text: dict[str, str] = {}
    for tok in tokens:
        beat_text[tok["range"]] = beat_text.get(tok["range"], "") + tok["word"]
    for name in beat_text:
        for wrong, right in corrections:
            beat_text[name] = beat_text[name].replace(wrong, right)

    with open(os.path.join(args.out, "script.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"# {final_seconds:.1f}s at {args.speed}x, "
                 f"{len(captions)} caption lines\n")
        fh.write("\n".join(beat_text.get(name, "") for name, _, _ in beats) + "\n")
    with open(os.path.join(args.out, "plan.json"), "w", encoding="utf-8") as fh:
        json.dump({"ranges": beats, "speed": args.speed, "keywords": keywords,
                   "corrections": corrections,
                   "source_seconds": round(raw_total, 2),
                   "final_seconds": round(final_seconds, 2)},
                  fh, ensure_ascii=False, indent=1)
    with open(os.path.join(args.out, "captions.json"), "w", encoding="utf-8") as fh:
        json.dump({"segments": captions, "keywords": keywords,
                   "final_seconds": round(final_seconds, 2)},
                  fh, ensure_ascii=False, indent=1)

    print("=" * 82)
    print(f"SCRIPT ({final_seconds:.1f}s at {args.speed}x, {len(captions)} lines)")
    print("=" * 82)
    for name, lo, hi in beats:
        print(f"\n[{name}]  source {lo:.2f}-{hi:.2f} ({(hi-lo)/args.speed:.1f}s out)")
        print(f"  {beat_text.get(name, '')}")
    print()
    print(f"CAPTION LINES ({len(captions)})")
    for cap in captions:
        marks = "".join(w["word"] if w.get("key") else "*" for w in cap["words"])
        print(f"[{cap['start']:6.2f} -> {cap['end']:6.2f}] {cap['text']}")
        if any(w.get("key") for w in cap["words"]):
            print(f"{'':>18}  colour: {marks}")
    print()
    print(f"key terms: {'、'.join(keywords) if keywords else '(none)'}")
    print(f"coloured characters: "
          f"{sum(1 for c in captions for w in c['words'] if w.get('key'))}")
    if corrected_lines:
        print(f"lines corrected: {corrected_lines}")
    print(f"wrote {args.out}/script.txt, plan.json, captions.json")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--out", default="work")
    ap.add_argument("--beats", default="",
                    help="start:end source seconds, comma separated, in playback order")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--keywords", default="auto",
                    help="auto | none | comma-separated list")
    ap.add_argument("--phrases", default="",
                    help="the script WITH punctuation, as literal text or a file "
                         "path. Caption lines are cut at punctuation, so no line "
                         "joins two clauses and no phrase is split.")
    ap.add_argument("--corrections", default="", help="wrong:right,wrong:right")
    ap.add_argument("--list-only", action="store_true",
                    help="print the merged transcript and stop (write the script first)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    segments = load_transcript(args.transcript)

    # --phrases takes either a file or the text itself; a script is easier to keep
    # and review as a file, so a path is checked for first.
    phrase_text = args.phrases
    if phrase_text and os.path.isfile(phrase_text):
        with open(phrase_text, encoding="utf-8") as fh:
            phrase_text = fh.read()

    corrections: list[tuple[str, str]] = []
    for pair in args.corrections.split(","):
        if ":" in pair:
            wrong, _, right = pair.partition(":")
            corrections.append((wrong.strip(), right.strip()))

    if args.keywords == "auto":
        keywords = derive_keywords(segments)
    elif args.keywords == "none":
        keywords = []
    else:
        keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    if args.list_only or not args.beats:
        print("=" * 82)
        print("MERGED TRANSCRIPT - write the script from this, then choose the beats")
        print("=" * 82)
        for seg in segments:
            text = "".join(w["word"] for w in seg["words"])
            for wrong, right in corrections:
                text = text.replace(wrong, right)
            print(f"[{seg['start']:7.2f} -> {seg['end']:7.2f}] {text}")
        print()
        print(f"key terms derived from this transcript ({len(keywords)}): "
              f"{'、'.join(keywords) if keywords else '(none)'}")
        print("\nnext: write the script with punctuation, then rerun with "
              "--beats and --phrases")
        if args.list_only:
            return 0

    beats = []
    for idx, chunk in enumerate(args.beats.split(",")):
        chunk = chunk.strip()
        if not chunk:
            continue
        lo_s, _, hi_s = chunk.partition(":")
        if not hi_s:
            raise SystemExit(f"beat {chunk!r} must be start:end")
        beats.append((f"beat{idx}", float(lo_s), float(hi_s)))
    if not beats:
        raise SystemExit("no beats given")

    raw_total = sum(hi - lo for _, lo, hi in beats)
    final_seconds = raw_total / args.speed

    def locate(t: float):
        offset = 0.0
        for name, lo, hi in beats:
            if lo <= t < hi:
                return name, offset + (t - lo) / args.speed
            offset += (hi - lo) / args.speed
        return None, None

    # Map each word onto the beat it overlaps most, and onto the OUTPUT timeline.
    # Requiring a word to sit entirely inside one beat drops words that end exactly
    # on a boundary (44.24-44.70 against a beat ending at 44.70), and a dropped word
    # splits the written term across two caption lines.
    beat_offsets: list[tuple[str, float, float, float]] = []
    offset = 0.0
    for name, lo, hi in beats:
        span = (hi - lo) / args.speed
        beat_offsets.append((name, lo, hi, offset))
        offset += span

    tokens = []
    for seg in segments:
        for word in seg["words"]:
            best = None
            for name, lo, hi, out_off in beat_offsets:
                overlap = min(word["end"], hi) - max(word["start"], lo)
                if overlap > 0 and (best is None or overlap > best[3]):
                    best = (name, lo, hi, overlap, out_off)
            if best is None:
                continue
            name, lo, hi, _overlap, out_off = best
            start = out_off + max(0.0, word["start"] - lo) / args.speed
            end = out_off + min(hi - lo, max(0.0, word["end"] - lo)) / args.speed
            tokens.append({"word": word["word"], "start": start,
                           "end": max(end, start + 0.01), "range": name})
    tokens.sort(key=lambda w: w["start"])

    # Caption lines come from the recogniser's own sentence boundaries. Those are
    # the only reliable break points in a transcript: the audio of continuous
    # speech has almost no internal silence (measured: most sentences here contain
    # no pause >= 120ms), and there is no punctuation to split on. A sentence is a
    # complete clause, which is exactly the granularity a caption wants.
    if phrase_text:
        captions = build_phrase_captions(
            tokens, phrase_text, keywords, corrections=corrections,
            beat_order=[name for name, _, _ in beats])
        if not captions:
            raise SystemExit("--phrases produced no captions; check that its wording "
                             "matches the transcript")
        corrected = _apply_corrections(captions, corrections) if corrections else 0
        print("caption mode: phrases (breaks from --phrases, using | for a line break)")
        return _emit(args, captions, beats, raw_total, final_seconds,
                     tokens, keywords, corrections, corrected)

    captions = build_sentence_captions(tokens, keywords, corrections)
    corrected = _apply_corrections(captions, corrections) if corrections else 0
    print("caption mode: sentence (breaks at recogniser sentence boundaries)")
    return _emit(args, captions, beats, raw_total, final_seconds,
                 tokens, keywords, corrections, corrected)


def build_sentence_captions(tokens: list[dict[str, Any]], keywords: list[str],
                            corrections: list[tuple[str, str]] | None = None,
                            max_chars: int = MAX_LINE_CHARS) -> list[dict[str, Any]]:
    """One caption line per recogniser sentence, split only when too long.

    Sentence boundaries are the honest break points: continuous speech has no
    internal silence to detect and a transcript has no punctuation, so anything
    finer is a guess. A sentence that cannot fit is broken **at a word boundary**,
    never mid-word - so 产品 does not become 产 on one line and 品 on the next.

    The recogniser's own word boundaries are used directly rather than a character
    count over a flat character stream: that stream has no word boundaries left in
    it, so counting characters slices words in half.
    """
    by_range: dict[str, list[dict[str, Any]]] = {}
    for tok in tokens:
        by_range.setdefault(tok["range"], []).append(tok)

    captions: list[dict[str, Any]] = []
    for group in by_range.values():
        # Join adjacent single characters back into words before measuring line
        # width. The recogniser emits 渠 and 道 as separate tokens, so a line break
        # computed on raw tokens lands between them and renders 渠 / 道 across two
        # lines. Rejoining first keeps the written word atomic.
        words: list[dict[str, Any]] = []
        for tok in group:
            if (words and len(tok["word"]) == 1 and len(words[-1]["word"]) == 1
                    and tok["start"] - words[-1]["end"] < MAX_WORD_GAP
                    and len(words[-1]["word"]) < MAX_MERGE_CHARS):
                words[-1] = {"word": words[-1]["word"] + tok["word"],
                             "start": words[-1]["start"], "end": tok["end"],
                             "range": tok["range"]}
            else:
                words.append(dict(tok))

        pieces: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        width = 0
        for tok in words:
            token_len = len(tok["word"])
            # Break before this word if adding it would overflow and the line
            # already carries something.
            if current and width + token_len > max_chars:
                pieces.append(current)
                current, width = [], 0
            current.append(tok)
            width += token_len
        if current:
            pieces.append(current)
        for piece in pieces:
            chars: list[dict[str, Any]] = []
            for tok in piece:
                span = max(tok["end"] - tok["start"], 0.01)
                step = span / max(len(tok["word"]), 1)
                cursor = tok["start"]
                for ch in tok["word"]:
                    chars.append({"char": ch, "start": cursor,
                                  "end": cursor + step, "range": tok["range"]})
                    cursor += step
            captions.append(_piece_to_caption(chars, keywords))
    captions.sort(key=lambda c: c["start"])
    return captions


if __name__ == "__main__":
    sys.exit(main())
