"""Assemble the demo video: cards + recorded app segments + Gemini TTS narration + burned-in captions.

Run:  python3 build.py   (after tts.py, record.mjs and cards.mjs). Output: out/yorisoi-demo.mp4
"""

import json
import re
import subprocess
import wave
from pathlib import Path

DEMO = Path(__file__).parent
OUT = DEMO / "out"
FF = (DEMO / ".ffmpeg-path").read_text().strip()
FPS = 30
W, H = 1920, 1080
PAD = 1.0  # seconds of breathing room after each narration line

cfg = json.loads((DEMO / "narration.json").read_text())
marks = json.loads((OUT / "video" / "marks.json").read_text())
work = OUT / "work"
work.mkdir(exist_ok=True)


def run(*args, cwd=None):
    subprocess.run([FF, "-v", "error", "-y", *args], check=True, cwd=cwd)


def probe_duration(path: Path) -> float:
    r = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True)
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def trimmed_audio(seg_id: str) -> tuple[Path, float]:
    """Narration with leading/trailing silence removed; returns (path, seconds)."""
    src, dst = OUT / "audio" / f"{seg_id}.wav", work / f"{seg_id}.wav"
    run("-i", str(src), "-af",
        "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
        "silenceremove=start_periods=1:start_threshold=-45dB,areverse", "-ar", "48000", "-ac", "1", str(dst))
    with wave.open(str(dst)) as w:
        return dst, w.getnframes() / w.getframerate()


# Picture sits above a caption band so captions never cover the app.
PIC_W, PIC_H = 1680, 945
SCALE = (f"scale={PIC_W}:{PIC_H}:flags=lanczos,pad={W}:{H}:{(W - PIC_W) // 2}:0:color=0xf3f5f7,"
         f"fps={FPS},format=yuv420p")


def card_clip(seg_id: str, dur: float) -> Path:
    out = work / f"{seg_id}.v.mp4"
    run("-loop", "1", "-t", f"{dur:.3f}", "-i", str(OUT / "cards" / f"{seg_id}.png"),
        "-vf", f"{SCALE},fade=t=in:st=0:d=0.4", "-c:v", "libx264", "-crf", "18", "-preset", "medium", str(out))
    return out


# Waits on Gemini, per segment: (from mark, offset, to mark, offset). Each is compressed to ~1.6 s.
WAITS = {
    "s4_conversation": [("draft_click", 1.5, "plan_shown", -0.3)],
    "s5b_ito": [("draft_click", 1.5, "plan_shown", -0.3), ("review_click", 1.0, "review_shown", 0.0)],
    "s5c_nguyen": [("draft_click", 1.5, "plan_shown", -0.3), ("copies_click", 1.0, "copies_shown", 0.0)],
    "s6_approval": [("copies_click", 1.0, "copies_shown", 0.0)],
}
# Playback speed of the normal-speed pieces around the waits (before wait 1, between waits, after the last).
# The conversation step repeats what the viewer saw for Mrs Tanaka, so it plays faster for Ito and Nguyen.
SPEEDS = {"s5b_ito": [2.0, 1.4, 1.0], "s5c_nguyen": [2.0, 1.0, 1.0]}
IDLE_MIN = 20.0  # an unchanged screen longer than this is a recording stall, not a deliberate pause


