import json

from app.rubric.parser import extract_rubric_file, parse_rubric_text


def test_parser_preserves_three_criteria_with_four_point_levels() -> None:
    rubric = parse_rubric_text(
        """Short response rubric (9 marks)
1. Accuracy — 3 marks
Excellent (3): Correct and complete.
Good (2): Mostly correct.
Basic (1): Partly correct.
Missing (0): Incorrect or absent.
2. Reasoning — 3 marks
Excellent (3): Fully supported.
Good (2): Sound but brief.
Basic (1): Limited.
Missing (0): No reasoning.
3. Communication — 3 marks
Excellent (3): Precise.
Good (2): Clear overall.
Basic (1): Sometimes unclear.
Missing (0): Cannot be assessed.
"""
    )

    assert len(rubric["criteria"]) == 3
    assert sum(item["weight"] for item in rubric["criteria"]) == 9
    assert all(len(item["levels"]) == 4 for item in rubric["criteria"])
    assert [level["points"] for level in rubric["criteria"][0]["levels"]] == [3, 2, 1, 0]
    assert [level["label"] for level in rubric["criteria"][0]["levels"]] == [
        "Excellent",
        "Good",
        "Basic",
        "Missing",
    ]


def test_parser_reads_markdown_table_levels() -> None:
    rubric = parse_rubric_text(
        """Practical rubric
| Criteria | 3 points | 2 points | 1 point | 0 points |
| --- | --- | --- | --- | --- |
| Accuracy (3 marks) | Complete | Mostly correct | Partial | Missing |
| Clarity (3 marks) | Precise | Clear | Uneven | Unclear |
"""
    )

    assert len(rubric["criteria"]) == 2
    assert [level["points"] for level in rubric["criteria"][1]["levels"]] == [3, 2, 1, 0]


def test_parser_infers_wide_table_roles_and_preserves_arbitrary_level_names() -> None:
    rubric = parse_rubric_text(
        """Studio assessment (8 marks)
| Maximum | Dimension | Exceeds expectations | On track | Needs revision |
| --- | --- | --- | --- | --- |
| 5 | Research design | **5** Rigorous and justified. | **3** Mostly sound. | **1** Major gaps. |
| 3 | Communication | **3** Precise. | **2** Generally clear. | **0** Not readable. |
"""
    )

    assert rubric["_parser"] == "scoring_table"
    assert [criterion["name"] for criterion in rubric["criteria"]] == [
        "Research design",
        "Communication",
    ]
    assert [criterion["weight"] for criterion in rubric["criteria"]] == [5, 3]
    assert [level["label"] for level in rubric["criteria"][0]["levels"]] == [
        "Exceeds expectations",
        "On track",
        "Needs revision",
    ]
    assert [level["points"] for level in rubric["criteria"][0]["levels"]] == [5, 3, 1]


def test_parser_uses_table_shape_when_column_vocabulary_is_unknown() -> None:
    rubric = parse_rubric_text(
        """Custom assessment (6 marks)
| What is assessed | Available | Gold | Silver | Resubmit |
| --- | --- | --- | --- | --- |
| Investigation | 4 | 4 Comprehensive. | 2 Adequate. | 0 Missing. |
| Presentation | 2 | 2 Polished. | 1 Understandable. | 0 Unclear. |
"""
    )

    assert [criterion["name"] for criterion in rubric["criteria"]] == [
        "Investigation",
        "Presentation",
    ]
    assert [criterion["weight"] for criterion in rubric["criteria"]] == [4, 2]
    assert [level["label"] for level in rubric["criteria"][0]["levels"]] == [
        "Gold",
        "Silver",
        "Resubmit",
    ]


def test_parser_handles_wrapped_matrix_rows_without_assuming_hd_scale() -> None:
    rubric = parse_rubric_text(
        """# Final Project Report (30 pts)
| Criterion | Pts | HD | DI | CR | PS | FL |
|---|---|---|---|---|---|---|
| Introduction | 5 | **5** Complete. | **4.2** Strong. | **3.7** Adequate. | **3.2** Partial. | **2.45** Fails to explain

most criteria. |
| Architecture | 25 | **25** Outstanding. | **21.2** Strong. | **18.7** Adequate. | **16.2** Partial. | **12** Missing. |
"""
    )

    assert rubric["title"] == "Final Project Report (30 pts)"
    assert [criterion["name"] for criterion in rubric["criteria"]] == [
        "Introduction",
        "Architecture",
    ]
    assert [criterion["weight"] for criterion in rubric["criteria"]] == [5, 25]
    assert [level["label"] for level in rubric["criteria"][0]["levels"]] == [
        "HD",
        "DI",
        "CR",
        "PS",
        "FL",
    ]
    assert rubric["criteria"][0]["levels"][-1]["description"] == "Fails to explain most criteria."


