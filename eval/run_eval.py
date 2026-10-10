"""Extraction evaluation on the three sample interviews.

Run from services/api:  uv run python ../../eval/run_eval.py [runs]
Prints per-resident recall and an overall summary, plus which model answered.
Each run makes 1 Gemini call per interview; results vary run to run, so report the spread.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")
from app import llm, store  # noqa: E402
from app.agents import critic, extractor  # noqa: E402

GT = json.loads((Path(__file__).parent / "ground_truth.json").read_text(encoding="utf-8"))
digits = lambda s: re.sub(r"\D", "", s or "")  # noqa: E731


def score(rid: str, ex: dict) -> dict:
    gt, e = GT[rid], ex["extraction"]
    people = {r: [p for p in e["people"] if p["role"] == r] for r in ("supporter", "emergency_contact")}

    def found(want, role):
        hits = [p for p in people[role] if want["name"] in p["name"]]
        return bool(hits), bool(hits) and (want["phone"] is None or digits(hits[0].get("phone")) == digits(want["phone"]))

    person_checks = [found(w, "supporter") for w in gt["supporters"]] + [found(w, "emergency_contact") for w in gt["emergency_contacts"]]
    fact_text = json.dumps(e, ensure_ascii=False)
    plan_like = {"consent": e["consent"]}
    limited_flag = any(f["id"] == "R-consent-limited" for f in critic.rule_flags(
        {**_blank_plan(), **plan_like}, {"home": {"flood": {"status": "no_mapped_zone"}}}, e))
    return {
        "people_found": sum(a for a, _ in person_checks), "people_total": len(person_checks),
        "phones_correct": sum(b for _, b in person_checks),
        "considerations_found": sum(k in {c["key"] for c in e["considerations"]} for k in gt["considerations"]),
        "considerations_total": len(gt["considerations"]),
        "facts_found": sum(k in fact_text for k in gt["facts"]), "facts_total": len(gt["facts"]),
        "consent_ok": e["consent"]["share_with_supporters"] == gt["consent_share"],
        "limited_consent_flagged": limited_flag if gt.get("consent_limited") else None,
        "kept_items": len(e["facts"]) + len(e["people"]) + len(e["considerations"]),
        "dropped_unsupported": len(ex["rejected"]),
        "model": ex["model"],
    }


def _blank_plan():
    return {"shelter": {"id": "S1", "certified_for_flood": True}, "route": {}, "evacuation_timing": {"level": "level3"},
            "transport": {"evidence": []}, "supporters": [], "emergency_contacts": [], "considerations": [],
            "special_notes": [], "support_notes": [], "items_to_take": []}


if __name__ == "__main__":
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    totals = {}
    for n in range(runs):
        for rid in GT:
            if rid.startswith("_"):
                continue
            s = score(rid, extractor.extract(store.sample_interview(rid)))
            print(f"run {n + 1} {rid}: {json.dumps(s, ensure_ascii=False)}")
            for k, v in s.items():
                if isinstance(v, bool) or isinstance(v, int):
                    totals[k] = totals.get(k, 0) + int(v)
    print("\nTOTAL over", runs, "run(s):")
    print(f"  people found        {totals['people_found']}/{totals['people_total']}")
    print(f"  phone numbers right {totals['phones_correct']}/{totals['people_total']}")
    print(f"  needs found         {totals['considerations_found']}/{totals['considerations_total']}")
    print(f"  key facts found     {totals['facts_found']}/{totals['facts_total']}")
    print(f"  consent correct     {totals['consent_ok']}/{3 * runs}")
    print(f"  items kept {totals['kept_items']}, dropped for no verbatim quote {totals['dropped_unsupported']}")
