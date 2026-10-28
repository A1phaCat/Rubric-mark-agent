from app.ingest import sid_from_filename
from app.ingest.anonymise import AnonymisationReport, Anonymiser, residual_identifiers
from app.rubric.matching import RubricCandidate, rank_rubrics

SALT = b"unit-test-salt-0123456789"


def test_identifiers_are_replaced_with_stable_pseudonyms() -> None:
    anonymiser = Anonymiser(SALT)
    report = AnonymisationReport()
    text = (
        "Name: Jane Doe\nStudent ID: 12345678\nContact jdoe012@student.monash.edu or 0412 345 678.\n"
        "--Student ID:12345678\nSubmitted by Alex Chen on Monday."
    )
    out = anonymiser.text(text, report)
    for secret in ("Jane Doe", "12345678", "jdoe012", "0412", "Alex Chen"):
        assert secret not in out
    assert "on Monday." in out
    assert out.count(f"[ID-{anonymiser.pseudonym('sid', '12345678', 6)}]") == 2
    assert residual_identifiers(out) == []
    assert report.student_ids == 2 and report.emails == 1 and report.phones == 1 and report.names == 2


def test_ordinary_numbers_and_code_are_kept() -> None:
    out = Anonymiser(SALT).text("60000 rows, 12.5% growth, 2021-05-01, pi 3.14159265\nname: python3")
    assert out == "60000 rows, 12.5% growth, 2021-05-01, pi 3.14159265\nname: python3"


def test_pseudonymous_student_number_is_parseable_and_salted() -> None:
    first, second = Anonymiser(SALT), Anonymiser(b"another-salt-abcdefghij")
    number = first.student_number("row-42")
    assert len(number) == 8 and number.isdigit()
    assert sid_from_filename(f"SID-{number}.pdf") == f"SID-{number}"
    assert number == first.student_number("row-42") != second.student_number("row-42")


def test_rubric_ranking_prefers_matching_content_and_reports_shared_terms() -> None:
    candidates = [
        RubricCandidate("rub_db", "Database design", "entity relationship schema SQL normalisation tables keys"),
        RubricCandidate("rub_essay", "Critical essay", "thesis argument evidence counterargument structure prose"),
    ]
    ranked = rank_rubrics(
        "Assignment 1B Full Database Model and Implementation",
        ["CREATE TABLE customer ... the relationship schema uses SQL foreign keys"],
        candidates,
    )
    assert ranked[0].rubric_id == "rub_db"
    assert ranked[0].score > ranked[1].score
    assert "sql" in ranked[0].shared_terms or "schema" in ranked[0].shared_terms
    assert rank_rubrics("x", [], []) == []


def test_roster_names_tutors_and_group_numbers_are_redacted_everywhere() -> None:
    from app.ingest.anonymise import Anonymiser, residual_identifiers

    text = (
        "Group 7 — Mia Chen, Tom Nguyen\n"
        "Members  Mia Chen (530112874), Tom Nguyen\n(530067731)\n"
        "Lab tutor  Dr K. Morrison approved. Later Chen wrote the plan.\n"
        "read_csv('98765432-Smith-A2.csv') doi 10.1080/00207543.2018.1533261 p=0.00390625"
    )
    out = Anonymiser(b"s" * 16).text(text)
    for leaked in ("Mia", "Chen", "Tom", "Nguyen", "Morrison", "Smith", "530112874", "530067731", "98765432",
                   "Group 7"):
        assert leaked not in out
    assert "10.1080/00207543.2018.1533261" in out and "0.00390625" in out
    assert residual_identifiers(out) == []


def test_genre_bonus_prefers_a_rubric_of_the_same_assessment_type() -> None:
    from app.rubric.matching import RubricCandidate, rank_rubrics

    candidates = [
        RubricCandidate("rub_progress", "Progress Report", "progress report data analysis project group"),
        RubricCandidate("rub_journal", "Reflective Journal", "reflection learning growth"),
    ]
    ranked = rank_rubrics("Reflective piece 15%", ["data analysis project group work"], candidates)
    assert ranked[0].rubric_id == "rub_journal" and ranked[0].genre == "reflective"


def test_cover_page_name_formats_are_redacted() -> None:
    from app.ingest.anonymise import Anonymiser

    text = (
        "Alex Chen - ID 12345678\nJohn Smith (Student ID: 23456789)\nstudentname: Kim Park\n"
        "By Ann Moss, Student ID 11223344\nStudent: Joe Bloggs\n- Jordan Lee (z1234567)\n"
        "Team Mercury: Jane Doe, Bob Brown and Sue Tan\nUnit name: Data Analysis\nThe model was trained by Monday."
    )
    out = Anonymiser(b"s" * 16).text(text)
    for leaked in ("Alex", "Smith", "Kim Park", "Moss", "Bloggs", "Jordan", "z1234567", "Jane", "Brown", "Sue"):
        assert leaked not in out
    assert "Unit name: Data Analysis" in out and "trained by Monday" in out
