"""Turn the written submissions into PDFs and the evaluation dataset, and check them.

    python -m eval.cohort.build        (needs the Markdown and Playwright packages)

The dataset lists only submissions that exist and pass the checks. Checks cover front
matter, length, required/omitted section structure, reference-list policy, track naming
and verbatim injection cases. Criterion-level quality remains an evaluation target and
cannot be certified by lexical checks alone.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
_REFERENCES = re.compile(
    r"^#+\s*(\d+\.?\s*)?(references|bibliography)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)
_SECTION_TERMS = {
    "c1": ("problem", "background", "motivation"),
    "c2": ("user", "stakeholder", "scope", "requirement"),
    "c3": ("product", "solution", "methodology", "technical", "architecture"),
    "c4": ("business", "value", "alternative", "evaluation"),
    "c5": ("feasibility", "risk", "semester", "milestone", "plan"),
}


def words(markdown: str) -> int:
    body = re.sub(r"^---\n.*?\n---\n", "", markdown, flags=re.DOTALL)
    body = _REFERENCES.split(body)[0]
    return len(re.findall(r"[A-Za-z0-9][\w'’-]*", body))


def problems(spec: dict[str, Any], text: str) -> list[str]:
    found = []
    if not text.startswith("---\n"):
        found.append("no front matter")
    count = words(text)
    if spec["type"] != "near_duplicate" and not 0.67 * spec["words"] <= count <= 1.33 * spec["words"]:
        found.append(f"{count} words, specified {spec['words']}")
    if spec.get("injection") and " ".join(spec["injection"]["text"].split()) not in " ".join(text.split()):
        found.append("the injected sentence is missing or changed")
    if "B — Research Prototype" in text or "B - Research Prototype" in text:
        found.append("obsolete Track B label")
    has_references = bool(_REFERENCES.search(text))
    if spec["type"] == "rough_unreferenced" and has_references:
        found.append("rough_unreferenced case unexpectedly has references")
    if spec["type"] not in {"rough_unreferenced", "near_duplicate"} and not has_references:
        found.append("no references section")
    if spec["type"] not in {"off_topic", "near_duplicate"}:
        headings = " ".join(
            re.findall(r"^#{1,4}\s+(.+)$", text, flags=re.MULTILINE)
        ).lower()
        missing = set(spec.get("missing_sections", []))
        for criterion, terms in _SECTION_TERMS.items():
            present = any(term in headings for term in terms)
            if criterion in missing and present:
                found.append(f"{criterion} should be omitted but a matching heading exists")
            elif criterion not in missing and not present:
                found.append(f"{criterion} has no recognisable section heading")
    return found


def main() -> None:
    from playwright.sync_api import sync_playwright

    from eval.proposals.build_pdfs import render

    specs = json.loads((HERE / "specs.json").read_text(encoding="utf-8"))
    (HERE / "pdf").mkdir(exist_ok=True)
    cases, rejected = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        for spec in specs:
            source = HERE / "src" / f"{spec['id']}.md"
            if not source.exists():
                continue
            text = source.read_text(encoding="utf-8")
            issues = problems(spec, text)
            if issues:
                rejected.append((spec["id"], issues))
                continue
            target = HERE / "pdf" / f"{spec['id']}.pdf"
            render(source, target, page)
            cases.append({
                "id": spec["id"], "rubric": "elec5623-business-proposal", "pdf": f"pdf/{spec['id']}.pdf",
                "source_row": 0, "type": spec["type"], "length": spec["length"], "words": words(text),
                "design": spec["topic"], "intended": spec["intended"], "planted": spec["planted"],
                **({"source": spec["source"]} if spec.get("source") else {}),
                "intended_total": sum(spec["intended"].values()),
            })
        browser.close()
    dataset = {
        "description": "A cohort of synthetic ELEC5623 business proposals written to a specification per "
                       "criterion by a different model from the one evaluated. Intended marks and planted gaps "
                       "are the specification, not human marks.",
        "rubrics": ["elec5623-business-proposal"],
        "decoys_from": "../datasets/main.json",
        "cases": cases,
    }
    (HERE / "dataset.json").write_text(json.dumps(dataset, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(cases)} submissions → {HERE / 'dataset.json'}")
    for sid, issues in rejected:
        print(f"  rejected {sid}: {'; '.join(issues)}")


if __name__ == "__main__":
    main()
