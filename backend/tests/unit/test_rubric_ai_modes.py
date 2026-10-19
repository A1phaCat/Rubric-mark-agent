from app.api.rubrics import _apply_draft_plan, _is_draft_request, _structure_errors


def test_informal_rubric_requirements_select_ai_draft_mode() -> None:
    assert _is_draft_request(
        "我需要4个criteria，每项满分3分，0到3每1分一个level，关于ELEC5623 proposal。"
    )
    assert not _is_draft_request(
        "CRITERION: Analysis\nMAX: 1\n1: Complete.\n0.5: Partial.\n0: Missing."
    )


def test_explicit_requests_to_write_or_complete_select_ai_draft_mode() -> None:
    assert _is_draft_request("I need a rubric whose structure is four criteria with four levels.")
    assert _is_draft_request("Can you write them for an ELEC5623 group proposal?")
    assert _is_draft_request("Please fill in the missing level descriptors below.")
    assert _is_draft_request("能不能帮我补全这些评分等级的描述？")


def test_plain_pasted_rubric_does_not_authorise_generation() -> None:
    assert not _is_draft_request(
        "Analysis (3 marks)\nExcellent (3): Complete analysis.\nDeveloping (1): Partial analysis."
    )
    assert not _is_draft_request(
        "Draft rubric\nCRITERION: Analysis\nMAX: 3\nExcellent (3): Complete analysis."
    )


def test_ai_structure_rejects_placeholders_and_empty_descriptors() -> None:
    errors = _structure_errors(
        {
            "title": "Proposal rubric",
            "criteria": [
                {
                    "name": "Criterion name",
                    "weight": 3,
                    "levels": [
                        {"label": "Level 1", "points": 1, "description": "Describe this level..."},
                        {"label": "Level 2", "points": 2, "description": ""},
                    ],
                }
            ],
        }
    )

    assert "criterion 1 has no meaningful name" in errors
    assert "criterion 1 level 1 has no descriptor" in errors
    assert "criterion 1 level 2 has no descriptor" in errors


def test_draft_numbers_are_derived_by_code_from_inclusive_range() -> None:
    parsed = {
        "title": "Proposal rubric",
        "criteria": [
            {
                "name": f"Criterion {index}",
                "levels": [
                    {"label": label, "description": f"Descriptor {label}."}
                    for label in ("Excellent", "Good", "Basic", "Missing")
                ],
            }
            for index in range(1, 5)
        ],
    }

    result = _apply_draft_plan(
        parsed,
        "我需要4个criteria，每个3个level，0-3，1分为一个level，关于proposal。",
    )

    assert [criterion["weight"] for criterion in result["criteria"]] == [3, 3, 3, 3]
    assert [level["points"] for level in result["criteria"][0]["levels"]] == [3, 2, 1, 0]
    assert result["total_score"] == 12
    assert any(item["code"] == "inclusive_score_range" for item in result["assumptions"])


def test_draft_without_marks_returns_a_question_instead_of_inventing_scores() -> None:
    result = _apply_draft_plan(
        {
            "title": "Proposal rubric",
            "criteria": [
                {
                    "name": "Analysis",
                    "levels": [
                        {"label": "Excellent", "description": "Complete and specific."},
                        {"label": "Missing", "description": "Not demonstrated."},
                    ],
                }
            ],
        },
        "Please create a rubric for a group proposal.",
    )

    assert result["criteria"][0]["weight"] is None
    assert result["criteria"][0]["levels"][0]["points"] is None
    assert result["questions"][0]["code"] == "criterion_marks_required"