def test_parser_groups_long_form_level_rows_by_criterion() -> None:
    rubric = parse_rubric_text(
        """Evidence rubric
Criterion\tBand\tScore\tDescriptor
Analysis\tConvincing\t4\tClaims are fully supported.
Analysis\tDeveloping\t2\tSome claims are supported.
Analysis\tAbsent\t0\tNo relevant analysis.
Reflection\tInsightful\t3\tSpecific and critical.
Reflection\tBasic\t1\tMostly descriptive.
Reflection\tMissing\t0\tNot included.
"""
    )

    assert [criterion["name"] for criterion in rubric["criteria"]] == [
        "Analysis",
        "Reflection",
    ]
    assert [criterion["weight"] for criterion in rubric["criteria"]] == [4, 3]
    assert [level["label"] for level in rubric["criteria"][1]["levels"]] == [
        "Insightful",
        "Basic",
        "Missing",
    ]


def test_parser_reports_missing_table_scores_instead_of_inventing_them() -> None:
    rubric = parse_rubric_text(
        """Qualitative rubric
| Criterion | Maximum | Demonstrated | Partly demonstrated | Not demonstrated |
| --- | --- | --- | --- | --- |
| Safety | 4 | Risks are controlled. | Some controls are missing. | Risks are ignored. |
"""
    )

    levels = rubric["criteria"][0]["levels"]
    assert [level["points"] for level in levels] == [None, None, None]
    assert sum(warning["code"] == "level_missing_points" for warning in rubric["warnings"]) == 3


def test_parser_reads_canvas_export_blocks_without_treating_granularity_as_criterion() -> None:
    rubric = parse_rubric_text(
        """# ELEC5623 Proposal — Canvas marking rubric (3.5 marks)
Source: Canvas export.
CRITERION: Problem and Motivation
ID: R1
MAX: 1.5
GRANULARITY: 0.5
1.5: Specific, supported and compelling.
1: Clear with minor gaps.
0.5: Vague or weakly supported.
0: Not addressed.

CRITERION: Technical Design
ID: R2
MAX: 2
GRANULARITY: 0.5
2: Credible, coherent and detailed.
1.5: Sound with minor gaps.
1: Plausible but incomplete.
0.5: Vague or unrealistic.
0: Not addressed.
"""
    )

    assert rubric["title"] == "ELEC5623 Proposal — Canvas marking rubric (3.5 marks)"
    assert [criterion["name"] for criterion in rubric["criteria"]] == [
        "Problem and Motivation",
        "Technical Design",
    ]
    assert [criterion["weight"] for criterion in rubric["criteria"]] == [1.5, 2]
    assert [len(criterion["levels"]) for criterion in rubric["criteria"]] == [4, 5]


def test_parser_flattens_explicit_scored_subcriteria_without_inventing_parent_levels() -> None:
    rubric = parse_rubric_text(
        """# Transport Planning — Assessment Rubric (2 Marks)
## CRITERION: Analysis
ID: R1
MAX: 2
### SUBCRITERION: Challenges
ID: R1.1
MAX: 1
1: Specific and supported.
0.5: Partly supported.
0: Missing.
### SUBCRITERION: Stakeholders
ID: R1.2
MAX: 1
1: Needs and conflicts are evaluated.
0.5: Stakeholders are listed.
0: Missing.
"""
    )

    assert [criterion["name"] for criterion in rubric["criteria"]] == [
        "Analysis — Challenges",
        "Analysis — Stakeholders",
    ]
    assert sum(criterion["weight"] for criterion in rubric["criteria"]) == 2
    assert all(
        [level["points"] for level in criterion["levels"]] == [1, 0.5, 0]
        for criterion in rubric["criteria"]
    )


def test_recognised_incomplete_rubric_returns_gaps_instead_of_failing() -> None:
    rubric = parse_rubric_text(
        """Draft rubric
CRITERION: Analysis
MAX: 3
Excellent (3):
"""
    )

    assert len(rubric["criteria"]) == 1
    assert len(rubric["criteria"][0]["levels"]) == 1
    assert {warning["code"] for warning in rubric["warnings"]} == {
        "criterion_needs_levels",
        "level_missing_descriptor",
    }


def test_named_levels_without_scores_are_not_assigned_invented_points() -> None:
    rubric = parse_rubric_text(
        """Reflection rubric
CRITERION: Reflection
MAX: 4
Excellent: Insightful and specific.
Good: Generally reflective.
Poor: Mostly descriptive.
"""
    )

    assert [level["points"] for level in rubric["criteria"][0]["levels"]] == [None, None, None]
    assert sum(warning["code"] == "level_missing_points" for warning in rubric["warnings"]) == 3


def test_canvas_json_is_parsed_without_llm_and_keeps_ratings() -> None:
    content = {
        "title": "Canvas rubric",
        "points_possible": 3,
        "criteria": [
            {
                "description": "Accuracy",
                "long_description": "Assesses correctness.",
                "points": 3,
                "ratings": [
                    {"description": "Excellent", "long_description": "Complete.", "points": 3},
                    {"description": "Missing", "long_description": "Absent.", "points": 0},
                ],
            }
        ],
    }

    text = json.dumps(content)
    rubric = parse_rubric_text(text, "canvas.json")

    assert rubric["_parser"] == "canvas_json"
    assert rubric["criteria"][0]["description"] == "Assesses correctness."
    assert [level["points"] for level in rubric["criteria"][0]["levels"]] == [3, 0]
    assert extract_rubric_file("canvas.json", text.encode()) == text
