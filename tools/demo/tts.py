"""Generate the narration with Gemini TTS. Run from services/api: uv run python ../../tools/demo/tts.py"""
import json, os, re, sys, time, wave
from pathlib import Path
sys.path.insert(0, ".")
from app import llm  # noqa: E402
from google.genai import types  # noqa: E402

DEMO = Path(__file__).parent
cfg = json.loads((DEMO / "narration.json").read_text())
out = DEMO / "out" / "audio"
out.mkdir(parents=True, exist_ok=True)
durations = {}
for seg in cfg["segments"]:
    path = out / f"{seg['id']}.wav"
    if not path.exists():
      r = None
      for attempt in range(6):  # free tier allows 3 TTS requests a minute
        try:
          r = llm.client().models.generate_content(
            model=os.getenv("TTS_MODEL", "gemini-3.8-flash-tts"),
            contents=seg["text"],
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=cfg["voice"])))))
          break
        except Exception as e:
          wait = float((re.findall(r"retry in ([0-9.]+)s", str(e)) or [25])[0]) + 2
          print("  rate limited, waiting", round(wait), "s"); time.sleep(wait)
      else:
        raise SystemExit(f"TTS still rate-limited for {seg['id']}; re-run later (finished segments are kept)")
      if True:
        data = r.candidates[0].content.parts[0].inline_data
        if data.mime_type == "audio/wav" or data.data[:4] == b"RIFF":
            path.write_bytes(data.data)
        else:  # raw 24 kHz 16-bit mono PCM
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(data.data)
    with wave.open(str(path)) as w:
        durations[seg["id"]] = round(w.getnframes() / w.getframerate(), 2)
    print(seg["id"], durations[seg["id"]], "s")
(out / "durations.json").write_text(json.dumps(durations, indent=1))
print("total", round(sum(durations.values()), 1), "s")
