"""Data shapes. Plan fields mirror the Cabinet Office sample form (個別避難計画 様式例)
published in the 避難行動要支援者の避難行動支援に関する取組指針."""

from typing import Literal

from pydantic import BaseModel, Field

# The form's "considerations during evacuation" checklist (避難時に配慮しなくてはならない事項).
CONSIDERATION_KEYS = {
    "long_term_care": "介護保険の認定を受けている / certified for long-term care",
    "disability_certificate": "手帳所持 / holds a disability certificate",
    "intractable_disease": "難病等の医療費支給認定 / intractable-disease certification",
    "medical_device": "医療機器の装着等をしている / uses a medical device",
    "cannot_stand_or_walk": "立つことや歩行ができない / cannot stand or walk",
    "hearing": "音が聞こえない（聞き取りにくい） / cannot hear well",
    "vision": "物が見えない（見えにくい） / cannot see well",
    "understanding": "言葉や文字の理解が難しい / difficulty understanding words or text",
    "judgement": "危険なことを判断できない / cannot judge danger",
    "recognition": "顔を見ても知人や家族と分からない / does not recognise familiar faces",
    "other": "その他 / other",
}
ConsiderationKey = Literal[
    "long_term_care", "disability_certificate", "intractable_disease", "medical_device", "cannot_stand_or_walk",
    "hearing", "vision", "understanding", "judgement", "recognition", "other",
]


# ---------- What the extractor (Gemini) may return. Every item carries a verbatim quote. ----------

class QuotedFact(BaseModel):
    topic: Literal[
        "mobility", "bedroom_and_stairs", "medical_device", "power_needs", "medications", "communication",
        "household", "past_disaster_experience", "pets", "items_to_take", "evacuation_preference",
        "transport", "worries", "other",
    ]
    value: str = Field(description="Short factual statement in Japanese, as said in the conversation.")
    quote: str = Field(description="Exact words copied from the transcript that support the value.")


class QuotedPerson(BaseModel):
    role: Literal["supporter", "emergency_contact"]
    name: str
    relation: str = Field(description="Relationship to the resident, e.g. 長女, 隣人, 民生委員.")
    phone: str | None = None
    address: str | None = None
    notes: str | None = None
    quote: str = Field(description="Exact words copied from the transcript that mention this person.")


class QuotedConsideration(BaseModel):
    key: ConsiderationKey
    detail: str
    quote: str


class QuotedConsent(BaseModel):
    plan_creation: Literal["yes", "no", "unclear"]
    share_with_supporters: Literal["yes", "no", "unclear"]
    quote: str


class InterviewExtraction(BaseModel):
    facts: list[QuotedFact]
    people: list[QuotedPerson]
    considerations: list[QuotedConsideration]
    consent: QuotedConsent


# ---------- The plan the planner (Gemini) drafts; every item cites evidence ids. ----------

class CitedText(BaseModel):
    text: str
    evidence: list[str] = Field(description="Evidence ids such as F3, P1, H1, S2, R:household.")


class PlannerOutput(BaseModel):
    shelter_id: str = Field(description="Exactly one of the candidate shelter ids, e.g. S1.")
    shelter_reason: CitedText
    evacuation_timing: Literal["level3", "level4"] = Field(
        description="level3 = start at 警戒レベル3（高齢者等避難）; level4 = start at 警戒レベル4（避難指示）.")
    timing_reason: CitedText
    transport: CitedText
    special_notes: list[CitedText] = Field(description="特記事項: facts about the person a helper must know.")
    support_notes: list[CitedText] = Field(description="避難支援時の留意事項: how to help on the day, route cautions.")
    items_to_take: list[CitedText]


class Flag(BaseModel):
    id: str
    severity: Literal["critical", "warning", "info"]
    source: Literal["rule", "ai_review"]
    field: str
    message: str


class AuditEntry(BaseModel):
    at: str
    actor: str
    action: str
    detail: str = ""


class PlanStatus(BaseModel):
    status: Literal["draft", "reviewed_with_resident", "approved"] = "draft"


class TranscriptIn(BaseModel):
    transcript: str
    actor: str = "care_manager"


class PlanEdit(BaseModel):
    plan: dict
    actor: str = "care_manager"
    note: str = ""


class StatusChange(BaseModel):
    status: Literal["draft", "reviewed_with_resident", "approved"]
    actor: str


class OutputsRequest(BaseModel):
    kinds: list[Literal["easy_read", "supporter_card", "translation"]] = ["easy_read", "supporter_card"]
    language: str | None = None  # for translation, e.g. "vi", "en"
