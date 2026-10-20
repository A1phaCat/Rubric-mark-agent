from __future__ import annotations

import asyncio

import pytest

from app.config import Settings
from app.grading.service import _normalise_gate, grade_criterion
from app.llm.protocol import LLMResponse
from app.retrieval import retrieve_passages
from app.rubric.assessment import normalise_assessment_plan


def _document() -> dict:
    paragraphs = [
        {"page": 1, "label": "", "kind": "heading", "text": "Evaluation"},
    ]
    paragraphs.extend(
        {
            "page": 1 + index // 4,
            "label": f"¶{index + 1}",
            "kind": "paragraph",
            "text": text,
        }
        for index, text in enumerate(
            [
                "The evaluation uses evidence citation accuracy and unsupported judgement rate.",
                "Target users include tutors, coordinators and university markers.",
                "The implementation uses a local queue and deterministic validation.",
                "The project compares manual marking with whole-document LLM grading.",
                "A semester plan identifies milestones, owners, risks and mitigations.",
                "Requirements include traceable evidence identifiers and measurable outputs.",
                "The report explains privacy, retention and access-control constraints.",
                "References are integrated into the argument using consistent citations.",
            ]
        )
    )
    return {"paragraphs": paragraphs}


def _criterion() -> dict:
    return {
        "id": "c1",
        "name": "Evaluation plan and measurable evidence",
        "description": "Assess objective metrics, baselines and evaluation design.",
        "weight": 5,
        "levels": [
            {"label": "Excellent", "points": 5, "description": "Specific metrics and baselines"},
            {"label": "Limited", "points": 2, "description": "Weak evaluation evidence"},
        ],
    }


def test_hybrid_vector_index_is_cached_and_returns_ranked_passages(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, llm="fake")
    first = retrieve_passages(
        _document(),
        _criterion(),
        limit=6,
        settings=settings,
        submission_id="sub_vector_test",
        document_version=1,
    )
    second = retrieve_passages(
        _document(),
        _criterion(),
        limit=6,
        settings=settings,
        submission_id="sub_vector_test",
        document_version=1,
    )

    assert len(first) == 6
    assert [item.id for item in second] == [item.id for item in first]
    assert first[0].vector_score != 0
    assert "evaluation" in first[0].text.lower()
    assert len(list((tmp_path / "index").glob("sub_vector_test-*.json"))) == 1


def test_fake_grader_selects_up_to_five_retrieved_passages(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, llm="fake", evidence_top_k=5)
    passages = retrieve_passages(
        _document(),
        _criterion(),
        limit=8,
        settings=settings,
        submission_id="sub_top_five",
        document_version=1,
    )
    result = asyncio.run(
        grade_criterion(settings, _criterion(), passages, {"submission_id": "sub_top_five"})
    )

    assert len(result["evidence"]) == 5
    assert len({item["passage_id"] for item in result["evidence"]}) == 5


def test_gate_does_not_silently_turn_invalid_model_evidence_into_zero(monkeypatch) -> None:
    class InvalidGateLLM:
        async def list_models(self):
            return []

        async def complete(self, *, purpose, prompt, metadata=None):
            del purpose, prompt, metadata
            return LLMResponse(
                '{"evidence":[{"passage_id":"prompt-example","quote":"not real",'
                '"role":"primary","relevance":"direct","aspect_ids":["criterion"]}]}',
                "test",
                1,
                1,
            )

    monkeypatch.setattr("app.grading.service.build_llm", lambda settings: InvalidGateLLM())
    settings = Settings(llm="minimax")

    with pytest.raises(ValueError, match="do not match"):
        asyncio.run(
            grade_criterion(
                settings,
                _criterion(),
                retrieve_passages(_document(), _criterion(), limit=3),
                {"submission_id": "sub_invalid_gate"},
            )
        )


def test_long_paragraphs_are_split_into_overlapping_vector_chunks(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, llm="fake")
    document = {
        "paragraphs": [
            {
                "page": 4,
                "label": "¶7",
                "kind": "paragraph",
                "start_offset": 100,
                "text": " ".join(f"token{index}" for index in range(500)),
            }
        ]
    }
    passages = retrieve_passages(
        document,
        _criterion(),
        limit=10,
        settings=settings,
        submission_id="sub_long_paragraph",
        document_version=1,
    )

    assert len(passages) == 3
    assert {item.id for item in passages} == {"p1c1", "p1c2", "p1c3"}
    assert all(len(item.text.split()) <= 220 for item in passages)
    assert min(item.start_offset for item in passages) == 100


def test_analytic_plan_uses_explicit_level_requirements() -> None:
    criterion = {
        "name": "Requirements",
        "levels": [
            {
                "label": "3",
                "points": 3,
                "description": (
                    "Target users are identified; scope is bounded; functional requirements "
                    "are testable; non-functional requirements are measurable."
                ),
            },
            {"label": "0", "points": 0, "description": "Not demonstrated."},
        ],
    }

    mode, aspects = normalise_assessment_plan(criterion)

    assert mode == "analytic"
    assert len(aspects) == 4
    assert all(item["source"] == "derived" for item in aspects)


def test_binary_plan_stays_single_requirement() -> None:
    criterion = {
        "name": "Includes an approved ethics statement",
        "levels": [
            {"label": "Meets requirement", "points": 1, "description": "Present."},
            {"label": "Does not meet", "points": 0, "description": "Missing."},
        ],
    }

    mode, aspects = normalise_assessment_plan(criterion)

    assert mode == "binary"
    assert [item["id"] for item in aspects] == ["criterion"]


def test_evidence_gate_does_not_treat_five_hits_as_full_coverage(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, llm="fake")
    criterion = {
        **_criterion(),
        "grading_mode": "analytic",
        "aspects": [
            {"id": "metrics", "label": "Objective metrics", "source": "explicit"},
            {"id": "baselines", "label": "Comparison baselines", "source": "explicit"},
            {"id": "protocol", "label": "Evaluation protocol", "source": "explicit"},
        ],
    }
    passages = retrieve_passages(
        _document(),
        criterion,
        limit=6,
        settings=settings,
        submission_id="sub_gate_coverage",
        document_version=1,
    )
    raw = {
        "evidence": [
            {
                "passage_id": item.id,
                "quote": item.text,
                "role": "supporting",
                "relevance": "direct",
                "aspect_ids": ["metrics"],
            }
            for item in passages[:5]
        ]
    }

    gate = _normalise_gate(criterion, passages, raw)

    assert len(gate["evidence"]) == 5
    assert gate["sufficiency"] == "partial"
    assert gate["coverage_ratio"] == 0.333
    assert gate["missing_aspects"] == ["baselines", "protocol"]
