"""Yorisoi API. One Cloud Run service serves the API under /api and the web app at /."""

import csv
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import llm, store
from .agents import critic, extractor, planner, rewriter, transcriber
from .config import settings
from .hazard import hazard_brief, priority
from .models import OutputsRequest, PlanEdit, StatusChange, TranscriptIn

app = FastAPI(title="Yorisoi API", version="0.1.0")


def _resident_or_404(rid: str) -> dict:
    r = store.resident(rid)
    if not r:
        raise HTTPException(404, f"Unknown resident {rid}")
    return r


def _bundle_or_404(rid: str) -> dict:
    b = store.plans.get(rid)
    if not b:
        raise HTTPException(404, "No plan yet for this resident")
    return b


def _audit(bundle: dict, actor: str, action: str, detail: str = "") -> None:
    bundle.setdefault("audit", []).append({"at": store.now(), "actor": actor, "action": action, "detail": detail})


def _llm_guard(fn, *args):
    try:
        return fn(*args)
    except llm.LLMUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/health")
def health():
    return {"ok": True, "model_fast": settings.model_fast, "model_critic": settings.model_critic,
            "maps_routes": bool(settings.maps_api_key), "llm_configured": bool(settings.gemini_api_key or settings.use_vertex)}


@app.get("/api/residents")
def list_residents():
    rows = []
    for r in store.residents():
        brief = hazard_brief(r["lat"], r["lon"])
        b = store.plans.get(r["id"])
        rows.append({
            **{k: r[k] for k in ("id", "name", "name_en", "age", "address", "care_level", "household", "language")},
            "flood": brief["home"]["flood"],
            "priority": priority(r, brief),
            "plan_status": b["status"] if b else "none",
            "open_flags": sum(1 for f in (b or {}).get("flags", []) if f["severity"] == "critical"),
            "has_sample_interview": store.sample_interview(r["id"]) is not None,
        })
    rows.sort(key=lambda x: (-x["priority"]["score"], x["id"]))
    return {"residents": rows}


@app.get("/api/stats")
def stats():
    rs = store.residents()
    approved = sum(1 for r in rs if (store.plans.get(r["id"]) or {}).get("status") == "approved")
    return {"registered": len(rs), "approved_plans": approved, "coverage": round(approved / len(rs), 3) if rs else 0,
            "national_reference": {"registered": 6_696_718, "with_plans": 1_014_017, "coverage": 0.151,
                                   "as_of": "2026-04-01", "source": "Cabinet Office and FDMA survey"}}


@app.get("/api/residents/{rid}")
def get_resident(rid: str):
    r = _resident_or_404(rid)
    brief = hazard_brief(r["lat"], r["lon"])
    return {"resident": r, "hazard": brief, "priority": priority(r, brief), "plan": store.plans.get(rid),
            "sample_interview": store.sample_interview(rid)}


@app.post("/api/residents/{rid}/transcribe")
async def transcribe(rid: str, audio: UploadFile = File(...)):
    _resident_or_404(rid)
    data = await audio.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "Audio over 20 MB; upload a shorter recording")
    return {"transcript": _llm_guard(transcriber.transcribe, data, audio.content_type or "audio/webm")}


@app.post("/api/residents/{rid}/draft")
def draft(rid: str, body: TranscriptIn):
    r = _resident_or_404(rid)
    if len(body.transcript.strip()) < 20:
        raise HTTPException(400, "Transcript is too short")
    brief = hazard_brief(r["lat"], r["lon"])
    ex = _llm_guard(extractor.extract, body.transcript)
    pl = _llm_guard(planner.draft, r, ex["extraction"], brief)
    flags = critic.rule_flags(pl["plan"], brief, ex["extraction"], ex["rejected"], pl["dropped_citations"])
    bundle = {
        "resident_id": rid, "status": "draft", "created_at": store.now(), "updated_at": store.now(),
        "transcript": body.transcript, "extraction": ex["extraction"], "rejected": ex["rejected"],
        "evidence": pl["evidence"], "plan": pl["plan"], "dropped_citations": pl["dropped_citations"],
        "flags": flags, "outputs": {}, "models": {"extract": ex["model"], "plan": pl["model"]}, "audit": [],
    }
    _audit(bundle, body.actor, "draft_created", f"{len(ex['extraction']['facts'])} facts, {len(ex['rejected'])} dropped")
    store.plans.put(rid, bundle)
    return bundle


@app.post("/api/residents/{rid}/plan/review")
def review(rid: str):
    r = _resident_or_404(rid)
    b = _bundle_or_404(rid)
    brief = hazard_brief(r["lat"], r["lon"])
    rules = critic.rule_flags(b["plan"], brief, b["extraction"], b.get("rejected"), b.get("dropped_citations"))
    ai = _llm_guard(critic.ai_review, b["plan"], b["evidence"], rules)
    b["flags"] = rules + ai
    b["models"]["review"] = settings.model_critic
    _audit(b, "yorisoi", "ai_review", f"{len(ai)} AI notes")
    store.plans.put(rid, b)
    return b


