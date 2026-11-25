import shutil
from pathlib import Path

import pytest

from app.sample.seed import RUBRIC_FILES, SampleDataError, load_rubric_files


def test_bundled_rubric_files_load_with_ids_from_file_names() -> None:
    specs = {spec["id"]: spec for spec in load_rubric_files()}
    assert {"rub_criticalessay", "rub_literaturereview", "rub_shortanswer"} <= set(specs)
    assert sum(c["weight"] for c in specs["rub_shortanswer"]["criteria"]) == 100
    assert not any(spec["id"].startswith("rub__") for spec in specs.values())  # templates ignored


def test_templates_parse_as_json_and_csv(tmp_path: Path) -> None:
    shutil.copy(RUBRIC_FILES / "_template.json", tmp_path / "lab.json")
    shutil.copy(RUBRIC_FILES / "_template.csv", tmp_path / "lab2.csv")
    specs = {spec["id"]: spec for spec in load_rubric_files(tmp_path)}
    assert [c["name"] for c in specs["rub_lab"]["criteria"]] == ["Method", "Results"]
    assert len(specs["rub_lab"]["criteria"][1]["levels"]) == 3
    assert [level["points"] for level in specs["rub_lab2"]["criteria"][0]["levels"]] == [10, 8.4, 7.4, 6.4, 4.9]
    assert specs["rub_lab2"]["source"] == "Preloaded · lab2.csv"


def test_an_ambiguous_file_stops_the_seed(tmp_path: Path) -> None:
    (tmp_path / "broken.csv").write_text("Criterion,Points,HD,FL\nArgument,30,Clear,None\n", encoding="utf-8")
    with pytest.raises(SampleDataError, match="broken.csv"):
        load_rubric_files(tmp_path)
