"""Plan critic. Hard rules always run; the Gemini review can only add warnings or notes.

The critic flags. It never edits a plan.
"""

import json

from pydantic import BaseModel

from .. import llm
from ..config import settings
from ..models import Flag


def _has(plan: dict, key: str) -> bool:
    return any(c["key"] == key for c in plan.get("considerations", []))


def _any_text(plan: dict, *words: str) -> bool:
    blob = json.dumps(plan, ensure_ascii=False)
    return any(w in blob for w in words)


def rule_flags(plan: dict, brief: dict, extraction: dict | None, rejected: list | None = None,
               dropped_citations: list | None = None) -> list[dict]:
    flags: list[Flag] = []

    def add(fid, sev, field, msg):
        flags.append(Flag(id=fid, severity=sev, source="rule", field=field, message=msg))

    shelter = plan.get("shelter") or {}
    home = brief["home"]["flood"]

    if not shelter.get("id"):
        add("R-shelter-missing", "critical", "shelter", "No evacuation destination chosen.")
    else:
        if not shelter.get("certified_for_flood"):
            add("R-shelter-not-certified", "critical", "shelter",
                f"{shelter['name']} is not designated for floods in the GSI dataset. Choose a flood-designated site.")
        site = shelter.get("flood_at_site") or {}
        if site.get("status") == "in_zone" and site.get("class_id", 0) >= 2:
            add("R-shelter-in-zone", "warning", "shelter",
                f"The shelter site itself is in a mapped flood zone ({site['label_en']}). Confirm upper-floor refuge "
                "is available there, or choose another site.")
        if shelter.get("overridden_by_code"):
            add("R-shelter-overridden", "info", "shelter",
                "The model proposed a shelter outside the candidate list, so the nearest suitable candidate was used.")

    route = plan.get("route") or {}
    worst = route.get("worst_flood_on_path") or {}
    if worst.get("status") == "in_zone" and worst.get("class_id", 0) >= 2:
        add("R-route-depth", "warning", "route",
            f"The path to the shelter crosses a mapped flood zone ({worst['label_en']}). Leave early (Level 3) and avoid "
            "this path once water is rising.")
    if route.get("method") == "straight_line":
        add("R-route-straight", "info", "route", "Walking route not computed (no Routes API key); distance is straight-line.")

    if home["status"] == "in_zone" and home.get("class_id", 0) >= 3:
        add("R-home-deep", "critical" if plan["evacuation_timing"]["level"] != "level3" else "info", "evacuation_timing",
            f"Home flood depth is {home['label_en']} in the maximum-scale scenario, deeper than a ground floor. "
            "Staying home upstairs is not a safe plan; evacuation must start early.")
    if home["status"] == "no_mapped_zone":
        add("R-home-nodata", "info", "home_hazard",
            "No mapped flood zone at the home. This is not proof of safety: prefectural-river data is partial.")

    if plan["evacuation_timing"]["level"] != "level3":
        add("R-timing", "warning", "evacuation_timing",
            "People who need help evacuating should normally start at Alert Level 3 (高齢者等避難).")

    n_sup = len(plan.get("supporters", []))
    if n_sup == 0:
        add("R-supporters-none", "critical", "supporters", "No named supporter. Someone must be assigned to help on the day.")
    elif n_sup == 1:
        add("R-supporters-one", "warning", "supporters",
            "Only one supporter is named; the Cabinet Office form provides two slots so help still comes if one is away.")
    for p in plan.get("supporters", []) + plan.get("emergency_contacts", []):
        if not p.get("phone"):
            add(f"R-phone-{p['id']}", "warning", "supporters" if p["role"] == "supporter" else "emergency_contacts",
                f"No phone number recorded for {p['name']}.")
    if not plan.get("emergency_contacts"):
        add("R-contacts-none", "warning", "emergency_contacts", "No emergency contact recorded.")

    if _has(plan, "medical_device") or _any_text(plan, "酸素", "人工呼吸", "吸引", "電動ベッド"):
        add("R-power", "warning", "shelter",
            "A medical device that needs power is mentioned. Shelter power is not in the open data: confirm with the "
            "facility, or plan a welfare shelter (福祉避難所) with power.")

    mobility_limited = _has(plan, "cannot_stand_or_walk") or _any_text(plan, "車いす", "車椅子", "杖", "歩行器")
    transport_people = [e for e in (plan.get("transport") or {}).get("evidence", []) if e.startswith("P")]
    if mobility_limited and (shelter.get("distance_m") or 0) > 1000 and not transport_people:
        add("R-transport", "warning", "transport",
            f"Mobility is limited and the shelter is {shelter.get('distance_m')} m away, but transport is not tied to a "
            "named person or confirmed service. Confirm who drives, and in what vehicle.")

    consent = plan.get("consent") or {}
    if consent.get("share_with_supporters") != "yes":
        add("R-consent", "critical", "consent",
            "No clear consent to share this plan with supporters. It cannot be shared until consent is recorded.")

    for section in ("special_notes", "support_notes", "items_to_take"):
        for i, item in enumerate(plan.get(section, []), start=1):
            if not item.get("evidence") and not item.get("text", "").startswith("要確認"):
                add(f"R-unsupported-{section}-{i}", "warning", section,
                    f"\"{item.get('text', '')[:40]}\" has no supporting evidence. Confirm it or delete it.")
    if rejected:
        add("R-rejected", "info", "extraction",
            f"{len(rejected)} extracted item(s) were dropped because their quote is not in the transcript.")
    if dropped_citations:
        add("R-bad-citations", "info", "plan", f"Ignored citations to unknown evidence: {', '.join(dropped_citations)}.")
    return [f.model_dump() for f in flags]


class _Review(BaseModel):
    class Item(BaseModel):
        severity: str  # "warning" | "info"
        field: str
        message: str

    items: list[Item]


REVIEW_SYSTEM = """You review a draft individual evacuation plan (Japan, Cabinet Office form) for contradictions,
omissions and unsafe assumptions. Compare the plan with the evidence list. Report only concrete problems a care
manager should check, in English, one sentence each. Do not restate problems already in the existing flags.
Severity must be "warning" or "info". Return an empty list if there is nothing new."""


def ai_review(plan: dict, evidence: dict, existing: list[dict]) -> list[dict]:
    prompt = json.dumps({"plan": plan, "evidence": evidence, "existing_flags": [f["message"] for f in existing]},
                        ensure_ascii=False)
    try:
        out = llm.structured(settings.model_critic, REVIEW_SYSTEM, prompt, _Review)
    except llm.LLMUnavailable:
        out = llm.structured(settings.model_fast, REVIEW_SYSTEM, prompt, _Review)
    flags = []
    for i, it in enumerate(out.items[:8], start=1):
        sev = it.severity if it.severity in ("warning", "info") else "warning"
        flags.append(Flag(id=f"AI-{i}", severity=sev, source="ai_review", field=it.field, message=it.message).model_dump())
    return flags
