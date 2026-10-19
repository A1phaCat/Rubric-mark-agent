from fastapi.testclient import TestClient

from app.main import app


def test_hybrid_parse_returns_recognised_partial_rubric_with_structured_warnings() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rubrics/parse",
            json={
                "source_name": "partial.txt",
                "text": "Draft rubric\nCRITERION: Analysis\nMAX: 3\nExcellent (3):",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["parser"] == "level_text"
    assert body["mode"] == "parsed"
    assert len(body["rubric"]["criteria"]) == 1
    assert {item["code"] for item in body["warnings"]} == {
        "criterion_needs_levels",
        "level_missing_descriptor",
    }
    assert body["assumptions"] == []
    assert body["questions"] == []
    assert "grading_mode" not in body["rubric"]["criteria"][0]
    assert "aspects" not in body["rubric"]["criteria"][0]


def test_hybrid_parse_accepts_canvas_json_without_calling_llm() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rubrics/parse",
            json={
                "source_name": "canvas.json",
                "text": """{
                  "title": "Canvas rubric",
                  "points_possible": 3,
                  "criteria": [{
                    "description": "Accuracy",
                    "points": 3,
                    "ratings": [
                      {"description": "Excellent", "long_description": "Complete.", "points": 3},
                      {"description": "Missing", "long_description": "Absent.", "points": 0}
                    ]
                  }]
                }""",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["parser"] == "canvas_json"
    assert body["rubric"]["total_score"] == 3
    assert [item["points"] for item in body["rubric"]["criteria"][0]["levels"]] == [3, 0]
    assert "grading_mode" not in body["rubric"]["criteria"][0]
    assert "aspects" not in body["rubric"]["criteria"][0]
