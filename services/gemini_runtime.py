"""
Runtime compartido y rápido para llamadas a Gemini Vision (V1–V7).

Resuelve los bloqueos de 20–55 s en producción:
  * Configura timeout explícito (>= 10 s por modelo, mínimo exigido por Gemini API) y attempts=1
    para evitar los 5 reintentos con backoff exponencial del SDK ante HTTP 503.
  * Aplica ThinkingConfig(thinking_level="MINIMAL"/"LOW") en modelos Gemini 3.x Flash
    para que el análisis visual estructurado responda en ~1.5–3 s en lugar de agotar tiempo.
  * Mantiene cooldown por modelo ante 503/504/429/404 y presupuesto máximo de tiempo total (20 s),
    garantizando entrega rápida de prompts incluso si el primer modelo agota tiempo o está saturado.
  * Respeta GEMINI_API_KEY configurada en entorno (incluyendo llaves AIza de 39 caracteres)
    y solo recurre a la llave de respaldo si la principal falta o es rechazada (401/403).
"""

from __future__ import annotations

import copy
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

VISION_MODELS: List[Tuple[str, Optional[str]]] = [
    ("gemini-3.5-flash-lite", "MINIMAL"),
    ("gemini-3.5-flash", "MINIMAL"),
    ("gemini-3.6-flash", "MINIMAL"),
    ("gemini-3.8-flash", "LOW"),
    ("gemini-3.1-flash-lite", "MINIMAL"),
    ("gemini-2.5-flash", None),
]

# La API de Gemini exige un deadline mínimo de 10 s (10000 ms) en X-Server-Timeout.
DEFAULT_TIMEOUT_MS = 10_000
MAX_WALL_SECONDS = 20.0
TRANSIENT_COOLDOWN_SECONDS = 60.0
NOT_FOUND_COOLDOWN_SECONDS = 600.0

_LOCK = threading.Lock()
_META_LOCK = threading.Lock()
_THREAD_VISION_META = threading.local()
_CLIENTS: Dict[Tuple[str, int], Any] = {}
_PREFERRED_MODEL: Optional[str] = None
_MODEL_COOLDOWN_UNTIL: Dict[str, float] = {}
_REJECTED_KEYS: set[str] = set()
_LAST_VISION_META: Dict[str, Any] = {
    "used_ai": False,
    "model": "",
    "error": "",
}


def _set_last_vision_meta(used_ai: bool, model: str, error: str) -> None:
    snap = {"used_ai": bool(used_ai), "model": str(model or ""), "error": str(error or "")}
    _THREAD_VISION_META.meta = snap
    with _META_LOCK:
        _LAST_VISION_META.update(snap)


def reset_runtime_state() -> None:
    """Reinicia estado compartido (útil para pruebas unitarias)."""
    global _PREFERRED_MODEL
    _THREAD_VISION_META.meta = None
    with _LOCK:
        _CLIENTS.clear()
        _PREFERRED_MODEL = None
        _MODEL_COOLDOWN_UNTIL.clear()
        _REJECTED_KEYS.clear()
    with _META_LOCK:
        _LAST_VISION_META.update({"used_ai": False, "model": "", "error": ""})


def get_last_vision_meta() -> Dict[str, Any]:
    t_meta = getattr(_THREAD_VISION_META, "meta", None)
    if isinstance(t_meta, dict):
        return dict(t_meta)
    with _META_LOCK:
        return dict(_LAST_VISION_META)


def is_key_rejected(key: str) -> bool:
    if not key:
        return True
    with _LOCK:
        return key in _REJECTED_KEYS


def mark_key_rejected(key: str) -> None:
    if not key:
        return
    with _LOCK:
        _REJECTED_KEYS.add(key)
        stale = [k for k in _CLIENTS if k[0] == key]
        for sk in stale:
            _CLIENTS.pop(sk, None)


def is_auth_error(err: Exception) -> bool:
    txt = str(err).upper()
    return any(
        tok in txt
        for tok in (
            "API_KEY_INVALID",
            "API KEY NOT VALID",
            "PERMISSION_DENIED",
            "UNAUTHENTICATED",
            "LEAKED",
            "401",
            "403",
        )
    )


def _is_not_found_error(err: Exception) -> bool:
    txt = str(err).upper()
    return "404" in txt or "NOT_FOUND" in txt or "NO LONGER AVAILABLE" in txt


def _is_thinking_arg_error(err: Exception) -> bool:
    txt = str(err).upper()
    return "THINKING" in txt and ("400" in txt or "INVALID_ARGUMENT" in txt or "NOT SUPPORTED" in txt)


def _is_transient_error(err: Exception) -> bool:
    txt = str(err).upper()
    return any(
        tok in txt
        for tok in (
            "503",
            "504",
            "429",
            "UNAVAILABLE",
            "HIGH DEMAND",
            "DEADLINE_EXCEEDED",
            "RESOURCE_EXHAUSTED",
            "QUOTA",
            "TIMED OUT",
            "TIMEOUT",
        )
    )


