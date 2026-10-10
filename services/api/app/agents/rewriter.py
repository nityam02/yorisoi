"""Approved facts → copies people actually read: easy-read Japanese, a supporter card, translations."""

import json

from .. import llm
from ..config import settings

LANG_NAMES = {"en": "English", "vi": "Vietnamese", "zh": "Simplified Chinese", "ko": "Korean", "pt": "Portuguese",
              "ne": "Nepali", "id": "Indonesian", "tl": "Tagalog"}

EASY_READ = """あなたは「やさしい日本語」の専門家です。個別避難計画の内容を、本人が読んで分かるように書き直してください。
- 1文は短く。むずかしい漢字にはふりがなを（かっこ）で付ける。
- 見出し: 「いつ にげる」「どこへ にげる」「だれが てつだう」「もっていく もの」「こまったら」
- 「だれが てつだう」には supporters（避難支援等実施者）だけを書く。emergency_contacts（家族などの連絡先）は「こまったら」に書く。
- 計画にない情報を足さない。電話番号は計画どおりに書く。Markdownで出力。"""

CARD = """個別避難計画から、避難支援者に渡す1枚のカードを作ってください（日本語、Markdown、A6に収まる長さ）。
項目: 対象者（氏名・住所）、避難開始のタイミング、避難先と経路の注意、本人への配慮（移動・医療機器・コミュニケーション）、
持ち出し品、緊急連絡先。計画にない情報を足さない。"""

TRANSLATE = """Translate this individual evacuation plan summary for the resident or family into {lang}.
Use plain, short sentences. Keep names, phone numbers and place names exactly; add the Japanese place name in
brackets after a translated name. Do not add information that is not in the plan. Output Markdown."""


def _plan_text(plan: dict) -> str:
    slim = {k: v for k, v in plan.items() if k not in ("route",)}
    return json.dumps(slim, ensure_ascii=False)


def easy_read(plan: dict) -> str:
    return llm.text(settings.model_fast, EASY_READ, _plan_text(plan), thinking="LOW")


def supporter_card(plan: dict) -> str:
    return llm.text(settings.model_fast, CARD, _plan_text(plan), thinking="LOW")


def translate(plan: dict, lang: str) -> str:
    return llm.text(settings.model_fast, TRANSLATE.format(lang=LANG_NAMES.get(lang, lang)), _plan_text(plan), thinking="LOW")
