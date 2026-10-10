"""Small geodesy helpers: Web Mercator tiles, distances, polyline sampling."""

import math


def tile_for(lat: float, lon: float, zoom: int) -> tuple[int, int, int, int]:
    """Return (tile_x, tile_y, pixel_x, pixel_y) of a point in a 256px XYZ tile."""
    n = 2**zoom
    xf = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    yf = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    x, y = int(xf), int(yf)
    return x, y, min(255, int((xf - x) * 256)), min(255, int((yf - y) * 256))


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def sample_line(points: list[tuple[float, float]], step_m: float = 40.0) -> list[tuple[float, float]]:
    """Points every ~step_m metres along a polyline of (lat, lon), endpoints included."""
    if not points:
        return []
    out = [points[0]]
    for (la1, lo1), (la2, lo2) in zip(points, points[1:]):
        seg = haversine_m(la1, lo1, la2, lo2)
        steps = max(1, int(seg // step_m))
        for i in range(1, steps + 1):
            t = i / steps
            out.append((la1 + (la2 - la1) * t, lo1 + (lo2 - lo1) * t))
    return out


def decode_polyline(encoded: str) -> list[tuple[float, float]]:
    """Decode a Google encoded polyline into (lat, lon) pairs."""
    coords, index, lat, lng = [], 0, 0, 0
    while index < len(encoded):
        for is_lng in (False, True):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lng:
                lng += delta
            else:
                lat += delta
        coords.append((lat / 1e5, lng / 1e5))
    return coords
