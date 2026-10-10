"""Recorded conversation (audio) → verbatim Japanese transcript with speaker labels."""

from .. import llm
from ..config import settings

SYSTEM = """日本語の会話を一字一句そのまま書き起こしてください。要約・補正・言い換えをしないこと。
話者ごとに改行し、行頭に「ケアマネ:」「本人:」「家族:」のいずれかを付ける。聞き取れない部分は［不明］と書く。"""


def transcribe(audio: bytes, mime_type: str) -> str:
    return llm.text(settings.model_fast, SYSTEM, [llm.audio_part(audio, mime_type), "書き起こしてください。"], temperature=0.0, thinking="LOW")