def idle_spans(src: Path, a: float, b: float) -> list[tuple[float, float]]:
    """Stretches inside [a, b] where the picture does not change for IDLE_MIN seconds or more."""
    from PIL import Image, ImageChops  # imported here: only needed for app segments

    tmp = work / f"idle_{src.stem}"
    if tmp.exists():
        for f in tmp.iterdir():
            f.unlink()
    tmp.mkdir(exist_ok=True)
    run("-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(src), "-vf", "fps=2,scale=320:-1", str(tmp / "f_%05d.png"))
    frames = sorted(tmp.iterdir())
    spans, run_start, prev = [], None, None
    for i, f in enumerate(frames):
        im = Image.open(f).convert("L")
        still = prev is not None and sum(ImageChops.difference(im, prev).getdata()) / (im.width * im.height) < 0.15
        t = a + i / 2
        if still and run_start is None:
            run_start = t - 0.5
        if (not still or i == len(frames) - 1) and run_start is not None:
            if t - run_start >= IDLE_MIN:
                spans.append((run_start + 0.5, t - 0.5))
            run_start = None
        prev = im
    return spans


def app_clip(seg_id: str, dur: float) -> Path:
    """Cut the recording into pieces (Gemini waits and stalls compressed), then fit to the narration length."""
    m = marks[seg_id]
    src = OUT / "video" / f"{seg_id}.webm"
    waits = [(m[a] + da, m[b] + db) for a, da, b, db in WAITS.get(seg_id, [])]
    speeds = SPEEDS.get(seg_id, [1.0] * (len(waits) + 1))
    pieces, cursor = [], m["ready"]  # (start, end, speed); speed None = compress
    for k, (wa, wb) in enumerate(waits):
        pieces.append((cursor, wa, speeds[k]))
        pieces.append((wa, wb, None))
        cursor = wb
    pieces.append((cursor, m["end"], speeds[len(waits)]))
    expanded = []
    for a, b, speed in pieces:
        if speed is None or speed != 1.0 or b - a < IDLE_MIN:
            expanded.append((a, b, speed))
            continue
        c = a
        for ia, ib in idle_spans(src, a, b):
            print(f"  {seg_id}: compressing a {ib - ia:.1f}s unchanged stretch at {ia:.1f}s")
            expanded += [(c, ia, 1.0), (ia, ib, (ib - ia) / 0.5)]
            c = ib
        expanded.append((c, b, 1.0))
    parts = []
    for i, (a, b, speed) in enumerate(x for x in expanded if x[1] - x[0] > 0.05):
        speed = speed or max(1.0, (b - a) / 1.6)  # compress a model wait to ~1.6 s
        p = work / f"{seg_id}.p{i}.mp4"
        run("-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(src), "-an",
            "-vf", f"setpts=PTS/{speed:.4f},{SCALE}", "-c:v", "libx264", "-crf", "18", "-preset", "medium", str(p))
        parts.append(p)
    lst = work / f"{seg_id}.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
    joined = work / f"{seg_id}.joined.mp4"
    run("-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined))
    length = probe_duration(joined)
    out = work / f"{seg_id}.v.mp4"
    if length > dur:  # speed up gently to fit the narration
        vf = f"setpts=PTS*{dur / length:.5f}"
    else:  # hold the last frame
        vf = f"tpad=stop_mode=clone:stop_duration={dur - length + 0.05:.3f}"
    run("-i", str(joined), "-vf", f"{vf},fps={FPS},format=yuv420p", "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium", str(out))
    print(f"  {seg_id}: recorded {length:.1f}s fitted to {dur:.1f}s (x{length / dur:.2f})")
    return out


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


TARGET = 180.0  # the rules say 3-4 minutes; the upload field says up to 3 minutes. Exactly 3:00 meets both.

segments, captions, t = [], [], 0.0
order = cfg["segments"]
for k, seg in enumerate(order):
    audio, speech = trimmed_audio(seg["id"])
    dur = speech + PAD + (0.6 if seg["kind"] == "card" else 0.0)
    if k == len(order) - 1:  # the closing card absorbs whatever makes the total exactly TARGET
        built = sum(probe_duration(c) for c in segments)
        dur = TARGET - built + 0.2  # a little over; the final encode trims to TARGET exactly
        if dur < speech + 0.5:
            raise SystemExit(f"Narration too long for {TARGET}s: closing card would be {dur:.1f}s")
        print(f"  closing card held for {dur:.1f}s to reach {TARGET:.0f}s")
    video = card_clip(seg["id"], dur) if seg["kind"] == "card" else app_clip(seg["id"], dur)
    clip = work / f"{seg['id']}.mp4"
    run("-i", str(video), "-i", str(audio), "-filter_complex", f"[1:a]apad=whole_dur={dur:.3f},aresample=48000[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t", f"{dur:.3f}", str(clip))
    segments.append(clip)
    # Caption timing: sentences share the speech time in proportion to their length.
    sentences = [s.strip() for s in re.split(r"(?<=[.:;])\s+", seg["text"]) if s.strip()]
    total = sum(len(s) for s in sentences)
    c = t
    for s in sentences:
        span = speech * len(s) / total
        captions.append((c, c + span, s))
        c += span
    t += probe_duration(clip)

(work / "all.txt").write_text("".join(f"file '{p.name}'\n" for p in segments))
joined = work / "joined.mp4"
run("-f", "concat", "-safe", "0", "-i", str(work / "all.txt"), "-c", "copy", str(joined))

srt = work / "captions.srt"
srt.write_text("".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{text}\n\n" for i, (a, b, text) in enumerate(captions, 1)))
final = OUT / "yorisoi-demo.mp4"
style = ("FontName=Helvetica Neue,FontSize=10.5,PrimaryColour=&H00362B1D,BorderStyle=1,"
         "Outline=0,Shadow=0,MarginV=7,MarginL=40,MarginR=40,Alignment=2")
run("-i", str(joined.resolve()), "-vf", f"subtitles={srt.name}:force_style='{style}'",
    "-af", f"apad,atrim=0:{TARGET}", "-t", f"{TARGET}", "-c:v", "libx264", "-crf", "20", "-preset", "medium",
    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(final.resolve()), cwd=work)
print(f"wrote {final}  ({probe_duration(final):.2f} s)")