@app.put("/api/residents/{rid}/plan")
def edit_plan(rid: str, body: PlanEdit):
    r = _resident_or_404(rid)
    b = _bundle_or_404(rid)
    if b["status"] == "approved":
        raise HTTPException(409, "Approved plans are locked; set status back to draft to edit")
    b["plan"] = body.plan
    b["updated_at"] = store.now()
    brief = hazard_brief(r["lat"], r["lon"])
    ai = [f for f in b.get("flags", []) if f["source"] == "ai_review"]
    b["flags"] = critic.rule_flags(b["plan"], brief, b["extraction"], b.get("rejected"), b.get("dropped_citations")) + ai
    b["outputs"] = {}  # outputs must be regenerated from the edited plan
    _audit(b, body.actor, "edited", body.note)
    store.plans.put(rid, b)
    return b


@app.post("/api/residents/{rid}/plan/status")
def set_status(rid: str, body: StatusChange):
    _resident_or_404(rid)
    b = _bundle_or_404(rid)
    if body.status == "approved":
        if b["status"] != "reviewed_with_resident":
            raise HTTPException(409, "Review the plan with the resident before approval")
        blocking = [f for f in b["flags"] if f["severity"] == "critical"]
        if blocking:
            raise HTTPException(409, f"{len(blocking)} critical flag(s) must be resolved first: "
                                     + "; ".join(f["message"] for f in blocking))
    b["status"] = body.status
    _audit(b, body.actor, f"status:{body.status}")
    store.plans.put(rid, b)
    return b


@app.post("/api/residents/{rid}/plan/outputs")
def outputs(rid: str, body: OutputsRequest):
    r = _resident_or_404(rid)
    b = _bundle_or_404(rid)
    out = b.setdefault("outputs", {})
    lang = body.language or (r["language"] if r["language"] != "ja" else "en")
    jobs = {"easy_read": (rewriter.easy_read, b["plan"]), "supporter_card": (rewriter.supporter_card, b["plan"]),
            "translation": (rewriter.translate, b["plan"], lang)}
    with ThreadPoolExecutor(max_workers=3) as pool:  # the three rewrites are independent
        futures = {k: pool.submit(_llm_guard, *jobs[k]) for k in body.kinds}
        results = {k: f.result() for k, f in futures.items()}
    for k, v in results.items():
        out[k] = {"language": lang, "text": v} if k == "translation" else v
    _audit(b, "yorisoi", "outputs_generated", ",".join(body.kinds))
    store.plans.put(rid, b)
    return b


@app.delete("/api/residents/{rid}/plan")
def reset_plan(rid: str):
    _resident_or_404(rid)
    store.plans.delete(rid)
    return {"ok": True}


@app.get("/api/residents/{rid}/plan/export.csv", response_class=PlainTextResponse)
def export_csv(rid: str):
    r = _resident_or_404(rid)
    b = _bundle_or_404(rid)
    p = b["plan"]
    sup = p.get("supporters", []) + [{}, {}]
    con = p.get("emergency_contacts", []) + [{}, {}]
    row = {
        "氏名": r["name"], "フリガナ": r.get("kana"), "生年月日": r.get("birth_date"), "年齢": r.get("age"), "性別": r.get("sex"),
        "住所": r.get("address"), "電話番号": r.get("phone"), "同居家族等": p["household"]["text"],
        "避難場所名称": p["shelter"]["name"], "避難場所住所": p["shelter"]["address"],
        "避難開始": p["evacuation_timing"]["label"],
        **{f"緊急時連絡先{i + 1}_{k}": con[i].get(v) for i in range(2) for k, v in (("氏名", "name"), ("続柄", "relation"), ("電話", "phone"))},
        **{f"避難支援等実施者{i + 1}_{k}": sup[i].get(v) for i in range(2) for k, v in (("氏名", "name"), ("続柄", "relation"), ("電話", "phone"))},
        "配慮事項": " / ".join(f"{c['label'].split(' / ')[0]}（{c['detail']}）" for c in p["considerations"]),
        "特記事項": " / ".join([p["home_hazard"]["text"]] + [x["text"] for x in p["special_notes"]]),
        "避難支援時の留意事項": " / ".join(x["text"] for x in p["support_notes"]),
        "持ち出し品": " / ".join(x["text"] for x in p["items_to_take"]),
        "情報提供への同意": p["consent"]["share_with_supporters"], "状態": b["status"],
    }
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(row))
    w.writeheader()
    w.writerow(row)
    return PlainTextResponse("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{rid}-plan.csv"'})


# Web app (built React files) served from the same service.
_dist: Path = settings.web_dist
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = _dist / path
        return FileResponse(target if path and target.is_file() else _dist / "index.html")
