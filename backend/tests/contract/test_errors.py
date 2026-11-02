from fastapi.testclient import TestClient

from app.main import app


def test_canvas_is_disconnected_by_default_and_uses_stable_error_shape() -> None:
    with TestClient(app) as client:
        settings = client.get("/api/v1/settings/canvas")
        assert settings.status_code == 200
        assert settings.json()["enabled"] is False and settings.json()["has_token"] is False

        courses = client.get("/api/v1/canvas/courses")
        assert courses.status_code == 409
        assert courses.json()["error"]["code"] == "canvas_not_connected"

        update = client.put("/api/v1/settings/canvas", json={"base_url": "http://canvas.example"})
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