def build_genai_client(api_key: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> Any:
    """Crea y cachea un cliente google-genai con timeout explícito (>= 10 s) y sin reintentos largos."""
    key = (api_key or "").strip()
    if not key:
        return None
    eff_timeout = max(10_000, int(timeout_ms))
    cache_key = (key, eff_timeout)
    with _LOCK:
        cached = _CLIENTS.get(cache_key)
    if cached is not None:
        return cached

    from google import genai
    from google.genai import types

    http_opts = None
    try:
        retry_cls = getattr(types, "HttpRetryOptions", None)
        if retry_cls is not None:
            http_opts = types.HttpOptions(
                timeout=eff_timeout,
                retry_options=retry_cls(attempts=1),
            )
        else:
            http_opts = types.HttpOptions(timeout=eff_timeout)
    except Exception:
        http_opts = None

    if http_opts is not None:
        try:
            client = genai.Client(api_key=key, http_options=http_opts)
        except TypeError:
            client = genai.Client(api_key=key)
    else:
        client = genai.Client(api_key=key)

    with _LOCK:
        _CLIENTS[cache_key] = client
    return client


def _attach_thinking_config(config: Any, thinking_level: Optional[str]) -> Any:
    """Adjunta ThinkingConfig sin mutar el objeto config original."""
    if not thinking_level:
        return config
    try:
        from google.genai import types

        thinking_cls = getattr(types, "ThinkingConfig", None)
        if thinking_cls is None:
            return config
        tc = thinking_cls(thinking_level=thinking_level)
        if config is None:
            return types.GenerateContentConfig(thinking_config=tc)
        if getattr(config, "thinking_config", None) is not None:
            return config
        if hasattr(config, "model_copy"):
            return config.model_copy(update={"thinking_config": tc})
        cloned = copy.copy(config)
        setattr(cloned, "thinking_config", tc)
        return cloned
    except Exception:
        return config


def _ordered_candidates(now: float) -> List[Tuple[str, Optional[str]]]:
    with _LOCK:
        pref = _PREFERRED_MODEL
        cooldowns = dict(_MODEL_COOLDOWN_UNTIL)

    ordered: List[Tuple[str, Optional[str]]] = []
    if pref:
        for pair in VISION_MODELS:
            if pair[0] == pref:
                ordered.append(pair)
                break
    for pair in VISION_MODELS:
        if pair not in ordered:
            ordered.append(pair)

    ready = [pair for pair in ordered if now >= cooldowns.get(pair[0], 0.0)]
    return ready


def call_gemini_fast(
    client: Any,
    contents: Any,
    config: Any = None,
    *,
    api_key: str = "",
    fallback_key: str = "",
    max_wall_seconds: float = MAX_WALL_SECONDS,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> Any:
    """
    Ejecuta generate_content de forma acotada en tiempo:
      - Omite modelos en cooldown reciente (503/504/429/404).
      - Aplica ThinkingConfig adecuado a cada modelo Gemini 3.x Flash.
      - Respeta un presupuesto total de tiempo (por defecto 16 s).
      - Si api_key falla por 401/403/LEAKED y hay fallback_key distinta, reintenta
        automáticamente con fallback_key y marca la llave rechazada en memoria.
    """
    now = time.time()
    candidates = _ordered_candidates(now)
    if not candidates:
        err_msg = "Modelos Gemini temporalmente saturados (en espera de enfriamiento); usando respaldo rápido."
        _set_last_vision_meta(False, "", err_msg)
        raise RuntimeError(err_msg)

    started = time.monotonic()
    last_err: Optional[Exception] = None
    active_client = client
    active_key = (api_key or "").strip()
    fb_key = (fallback_key or "").strip()

    for model_name, thinking_level in candidates:
        if (time.monotonic() - started) >= max_wall_seconds:
            break
        with _LOCK:
            if time.time() < _MODEL_COOLDOWN_UNTIL.get(model_name, 0.0):
                continue

        eff_config = _attach_thinking_config(config, thinking_level)
        try:
            res = active_client.models.generate_content(
                model=model_name,
                contents=contents,
                config=eff_config,
            )
            with _LOCK:
                global _PREFERRED_MODEL
                _PREFERRED_MODEL = model_name
                _MODEL_COOLDOWN_UNTIL.pop(model_name, None)
            _set_last_vision_meta(True, model_name, "")
            return res
        except Exception as exc:
            # Si falló únicamente por thinking_level no soportado, reintentar sin thinking_config
            if thinking_level and _is_thinking_arg_error(exc) and (time.monotonic() - started) < max_wall_seconds:
                try:
                    res = active_client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=config,
                    )
                    with _LOCK:
                        _PREFERRED_MODEL = model_name
                        _MODEL_COOLDOWN_UNTIL.pop(model_name, None)
                    _set_last_vision_meta(True, model_name, "")
                    return res
                except Exception as exc_retry:
                    exc = exc_retry

            if is_auth_error(exc):
                if active_key:
                    mark_key_rejected(active_key)
                if fb_key and fb_key != active_key and not is_key_rejected(fb_key):
                    fb_client = build_genai_client(fb_key, timeout_ms=timeout_ms)
                    if fb_client is not None:
                        return call_gemini_fast(
                            fb_client,
                            contents,
                            config=config,
                            api_key=fb_key,
                            fallback_key="",
                            max_wall_seconds=max(4.0, max_wall_seconds - (time.monotonic() - started)),
                            timeout_ms=timeout_ms,
                        )
                _set_last_vision_meta(False, "", str(exc)[:220])
                raise

            if _is_not_found_error(exc):
                with _LOCK:
                    _MODEL_COOLDOWN_UNTIL[model_name] = time.time() + NOT_FOUND_COOLDOWN_SECONDS
                    if _PREFERRED_MODEL == model_name:
                        _PREFERRED_MODEL = None
            elif _is_transient_error(exc):
                with _LOCK:
                    _MODEL_COOLDOWN_UNTIL[model_name] = time.time() + TRANSIENT_COOLDOWN_SECONDS
                    if _PREFERRED_MODEL == model_name:
                        _PREFERRED_MODEL = None
            last_err = exc

    err_out = last_err if last_err is not None else RuntimeError("Tiempo agotado conectando con Gemini API")
    _set_last_vision_meta(False, "", str(err_out)[:220])
    raise err_out
