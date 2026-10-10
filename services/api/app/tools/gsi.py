"""Deterministic tools over Japan's public GSI / Hazard Map Portal data.

Facts in a plan come from here, never from the language model.
"""

import io
import json
from dataclasses import dataclass, asdict
from pathlib import Path

import httpx
from PIL import Image

from ..config import settings
from ..geo import haversine_m, tile_for

FLOOD_TILE_URL = "https://disaportaldata.gsi.go.jp/raster/01_flood_l2_shinsuishin_data/{z}/{x}/{y}.png"
SHELTER_TILE_URL = "https://cyberjapandata.gsi.go.jp/xyz/skhb0{code}/{z}/{x}/{y}.geojson"
ADDRESS_SEARCH_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"

ATTRIBUTIONS = [
    {"label": "Flood depth: Hazard Map Portal (MLIT), 洪水浸水想定区域（想定最大規模）", "url": "https://disaportal.gsi.go.jp/hazardmapportal/hazardmap/copyright/opendata.html"},
    {"label": "Shelters: GSI designated emergency evacuation sites (指定緊急避難場所)", "url": "https://www.gsi.go.jp/bousaichiri/hinanbasho.html"},
    {"label": "Base map: GSI tiles (地理院タイル)", "url": "https://maps.gsi.go.jp/development/ichiran.html"},
]

# Official legend of the maximum-scale flood depth tiles (verified against live tiles).
FLOOD_LEGEND = [
    # rgb, class id, Japanese label, English label, min m, max m
    ((247, 245, 169), 1, "0.5m未満", "under 0.5 m", 0.0, 0.5),
    ((255, 216, 192), 2, "0.5〜3m", "0.5–3 m", 0.5, 3.0),
    ((255, 183, 183), 3, "3〜5m", "3–5 m", 3.0, 5.0),
    ((255, 145, 145), 4, "5〜10m", "5–10 m", 5.0, 10.0),
    ((242, 133, 201), 5, "10〜20m", "10–20 m", 10.0, 20.0),
    ((220, 122, 220), 6, "20m以上", "20 m or more", 20.0, None),
]

# Disaster-type flags used by the shelter dataset (disaster1..disaster8).
HAZARD_TYPES = {
    1: ("洪水", "flood"),
    2: ("崖崩れ・土石流及び地滑り", "landslide"),
    3: ("高潮", "storm surge"),
    4: ("地震", "earthquake"),
    5: ("津波", "tsunami"),
    6: ("大規模な火事", "large fire"),
    7: ("内水氾濫", "inland flooding"),
    8: ("火山現象", "volcanic"),
}

_client = httpx.Client(timeout=20.0, headers={"User-Agent": "yorisoi-prototype/0.1"})


def _cached_get(url: str, kind: str) -> bytes | None:
    """GET with an on-disk cache. Returns None on 404 (tile outside data coverage)."""
    key = url.split("://", 1)[1].replace("/", "_")
    path: Path = settings.cache_dir / kind / key
    if path.exists():
        data = path.read_bytes()
        return None if data == b"__404__" else data
    resp = _client.get(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    if resp.status_code == 404:
        path.write_bytes(b"__404__")
        return None
    resp.raise_for_status()
    path.write_bytes(resp.content)
    return resp.content


@dataclass
class FloodDepth:
    status: str  # in_zone | no_mapped_zone | unknown_colour | error
    class_id: int  # 0 when not in a mapped zone
    label_ja: str
    label_en: str
    min_m: float | None
    max_m: float | None
    zoom: int
    tile_url: str

    def as_dict(self) -> dict:
        return asdict(self)


def flood_depth(lat: float, lon: float, zoom: int = 17) -> FloodDepth:
    """Read the flood-depth class at a point from the hazard tile's pixel colour.

    A transparent pixel means "no mapped flood zone here", which is NOT proof of safety:
    prefectural-river coverage is partial.
    """
    for z in (zoom, 16, 15):
        x, y, px, py = tile_for(lat, lon, z)
        url = FLOOD_TILE_URL.format(z=z, x=x, y=y)
        try:
            data = _cached_get(url, "flood")
        except httpx.HTTPError as exc:
            return FloodDepth("error", 0, "取得失敗", f"could not fetch tile ({exc.__class__.__name__})", None, None, z, url)
        if data is None:
            continue  # no tile at this zoom; try coarser
        r, g, b, a = Image.open(io.BytesIO(data)).convert("RGBA").getpixel((px, py))
        if a == 0:
            return FloodDepth("no_mapped_zone", 0, "想定浸水区域外（データなし）", "no mapped flood zone (not proof of safety)", None, None, z, url)
        best = min(FLOOD_LEGEND, key=lambda row: sum((p - q) ** 2 for p, q in zip(row[0], (r, g, b))))
        if sum((p - q) ** 2 for p, q in zip(best[0], (r, g, b))) > 300:
            return FloodDepth("unknown_colour", 0, "判定不能", f"unrecognised colour {(r, g, b)}", None, None, z, url)
        _, cid, ja, en, lo, hi = best
        return FloodDepth("in_zone", cid, ja, en, lo, hi, z, url)
    return FloodDepth("no_mapped_zone", 0, "想定浸水区域外（データなし）", "no mapped flood zone (not proof of safety)", None, None, zoom, "")


@dataclass
class Shelter:
    id: str
    name: str
    address: str
    lat: float
    lon: float
    distance_m: float
    hazards: list[str]  # English hazard names the site is designated for
    certified_for_flood: bool
    flood_at_site: dict | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def shelters_near(lat: float, lon: float, hazard_code: int = 1, radius_m: float = 3000.0, limit: int = 6,
                  with_site_depth: bool = True) -> list[Shelter]:
    """Designated emergency evacuation sites for one hazard type, nearest first."""
    z = 10
    cx, cy, _, _ = tile_for(lat, lon, z)
    seen: dict[str, Shelter] = {}
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            url = SHELTER_TILE_URL.format(code=hazard_code, z=z, x=cx + dx, y=cy + dy)
            data = _cached_get(url, "shelters")
            if not data:
                continue
            for feat in json.loads(data).get("features", []):
                slon, slat = feat["geometry"]["coordinates"][:2]
                props = feat.get("properties", {})
                sid = f"{props.get('name')}|{slat:.6f}|{slon:.6f}"
                if sid in seen:
                    continue
                dist = haversine_m(lat, lon, slat, slon)
                if dist > radius_m:
                    continue
                flags = [HAZARD_TYPES[i][1] for i in HAZARD_TYPES if props.get(f"disaster{i}") == 1]
                seen[sid] = Shelter(
                    id=f"S{len(seen) + 1}",
                    name=props.get("name") or "(名称なし)",
                    address=props.get("address") or "",
                    lat=slat,
                    lon=slon,
                    distance_m=round(dist),
                    hazards=flags,
                    certified_for_flood="flood" in flags,
                )
    ranked = sorted(seen.values(), key=lambda s: s.distance_m)[:limit]
    for i, s in enumerate(ranked, start=1):
        s.id = f"S{i}"
        if with_site_depth:
            s.flood_at_site = flood_depth(s.lat, s.lon).as_dict()
    return ranked


def geocode(address: str) -> dict | None:
    """Address → coordinates using GSI's free address search (Japanese addresses)."""
    resp = _client.get(ADDRESS_SEARCH_URL, params={"q": address})
    resp.raise_for_status()
    hits = resp.json()
    if not hits:
        return None
    lon, lat = hits[0]["geometry"]["coordinates"]
    return {"lat": lat, "lon": lon, "label": hits[0]["properties"].get("title", address)}
