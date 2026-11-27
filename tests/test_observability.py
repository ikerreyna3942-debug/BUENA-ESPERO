"""Tests for structured JSON logging, secret redaction, error taxonomy,
ThreadPoolExecutor context propagation, bounded RED metrics, and Gemini runtime telemetry.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services import gemini_runtime, observability


def _reject_non_rfc8259(const: str):
    raise ValueError(f"Non-RFC8259 constant: {const}")


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self.setFormatter(observability.JSONLogFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))

    def parsed(self) -> list[dict]:
        return [json.loads(line, parse_constant=_reject_non_rfc8259) for line in self.lines]


class TestObservabilityModule(unittest.TestCase):
    def setUp(self) -> None:
        observability.reset_observability_state()
        gemini_runtime.reset_runtime_state()
        self.logger = observability.get_logger()
        self.capture = _CaptureHandler()
        self.logger.addHandler(self.capture)

    def tearDown(self) -> None:
        self.logger.removeHandler(self.capture)
        observability.reset_observability_state()
        gemini_runtime.reset_runtime_state()

    def test_single_line_json_schema_contains_all_required_fields(self) -> None:
        ctx = observability.set_run_context("studio_v8", request_id="req-abc123")
        self.assertEqual(ctx, {"entry_point": "studio_v8", "request_id": "req-abc123"})

        observability.log_event(
            "gemini.vision.ok",
            service="gemini_runtime",
            operation="call_gemini_fast",
            level="info",
            status="ok",
            duration_ms=142.5,
            model="gemini-3.5-flash-lite",
            error_class=None,
            attempt=1,
            meta={"thinking_level": "MINIMAL"},
        )

        self.assertEqual(len(self.capture.lines), 1)
        raw_line = self.capture.lines[0]
        self.assertNotIn("\n", raw_line)
        rec = json.loads(raw_line, parse_constant=_reject_non_rfc8259)

        expected_keys = {
            "ts",
            "level",
            "event",
            "service",
            "entry_point",
            "request_id",
            "operation",
            "status",
            "duration_ms",
            "model",
            "error_class",
            "attempt",
            "meta",
        }
        self.assertEqual(set(rec.keys()), expected_keys)
        self.assertEqual(rec["level"], "info")
        self.assertEqual(rec["event"], "gemini.vision.ok")
        self.assertEqual(rec["service"], "gemini_runtime")
        self.assertEqual(rec["entry_point"], "studio_v8")
        self.assertEqual(rec["request_id"], "req-abc123")
        self.assertEqual(rec["operation"], "call_gemini_fast")
        self.assertEqual(rec["status"], "ok")
        self.assertEqual(rec["duration_ms"], 142.5)
        self.assertEqual(rec["model"], "gemini-3.5-flash-lite")
        self.assertIsNone(rec["error_class"])
        self.assertEqual(rec["attempt"], 1)
        self.assertEqual(rec["meta"], {"thinking_level": "MINIMAL"})

    def test_redact_secrets_scrubs_all_credential_patterns_and_nested_meta(self) -> None:
        # 100% synthetic test placeholders built via concatenation so raw source bytes
        # never resemble real credentials or trigger GitHub Push Protection (GH013).
        fake_aiza = "AIza" + "Sy0000DummyTestKey00000000000000000"
        fake_oauth = "ya29." + "0000Dummy.OAuth_Access-Token000000"
        fake_aq = "AQ." + "0000Dummy.Google_Key-TestOnly000000000"
        fake_gocspx = "GOCSPX-" + "0000Dummy_Client-Secret00000"
        fake_refresh = "1//" + "00Dummy_Refresh-Token_TestOnly0000000000"
        fake_bearer = "Bearer " + "dummy.jwt.test.token.value"
        fake_bearer_lower = "bearer " + "dummy.lower.test.token.value"
        pem_hdr = "-----BEGIN " + "PRIVATE KEY-----"
        pem_ftr = "-----END " + "PRIVATE KEY-----"
        fake_pem = f"{pem_hdr}\nSYNTHETIC_PEM_BODY_NOT_REAL_000000000000\n{pem_ftr}"
        long_fake_pem = (
            f"{pem_hdr}\n"
            + ("SYNTHETIC_TRUNC_PEM_NOT_REAL_000000000000\n" * 40)
            + pem_ftr
        )
        truncated_fake_pem = long_fake_pem[:220]
        self.assertNotIn(pem_ftr, truncated_fake_pem)

        combined = (
            f"keys: {fake_aiza} | {fake_oauth} | {fake_aq} | "
            f"{fake_gocspx} | {fake_refresh} | {fake_bearer} | {fake_bearer_lower} | {fake_pem}"
        )
        redacted = observability.redact_secrets(combined)
        for secret in (
            fake_aiza,
            fake_oauth,
            fake_aq,
            fake_gocspx,
            fake_refresh,
            "dummy.jwt.test.token.value",
            "dummy.lower.test.token.value",
            "SYNTHETIC_PEM_BODY_NOT_REAL",
        ):
            self.assertNotIn(secret, redacted)
        self.assertIn("[REDACTED_API_KEY]", redacted)
        self.assertIn("[REDACTED_OAUTH_TOKEN]", redacted)
        self.assertIn("[REDACTED_GOOGLE_KEY]", redacted)
        self.assertIn("[REDACTED_CLIENT_SECRET]", redacted)
        self.assertIn("[REDACTED_REFRESH_TOKEN]", redacted)
        self.assertIn("Bearer [REDACTED_TOKEN]", redacted)
        self.assertIn("[REDACTED_PRIVATE_KEY]", redacted)

        # Verify truncated / unterminated PEM private keys (e.g. sliced at 220 chars) are scrubbed
        redacted_trunc = observability.redact_secrets(f"SA parse failed: {truncated_fake_pem}")
        self.assertNotIn("SYNTHETIC_TRUNC_PEM_NOT_REAL", redacted_trunc)
        self.assertIn("[REDACTED_PRIVATE_KEY]", redacted_trunc)

        # Verify log_event scrubs secrets inside nested meta (and truncated PEM) and never leaks to JSON
        observability.log_event(
            f"err with {fake_aiza}",
            service="sheets_service",
            operation="auth",
            level="error",
            status="error",
            error_class="auth_401_403",
            meta={"nested": {"err": combined, "trunc_pem": truncated_fake_pem}},
        )
        emitted = self.capture.lines[-1]
        self.assertIsInstance(json.loads(emitted, parse_constant=_reject_non_rfc8259), dict)
        for secret in (
            fake_aiza,
            fake_oauth,
            fake_aq,
            fake_gocspx,
            fake_refresh,
            "dummy.jwt.test.token.value",
            "dummy.lower.test.token.value",
            "SYNTHETIC_PEM_BODY_NOT_REAL",
            "SYNTHETIC_TRUNC_PEM_NOT_REAL",
        ):
            self.assertNotIn(secret, emitted)

    def test_classify_error_bounded_taxonomy(self) -> None:
        cases = [
            (RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded"), "quota_429"),
            (RuntimeError("HTTP 403 PERMISSION_DENIED API key was reported as leaked"), "auth_401_403"),
            (RuntimeError("401 UNAUTHENTICATED invalid api key"), "auth_401_403"),
            (RuntimeError("404 NOT_FOUND model no longer available"), "not_found_404"),
            (TimeoutError("request timed out"), "timeout"),
            (RuntimeError("DEADLINE_EXCEEDED waiting for upstream"), "timeout"),
            (RuntimeError("503 UNAVAILABLE high demand"), "transient_5xx"),
            (RuntimeError("502 Bad Gateway"), "transient_5xx"),
            (RuntimeError("400 INVALID_ARGUMENT bad request"), "bad_request_400"),
            (ConnectionError("Connection reset by peer"), "network"),
            (ValueError("unexpected parsing failure"), "other"),
        ]
        for exc, expected in cases:
            got = observability.classify_error(exc)
            self.assertEqual(got, expected, f"Failed for {exc!r}: got {got}")
            self.assertIn(got, observability.VALID_ERROR_CLASSES)

    def test_context_propagates_across_thread_pool_executor(self) -> None:
        observability.set_run_context("studio_v8", request_id="req-parallel-99")

        def _worker(tag: str) -> dict:
            ctx = observability.get_run_context()
            observability.log_event(
                "worker.done",
                service="ai_prompt_service_v8",
                operation="analyze_all_parallel",
                meta={"tag": tag},
            )
            return ctx

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futs = [
                ex.submit(observability.copy_context_for_thread(_worker, f"slot-{i}"))
                for i in range(3)
            ]
            results = [f.result() for f in futs]

        for r in results:
            self.assertEqual(r["entry_point"], "studio_v8")
            self.assertEqual(r["request_id"], "req-parallel-99")

        records = self.capture.parsed()
        self.assertEqual(len(records), 3)
        for rec in records:
            self.assertEqual(rec["entry_point"], "studio_v8")
            self.assertEqual(rec["request_id"], "req-parallel-99")

    def test_bounded_red_metrics_and_percentiles_p50_p95_p99(self) -> None:
        reg = observability.MetricsRegistry(maxlen=100)
        for ms in range(1, 151):
            reg.record(
                "gemini_runtime",
                "vision_generate_content",
                duration_ms=float(ms),
                is_error=(ms % 10 == 0),
                error_class="quota_429" if ms % 10 == 0 else None,
            )

        snap = reg.snapshot()
        self.assertIn("gemini_runtime.vision_generate_content", snap)
        m = snap["gemini_runtime.vision_generate_content"]
        self.assertEqual(m["count"], 150)
        self.assertEqual(m["error_count"], 15)
        self.assertEqual(m["error_by_class"], {"quota_429": 15})
        # Bounded deque retained only the last 100 samples (51..150)
        self.assertEqual(m["samples"], 100)
        self.assertGreaterEqual(m["p50_ms"], 100.0)
        self.assertLessEqual(m["p50_ms"], 101.0)
        self.assertGreaterEqual(m["p95_ms"], 144.0)
        self.assertGreaterEqual(m["p99_ms"], 148.0)
        self.assertLessEqual(m["p50_ms"], m["p95_ms"])
        self.assertLessEqual(m["p95_ms"], m["p99_ms"])

    def test_observe_call_records_success_and_exception_metrics(self) -> None:
        observability.set_run_context("alta_fotos", request_id="req-obs-01")

        with observability.observe_call("sheets_service", "upload_file", model=None) as st:
            st["meta"]["bytes"] = 1024

        with self.assertRaises(RuntimeError):
            with observability.observe_call("sheets_service", "upload_file"):
                raise RuntimeError("429 RESOURCE_EXHAUSTED")

        snap = observability.get_metrics_snapshot()
        m = snap["sheets_service.upload_file"]
        self.assertEqual(m["count"], 2)
        self.assertEqual(m["error_count"], 1)
        self.assertEqual(m["error_by_class"], {"quota_429": 1})
        self.assertGreaterEqual(m["p50_ms"], 0.0)

        recs = self.capture.parsed()
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["status"], "ok")
        self.assertEqual(recs[0]["entry_point"], "alta_fotos")
        self.assertEqual(recs[1]["status"], "error")
        self.assertEqual(recs[1]["error_class"], "quota_429")
        self.assertEqual(recs[1]["request_id"], "req-obs-01")

    def test_gemini_runtime_induced_429_503_403_emits_structured_logs_and_metrics(self) -> None:
        observability.set_run_context("studio_v8", request_id="req-gem-429-503")
        calls: list[str] = []
        quota_dummy_key = "AIza" + "Sy0000DummyQuotaKey0000000000000000"
        auth_dummy_key = "AIza" + "Sy0000DummyAuthKey00000000000000000"

        class _FakeModels:
            def generate_content(self, model, contents, config=None):
                calls.append(model)
                if len(calls) == 1:
                    raise RuntimeError(f"429 RESOURCE_EXHAUSTED quota exceeded for {quota_dummy_key}")
                if len(calls) == 2:
                    raise RuntimeError("503 UNAVAILABLE high demand")
                return SimpleNamespace(text='{"ok": true}')

        fake_client = SimpleNamespace(models=_FakeModels())
        res = gemini_runtime.call_gemini_fast(fake_client, contents=["hi"], api_key="test-key")
        self.assertEqual(res.text, '{"ok": true}')
        self.assertEqual(len(calls), 3)

        records = self.capture.parsed()
        raw_joined = "\n".join(self.capture.lines)
        self.assertNotIn(quota_dummy_key, raw_joined)
        self.assertIn("[REDACTED_API_KEY]", raw_joined)

        error_classes = [r["error_class"] for r in records if r["error_class"]]
        self.assertIn("quota_429", error_classes)
        self.assertIn("transient_5xx", error_classes)
        self.assertTrue(any(r["event"] == "gemini.vision.transient_cooldown" for r in records))
        self.assertTrue(all(r["request_id"] == "req-gem-429-503" for r in records))
        self.assertTrue(all(r["entry_point"] == "studio_v8" for r in records))

        # Induced 403 auth failure with no fallback
        class _AuthFailModels:
            def generate_content(self, model, contents, config=None):
                raise RuntimeError(f"403 PERMISSION_DENIED API key leaked {auth_dummy_key}")

        with self.assertRaises(RuntimeError):
            gemini_runtime.call_gemini_fast(
                SimpleNamespace(models=_AuthFailModels()),
                contents=["hi"],
                api_key="bad-key",
                fallback_key="",
            )

        post_records = self.capture.parsed()
        self.assertTrue(
            any(
                r["event"] == "gemini.vision.auth_failed" and r["error_class"] == "auth_401_403"
                for r in post_records
            )
        )
        self.assertNotIn(auth_dummy_key, "\n".join(self.capture.lines))

        snap = observability.get_metrics_snapshot()
        self.assertIn("gemini_runtime.vision_generate_content", snap)
        m = snap["gemini_runtime.vision_generate_content"]
        self.assertGreaterEqual(m["count"], 4)
        self.assertGreaterEqual(m["error_count"], 3)
        self.assertIn("quota_429", m["error_by_class"])
        self.assertIn("transient_5xx", m["error_by_class"])
        self.assertIn("auth_401_403", m["error_by_class"])

    def test_redact_truncated_pem_straddling_key_and_safe_error_text(self) -> None:
        pem_hdr = "-----BEGIN " + "PRIVATE KEY-----"
        pem_ftr = "-----END " + "PRIVATE KEY-----"
        long_pem = f"{pem_hdr}\n" + ("SYNTHETIC_PEM_LINE_NOT_REAL_000000000000\n" * 45) + pem_ftr
        self.assertGreater(len(long_pem), 1600)

        # 1. Truncated PEM passed through safe_error_text must never leak PEM body
        safe_pem = observability.safe_error_text(f"SA auth failed: {long_pem}", max_len=220)
        self.assertNotIn("SYNTHETIC_PEM_LINE_NOT_REAL", safe_pem)
        self.assertIn("[REDACTED_PRIVATE_KEY]", safe_pem)
        self.assertLessEqual(len(safe_pem), 220)

        # 2. API key straddling index 220 must be redacted BEFORE slicing
        straddle_key = "AIza" + "Sy0000StraddleBoundaryKey000000000"
        straddle_msg = ("x" * 210) + straddle_key + " trailing"
        safe_straddle = observability.safe_error_text(straddle_msg, max_len=220)
        self.assertNotIn("AIza", safe_straddle)
        self.assertNotIn("StraddleBoundaryKey", safe_straddle)
        self.assertLessEqual(len(safe_straddle), 220)

        # 3. Broken __str__ exception must never raise in safe_error_text
        class _BrokenExc(Exception):
            def __str__(self) -> str:
                raise RuntimeError("boom in __str__")

        broken_out = observability.safe_error_text(_BrokenExc(), max_len=220)
        self.assertIn("str_failed", broken_out)

        # 4. Live gemini_runtime.call_gemini_fast 403 with 1,650-char PEM scrubs both logs & last_vision_meta
        class _PemAuthModels:
            def generate_content(self, model, contents, config=None):
                raise RuntimeError(f"403 PERMISSION_DENIED bad key: {long_pem}")

        with self.assertRaises(RuntimeError):
            gemini_runtime.call_gemini_fast(
                SimpleNamespace(models=_PemAuthModels()),
                contents=["hi"],
                api_key="bad-key",
                fallback_key="",
            )

        raw_logs = "\n".join(self.capture.lines)
        self.assertNotIn("SYNTHETIC_PEM_LINE_NOT_REAL", raw_logs)
        self.assertIn("[REDACTED_PRIVATE_KEY]", raw_logs)
        meta_err = gemini_runtime.get_last_vision_meta()["error"]
        self.assertNotIn("SYNTHETIC_PEM_LINE_NOT_REAL", meta_err)
        self.assertIn("[REDACTED_PRIVATE_KEY]", meta_err)
        self.assertGreater(len(self.capture.parsed()), 0)

    def test_redact_non_string_meta_dict_keys_sets_bytes_paths_exceptions(self) -> None:
        k_aiza = "AIza" + "Sy0000DummyDictKeySecret0000000000"
        k_oauth = "ya29." + "0000DummySetOAuthToken00000000000"
        k_refresh = "1//" + "00DummyBytesRefreshToken000000000000"
        k_aq = "AQ." + "0000DummyPathGoogleKey0000000000000"
        k_gocspx = "GOCSPX-" + "0000DummyExcClientSecret0000"
        k_bearer = "Bearer " + "dummy.custom.obj.jwt.token"

        class _CustomHolder:
            def __str__(self) -> str:
                return f"auth={k_bearer}"

        observability.log_event(
            "meta.non_string.redaction",
            service="observability",
            operation="test",
            meta={
                f"key_{k_aiza}": "val",
                "set_field": {k_oauth},
                "frozenset_field": frozenset([k_oauth]),
                "bytes_field": k_refresh.encode("utf-8"),
                "bytearray_field": bytearray(k_refresh.encode("utf-8")),
                "path_field": Path(f"synthetic/{k_aq}/cred.json"),
                "exc_field": RuntimeError(f"failed {k_gocspx}"),
                "custom_obj": _CustomHolder(),
            },
        )

        emitted = self.capture.lines[-1]
        parsed = json.loads(emitted, parse_constant=_reject_non_rfc8259)
        self.assertIsInstance(parsed, dict)
        for secret in (
            k_aiza,
            k_oauth,
            k_refresh,
            k_aq,
            k_gocspx,
            "dummy.custom.obj.jwt.token",
        ):
            self.assertNotIn(secret, emitted)
        self.assertIn("[REDACTED_API_KEY]", emitted)
        self.assertIn("[REDACTED_OAUTH_TOKEN]", emitted)
        self.assertIn("[REDACTED_REFRESH_TOKEN]", emitted)
        self.assertIn("[REDACTED_GOOGLE_KEY]", emitted)
        self.assertIn("[REDACTED_CLIENT_SECRET]", emitted)
        self.assertIn("Bearer [REDACTED_TOKEN]", emitted)

    def test_fail_open_telemetry_circular_meta_bad_numbers_nan_and_exception_preservation(self) -> None:
        # 1. Circular dict/list + shared non-circular sibling DAG + deep nesting > 12
        circ: dict = {"name": "root"}
        circ["self"] = circ
        circ_list: list = []
        circ_list.append(circ_list)
        shared = {"ok": 42}
        deep: dict = {"leaf": "end"}
        for _ in range(14):
            deep = {"nested": deep}

        class _BrokenMetaObj:
            def __str__(self) -> str:
                raise RuntimeError("meta __str__ exploded")

        payload = observability.log_event(
            "telemetry.fail_open.test",
            service="observability",
            operation="fail_open",
            duration_ms="bad",  # type: ignore[arg-type]
            attempt="bad",  # type: ignore[arg-type]
            meta={
                "circ": circ,
                "circ_list": circ_list,
                "sib1": shared,
                "sib2": shared,
                "deep": deep,
                "nan_val": float("nan"),
                "inf_val": float("inf"),
                "broken_obj": _BrokenMetaObj(),
            },
        )
        self.assertIsNone(payload["duration_ms"])
        self.assertIsNone(payload["attempt"])
        self.assertEqual(payload["meta"]["circ"]["self"], "[CIRCULAR_REF]")
        self.assertEqual(payload["meta"]["circ_list"][0], "[CIRCULAR_REF]")
        self.assertEqual(payload["meta"]["sib1"], {"ok": 42})
        self.assertEqual(payload["meta"]["sib2"], {"ok": 42})
        self.assertIsNone(payload["meta"]["nan_val"])
        self.assertIsNone(payload["meta"]["inf_val"])
        self.assertIn("[MAX_DEPTH]", json.dumps(payload["meta"]["deep"]))
        self.assertIn("str_failed", payload["meta"]["broken_obj"])

        # NaN/Inf durations must not pollute metrics or break RFC 8259 JSON
        observability.log_event(
            "telemetry.nan_duration",
            service="observability",
            operation="fail_open",
            duration_ms=float("nan"),
        )
        observability.log_event(
            "telemetry.inf_duration",
            service="observability",
            operation="fail_open",
            duration_ms=float("inf"),
        )
        reg = observability.MetricsRegistry(maxlen=10)
        reg.record("svc", "op", duration_ms=10.0)
        reg.record("svc", "op", duration_ms=float("nan"))
        reg.record("svc", "op", duration_ms=float("inf"))
        reg.record("svc", "op", duration_ms="bad")  # type: ignore[arg-type]
        snap = reg.snapshot()["svc.op"]
        self.assertEqual(snap["count"], 4)
        self.assertEqual(snap["samples"], 1)
        self.assertEqual(snap["p50_ms"], 10.0)

        # 2. Mutated state["meta"] inside observe_call must NEVER swallow caller exception
        class _CallerSentinelError(RuntimeError):
            pass

        with self.assertRaises(_CallerSentinelError):
            with observability.observe_call("svc", "mutated_meta") as st:
                st["meta"] = "not-a-dict"
                raise _CallerSentinelError("original failure")

        # 3. Broken exc.__str__() inside observe_call must NEVER swallow caller exception
        class _BrokenCallerError(Exception):
            def __str__(self) -> str:
                raise ValueError("cannot stringify exception")

        with self.assertRaises(_BrokenCallerError):
            with observability.observe_call("svc", "broken_exc"):
                raise _BrokenCallerError()

        # Every emitted line must be strict RFC 8259 JSON
        parsed_all = self.capture.parsed()
        self.assertGreaterEqual(len(parsed_all), 5)

    def test_copy_context_for_thread_reusable_concurrently_and_v7_threadpool_and_logger_lock(self) -> None:
        observability.set_run_context("studio_v7", request_id="req-reusable-ctx")
        barrier = threading.Barrier(4)

        def _barrier_worker(idx: int) -> tuple[int, dict]:
            barrier.wait(timeout=5.0)
            return idx, observability.get_run_context()

        # Single wrapped callable reused concurrently across 4 threads (Barrier + executor.map)
        wrapped = observability.copy_context_for_thread(_barrier_worker)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            results = list(ex.map(wrapped, range(4)))
        self.assertEqual(len(results), 4)
        for idx, ctx in results:
            self.assertEqual(ctx["entry_point"], "studio_v7")
            self.assertEqual(ctx["request_id"], "req-reusable-ctx")

        # Verify AIPromptServiceV7.analyze_all_parallel propagates entry_point & request_id
        from services.ai_prompt_service_v7 import AIPromptServiceV7

        v7_svc = AIPromptServiceV7()
        seen_ctxs: list[dict] = []
        seen_lock = threading.Lock()

        def _stub_furn(furniture_bytes=None, notas_usuario=""):
            with seen_lock:
                seen_ctxs.append(observability.get_run_context())
            return {"furniture_type": "Sillón"}

        def _stub_mat(sample_bytes, material_type="wood", sample_name=""):
            with seen_lock:
                seen_ctxs.append(observability.get_run_context())
            return {"color": "ok", "material_type": material_type}

        v7_svc.analyze_furniture_for_enhancement = _stub_furn  # type: ignore[method-assign]
        v7_svc.analyze_material = _stub_mat  # type: ignore[method-assign]
        observability.set_run_context("studio_v7", request_id="req-v7-parallel-77")
        v7_svc.analyze_all_parallel(
            furniture_bytes=[b"furn"],
            wood_bytes=b"wood",
            wood_name="Roble",
            fabric_bytes=b"fab",
            fabric_name="Lino",
        )
        self.assertEqual(len(seen_ctxs), 3)
        for ctx in seen_ctxs:
            self.assertEqual(ctx["entry_point"], "studio_v7")
            self.assertEqual(ctx["request_id"], "req-v7-parallel-77")

        # Verify concurrent get_logger() initialization attaches exactly 1 handler
        logger = logging.getLogger(observability._LOGGER_NAME)
        orig_handlers = list(logger.handlers)
        try:
            logger.handlers.clear()
            init_barrier = threading.Barrier(6)

            def _init_logger(_i: int) -> int:
                init_barrier.wait(timeout=5.0)
                return len(observability.get_logger().handlers)

            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
                counts = list(ex.map(_init_logger, range(6)))
            self.assertEqual(len(logger.handlers), 1)
            self.assertTrue(all(c == 1 for c in counts))
        finally:
            logger.handlers.clear()
            for h in orig_handlers:
                logger.addHandler(h)

    def test_classify_error_word_boundaries_precedence_and_bare_timeout_cooldown(self) -> None:
        self.assertEqual(
            observability.classify_error("403 PERMISSION_DENIED: quota project not enabled"),
            "auth_401_403",
        )
        self.assertEqual(
            observability.classify_error("Port 4000 refused (ECONNREFUSED)"),
            "network",
        )
        self.assertEqual(
            observability.classify_error("Failed reading IMG_4290.jpg"),
            "other",
        )
        self.assertEqual(
            observability.classify_error("Order 4041"),
            "other",
        )
        self.assertEqual(
            observability.classify_error("5000px"),
            "other",
        )
        self.assertTrue(gemini_runtime._is_transient_error(TimeoutError()))

        # Bare TimeoutError() must trigger transient_cooldown in call_gemini_fast
        calls: list[str] = []

        class _BareTimeoutModels:
            def generate_content(self, model, contents, config=None):
                calls.append(model)
                if len(calls) == 1:
                    raise TimeoutError()
                return SimpleNamespace(text='{"ok": true}')

        res = gemini_runtime.call_gemini_fast(
            SimpleNamespace(models=_BareTimeoutModels()),
            contents=["hi"],
            api_key="test-key",
        )
        self.assertEqual(res.text, '{"ok": true}')
        recs = self.capture.parsed()
        self.assertTrue(
            any(
                r["event"] == "gemini.vision.transient_cooldown" and r["error_class"] == "timeout"
                for r in recs
            )
        )

        # 403 with "quota" word must log consistent auth_401_403 across adjacent records
        self.capture.lines.clear()
        gemini_runtime.reset_runtime_state()

        class _QuotaWord403Models:
            def generate_content(self, model, contents, config=None):
                raise RuntimeError("403 PERMISSION_DENIED: quota project not enabled")

        with self.assertRaises(RuntimeError):
            gemini_runtime.call_gemini_fast(
                SimpleNamespace(models=_QuotaWord403Models()),
                contents=["hi"],
                api_key="bad-key",
                fallback_key="",
            )

        adj = self.capture.parsed()
        self.assertGreaterEqual(len(adj), 2)
        err_classes = [r["error_class"] for r in adj if r["status"] == "error"]
        self.assertTrue(err_classes)
        self.assertTrue(all(ec == "auth_401_403" for ec in err_classes), f"Inconsistent classes: {err_classes}")


if __name__ == "__main__":
    unittest.main()
