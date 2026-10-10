"""Runtime settings, read once from the environment (and ../../.env in local dev)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
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

    store_dir: Path = Path(os.getenv("YORISOI_STORE_DIR", Path(__file__).resolve().parents[1] / "var"))
    cache_dir: Path = Path(os.getenv("YORISOI_CACHE_DIR", Path(__file__).resolve().parents[1] / ".cache"))
    web_dist: Path = Path(os.getenv("YORISOI_WEB_DIST", REPO_ROOT / "apps" / "web" / "dist"))


settings = Settings()
