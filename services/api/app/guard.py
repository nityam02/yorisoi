"""Public-demo protection: a private sandbox per visitor, and limits on Gemini-backed actions so nobody can
run up the project's bill. Limits are per Cloud Run instance (max 3 instances)."""

import os
import re
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_SID = re.compile(r"^[A-Za-z0-9-]{8,64}$")

PER_VISITOR_PER_HOUR = int(os.getenv("YORISOI_LIMIT_PER_HOUR", "40"))
PER_IP_PER_HOUR = int(os.getenv("YORISOI_LIMIT_PER_IP_HOUR", "80"))
PER_INSTANCE_PER_DAY = int(os.getenv("YORISOI_LIMIT_PER_DAY", "800"))
MAX_TRANSCRIPT_CHARS = 20_000

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)
_day = {"start": time.time(), "count": 0}


def session_id(request: Request) -> str:
    """The visitor's sandbox id (random, made by the browser). Plans are stored per sandbox."""
    sid = request.headers.get("x-yorisoi-session") or request.query_params.get("sid") or ""
    return sid if _SID.match(sid) else "public"


def plan_key(request: Request, rid: str) -> str:
    return f"{session_id(request)}__{rid}"


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def charge(request: Request, units: int = 1) -> None:
    """Count `units` Gemini calls against the visitor, their IP and the instance; refuse with 429 when over."""
    now = time.time()
    keys = [("s:" + session_id(request), PER_VISITOR_PER_HOUR), ("ip:" + _client_ip(request), PER_IP_PER_HOUR)]
    with _lock:
        if now - _day["start"] > 86_400:
            _day.update(start=now, count=0)
        if _day["count"] + units > PER_INSTANCE_PER_DAY:
            raise HTTPException(429, "The demo's daily AI allowance is used up. Please try again tomorrow.")
        for key, limit in keys:
            q = _hits[key]
            while q and now - q[0] > 3600:
                q.popleft()
            if len(q) + units > limit:
                raise HTTPException(429, f"Demo limit reached: at most {limit} AI actions an hour. Please try again later.")
        for key, _ in keys:
            _hits[key].extend([now] * units)
        _day["count"] += units


def reset_for_tests() -> None:
    with _lock:
        _hits.clear()
        _day.update(start=time.time(), count=0)
