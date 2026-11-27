"""Structured JSON logging, secret redaction, error taxonomy, context propagation,
and bounded in-memory RED metrics (Rate, Errors, Duration p50/p95/p99).

Uses Python standard library ONLY (zero extra dependencies for Render 512 MB RAM safety).
"""

from __future__ import annotations

import collections
import contextlib
import contextvars
import datetime
import json
import logging
import math
import re
import sys
import threading
import time
import uuid
from typing import Any, Callable, Deque, Dict, Iterator, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Bounded Error Taxonomy (low-cardinality metric labels)
# ---------------------------------------------------------------------------
VALID_ERROR_CLASSES = frozenset(
    {
        "quota_429",
        "auth_401_403",
        "not_found_404",
        "timeout",
        "transient_5xx",
        "bad_request_400",
        "network",
        "other",
    }
)

# ---------------------------------------------------------------------------
# Context Propagation (entry_point + request_id across threads)
# ---------------------------------------------------------------------------
_ENTRY_POINT: contextvars.ContextVar[str] = contextvars.ContextVar("buena_entry_point", default="unknown")
_REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar("buena_request_id", default="")


def set_run_context(entry_point: str, request_id: Optional[str] = None) -> Dict[str, str]:
    """Stamp entry_point and request_id for the current execution context."""
    ep = str(entry_point or "unknown").strip() or "unknown"
    rid = str(request_id).strip() if request_id else uuid.uuid4().hex[:12]
    _ENTRY_POINT.set(ep)
    _REQUEST_ID.set(rid)
    return {"entry_point": ep, "request_id": rid}


def get_run_context() -> Dict[str, str]:
    """Return the active entry_point and request_id for the current context."""
    return {
        "entry_point": _ENTRY_POINT.get() or "unknown",
        "request_id": _REQUEST_ID.get() or "",
    }


