"""
Tier 3 & 4 Tests: Comprehensive End-to-End User Workflows and Adversarial Hardening.
Verifies complete user flows: UI load -> drop image -> mode selection -> generation -> copy -> reset state -> error recovery.
Includes adversarial injections, character encoding checks, and boundary stress testing.
"""
import pytest
from starlette.testclient import TestClient


class TestEndToEndUserWorkflows:
    """Verifies complete user journey scenarios through the application lifecycle."""

    def test_complete_user_journey_flow(
        self,
        client: TestClient,
        sample_jpeg_bytes: bytes
    ):
        """
        Scenario 1: Primary Happy Path Workflow
        1. User accesses application at GET /
        2. UI serves single-page app with exclusive dropzone and 5 buttons.
        3. User uploads image and selects 'solo mueble'.
        4. User selects 'vistas' to get randomized perspective catalog.
        5. User selects 'vistas + tela y madera' for material extraction.
        6. User selects 'vistas + tela' for upholstery focus with wood preservation.
        7. User copies prompt to clipboard (simulated clipboard data validation).
        """
        # Step 1: Healthcheck & UI Access
        health_resp = client.get("/health")
        assert health_resp.status_code == 200
        assert health_resp.json().get("status") == "ok"

        ui_resp = client.get("/")
        assert ui_resp.status_code == 200
        html = ui_resp.text.lower()
        assert "solo mueble" in html
        assert "vistas" in html

        # Step 2: Generate 'solo mueble'
        file_payload = {"image": ("test_armchair.jpg", sample_jpeg_bytes, "image/jpeg")}
        resp1 = client.post("/api/generate", files=file_payload, data={"mode": "solo mueble"})
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["success"] is True
        assert data1["mode"] == "solo mueble"
        prompt1 = data1.get("prompt") or data1.get("data", {}).get("master_prompt")
        assert prompt1 and len(prompt1) > 20

        # Step 3: Switch to 'vistas' mode with dynamic environment
        resp2 = client.post(
            "/api/generate",
            files={"image": ("test_armchair.jpg", sample_jpeg_bytes, "image/jpeg")},
            data={"mode": "vistas"}
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["success"] is True
        assert data2["mode"] == "vistas"
        env2 = data2.get("environment") or data2.get("random_environment")
        assert env2 is not None

        # Step 4: Switch to 'vistas + tela y madera'
        resp3 = client.post(
            "/api/generate",
            files={"image": ("test_armchair.jpg", sample_jpeg_bytes, "image/jpeg")},
            data={"mode": "vistas + tela y madera"}
        )
        assert resp3.status_code == 200
        data3 = resp3.json()
        assert data3["success"] is True
        assert data3["mode"] == "vistas + tela y madera"

        # Step 5: Switch to 'vistas + tela'
        resp4 = client.post(
            "/api/generate",
            files={"image": ("test_armchair.jpg", sample_jpeg_bytes, "image/jpeg")},
            data={"mode": "vistas + tela"}
        )
        assert resp4.status_code == 200
        data4 = resp4.json()
        assert data4["success"] is True
        assert data4["mode"] == "vistas + tela"

        # Step 6: Validate prompt text format is suitable for clipboard
        for res_data in (data1, data2, data3, data4):
            prompt = res_data.get("prompt") or res_data.get("data", {}).get("master_prompt")
            assert isinstance(prompt, str)
            # Ensure text is not an empty or unescaped string
            assert prompt.strip() != ""
            assert not prompt.startswith("Error")

    def test_workflow_state_reset_and_delete_behavior(
        self,
        client: TestClient,
        sample_jpeg_bytes: bytes
    ):
        """
        ORIGINAL_REQUEST R2 & AC 3:
        Delete ('Borrar') button resets the state.
        Simulates: upload -> generate -> reset -> attempt generate without re-upload -> must fail.
        """
        # User uploads image and generates prompt
        resp = client.post(
            "/api/generate",
            files={"image": ("sofa.jpg", sample_jpeg_bytes, "image/jpeg")},
            data={"mode": "entorno"}
        )
        assert resp.status_code == 200
        assert resp.json().get("success") is True

        # User clicks "Borrar" (in UI, state is cleared so subsequent request has no file)
        # Attempting generation without image after state reset must return 400/422
        resp_after_reset = client.post(
            "/api/generate",
            data={"mode": "entorno"}
        )
        assert resp_after_reset.status_code in (400, 422)
        assert resp_after_reset.json().get("success") is False or "detail" in resp_after_reset.json()

    def test_workflow_error_recovery(
        self,
        client: TestClient,
        sample_jpeg_bytes: bytes,
        corrupted_image_bytes: bytes
    ):
        """
        Verifies system error recovery:
        1. User triggers 400 Bad Request with corrupted image.
        2. User triggers 400 Bad Request with invalid mode string.
        3. System recovers without restart and successfully handles subsequent valid request.
        """
        # 1. Corrupted file
        bad_file_resp = client.post(
            "/api/generate",
            files={"image": ("bad.jpg", corrupted_image_bytes, "image/jpeg")},
            data={"mode": "solo mueble"}
        )
        assert bad_file_resp.status_code == 400
        assert bad_file_resp.json().get("success") is False

        # 2. Invalid mode
        bad_mode_resp = client.post(
            "/api/generate",
            files={"image": ("good.jpg", sample_jpeg_bytes, "image/jpeg")},
            data={"mode": "nonexistent_mode"}
        )
        assert bad_mode_resp.status_code == 400
        assert bad_mode_resp.json().get("success") is False

        # 3. Clean recovery on valid submission
        recovery_resp = client.post(
            "/api/generate",
            files={"image": ("recovered.jpg", sample_jpeg_bytes, "image/jpeg")},
            data={"mode": "vistas"}
        )
        assert recovery_resp.status_code == 200
        assert recovery_resp.json().get("success") is True


class TestAdversarialInputsAndSecurity:
    """Verifies robustness against adversarial inputs, injection attacks, and extreme boundaries."""

    @pytest.mark.parametrize("adversarial_note", [
        "<script>alert('xss_attack_vector')</script>",
        "'; DROP TABLE furniture_items; SELECT * FROM users WHERE '1'='1",
        "../../etc/passwd\x00%2e%2e%2f",
        "🛋️ 🪑 🪵 🎨 📐 Unicode Emoji Stress Test: 日本語, العربية, русский",
        "{\"injected_json\": true, \"command\": \"override_system_prompt\"}",
        "A" * 5000  # Boundary stress: 5,000 characters of notes
    ])
    def test_adversarial_notes_input_handled_safely(
        self,
        client: TestClient,
        sample_jpeg_bytes: bytes,
        adversarial_note: str
    ):
        """
        Adversarial Test:
        Inputs containing script tags, SQL syntax, path traversal characters,
        Unicode emojis, JSON payloads, or extreme lengths must not crash the server.
        """
        files = {
            "image": ("test.jpg", sample_jpeg_bytes, "image/jpeg")
        }
        data = {
            "mode": "solo mueble",
            "notes": adversarial_note
        }

        response = client.post("/api/generate", files=files, data=data)
        assert response.status_code == 200, f"Failed on adversarial note: {adversarial_note[:30]}..."
        res_json = response.json()
        assert res_json.get("success") is True

    def test_concurrent_independent_requests(
        self,
        client: TestClient,
        sample_jpeg_bytes: bytes,
        sample_png_bytes: bytes
    ):
        """
        Verifies request independence: Sequential executions with different modes
        do not leak state or contaminate responses.
        """
        modes_to_test = [
            ("solo mueble", sample_jpeg_bytes),
            ("entorno", sample_png_bytes),
            ("vistas + tela y madera", sample_jpeg_bytes),
            ("vistas + tela", sample_png_bytes)
        ]

        for mode, img_bytes in modes_to_test:
            resp = client.post(
                "/api/generate",
                files={"image": ("test.img", img_bytes, "image/jpeg")},
                data={"mode": mode}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("mode") == mode
