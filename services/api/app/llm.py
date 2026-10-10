"""Thin wrapper around the Google Gen AI SDK (Gemini API key or Vertex AI)."""

import time
from functools import lru_cache
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from .config import settings

T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def client() -> genai.Client:
    if settings.use_vertex:
        return genai.Client(vertexai=True, project=settings.gcp_project, location=settings.gcp_location)
    if not settings.gemini_api_key:
        raise LLMUnavailable("Set GEMINI_API_KEY (or GOOGLE_GENAI_USE_VERTEXAI=true with a project).")
    return genai.Client(api_key=settings.gemini_api_key)


def _call(model: str, contents, config: types.GenerateContentConfig, retries: int = 2):
    last = None
    for attempt in range(retries + 1):
        try:
            return client().models.generate_content(model=model, contents=contents, config=config)
        except errors.APIError as exc:  # rate limits and transient 5xx get a short retry
            last = exc
            if getattr(exc, "code", None) not in (429, 500, 502, 503, 504) or attempt == retries:
                break
            time.sleep(2 * (attempt + 1))
    raise LLMUnavailable(f"Gemini call failed on {model}: {last}")


def _thinking(level: str | None) -> types.ThinkingConfig | None:
    return types.ThinkingConfig(thinking_level=level) if level else None


def structured(model: str, system: str, prompt: str | list, schema: type[T], temperature: float = 0.2,
               thinking: str | None = None) -> T:
    resp = _call(
        model,
        prompt,
        types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=temperature,
            thinking_config=_thinking(thinking),
        ),
    )
    if resp.parsed is None:
        raise LLMUnavailable(f"{model} returned no parseable JSON")
    return resp.parsed


def text(model: str, system: str, prompt: str | list, temperature: float = 0.3, thinking: str | None = None) -> str:
    resp = _call(model, prompt, types.GenerateContentConfig(system_instruction=system, temperature=temperature,
                                                            thinking_config=_thinking(thinking)))
    return (resp.text or "").strip()


def audio_part(data: bytes, mime_type: str) -> types.Part:
    return types.Part.from_bytes(data=data, mime_type=mime_type)
