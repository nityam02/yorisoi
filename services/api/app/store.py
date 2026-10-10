"""Plan storage. Local JSON files by default; Firestore on Cloud Run (YORISOI_STORE=firestore)."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

DATA_DIR = Path(__file__).resolve().parent / "data"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def residents() -> list[dict]:
    return json.loads((DATA_DIR / "residents.json").read_text(encoding="utf-8"))["residents"]


def resident(rid: str) -> dict | None:
    return next((r for r in residents() if r["id"] == rid), None)


def sample_interview(rid: str) -> str | None:
    path = DATA_DIR / "interviews" / f"{rid}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else None


class _FileStore:
    def __init__(self, root: Path):
        self.root = root / "plans"
        self.root.mkdir(parents=True, exist_ok=True)

    def get(self, rid: str) -> dict | None:
        p = self.root / f"{rid}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def put(self, rid: str, bundle: dict) -> None:
        tmp = self.root / f"{rid}.json.tmp"
        tmp.write_text(json.dumps(bundle, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.root / f"{rid}.json")

    def delete(self, rid: str) -> None:
        (self.root / f"{rid}.json").unlink(missing_ok=True)


class _FirestoreStore:
    def __init__(self):
        from google.cloud import firestore  # imported only when this backend is used

        self.col = firestore.Client(project=settings.gcp_project).collection("plans")

    def get(self, rid: str) -> dict | None:
        snap = self.col.document(rid).get()
        return json.loads(snap.to_dict()["json"]) if snap.exists else None

    def put(self, rid: str, bundle: dict) -> None:
        # Stored as one JSON string: plans contain nested lists Firestore would otherwise reshape.
        self.col.document(rid).set({"json": json.dumps(bundle, ensure_ascii=False), "updated_at": now()})

    def delete(self, rid: str) -> None:
        self.col.document(rid).delete()


plans = _FirestoreStore() if os.getenv("YORISOI_STORE") == "firestore" else _FileStore(settings.store_dir)