def copy_context_for_thread(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Callable[..., Any]:
    """Wrap a callable with a snapshot of the current contextvars for ThreadPoolExecutor."""
    ctx = contextvars.copy_context()

    def _wrapped(*call_args: Any, **call_kwargs: Any) -> Any:
        merged_args = args + call_args
        merged_kwargs = {**kwargs, **call_kwargs}
        return ctx.copy().run(fn, *merged_args, **merged_kwargs)

    return _wrapped


# ---------------------------------------------------------------------------
# Secret Redaction
# ---------------------------------------------------------------------------
_SECRET_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
            re.MULTILINE,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*",
            re.MULTILINE,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (re.compile(r"AIza[0-9A-Za-z_-]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"ya29\.[0-9A-Za-z._-]+"), "[REDACTED_OAUTH_TOKEN]"),
    (re.compile(r"1//[0-9A-Za-z._-]{20,}"), "[REDACTED_REFRESH_TOKEN]"),
    (re.compile(r"AQ\.[0-9A-Za-z._-]+"), "[REDACTED_GOOGLE_KEY]"),
    (re.compile(r"GOCSPX-[0-9A-Za-z_-]+"), "[REDACTED_CLIENT_SECRET]"),
    (re.compile(r"(?i)Bearer\s+\S+"), "Bearer [REDACTED_TOKEN]"),
)


def _safe_str(val: Any) -> str:
    """Fail-open conversion of any object to str (never raises on broken __str__)."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (bytes, bytearray, memoryview)):
        try:
            return bytes(val).decode("utf-8", errors="replace")
        except Exception:
            return "<bytes:decode_failed>"
    try:
        return str(val)
    except Exception:
        try:
            return f"<{type(val).__name__}:str_failed>"
        except Exception:
            return "<object:str_failed>"


def redact_secrets(text: Any) -> str:
    """Scrub API keys, OAuth/refresh tokens, Bearer credentials, and full/truncated PEM keys."""
    if text is None:
        return ""
    out = _safe_str(text)
    for pattern, replacement in _SECRET_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def safe_error_text(exc_or_msg: Any, max_len: int = 220) -> str:
    """Safely stringify, redact secrets FIRST, and truncate AFTER (never raises)."""
    redacted = redact_secrets(exc_or_msg)
    try:
        limit = int(max_len)
    except Exception:
        limit = 220
    if limit <= 0:
        return ""
    return redacted[:limit]


def _redact_value(
    val: Any,
    *,
    _seen: Optional[set[int]] = None,
    _depth: int = 0,
    max_depth: int = 10,
) -> Any:
    if val is None or isinstance(val, (bool, int)):
        return val
    if isinstance(val, float):
        return val if math.isfinite(val) else None
    if isinstance(val, str):
        return redact_secrets(val)
    if isinstance(val, (bytes, bytearray, memoryview)):
        return redact_secrets(_safe_str(val))
    if _depth >= max_depth:
        return "[MAX_DEPTH]"

    seen = _seen if _seen is not None else set()

    if isinstance(val, dict):
        obj_id = id(val)
        if obj_id in seen:
            return "[CIRCULAR_REF]"
        seen.add(obj_id)
        try:
            out: Dict[str, Any] = {}
            for k, v in val.items():
                clean_k = redact_secrets(_safe_str(k))
                out[clean_k] = _redact_value(v, _seen=seen, _depth=_depth + 1, max_depth=max_depth)
            return out
        except Exception:
            return "[REDACTED_DICT_ERROR]"
        finally:
            seen.discard(obj_id)

    if isinstance(val, (list, tuple, set, frozenset)):
        obj_id = id(val)
        if obj_id in seen:
            return "[CIRCULAR_REF]"
        seen.add(obj_id)
        try:
            return [_redact_value(item, _seen=seen, _depth=_depth + 1, max_depth=max_depth) for item in val]
        except Exception:
            return "[REDACTED_SEQ_ERROR]"
        finally:
            seen.discard(obj_id)

    return redact_secrets(_safe_str(val))


# ---------------------------------------------------------------------------
# Error Classification
# ---------------------------------------------------------------------------
_RE_HTTP_429 = re.compile(r"\b429\b")
_RE_HTTP_AUTH = re.compile(r"\b(?:401|403)\b")
_RE_HTTP_404 = re.compile(r"\b404\b")
_RE_HTTP_5XX = re.compile(r"\b50[0234]\b")
_RE_HTTP_400 = re.compile(r"\b400\b")


def classify_error(exc_or_msg: Any) -> str:
    """Classify an exception or error message into a bounded error taxonomy."""
    if isinstance(exc_or_msg, TimeoutError):
        return "timeout"
    if isinstance(exc_or_msg, (ConnectionError, BrokenPipeError)):
        return "network"

    txt = _safe_str(exc_or_msg)
    up = txt.upper()

    if _RE_HTTP_429.search(up):
        return "quota_429"
    if _RE_HTTP_AUTH.search(up) or any(
        tok in up
        for tok in (
            "API_KEY_INVALID",
            "API KEY NOT VALID",
            "PERMISSION_DENIED",
            "UNAUTHENTICATED",
            "UNAUTHORIZED",
            "FORBIDDEN",
            "LEAKED",
            "INVALID_GRANT",
        )
    ):
        return "auth_401_403"
    if any(tok in up for tok in ("RESOURCE_EXHAUSTED", "QUOTA", "RATE_LIMIT", "RATE LIMIT", "TOO MANY REQUESTS")):
        return "quota_429"
    if _RE_HTTP_404.search(up) or any(tok in up for tok in ("NOT_FOUND", "NO LONGER AVAILABLE", "FILE NOT FOUND")):
        return "not_found_404"
    if any(tok in up for tok in ("TIMEOUT", "TIMED OUT", "DEADLINE_EXCEEDED")):
        return "timeout"
    if _RE_HTTP_5XX.search(up) or any(
        tok in up
        for tok in (
            "UNAVAILABLE",
            "HIGH DEMAND",
            "BAD GATEWAY",
            "SERVICE UNAVAILABLE",
            "OVERLOADED",
            "INTERNAL_ERROR",
        )
    ):
        return "transient_5xx"
    if _RE_HTTP_400.search(up) or any(tok in up for tok in ("INVALID_ARGUMENT", "BAD_REQUEST", "BAD REQUEST")):
        return "bad_request_400"
    if any(
        tok in up
        for tok in (
            "CONNECTION",
            "CONNRESET",
            "ECONNREFUSED",
            "URLERROR",
            "SSLERROR",
            "NAME OR SERVICE NOT KNOWN",
            "TEMPORARY FAILURE IN NAME RESOLUTION",
            "NETWORK",
        )
    ):
        return "network"
    return "other"


# ---------------------------------------------------------------------------
# Bounded Thread-Safe RED Metrics Registry
# ---------------------------------------------------------------------------
def _coerce_duration_ms(val: Any) -> Optional[float]:
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
    except Exception:
        return None
    if not math.isfinite(f):
        return None
    return round(max(0.0, f), 2)


def _coerce_attempt(val: Any) -> Optional[int]:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, float) and not math.isfinite(val):
        return None
    try:
        return int(val)
    except Exception:
        return None


def _compute_percentile(sorted_vals: List[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 2)
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return round(sorted_vals[low], 2)
    frac = rank - low
    val = sorted_vals[low] + frac * (sorted_vals[high] - sorted_vals[low])
    return round(val, 2)


class MetricsRegistry:
    """Thread-safe bounded RED metrics store keyed strictly by low-cardinality (service, operation)."""

    def __init__(self, maxlen: int = 500) -> None:
        self._maxlen = max(1, int(maxlen))
        self._lock = threading.Lock()
        self._series: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def record(
        self,
        service: str,
        operation: str,
        *,
        duration_ms: Optional[float] = None,
        is_error: bool = False,
        error_class: Optional[str] = None,
    ) -> None:
        svc = _safe_str(service or "unknown").strip() or "unknown"
        op = _safe_str(operation or "unknown").strip() or "unknown"
        key = (svc, op)
        err_cls: Optional[str] = None
        if error_class is not None and error_class != "":
            err_cls = error_class if (isinstance(error_class, str) and error_class in VALID_ERROR_CLASSES) else "other"
        dur = _coerce_duration_ms(duration_ms)

        with self._lock:
            entry = self._series.get(key)
            if entry is None:
                entry = {
                    "count": 0,
                    "error_count": 0,
                    "error_by_class": {},
                    "durations": collections.deque(maxlen=self._maxlen),
                }
                self._series[key] = entry

            entry["count"] += 1
            if is_error or err_cls is not None:
                entry["error_count"] += 1
                cls_key = err_cls or "other"
                entry["error_by_class"][cls_key] = entry["error_by_class"].get(cls_key, 0) + 1
            if dur is not None:
                entry["durations"].append(dur)

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            out: Dict[str, Dict[str, Any]] = {}
            for (svc, op), entry in sorted(self._series.items()):
                vals = sorted(entry["durations"])
                out[f"{svc}.{op}"] = {
                    "service": svc,
                    "operation": op,
                    "count": entry["count"],
                    "error_count": entry["error_count"],
                    "error_by_class": dict(entry["error_by_class"]),
                    "samples": len(vals),
                    "p50_ms": _compute_percentile(vals, 50.0),
                    "p95_ms": _compute_percentile(vals, 95.0),
                    "p99_ms": _compute_percentile(vals, 99.0),
                }
            return out

    def reset(self) -> None:
        with self._lock:
            self._series.clear()


_METRICS = MetricsRegistry(maxlen=500)


def get_metrics_snapshot() -> Dict[str, Dict[str, Any]]:
    """Return RED metrics snapshot (counts, error_by_class, p50/p95/p99 ms) per (service, operation)."""
    return _METRICS.snapshot()


def reset_observability_state() -> None:
    """Reset in-memory metrics and context (useful for deterministic unit tests)."""
    _METRICS.reset()
    _ENTRY_POINT.set("unknown")
    _REQUEST_ID.set("")


# ---------------------------------------------------------------------------
# Single-Line JSON Formatter & Logger
# ---------------------------------------------------------------------------
def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class JSONLogFormatter(logging.Formatter):
    """Formats LogRecord payloads as deterministic single-line JSON with secret redaction."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            payload = getattr(record, "structured_payload", None)
            if isinstance(payload, dict):
                clean_payload = _redact_value(payload)
            else:
                ctx = get_run_context()
                try:
                    msg = record.getMessage()
                except Exception:
                    msg = _safe_str(getattr(record, "msg", ""))
                clean_payload = {
                    "ts": _utc_now_iso(),
                    "level": _safe_str(getattr(record, "levelname", "info")).lower() or "info",
                    "event": "log_message",
                    "service": redact_secrets(_safe_str(getattr(record, "name", _LOGGER_NAME))),
                    "entry_point": ctx["entry_point"],
                    "request_id": ctx["request_id"],
                    "operation": "log",
                    "status": "ok",
                    "duration_ms": None,
                    "model": None,
                    "error_class": None,
                    "attempt": None,
                    "meta": {"message": redact_secrets(msg)},
                }
            return json.dumps(
                clean_payload,
                ensure_ascii=False,
                separators=(",", ":"),
                default=lambda o: redact_secrets(_safe_str(o)),
                allow_nan=False,
            )
        except Exception:
            fallback = {
                "ts": _utc_now_iso(),
                "level": "error",
                "event": "observability.format_error",
                "service": "observability",
                "entry_point": "unknown",
                "request_id": "",
                "operation": "format",
                "status": "error",
                "duration_ms": None,
                "model": None,
                "error_class": "other",
                "attempt": None,
                "meta": {},
            }
            return json.dumps(fallback, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


_LOGGER_NAME = "buena_espero"
_LOGGER_LOCK = threading.Lock()


def get_logger() -> logging.Logger:
    """Return the configured structured JSON logger."""
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        with _LOGGER_LOCK:
            if not logger.handlers:
                handler = logging.StreamHandler(sys.stderr)
                handler.setFormatter(JSONLogFormatter())
                logger.addHandler(handler)
                logger.setLevel(logging.INFO)
                logger.propagate = False
    return logger


_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


def log_event(
    event: str,
    *,
    service: str,
    operation: str,
    level: str = "info",
    status: str = "ok",
    duration_ms: Optional[float] = None,
    model: Optional[str] = None,
    error_class: Optional[str] = None,
    attempt: Optional[int] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Emit a single-line structured JSON log event and return its redacted payload (strictly fail-open)."""
    try:
        lvl_norm = _safe_str(level or "info").strip().lower()
        if lvl_norm == "warn":
            lvl_norm = "warning"
        py_level = _LEVEL_MAP.get(lvl_norm, logging.INFO)

        ctx = get_run_context()
        err_norm: Optional[str] = None
        if error_class is not None and error_class != "":
            err_norm = error_class if (isinstance(error_class, str) and error_class in VALID_ERROR_CLASSES) else "other"

        payload: Dict[str, Any] = {
            "ts": _utc_now_iso(),
            "level": lvl_norm if lvl_norm in _LEVEL_MAP else "info",
            "event": redact_secrets(_safe_str(event or "event")),
            "service": redact_secrets(_safe_str(service or "unknown")),
            "entry_point": ctx["entry_point"],
            "request_id": ctx["request_id"],
            "operation": redact_secrets(_safe_str(operation or "unknown")),
            "status": redact_secrets(_safe_str(status or "ok")),
            "duration_ms": _coerce_duration_ms(duration_ms),
            "model": redact_secrets(model) if model is not None else None,
            "error_class": err_norm,
            "attempt": _coerce_attempt(attempt),
            "meta": _redact_value(meta) if isinstance(meta, dict) else {},
        }

        try:
            logger = get_logger()
            logger.log(py_level, payload["event"], extra={"structured_payload": payload})
        except Exception:
            pass
        return payload
    except Exception:
        return {
            "ts": _utc_now_iso(),
            "level": "error",
            "event": "observability.log_event_error",
            "service": "observability",
            "entry_point": "unknown",
            "request_id": "",
            "operation": "log_event",
            "status": "error",
            "duration_ms": None,
            "model": None,
            "error_class": "other",
            "attempt": None,
            "meta": {},
        }


@contextlib.contextmanager
def observe_call(
    service: str,
    operation: str,
    *,
    model: Optional[str] = None,
    attempt: Optional[int] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Iterator[Dict[str, Any]]:
    """Context manager measuring latency, updating RED metrics, and emitting a JSON event (strictly fail-open)."""
    started = time.monotonic()
    state: Dict[str, Any] = {
        "event": f"{service}.{operation}",
        "status": "ok",
        "level": None,
        "model": model,
        "attempt": attempt,
        "error_class": None,
        "meta": dict(meta) if isinstance(meta, dict) else {},
    }
    try:
        yield state
    except Exception as exc:
        try:
            elapsed_ms = round((time.monotonic() - started) * 1000.0, 2)
            err_cls = state.get("error_class") or classify_error(exc)
            state["status"] = "error"
            state["error_class"] = err_cls
            raw_meta = state.get("meta")
            err_meta = dict(raw_meta) if isinstance(raw_meta, dict) else {}
            err_meta["error"] = safe_error_text(exc, max_len=240)
            lvl = state.get("level") or ("warning" if err_cls in ("quota_429", "transient_5xx", "timeout") else "error")
            _METRICS.record(
                service,
                operation,
                duration_ms=elapsed_ms,
                is_error=True,
                error_class=err_cls,
            )
            log_event(
                state.get("event") or f"{service}.{operation}",
                service=service,
                operation=operation,
                level=lvl,
                status="error",
                duration_ms=elapsed_ms,
                model=state.get("model"),
                error_class=err_cls,
                attempt=state.get("attempt"),
                meta=err_meta,
            )
        except Exception:
            pass
        raise
    else:
        try:
            elapsed_ms = round((time.monotonic() - started) * 1000.0, 2)
            status = _safe_str(state.get("status") or "ok")
            err_cls = state.get("error_class")
            is_err = status == "error" or bool(err_cls)
            lvl = state.get("level")
            if not lvl:
                if status == "error":
                    lvl = "error"
                elif status in ("degraded", "fallback", "cooldown_skip", "retry", "warning"):
                    lvl = "warning"
                else:
                    lvl = "info"
            safe_meta = state.get("meta") if isinstance(state.get("meta"), dict) else {}
            _METRICS.record(
                service,
                operation,
                duration_ms=elapsed_ms,
                is_error=is_err,
                error_class=err_cls,
            )
            log_event(
                state.get("event") or f"{service}.{operation}",
                service=service,
                operation=operation,
                level=lvl,
                status=status,
                duration_ms=elapsed_ms,
                model=state.get("model"),
                error_class=err_cls,
                attempt=state.get("attempt"),
                meta=safe_meta,
            )
        except Exception:
            pass
