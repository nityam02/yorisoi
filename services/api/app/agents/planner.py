"""Facts + hazard tools → a draft plan in the Cabinet Office form's fields.

Gemini writes the reasoning-heavy fields; code fills every factual field from the register,
the verified extraction and the hazard tools, and rejects citations that point nowhere.
"""

import json

from .. import llm
from ..config import settings
from ..models import CONSIDERATION_KEYS, PlannerOutput
from ..tools.routes import walking_route

SYSTEM = """あなたは日本の市町村の個別避難計画（内閣府様式例）の下書きを作るアシスタントです。
与えられた「根拠一覧」だけを使い、各項目に根拠ID（例: F3, P1, C2, H1, S2, RT1, R:household）を必ず付けてください。

規則:
- shelter_id は候補一覧の ID から一つだけ選ぶ。洪水に対応した指定緊急避難場所を優先し、その場所自体が深く浸水する想定の場合や、本人の移動能力で到達が難しい場合は理由を書く。
- 避難行動要支援者は原則として警戒レベル3（高齢者等避難）で避難を開始する（level3）。level4 を選ぶ場合は根拠を示す。
- 根拠一覧にない事実を書かない。分からないことは「要確認：…」と書き、根拠は空にする。
- special_notes（特記事項）は支援者が知るべき本人の状態、support_notes（避難支援時の留意事項）は当日の支援方法と経路上の注意。
- すべて日本語で、短く具体的に。"""


def evidence_catalogue(resident: dict, extraction: dict, brief: dict) -> dict[str, str]:
    cat: dict[str, str] = {}
    for key in ("name", "age", "sex", "address", "household", "care_level", "disability_certificate", "language", "register_notes"):
        if resident.get(key) not in (None, ""):
            cat[f"R:{key}"] = f"名簿 {key}: {resident[key]}"
    for f in extraction["facts"]:
        cat[f["id"]] = f"[{f['topic']}] {f['value']}（発言: {f['quote']}）"
    for p in extraction["people"]:
        cat[p["id"]] = f"[{p['role']}] {p['name']}（{p['relation']}） 電話:{p.get('phone') or '未聴取'}（発言: {p['quote']}）"
    for c in extraction["considerations"]:
        cat[c["id"]] = f"[配慮:{c['key']}] {c['detail']}（発言: {c['quote']}）"
    k = extraction["consent"]
    cat["K1"] = f"同意 計画作成:{k['plan_creation']} 情報提供:{k['share_with_supporters']}"
    flood = brief["home"]["flood"]
    cat["H1"] = f"自宅の想定浸水深（想定最大規模・洪水）: {flood['label_ja']}（状態 {flood['status']}）"
    for s in brief["shelters"]:
        site = s.get("flood_at_site") or {}
        cat[s["id"]] = (f"候補 {s['name']}（{s['address']}） 直線距離 {s['distance_m']}m 洪水対応:{'はい' if s['certified_for_flood'] else 'いいえ'}"
                        f" 敷地の想定浸水深:{site.get('label_ja', '不明')}")
    rt = brief.get("route_to_suggested")
    if rt:
        cat["RT1"] = (f"{brief['suggested_shelter_id']} までの経路 {rt['distance_m']}m（{rt['method']}）"
                      f" 経路上の最大想定浸水深: {rt['worst_flood_on_path'].get('label_ja')}")
    return cat


def _clean(cited: dict, valid: set[str], dropped: list[str]) -> dict:
    ok = [e for e in cited.get("evidence", []) if e in valid]
    dropped += [e for e in cited.get("evidence", []) if e not in valid]
    return {"text": cited["text"], "evidence": ok}


def draft(resident: dict, extraction: dict, brief: dict) -> dict:
    cat = evidence_catalogue(resident, extraction, brief)
    prompt = "根拠一覧:\n" + "\n".join(f"{k}: {v}" for k, v in cat.items())
    prompt += "\n\n候補避難場所 ID: " + ", ".join(s["id"] for s in brief["shelters"])
    out: PlannerOutput = llm.structured(settings.model_fast, SYSTEM, prompt, PlannerOutput, thinking="LOW")
    o = out.model_dump()

    valid = set(cat)
    dropped: list[str] = []
    shelters = {s["id"]: s for s in brief["shelters"]}
    shelter_overridden = o["shelter_id"] not in shelters
    shelter = shelters.get(o["shelter_id"]) or shelters.get(brief.get("suggested_shelter_id"))

    route = None
    if shelter:
        route = brief.get("route_to_suggested") if shelter["id"] == brief.get("suggested_shelter_id") \
            else walking_route((resident["lat"], resident["lon"]), (shelter["lat"], shelter["lon"]))

    people = extraction["people"]
    considerations = [{"key": c["key"], "label": CONSIDERATION_KEYS[c["key"]], "detail": c["detail"], "evidence": [c["id"]]}
                      for c in extraction["considerations"]]
    if resident.get("care_level") and not any(c["key"] == "long_term_care" for c in considerations):
        considerations.append({"key": "long_term_care", "label": CONSIDERATION_KEYS["long_term_care"],
                               "detail": resident["care_level"], "evidence": ["R:care_level"]})
    if resident.get("disability_certificate") and not any(c["key"] == "disability_certificate" for c in considerations):
        considerations.append({"key": "disability_certificate", "label": CONSIDERATION_KEYS["disability_certificate"],
                               "detail": resident["disability_certificate"], "evidence": ["R:disability_certificate"]})

    flood = brief["home"]["flood"]
    home_hazard = {"text": f"自宅（想定最大規模の洪水）の想定浸水深: {flood['label_ja']}", "evidence": ["H1"]}

    plan = {
        "person": {k: resident.get(k) for k in ("name", "kana", "birth_date", "age", "sex", "address", "phone", "guardian")},
        "household": {"text": resident.get("household_detail") or "", "evidence": ["R:household"]},
        "shelter": {
            "id": shelter["id"] if shelter else None,
            "name": shelter["name"] if shelter else "要確認",
            "address": shelter["address"] if shelter else "",
            "lat": shelter["lat"] if shelter else None,
            "lon": shelter["lon"] if shelter else None,
            "certified_for_flood": shelter["certified_for_flood"] if shelter else False,
            "flood_at_site": shelter.get("flood_at_site") if shelter else None,
            "distance_m": shelter["distance_m"] if shelter else None,
            "reason": _clean(o["shelter_reason"], valid, dropped),
            "overridden_by_code": shelter_overridden,
        },
        "route": route,
        "evacuation_timing": {
            "level": o["evacuation_timing"],
            "label": "警戒レベル3（高齢者等避難）で避難開始" if o["evacuation_timing"] == "level3" else "警戒レベル4（避難指示）で避難開始",
            "reason": _clean(o["timing_reason"], valid, dropped),
        },
        "transport": _clean(o["transport"], valid, dropped),
        "emergency_contacts": [p for p in people if p["role"] == "emergency_contact"],
        "supporters": [p for p in people if p["role"] == "supporter"],
        "considerations": considerations,
        "home_hazard": home_hazard,
        "special_notes": [_clean(x, valid, dropped) for x in o["special_notes"]],
        "support_notes": [_clean(x, valid, dropped) for x in o["support_notes"]],
        "items_to_take": [_clean(x, valid, dropped) for x in o["items_to_take"]],
        "consent": extraction["consent"],
    }
    return {"plan": plan, "evidence": cat, "dropped_citations": sorted(set(dropped)), "model": settings.model_fast,
            "planner_raw": json.loads(out.model_dump_json())}
