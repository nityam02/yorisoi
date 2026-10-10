"""Walking route from home to shelter, checked against the flood-depth tiles.

Uses the Google Maps Routes API when MAPS_API_KEY is set. Without it, falls back to a
straight line and says so: no invented walking times.
"""

import httpx

from ..config import settings
from ..geo import decode_polyline, haversine_m, sample_line
from .gsi import flood_depth

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


def _depth_along(points: list[tuple[float, float]]) -> dict:
    """Worst flood-depth class sampled along a path (~every 40 m)."""
    worst = None
    for lat, lon in sample_line(points, 40.0):
        d = flood_depth(lat, lon)
        if d.status == "in_zone" and (worst is None or d.class_id > worst["class_id"]):
            worst = d.as_dict()
    return worst or {"status": "no_mapped_zone", "class_id": 0, "label_en": "no mapped flood zone along path", "label_ja": "経路上に想定浸水区域なし"}


def walking_route(home: tuple[float, float], dest: tuple[float, float]) -> dict:
    if settings.maps_api_key:
        try:
            resp = httpx.post(
                ROUTES_URL,
                timeout=20.0,
                headers={
                    "X-Goog-Api-Key": settings.maps_api_key,
                    "X-Goog-FieldMask": "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline",
                },
                json={
                    "origin": {"location": {"latLng": {"latitude": home[0], "longitude": home[1]}}},
                    "destination": {"location": {"latLng": {"latitude": dest[0], "longitude": dest[1]}}},
                    "travelMode": "WALK",
                    "languageCode": "ja-JP",
                },
            )
            resp.raise_for_status()
            route = resp.json()["routes"][0]
            pts = decode_polyline(route["polyline"]["encodedPolyline"])
            return {
                "method": "google_routes_walk",
                "distance_m": route["distanceMeters"],
                "duration_s": int(route["duration"].rstrip("s")),
                "path": pts,
                "worst_flood_on_path": _depth_along(pts),
            }
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            fallback_reason = f"Routes API unavailable ({exc.__class__.__name__})"
    else:
        fallback_reason = "No MAPS_API_KEY configured"

    pts = [home, dest]
    return {
        "method": "straight_line",
        "note": f"{fallback_reason}: straight-line distance only; walking route not computed.",
        "distance_m": round(haversine_m(*home, *dest)),
        "duration_s": None,
        "path": pts,
        "worst_flood_on_path": _depth_along(pts),
    }
