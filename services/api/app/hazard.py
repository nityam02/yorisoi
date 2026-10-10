"""Pre-visit hazard brief: everything the care worker should know before knocking."""

from functools import lru_cache

from .tools.gsi import ATTRIBUTIONS, flood_depth, shelters_near
from .tools.routes import walking_route


def _shelter_rank(s: dict) -> tuple:
    """Prefer flood-certified sites that are not themselves deep in the flood zone, then nearer."""
    site = s.get("flood_at_site") or {}
    deep = site.get("status") == "in_zone" and site.get("class_id", 0) >= 3  # 3 m or deeper at the site
    return (not s["certified_for_flood"], deep, s["distance_m"])


@lru_cache(maxsize=256)
def hazard_brief(lat: float, lon: float) -> dict:
    home = flood_depth(lat, lon).as_dict()
    shelters = [s.as_dict() for s in shelters_near(lat, lon, hazard_code=1)]
    ranked = sorted(shelters, key=_shelter_rank)
    suggested = ranked[0] if ranked else None
    route = walking_route((lat, lon), (suggested["lat"], suggested["lon"])) if suggested else None
    return {
        "home": {"lat": lat, "lon": lon, "flood": home},
        "shelters": shelters,
        "suggested_shelter_id": suggested["id"] if suggested else None,
        "route_to_suggested": route,
        "attributions": ATTRIBUTIONS,
    }


def priority(resident: dict, brief: dict) -> dict:
    """Transparent risk score for the worklist. Missing data raises priority, never lowers it."""
    parts = []
    flood = brief["home"]["flood"]
    depth_pts = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 5}.get(flood.get("class_id", 0), 0)
    if flood["status"] != "in_zone" and flood["status"] != "no_mapped_zone":
        depth_pts = 3  # unknown → treat as moderate
    parts.append(("Flood depth at home", depth_pts * 2))
    household = resident.get("household")
    parts.append(("Lives alone" if household == "alone" else "Household unknown" if household is None else "Lives with others",
                  2 if household in ("alone", None) else 0))
    mobility = resident.get("mobility")
    parts.append(("Mobility", {"cannot_walk": 2, "needs_help": 1, "independent": 0}.get(mobility, 2)))
    device = resident.get("medical_device")
    parts.append(("Medical device", 2 if device in (True, None) else 0))
    return {"score": sum(p for _, p in parts), "parts": [{"label": l, "points": p} for l, p in parts]}
