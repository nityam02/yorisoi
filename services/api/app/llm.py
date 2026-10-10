"""Thin wrapper around the Google Gen AI SDK (Gemini API key or Vertex AI)."""

import logging
import re
import threading
import time
from functools import lru_cache
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from .config import settings

T = TypeVar("T", bound=BaseModel)
log = logging.getLogger("yorisoi.llm")
_local = threading.local()
_cooldown: dict[str, float] = {}  # model -> time until which it is skipped after a 429


def last_model() -> str | None:
    """The model that actually answered the most recent call on this thread (after any fallback)."""
    return getattr(_local, "model", None)


def _chain(model: str) -> list[str]:
    if model == settings.model_fast:
        return [model, *settings.fast_fallbacks]
    if model == settings.model_critic:
        return [model, *settings.critic_fallbacks]
    return [model]


def _supports_thinking_level(model: str) -> bool:
    return re.match(r"gemini-3\.[5-9]", model) is not None


class LLMUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def client() -> genai.Client:
    if settings.use_vertex:
        return genai.Client(vertexai=True, project=settings.gcp_project, location=settings.gcp_location)
    if not settings.gemini_api_key:
        raise LLMUnavailable("Set GEMINI_API_KEY (or GOOGLE_GENAI_USE_VERTEXAI=true with a project).")
    return genai.Client(api_key=settings.gemini_api_key)


def _call(model: str, contents, config: types.GenerateContentConfig):
    last = None
    chain = _chain(model)
    ready = [m for m in chain if _cooldown.get(m, 0) < time.time()] or chain
    for m in ready:
        cfg = config if _supports_thinking_level(m) else config.model_copy(update={"thinking_config": None})
        for attempt in range(2):
            try:
                resp = client().models.generate_content(model=m, contents=contents, config=cfg)
                _local.model = m
                return resp
            except errors.APIError as exc:
                last = exc
                code = getattr(exc, "code", None)
                log.warning("Gemini %s attempt %d failed: %s", m, attempt + 1, str(exc)[:200])
                if code == 503 and attempt == 0:
                    time.sleep(2)  # brief overload: one retry on the same model
                    continue
                if code == 429:
                    _cooldown[m] = time.time() + 600  # out of quota: skip this model for 10 minutes
                if code in (429, 500, 502, 503, 504):
                    break  # quota or capacity: move to the next model in the chain
                raise LLMUnavailable(f"Gemini call failed on {m}: {exc}") from exc
    raise LLMUnavailable(f"All models busy or out of quota (last: {last})")


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
