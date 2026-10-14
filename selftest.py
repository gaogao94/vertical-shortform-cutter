"""Self-test for the skill: builds a synthetic CJK transcript + video and runs the
whole pipeline. No real content is used - the words are placeholders chosen to
exercise the merge, correction and keyword logic.

Run:  python selftest.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "scripts")


def find_ffmpeg():
    """PATH first, then a sibling tools/bin - the same order render.py uses."""
    import shutil
    found = shutil.which("ffmpeg")
    if found:
        return found
    for cand in (os.path.join(HERE, "..", "..", "tools", "bin", "ffmpeg.exe"),
                 os.path.join(HERE, "..", "..", "..", "tools", "bin", "ffmpeg.exe"),
                 os.path.join(HERE, "bin", "ffmpeg.exe")):
        if os.path.isfile(cand):
            return os.path.abspath(cand)
    raise SystemExit("ffmpeg not found: put it on PATH or install it beside this file")


FFMPEG = find_ffmpeg()
WORK = tempfile.mkdtemp(prefix="skill-selftest-")
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name}  {detail}")


def build_transcript(path):
    """Single-character CJK tokens, deliberately: that is what a real ASR emits,
    and it exercises the merge -> correct -> re-split path."""
    def chars(text, t0, per=0.16):
        words, t = [], t0
        for ch in text:
            words.append({"word": ch, "start": round(t, 3), "end": round(t + per, 3)})
            t += per
        return words, t

    segments = []
    # A: opening question.
    text_a = "你要拿什么产品去做"
    words_a, end_a = chars(text_a, 10.0)
    segments.append({"start": 10.0, "end": round(end_a, 2), "text": text_a, "words": words_a})
    # B: the payoff, holding a mis-transcribed 数字 that must be corrected. Written
    #    as adjacent characters so the merge cap can split the term across units -
    #    the case that shipped a wrong word to the viewer once.
    text_b = "我不能把手里的数字卖给一堆人"
    words_b, end_b = chars(text_b, 30.0)
    segments.append({"start": 30.0, "end": round(end_b, 2), "text": text_b, "words": words_b})
    # C: filler, excluded by the caller's beat choice.
    text_c = "对吧是不是"
    words_c, end_c = chars(text_c, 45.0)
    segments.append({"start": 45.0, "end": round(end_c, 2), "text": text_c, "words": words_c})
    # D: closing line.
    text_d = "没有客户项目就做不起来"
    words_d, end_d = chars(text_d, 52.0)
    segments.append({"start": 52.0, "end": round(end_d, 2), "text": text_d, "words": words_d})
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"segments": segments}, fh, ensure_ascii=False, indent=1)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace")


print("=" * 74)
print("building synthetic source")
print("=" * 74)
transcript = os.path.join(WORK, "words.json")
build_transcript(transcript)
video = os.path.join(WORK, "src.mp4")
# Pink noise, not a sine: loudnorm's dynamic mode measures EBU R128 loudness, and a
# constant test tone trips it into thinking the signal is silence (measured -70
# LUFS output). Speech-like broadband noise is what the normaliser is built for.
proc = run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=0x203040:s=720x1280:r=30:d=60",
            "-f", "lavfi", "-i",
            "anoisesrc=color=pink:amplitude=0.05:duration=60:sample_rate=44100",
            "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
            "-c:a", "aac", video])
check("synthetic video built", os.path.isfile(video), proc.stderr[-300:])
print(f"  source: 720x1280, 60s -> {video}")

print()
print("=" * 74)
print("step 1: build.py --list-only (read the transcript, derive key terms)")
print("=" * 74)
listing = run([sys.executable, os.path.join(SCRIPTS, "build.py"),
               "--transcript", transcript, "--out", WORK, "--list-only"])
out = listing.stdout or ""
print("\n".join(out.splitlines()[-5:]) if out else listing.stderr[-600:])
check("--list-only exits 0", listing.returncode == 0, listing.stderr[-400:])
check("--list-only refuses to cut (no plan written)",
      not os.path.isfile(os.path.join(WORK, "plan.json")))
check("key terms printed", "key terms" in out, out[-200:])

print()
print("=" * 74)
print("step 2: build.py --beats (cut) with an explicit correction")
print("=" * 74)
build_cmd = [sys.executable, os.path.join(SCRIPTS, "build.py"),
             "--transcript", transcript, "--out", WORK,
             "--beats", "10:14.4,30:36.8,52:58.4",
             "--speed", "1.35",
             "--keywords", "产品,客户,项目",
             "--corrections", "数字:产品"]
proc = run(build_cmd)
print("\n".join((proc.stdout or "").splitlines()[-12:]) if proc.stdout else proc.stderr[-600:])
check("build.py exits 0", proc.returncode == 0, proc.stderr[-400:])

plan_path = os.path.join(WORK, "plan.json")
caps_path = os.path.join(WORK, "captions.json")
script_path = os.path.join(WORK, "script.txt")
check("plan.json written", os.path.isfile(plan_path))
check("captions.json written", os.path.isfile(caps_path))
check("script.txt written", os.path.isfile(script_path))

if os.path.isfile(caps_path):
    caps = json.load(open(caps_path, encoding="utf-8"))
    segs = caps["segments"]
    script = "".join(s["text"] for s in segs)
    coloured = sum(1 for s in segs for w in s["words"] if w.get("key"))
    longest = max(s["end"] - s["start"] for s in segs)

    check("filler excluded by the beat choice", "对吧" not in script, script[:60])
    check("key words coloured (>0)", coloured > 0, str(coloured))

    # The regression that shipped once: correction applied per merged unit, and the
    # merge cap had split 数字 across two units, so the mis-transcribed word
    # survived into the rendered caption.
    check("correction applied to the caption text",
          "数字" not in script and "产品" in script, script[:80])

    check("no line exceeds 2.7s", longest <= 2.7, f"{longest:.2f}")
    # Read the limit from the module instead of hardcoding it, so changing the
    # default cannot leave this assertion silently stale.
    sys.path.insert(0, SCRIPTS)
    import build as build_mod  # noqa: E402
    limit = build_mod.MAX_LINE_CHARS
    check(f"no line exceeds {limit} chars",
          all(len(s["text"]) <= limit for s in segs),
          str(max(len(s["text"]) for s in segs)))
    check("output timeline is compressed",
          caps["final_seconds"] < 20, str(caps["final_seconds"]))
    check("keyword list recorded in the plan",
          json.load(open(plan_path, encoding="utf-8"))["keywords"] == ["产品", "客户", "项目"])

    # A replacement of a different length must not shift the highlight onto the
    # wrong characters: every coloured character must still be a keyword character.
    coloured_chars = "".join(w["word"] for s in segs for w in s["words"] if w.get("key"))
    check("highlight stays aligned after a length change",
          bool(coloured_chars) and all(c in "产品客户项目" for c in coloured_chars),
          repr(coloured_chars))

    # A key phrase must never be cut in half by a line break.
    KW = ["产品", "客户", "项目"]
    cut_keys = []
    for idx, seg in enumerate(segs[:-1]):
        tail, head = seg["text"][-3:], segs[idx + 1]["text"][:3]
        for kw in KW:
            for size in range(1, len(kw)):
                if tail.endswith(kw[:size]) and head.startswith(kw[size:]):
                    cut_keys.append((kw, seg["text"], segs[idx + 1]["text"]))
    check("no key phrase cut by a line break", not cut_keys, str(cut_keys))

print()
print("=" * 74)
print("step 3: render.py")
print("=" * 74)
rendered = os.path.join(WORK, "short.mp4")
proc = run([sys.executable, os.path.join(SCRIPTS, "render.py"),
            "--video", video, "--plan", plan_path, "--captions", caps_path,
            "--output", rendered, "--ffmpeg", FFMPEG])
print("\n".join((proc.stdout or "").splitlines()[-6:]) if proc.stdout else "")
if proc.returncode != 0:
    print(proc.stderr[-900:])
check("render.py exits 0", proc.returncode == 0)
check("output written", os.path.isfile(rendered))
check("ass sidecar written", os.path.isfile(os.path.splitext(rendered)[0] + ".ass"))

if os.path.isfile(rendered):
    # Verify through the same fallback render.py uses, so this works whether or
    # not ffprobe exists on the machine.
    sys.path.insert(0, SCRIPTS)
    import render as render_mod  # noqa: E402
    info = render_mod.probe(rendered, FFMPEG)
    vid = next((s for s in info.get("streams", []) if s["codec_type"] == "video"), {})
    check("output frame rate is a clean 30",
          str(vid.get("r_frame_rate")) == "30/1", str(vid.get("r_frame_rate")))
    check("output is vertical",
          vid.get("width") == 720 and vid.get("height") == 1280,
          f"{vid.get('width')}x{vid.get('height')}")

    # Loudness via RMS rather than an ebur128 report: that report carries per-frame
    # lines, so a regex over it can latch onto an interval figure and report a
    # false failure.
    stats = run([FFMPEG, "-hide_banner", "-i", rendered, "-vn",
                 "-af", "astats=metadata=1:reset=0", "-f", "null", "NUL"])
    text = stats.stderr or ""
    rms = re.search(r"RMS level dB:\s*(-?\d+\.\d+)", text)
    peak = re.search(r"Peak level dB:\s*(-?\d+\.\d+)", text)
    rms_db = float(rms.group(1)) if rms else None
    peak_db = float(peak.group(1)) if peak else None
    check("export carries real signal (RMS above -30 dBFS)",
          rms_db is not None and rms_db > -30.0, f"RMS {rms_db} dB")
    # Assert against the digital ceiling, not a headroom figure. loudnorm's
    # true-peak target is a limiter, and synthetic broadband noise can land within
    # a fraction of a dB of it; a tighter bound produced an intermittent false
    # failure on a file that was perfectly well formed.
    check("export does not clip (peak below 0 dBFS)",
          peak_db is not None and peak_db < 0.0, f"peak {peak_db} dB")
    check("source amplitude was raised, not passed through",
          rms_db is not None and rms_db > -25.0, f"RMS {rms_db} dB")

print()
print("=" * 74)
print(f"RESULT: {passed} passed, {failed} failed")
print(f"work dir: {WORK}")
print("=" * 74)
sys.exit(0 if failed == 0 else 1)
