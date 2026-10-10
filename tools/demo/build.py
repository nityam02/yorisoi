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
PAD = 0.5  # seconds of breathing room after each narration line

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


def app_clip(seg_id: str, dur: float) -> Path:
    """Cut the recording into pieces (waiting stretches compressed), then fit to the narration length."""
    m = marks[seg_id]
    src = OUT / "video" / f"{seg_id}.webm"
    pieces = []  # (start, end, speed)
    if seg_id == "s4_conversation":
        pieces = [(m["ready"], m["draft_click"] + 1.5, 1.0), (m["draft_click"] + 1.5, m["plan_shown"] - 0.3, None),
                  (m["plan_shown"] - 0.3, m["end"], 1.0)]
    elif seg_id == "s6_approval":
        pieces = [(m["ready"], m["copies_click"] + 1.0, 1.0), (m["copies_click"] + 1.0, m["copies_shown"], None),
                  (m["copies_shown"], m["end"], 1.0)]
    else:
        pieces = [(m["ready"], m["end"], 1.0)]
    parts = []
    for i, (a, b, speed) in enumerate(pieces):
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


segments, captions, t = [], [], 0.0
for seg in cfg["segments"]:
    audio, speech = trimmed_audio(seg["id"])
    dur = speech + PAD + (0.6 if seg["kind"] == "card" else 0.0)
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
    t += dur

(work / "all.txt").write_text("".join(f"file '{p.name}'\n" for p in segments))
joined = work / "joined.mp4"
run("-f", "concat", "-safe", "0", "-i", str(work / "all.txt"), "-c", "copy", str(joined))

srt = work / "captions.srt"
srt.write_text("".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{text}\n\n" for i, (a, b, text) in enumerate(captions, 1)))
final = OUT / "yorisoi-demo.mp4"
style = ("FontName=Helvetica Neue,FontSize=10.5,PrimaryColour=&H00362B1D,BorderStyle=1,"
         "Outline=0,Shadow=0,MarginV=7,MarginL=40,MarginR=40,Alignment=2")
run("-i", str(joined.resolve()), "-vf", f"subtitles={srt.name}:force_style='{style}'", "-c:v", "libx264", "-crf", "20",
    "-preset", "medium", "-c:a", "copy", "-movflags", "+faststart", str(final.resolve()), cwd=work)
print(f"wrote {final}  ({probe_duration(final):.1f} s)")
