"""Runtime settings, read once from the environment (and ../../.env in local dev)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_HERE = Path(__file__).resolve()
# Repo root in local dev; in the container the tree is shallower, so fall back to /.
REPO_ROOT = _HERE.parents[3] if len(_HERE.parents) > 3 else _HERE.parents[-1]
load_dotenv(REPO_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    use_vertex: bool = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
    gcp_project: str | None = os.getenv("GOOGLE_CLOUD_PROJECT")
    gcp_location: str = os.getenv("GOOGLE_CLOUD_LOCATION", "asia-northeast1")
    maps_api_key: str | None = os.getenv("MAPS_API_KEY") or None

    # Model choices. Override per environment without code changes.
    model_fast: str = os.getenv("YORISOI_MODEL_FAST", "gemini-3.5-flash")
    model_critic: str = os.getenv("YORISOI_MODEL_CRITIC", "gemini-3.1-pro-preview")
    model_live: str = os.getenv("YORISOI_MODEL_LIVE", "gemini-3.8-live")
    # Tried in order when a model is overloaded (503) or out of quota (429).
    fast_fallbacks: tuple = tuple(os.getenv("YORISOI_FAST_FALLBACKS", "gemini-3.1-flash-lite,gemini-2.5-flash").split(","))
    critic_fallbacks: tuple = tuple(os.getenv("YORISOI_CRITIC_FALLBACKS", "gemini-2.5-pro,gemini-3.5-flash,gemini-2.5-flash").split(","))

    store_dir: Path = Path(os.getenv("YORISOI_STORE_DIR", Path(__file__).resolve().parents[1] / "var"))
    cache_dir: Path = Path(os.getenv("YORISOI_CACHE_DIR", Path(__file__).resolve().parents[1] / ".cache"))
    web_dist: Path = Path(os.getenv("YORISOI_WEB_DIST", REPO_ROOT / "apps" / "web" / "dist"))


settings = Settings()
