"""Deterministic parts only: no network, no Gemini."""

import io

import pytest
from PIL import Image

from app.agents import critic, extractor
from app.hazard import priority
from app.tools import gsi


def _tile(rgba):
    buf = io.BytesIO()
    Image.new("RGBA", (256, 256), rgba).save(buf, "PNG")
    return buf.getvalue()


@pytest.mark.parametrize("rgb,cid", [(row[0], row[1]) for row in gsi.FLOOD_LEGEND])
def test_every_legend_colour_maps_to_its_class(monkeypatch, rgb, cid):
    monkeypatch.setattr(gsi, "_cached_get", lambda url, kind: _tile((*rgb, 255)))
    d = gsi.flood_depth(34.6, 133.7)
    assert d.status == "in_zone" and d.class_id == cid


def test_transparent_pixel_is_no_mapped_zone_not_safe(monkeypatch):
    monkeypatch.setattr(gsi, "_cached_get", lambda url, kind: _tile((0, 0, 0, 0)))
    d = gsi.flood_depth(34.6, 133.7)
    assert d.status == "no_mapped_zone" and "not proof of safety" in d.label_en


def test_missing_tiles_fall_back_and_report_no_zone(monkeypatch):
    monkeypatch.setattr(gsi, "_cached_get", lambda url, kind: None)
    assert gsi.flood_depth(34.6, 133.7).status == "no_mapped_zone"


def test_unknown_colour_is_reported(monkeypatch):
    monkeypatch.setattr(gsi, "_cached_get", lambda url, kind: _tile((10, 200, 30, 255)))
    assert gsi.flood_depth(34.6, 133.7).status == "unknown_colour"


TRANSCRIPT = "本人: 長女の山口美和です。携帯は090-0000-1111です。\n本人: 一階の和室で寝ています。"


def test_quote_must_appear_in_transcript():
    t = extractor._norm(TRANSCRIPT)
    assert extractor._supported("長女の山口美和です", t)
    assert extractor._supported("携帯は０９０−0000−1111です", t)  # full-width digits normalise
    assert not extractor._supported("二階で寝ています", t)
    assert not extractor._supported("。", t)


def _plan(**over):
    plan = {
        "shelter": {"id": "S1", "name": "X", "certified_for_flood": True, "flood_at_site": {"status": "no_mapped_zone"},
                    "distance_m": 500},
        "route": {"method": "google_routes_walk", "worst_flood_on_path": {"status": "no_mapped_zone", "class_id": 0}},
        "evacuation_timing": {"level": "level3"},
        "transport": {"text": "徒歩", "evidence": ["F1"]},
        "supporters": [{"id": "P1", "role": "supporter", "name": "A", "phone": "1"},
                       {"id": "P2", "role": "supporter", "name": "B", "phone": "2"}],
        "emergency_contacts": [{"id": "P3", "role": "emergency_contact", "name": "C", "phone": "3"}],
        "considerations": [],
        "special_notes": [], "support_notes": [], "items_to_take": [],
        "consent": {"share_with_supporters": "yes"},
    }
    plan.update(over)
    return plan


BRIEF = {"home": {"flood": {"status": "in_zone", "class_id": 2, "label_en": "0.5–3 m"}}}


def _ids(flags):
    return {f["id"] for f in flags}


def test_clean_plan_has_no_warnings_or_criticals():
    flags = critic.rule_flags(_plan(), BRIEF, None)
    assert not [f for f in flags if f["severity"] in ("critical", "warning")]


def test_uncertified_shelter_is_critical():
    p = _plan(shelter={**_plan()["shelter"], "certified_for_flood": False})
    assert "R-shelter-not-certified" in _ids(critic.rule_flags(p, BRIEF, None))


def test_missing_consent_blocks():
    flags = critic.rule_flags(_plan(consent={"share_with_supporters": "unclear"}), BRIEF, None)
    assert any(f["id"] == "R-consent" and f["severity"] == "critical" for f in flags)


def test_oxygen_needs_power_check():
    p = _plan(special_notes=[{"text": "在宅酸素を使用", "evidence": ["F2"]}])
    assert "R-power" in _ids(critic.rule_flags(p, BRIEF, None))


def test_one_supporter_and_unsupported_note_warn():
    p = _plan(supporters=_plan()["supporters"][:1], support_notes=[{"text": "根拠のない記述", "evidence": []}])
    ids = _ids(critic.rule_flags(p, BRIEF, None))
    assert "R-supporters-one" in ids and "R-unsupported-support_notes-1" in ids


def test_wheelchair_far_shelter_without_named_driver_warns():
    p = _plan(considerations=[{"key": "cannot_stand_or_walk"}], shelter={**_plan()["shelter"], "distance_m": 1500},
              transport={"text": "福祉タクシーなど", "evidence": ["F3"]})
    assert "R-transport" in _ids(critic.rule_flags(p, BRIEF, None))
    p["transport"] = {"text": "中村さんの車", "evidence": ["P1"]}
    assert "R-transport" not in _ids(critic.rule_flags(p, BRIEF, None))


def test_missing_data_raises_priority():
    brief = {"home": {"flood": {"status": "in_zone", "class_id": 3}}}
    known = priority({"household": "with_family", "mobility": "independent", "medical_device": False}, brief)
    unknown = priority({"household": None, "mobility": None, "medical_device": None}, brief)
    assert unknown["score"] > known["score"]


def test_consent_limited_to_named_people_warns():
    p = _plan(consent={"share_with_supporters": "yes", "quote": "学校と鈴木さんには見せていいです。ほかの人は、ちょっと心配です。"})
    assert "R-consent-limited" in _ids(critic.rule_flags(p, BRIEF, None))


def test_multi_speaker_quote_needs_every_sentence_verbatim():
    t = extractor._norm("本人: 計画を作るのはかまわん。\n家族: 近所の人に知らせるのも、うちは構いません。\n本人: ああ、それでええ。")
    assert extractor._supported("計画を作るのはかまわん。近所の人に知らせるのも、うちは構いません。", t)
    assert extractor._supported("家族: 近所の人に知らせるのも、うちは構いません。\n本人: ああ、それでええ。", t)
    assert not extractor._supported("計画を作るのはかまわん。誰にでも見せていい。", t)
