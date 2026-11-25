from fastapi.testclient import TestClient

from app.main import app


def test_canvas_settings_start_disconnected_and_reject_a_blank_address() -> None:
    with TestClient(app) as client:
        settings = client.get("/api/v1/settings/canvas")
        assert settings.status_code == 200
        assert settings.json()["has_token"] is False and settings.json()["enabled"] is False
        update = client.put("/api/v1/settings/canvas", json={"base_url": "  "})
        assert update.status_code == 422
        assert update.json()["error"]["code"] == "validation_error"


def test_batch_pdf_export_is_an_explicit_post_mvp_stub() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/batches/bat_quiz2/report-export")
        assert response.status_code == 501
        assert response.json()["error"]["code"] == "feature_not_enabled"


def test_ai_connection_test_uses_server_side_provider_registry() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/settings/ai/test",
            json={"provider": "fake", "model": "fake-marker-v1"},
        )
        assert response.status_code == 200
        assert response.json()["models"] == ["fake-marker-v1"]


def test_ai_connection_test_skips_the_probe_for_a_model_the_provider_does_not_offer() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/settings/ai/test", json={"provider": "fake", "model": "gpt-5-mini"})
        body = response.json()
        assert body["ok"] is True and body["model"] is None and body["models"] == ["fake-marker-v1"]
        assert "Choose a model" in body["message"]
        offered = client.post("/api/v1/settings/ai/test", json={"provider": "fake", "model": "fake-marker-v1"}).json()
        assert offered["ok"] is True and offered["model"] == "fake-marker-v1"
