"""Interview → facts. Gemini extracts; code keeps only items whose quote is in the transcript."""

import re
import unicodedata

from .. import llm
from ..config import settings
from ..models import InterviewExtraction

SYSTEM = """あなたは日本の市町村で個別避難計画づくりを支援するアシスタントです。
ケアマネジャー等と本人・家族の会話の書き起こしから、計画に必要な事実だけを抽出してください。

厳守:
- 書き起こしで実際に述べられたことだけを抽出する。推測・一般論・補完をしない。
- すべての項目の quote には、書き起こしの文言をそのまま（一字一句）コピーする。要約しない。
- people: 避難を手伝える人は role=supporter、連絡を取る家族などは role=emergency_contact。電話番号は述べられた場合のみ。
- considerations: 様式の配慮事項チェック欄に当たる内容（歩行困難、医療機器、聴覚、理解、判断、介護認定、手帳など）。
- consent: 計画作成への同意と、支援者等への情報提供への同意。はっきりしなければ unclear。
- value や detail は日本語で簡潔に。"""

_PUNCT = re.compile(r"[\s、。，．,.!！?？「」『』（）()・…ー〜~\-—–‐‑−:：;；\"'“”‘’]")


def _norm(s: str) -> str:
    return _PUNCT.sub("", unicodedata.normalize("NFKC", s))


def _supported(quote: str, transcript_norm: str) -> bool:
    q = _norm(quote)
    if len(q) < 2:
        return False
    if q in transcript_norm:
        return True
    # Allow a quote stitched from two adjacent fragments ("A … B"): both halves must appear.
    parts = [p for p in re.split(r"[…]|\.\.\.", quote) if _norm(p)]
    return len(parts) > 1 and all(_norm(p) in transcript_norm for p in parts)


def extract(transcript: str) -> dict:
    raw: InterviewExtraction = llm.structured(
        settings.model_fast,
        SYSTEM,
        f"書き起こし:\n<<<\n{transcript}\n>>>",
        InterviewExtraction,
        thinking="LOW",
    )
    tnorm = _norm(transcript)
    kept = {"facts": [], "people": [], "considerations": [], "consent": None}
    rejected = []

    for i, f in enumerate(raw.facts, start=1):
        item = {"id": f"F{i}", **f.model_dump()}
        (kept["facts"] if _supported(f.quote, tnorm) else rejected).append(item)
    for i, p in enumerate(raw.people, start=1):
        item = {"id": f"P{i}", **p.model_dump()}
        (kept["people"] if _supported(p.quote, tnorm) else rejected).append(item)
    for i, c in enumerate(raw.considerations, start=1):
        item = {"id": f"C{i}", **c.model_dump()}
        (kept["considerations"] if _supported(c.quote, tnorm) else rejected).append(item)

    consent = {"id": "K1", **raw.consent.model_dump()}
    if not _supported(raw.consent.quote, tnorm):
        rejected.append(dict(consent))
        consent.update(plan_creation="unclear", share_with_supporters="unclear", quote="")
    kept["consent"] = consent
    return {"extraction": kept, "rejected": rejected, "model": llm.last_model()}
