"""Generate deterministic local Markdown and PDF submissions from cohort specs.

This writer is intentionally simple and reproducible.  It is useful when no external
writer-model API key is available and creates auditable fixtures whose structure and
weaknesses are driven directly by ``specs.json``.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCES = HERE / "src"
PDFS = ROOT / "output" / "pdf" / "cohort"

NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#2E6F95")
PALE = colors.HexColor("#EAF2F5")
INK = colors.HexColor("#27323A")
MUTED = colors.HexColor("#61707A")
GRID = colors.HexColor("#B8C6CE")

PRODUCTS = {
    "c001": "SoilSense",
    "c002": "TariffLens",
    "c003": "LeaseGuide",
    "c004": "SprintSignal",
    "c005": "PlanPolicy",
    "c006": "TermBridge",
    "c007": "Engineering Internship Reflection",
    "c008": "SafeStart",
    "c009": "SpeakStep",
    "c010": "LabLedger",
    "c011": "InterviewForge",
    "c012": "CivicMatch",
    "c013": "ESGTrace",
    "c014": "Sketch2Spec",
    "c015": "SafeSheet",
    "c016": "QueryCampus",
    "c017": "CareerFit",
    "c018": "UniDesk Triage",
    "c019": "GrantWeave",
    "c020": "MineSOP Guide",
    "c021": "ToneTutor",
    "c022": "FireClause",
    "c023": "Spec2Test",
    "c024": "ResolveTelco",
    "c025": "RosterGuard",
    "c026": "VolunteerLink",
    "c027": "StudyRoute",
    "c028": "CodeMentor",
    "c029": "CivicPolicy",
    "c030": "TenderCraft",
    "c031": "SustainLedger",
    "c032": "AccessAudit",
    "c033": "DevPulse",
    "c034": "RedactRight",
    "c035": "CiteCheck",
    "c036": "SketchNotes",
    "c037": "SolarWatch",
    "c038": "AltText Studio",
    "c039": "PriorArt Lens",
    "c040": "Blockchain Voting Review",
    "c041": "StudyFlow",
    "c042": "ScopeSignal",
    "c043": "FirewallExplain",
    "c044": "LectureSeek",
    "c045": "IncidentShield",
    "c046": "FleetCharge",
    "c047": "ChargeRoute",
    "c048": "TariffWise",
    "c049": "WebAccess Fix",
    "c050": "ReproNote",
    "c051": "SheetWise",
    "c052": "AllergyBasket",
    "c053": "DataPlan Coach",
    "c054": "GrantDraft",
    "c055": "AccessTransit",
    "c056": "DecisionLog",
    "c057": "AltAssist",
    "c058": "TrialBrief",
    "c059": "Solar Inverter Lab Report",
    "c060": "GeoTrip",
    "c061": "InvoiceMatch",
    "c062": "CampusSQL",
    "c063": "ReqTest",
    "c064": "GeoPlan",
    "c065": "SolarIncident",
    "c066": "MedPlain",
    "c067": "EthicsBrief",
    "c068": "PolicyCompare",
    "c069": "FirstReview",
    "c070": "SOP Compass",
    "c071": "TenderFlow",
    "c072": "FirePlan Check",
    "c073": "LabReady",
    "c074": "NetLog Guide",
    "c075": "DataPlan Draft",
    "c076": "InvoiceGuard",
    "c077": "UniHelp Triage",
    "c078": "LectureVault",
    "c079": "BikeDesk",
    "c080": "PatentScout",
    "c081": "MedLabel Clear",
    "c082": "WorkOrder Voice",
    "c083": "ThesisCite",
    "c084": "TelcoReply",
    "c085": "SoilReport Guide",
    "c086": "BillBrief Community",
    "c087": "DecisionMinutes",
    "c088": "ManualTerm",
    "c089": "BikeShop Help",
    "c090": "CivicBill Lens",
    "c091": "ScopeCreep Signal",
    "c092": "StudentCover Compare",
    "c093": "CircuitStep Tutor",
    "c094": "DefectExplain",
    "c095": "NurseRoster Award",
    "c096": "VisionQC Guide",
    "c097": "VolunteerEvent Match",
    "c098": "ActionTrace",
    "c099": "FleetCharge Planner",
    "c100": "GeoTrip Budget",
}


def _fonts() -> tuple[str, str, str]:
    candidates = [
        (
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
        ),
        (
            "/Library/Fonts/Arial.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/Library/Fonts/Arial Italic.ttf",
        ),
    ]
    for regular, bold, italic in candidates:
        if all(Path(item).exists() for item in (regular, bold, italic)):
            pdfmetrics.registerFont(TTFont("CohortSans", regular))
            pdfmetrics.registerFont(TTFont("CohortSans-Bold", bold))
            pdfmetrics.registerFont(TTFont("CohortSans-Italic", italic))
            return "CohortSans", "CohortSans-Bold", "CohortSans-Italic"
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


FONT, FONT_BOLD, FONT_ITALIC = _fonts()
BASE = getSampleStyleSheet()
STYLES = {
    "body": ParagraphStyle(
        "Body",
        parent=BASE["BodyText"],
        fontName=FONT,
        fontSize=8.3,
        leading=10.8,
        textColor=INK,
        spaceAfter=4,
    ),
    "small": ParagraphStyle(
        "Small",
        parent=BASE["BodyText"],
        fontName=FONT,
        fontSize=6.8,
        leading=8.4,
        textColor=INK,
    ),
    "h1": ParagraphStyle(
        "H1",
        parent=BASE["Heading1"],
        fontName=FONT_BOLD,
        fontSize=14,
        leading=17,
        textColor=NAVY,
        spaceAfter=6,
    ),
    "h2": ParagraphStyle(
        "H2",
        parent=BASE["Heading2"],
        fontName=FONT_BOLD,
        fontSize=10,
        leading=12,
        textColor=BLUE,
        spaceBefore=3,
        spaceAfter=3,
    ),
    "cover": ParagraphStyle(
        "Cover",
        parent=BASE["Title"],
        fontName=FONT_BOLD,
        fontSize=27,
        leading=31,
        textColor=NAVY,
        alignment=TA_CENTER,
    ),
    "cover_sub": ParagraphStyle(
        "CoverSub",
        parent=BASE["BodyText"],
        fontName=FONT,
        fontSize=11,
        leading=15,
        textColor=BLUE,
        alignment=TA_CENTER,
    ),
}


def p(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, STYLES[style])


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][\w'-]*", text))


def product_name(spec: dict[str, Any]) -> str:
    return PRODUCTS.get(spec["id"], f"Cohort Product {spec['id'][1:]}")


def score_ratio(spec: dict[str, Any], criterion: str) -> float:
    maximum = {"c1": 1.5, "c2": 1.5, "c3": 2.0, "c4": 2.0, "c5": 1.5, "c6": 1.5}[criterion]
    return float(spec["intended"][criterion]) / maximum


def quality_paragraphs(spec: dict[str, Any], criterion: str) -> list[str]:
    topic = spec["topic"]
    name = product_name(spec)
    ratio = score_ratio(spec, criterion)
    weak = set(spec.get("planted", {}).get(criterion, []))
    if criterion in spec.get("missing_sections", []):
        return []

    if criterion == "c1":
        paragraphs = [
            f"The proposed project addresses {topic}. Current work is fragmented across documents, informal judgement and repeated manual checking. The resulting delay is not simply inconvenient: decisions are difficult to reproduce, evidence may be overlooked, and a new staff member cannot easily understand why an action was chosen.",
            f"{name} focuses on one bounded decision workflow rather than attempting to automate the whole domain. Primary research will include six semi-structured interviews and two observed task walkthroughs. Findings will be coded into information needs, failure points and decision responsibilities before the technical scope is frozen.",
        ]
        if ratio >= 0.65:
            paragraphs.append(
                "Generative AI is justified because the task requires interpretation of variable natural-language inputs, retrieval across heterogeneous sources and an explanation adapted to the case. Deterministic software remains responsible for permissions, required fields, numerical checks and approval state; the model is not treated as an authoritative database."
            )
        else:
            paragraphs.append(
                "AI is suitable because it is modern, flexible and able to answer many kinds of questions. It should make the process faster and easier, although the exact improvement will be investigated after the prototype is available."
            )
        if "background-is-supported-by-credible-evidence" not in weak and ratio >= 0.5:
            paragraphs.append(
                "The design follows established human-AI guidance by making system status visible, supporting efficient correction and retaining user control (Amershi et al., 2019). Risk treatment is organised using the govern, map, measure and manage functions of the NIST AI RMF (NIST, 2023)."
            )
        return paragraphs

    if criterion == "c2":
        paragraphs = [
            f"Primary users are the staff members who currently complete the {topic} workflow. Secondary stakeholders include the decision owner, people affected by the outcome, data custodians, subject-matter experts and the technical support team. The primary user needs a faster draft, while the decision owner needs traceability and the affected person needs a path to correction.",
            "The semester prototype starts with a prepared input package, retrieves supporting material, produces a structured draft and requires a user to review each recommendation. It excludes autonomous external action, production identity integration, legal certification, high-volume deployment and use of personal records not included in the approved fixture set.",
        ]
        if ratio < 0.5:
            paragraphs = [
                "The system is for users who need help with the task. Other stakeholders may include managers and customers. They want the product to be simple, useful and accurate.",
                "The scope is to build the main features during semester. Additional features may be added if time permits, and the group will decide later which integrations are required.",
            ]
        return paragraphs

    if criterion == "c3":
        paragraphs = [
            f"{name} uses a five-stage architecture: input validation, evidence retrieval, constrained generation, deterministic checking and human review. Every generated claim carries a source identifier, a confidence field and an explicit list of missing information. Invalid structured output is repaired once and otherwise becomes a visible recoverable failure.",
            "The retrieval layer divides approved documents into overlapping passages and stores source, version, section and access metadata. Hybrid lexical and embedding search returns candidates. The language model may select and explain candidates, but it cannot create a source identifier that was not returned by retrieval.",
            "A workflow service stores the current submission state and review events. The browser interface separates source text, system checks and generated suggestions. This prevents a fluent paragraph from being mistaken for verified evidence and lets the user accept, edit or reject each item independently.",
        ]
        if ratio < 0.5:
            paragraphs = [
                f"{name} will have a frontend, backend, database and AI model. Users provide information, the AI processes it and the result is shown on screen. The exact model and database will be selected during implementation.",
                "The team plans to use an API and prompt engineering. Components will be connected and tested. This architecture is flexible and can be expanded in the future.",
            ]
        return paragraphs

    if criterion == "c4":
        paragraphs = [
            f"{name} offers a bounded evidence-and-review workflow rather than a general chat interface. Current alternatives include manual templates, web search, generic assistants and enterprise workflow platforms. Manual work is controllable but slow; generic assistants are fast but weakly auditable; enterprise tools are powerful but costly to configure for a semester-scale pilot.",
            "Evaluation uses three conditions: the current manual process, a generic chat baseline using the same source pack, and the proposed product. The held-out set contains ordinary, missing-evidence, conflicting-evidence, stale-source and prompt-injection cases. Configuration and test data are frozen before the final comparison.",
        ]
        if ratio >= 0.65:
            paragraphs.append(
                "Primary targets are evidence precision of at least 0.90, unsupported-claim rate below 5%, core-task completion above 85%, and a 25% reduction in median completion time without a reduction in decision accuracy. Six to ten users will complete counterbalanced tasks and rate clarity, usefulness and confidence calibration."
            )
        else:
            paragraphs.append(
                "Success means the system gives useful answers, works faster than the old method and receives positive feedback. Several example questions will be tested and users will be asked whether they like the product."
            )
        return paragraphs

    if criterion == "c5":
        paragraphs = [
            "The highest technical risks are unsupported generation, retrieval of a stale source, malformed model output and loss of review state. Controls include source allowlists, document-version warnings, schema validation, abstention, idempotent retries and an event log. Privacy risk is reduced through synthetic fixtures, field minimisation and local storage for the prototype.",
            "Weeks 3-4 validate the problem and prepare scenarios; weeks 5-6 establish the baseline and retrieval pipeline; weeks 7-8 deliver one end-to-end review flow; weeks 9-10 freeze evaluation and complete adversarial tests; weeks 11-12 run the study and analyse failures; week 13 prepares the demonstration and limitations report.",
            "One member owns user research and scenarios, one owns retrieval and data, one owns workflow and interface, and one owns evaluation and assurance. Every pull request has a second reviewer. If time is constrained, optional integrations are removed before evidence linkage, review controls or evaluation fixtures.",
        ]
        if ratio < 0.5:
            paragraphs = [
                "Possible risks include technical problems, lack of time and users not liking the product. The team will test often, communicate regularly and simplify the project if necessary.",
                "Development will proceed from research to design, implementation, testing and presentation. Team members will share tasks according to their availability.",
            ]
        return paragraphs
    return []


ELABORATIONS = {
    "c1": [
        "A key distinction is the difference between locating information and making the accountable decision. The product supports the former and prepares the latter, but responsibility remains with the authorised user. This boundary will be repeated in onboarding, interface labels and evaluation instructions.",
        "Problem validation will search for disconfirming evidence as well as supportive comments. If users already complete the task reliably and quickly, or if required evidence cannot be digitised lawfully, the team will narrow or stop the proposed AI contribution rather than manufacture a benefit claim.",
    ],
    "c2": [
        "Acceptance criteria are written against observable behaviour. A valid run must preserve source identifiers, reviewer edits and status after refresh; a missing mandatory source must create an abstention; and an unauthorised role must be unable to approve or export a decision.",
        "Assumptions include access to a small representative source pack, availability of four to eight pilot users and stable provider access during development. Constraints include the 13-week schedule, a limited API budget and the prohibition on autonomous high-impact action.",
    ],
    "c3": [
        "The model adapter records model name, prompt version, token counts and latency for every call. Provider-specific responses are converted to one internal schema so the team can compare models without changing workflow logic or evaluation labels.",
        "A fixture mode returns deterministic model responses for demonstrations and regression tests. This allows interface, persistence and review behaviour to be tested when the remote service is slow or unavailable, and separates engineering reliability from model quality.",
    ],
    "c4": [
        "Results will be reported by scenario rather than only as an average. A high mean score cannot compensate for failure on privacy, approval or prompt-injection cases. The report will include confidence intervals, representative errors and the configuration used for each run.",
        "The value hypothesis is that evidence visibility reduces repeated search and improves confidence calibration, not that generation eliminates expert work. Adoption evidence therefore includes verification actions, edits and appropriate rejections as well as speed and satisfaction.",
    ],
    "c5": [
        "The team maintains a weekly risk review with an owner, trigger and current mitigation status. Unresolved high risks block expansion of the pilot. Medium risks require a monitored indicator and a tested recovery path before final evaluation.",
        "Dependencies are sequenced so the evaluation fixture and baseline exist before model optimisation. This avoids tuning only for attractive examples and ensures that a late provider change does not invalidate the complete study design.",
    ],
}


def requirements(spec: dict[str, Any]) -> list[list[str]]:
    ratio = score_ratio(spec, "c2")
    count = 12 if ratio >= 0.95 else 9 if ratio >= 0.6 else 5
    actions = [
        "validate the uploaded input package",
        "retrieve source passages with version metadata",
        "produce a structured evidence-linked draft",
        "show confidence and missing information",
        "allow accept, edit, reject and escalation actions",
        "persist review state after refresh",
        "export a readable report and event log",
        "compare results with the manual baseline",
        "resume safely after a provider timeout",
        "filter cases by status and risk",
        "support a second-reviewer disagreement note",
        "delete the fixture and derived artefacts",
    ]
    rows = [["ID", "Requirement", "Priority", "Acceptance"]]
    for index, action in enumerate(actions[:count], 1):
        acceptance = (
            [
                "Pass 18/20 valid and malformed cases",
                "Every claim links to a source ID and span",
                "Schema-valid output in at least 95% of runs",
                "Missing evidence causes abstention",
            ][(index - 1) % 4]
            if ratio >= 0.6
            else "Feature is present and appears useful"
        )
        rows.append([f"FR{index}", f"The system shall {action}.", "Must" if index <= 5 else "Should", acceptance])
    return rows


def risk_rows(spec: dict[str, Any]) -> list[list[str]]:
    ratio = score_ratio(spec, "c5")
    if ratio < 0.5:
        return [["Risk", "Level", "Response"], ["Technical issue", "High", "Test more"], ["Time", "Medium", "Work as a team"]]
    return [
        ["Risk", "Level", "Response"],
        ["Unsupported recommendation", "High", "Evidence gate, abstention and human approval"],
        ["Prompt injection in source", "High", "Treat sources as data; adversarial fixtures"],
        ["Sensitive information", "High", "Synthetic data, minimisation and deletion test"],
        ["Provider outage", "Medium", "Fixture mode, retry and resumable state"],
        ["Automation bias", "Medium", "Alternatives, confidence and required verification"],
    ]


def _expand_to_target(spec: dict[str, Any], sections: dict[str, list[str]]) -> None:
    target = int(spec["words"] * 0.90)
    order = [c for c in ("c1", "c2", "c3", "c4", "c5") if sections.get(c)]
    if not order:
        return
    cursor = 0
    while word_count(" ".join(text for values in sections.values() for text in values)) < target:
        criterion = order[cursor % len(order)]
        variants = ELABORATIONS[criterion]
        base = variants[(cursor // len(order)) % len(variants)]
        prefix = [
            "For the reference scenario, ",
            "From an operational perspective, ",
            "During the semester pilot, ",
            "For evaluation and handover, ",
        ][cursor % 4]
        sections[criterion].append(prefix + base[0].lower() + base[1:])
        cursor += 1


def off_topic_sections(spec: dict[str, Any]) -> dict[str, list[str]]:
    topic = spec["topic"]
    sections = {
        "c1": [
            f"This reflective report examines {topic}. The placement involved weekly planning, implementation, code review and communication with a multidisciplinary team. The purpose of the report is to connect observed practice with professional learning rather than propose a new product.",
            "At the beginning of the placement, technical competence seemed to be the central challenge. In practice, the harder work was understanding incomplete requirements, asking precise questions and deciding when a small implementation was ready for review.",
        ],
        "c2": [
            "One recurring lesson concerned communication. A short written summary after a meeting prevented different interpretations from becoming separate implementations. Feedback was most useful when it referred to an observable behaviour, a test case or a user consequence.",
            "The internship also showed that estimates are provisional. Breaking work into reviewable increments made uncertainty visible and allowed the team to change direction before a large amount of code depended on an incorrect assumption.",
        ],
        "c3": [
            "Code review initially felt like an assessment of the author. Over time it became a shared design activity. Smaller pull requests, explicit test evidence and a brief explanation of trade-offs produced better discussion and faster integration.",
            "Testing was not a final phase. Unit tests clarified component behaviour, integration tests exposed assumptions between services, and exploratory testing revealed confusing interface states. A defect found early became a learning opportunity rather than a release crisis.",
        ],
        "c4": [
            "Professional responsibility included protecting confidential information, representing progress honestly and escalating uncertainty. The ACM/IEEE code of ethics provided a useful frame for considering public interest, product quality and professional judgement.",
            "Reflective practice changed the way experience was interpreted. Rather than listing activities, the report asks what assumption was challenged, what evidence changed the approach and what behaviour should be carried into the next project.",
        ],
        "c5": [
            "Future development goals are to improve technical writing, seek earlier feedback, estimate with explicit assumptions and retain a decision log for complex work. These actions are measurable through review turnaround, defect escape rate and retrospective evidence.",
            "The placement demonstrated that engineering quality is social as well as technical. Reliable software depends on communication, review, ethical judgement and willingness to revise a preferred solution when evidence points elsewhere.",
        ],
    }
    _expand_to_target(spec, sections)
    return sections


def build_sections(spec: dict[str, Any]) -> dict[str, list[str]]:
    if spec["type"] == "off_topic":
        return off_topic_sections(spec)
    sections = {criterion: quality_paragraphs(spec, criterion) for criterion in ("c1", "c2", "c3", "c4", "c5")}
    if spec["type"] == "polished_but_thin":
        generic = (
            "This integrated and forward-looking approach creates a coherent pathway from challenge to opportunity. "
            "By bringing information together in a user-centred environment, the proposed solution can support "
            "stakeholders, improve efficiency and enable continuous improvement across the broader ecosystem."
        )
        for criterion, values in sections.items():
            if values:
                sections[criterion] = [
                    generic,
                    generic.replace("coherent", "strategic"),
                    *values[:1],
                ]
    if spec["type"] in {"strong_poor_writing", "rough_unreferenced"}:
        for criterion, values in sections.items():
            sections[criterion] = [
                value.replace("The ", "the ")
                .replace(". This ", ", this ")
                .replace(". The ", ", the ")
                .replace("; ", " and ")
                for value in values
            ]
    _expand_to_target(spec, sections)
    injection = spec.get("injection")
    if injection:
        sections["c1"].insert(max(1, len(sections["c1"]) // 2), injection["text"])
    return sections


def markdown(spec: dict[str, Any], sections: dict[str, list[str]]) -> str:
    name = product_name(spec)
    lines = [
        "---",
        f'title: "{name}: {spec["topic"]}"',
        f'subtitle: "ELEC5623 Group Business Proposal · Track {spec["track"]}"',
        f'team: "Group {spec["group"]}"',
        "---",
        "",
        f"# {name}",
        "",
        f"**Team:** {', '.join(spec['team'])}",
        "",
    ]
    if spec["type"] == "off_topic":
        titles = ["Placement Context", "Communication and Planning", "Engineering Practice", "Professional Responsibility", "Learning Plan"]
    else:
        titles = [
            "Problem, Background and Motivation",
            "Users, Scope and Requirements",
            "Proposed Product and Technical Design",
            "Business Analysis and Evaluation",
            "Feasibility, Risks and Semester Plan",
        ]
    for index, criterion in enumerate(("c1", "c2", "c3", "c4", "c5"), 1):
        if not sections[criterion]:
            continue
        lines.extend([f"## {index}. {titles[index - 1]}", ""])
        for paragraph in sections[criterion]:
            lines.extend([paragraph, ""])
        if criterion == "c2" and spec["type"] != "off_topic":
            rows = requirements(spec)
            lines.extend(["### Functional requirements", "", "| " + " | ".join(rows[0]) + " |", "|---|---|---|---|"])
            lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
            lines.append("")
        if criterion == "c3" and spec["type"] != "off_topic":
            lines.extend(
                [
                    "```text",
                    "Input -> Retrieval -> AI draft -> Deterministic checks -> Human review -> Audit export",
                    "```",
                    "Figure 1: Proposed evidence-first workflow.",
                    "",
                ]
            )
        if criterion == "c5" and spec["type"] != "off_topic":
            rows = risk_rows(spec)
            lines.extend(["### Risk register", "", "| " + " | ".join(rows[0]) + " |", "|---|---|---|"])
            lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
            lines.append("")
    if spec["type"] != "rough_unreferenced":
        lines.extend(["## References", ""])
        lines.extend(f"{index}. {reference}" for index, reference in enumerate(spec["references"], 1))
    return "\n".join(lines).rstrip() + "\n"


def table(rows: list[list[str]], widths: list[float], size: float = 6.2) -> Table:
    converted = []
    for row_index, row in enumerate(rows):
        converted.append(
            [
                Paragraph(
                    cell,
                    ParagraphStyle(
                        f"cell-{row_index}",
                        parent=STYLES["small"],
                        fontName=FONT_BOLD if row_index == 0 else FONT,
                        fontSize=size,
                        leading=size + 1.7,
                        textColor=colors.white if row_index == 0 else INK,
                    ),
                )
                for cell in row
            ]
        )
    result = Table(converted, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                ("GRID", (0, 0), (-1, -1), 0.35, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ]
        )
    )
    return result


class Diagram(Flowable):
    def __init__(self) -> None:
        super().__init__()
        self.width = 170 * mm
        self.height = 48 * mm

    def draw(self) -> None:
        labels = ["Input", "Evidence", "AI draft", "Checks", "Review", "Export"]
        box_w = 22 * mm
        gap = 7.5 * mm
        y = 15 * mm
        for index, label in enumerate(labels):
            x = index * (box_w + gap)
            self.canv.setFillColor(PALE)
            self.canv.setStrokeColor(BLUE)
            self.canv.roundRect(x, y, box_w, 15 * mm, 2 * mm, fill=1, stroke=1)
            self.canv.setFillColor(NAVY)
            self.canv.setFont(FONT_BOLD, 6.7)
            self.canv.drawCentredString(x + box_w / 2, y + 6.2 * mm, label)
            if index < len(labels) - 1:
                self.canv.setStrokeColor(MUTED)
                self.canv.line(x + box_w, y + 7.5 * mm, x + box_w + gap - 1 * mm, y + 7.5 * mm)


def header_footer(canvas: Any, doc: Any, spec: dict[str, Any]) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(colors.HexColor("#D2DCE2"))
    canvas.line(18 * mm, height - 13 * mm, width - 18 * mm, height - 13 * mm)
    canvas.setFont(FONT, 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, height - 10 * mm, f"ELEC5623 | {product_name(spec)} | Group {spec['group']}")
    canvas.drawRightString(width - 18 * mm, height - 10 * mm, "Group Business Proposal")
    canvas.line(18 * mm, 13 * mm, width - 18 * mm, 13 * mm)
    canvas.drawString(18 * mm, 9 * mm, "ELEC5623 Applied Generative AI in Engineering")
    canvas.drawRightString(width - 18 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def pdf_story(spec: dict[str, Any], sections: dict[str, list[str]]) -> list[Flowable]:
    name = product_name(spec)
    story: list[Flowable] = [
        Spacer(1, 25 * mm),
        p("ELEC5623", "cover_sub"),
        Spacer(1, 7 * mm),
        p(name, "cover"),
        p(spec["topic"].capitalize(), "cover_sub"),
        Spacer(1, 15 * mm),
        table(
            [
                ["Field", "Submission details"],
                ["Track", spec["track"]],
                ["Group", str(spec["group"])],
                ["Members", ", ".join(spec["team"])],
                ["Assessment", "ELEC5623 Group Business Proposal"],
            ],
            [35 * mm, 127 * mm],
            7,
        ),
        Spacer(1, 18 * mm),
        p("Submitted for assessment", "cover_sub"),
        PageBreak(),
    ]
    if spec["type"] == "off_topic":
        titles = ["Placement Context", "Communication and Planning", "Engineering Practice", "Professional Responsibility", "Learning Plan"]
    else:
        titles = [
            "Problem, Background and Motivation",
            "Users, Scope and Requirements",
            "Proposed Product and Technical Design",
            "Business Analysis and Evaluation",
            "Feasibility, Risks and Semester Plan",
        ]
    for index, criterion in enumerate(("c1", "c2", "c3", "c4", "c5"), 1):
        values = sections[criterion]
        if not values:
            continue
        parts = 3 if spec["type"] == "incomplete" else 2
        chunk_size = max(1, (len(values) + parts - 1) // parts)
        chunks = [
            values[start : start + chunk_size]
            for start in range(0, len(values), chunk_size)
        ]
        for chunk_index, chunk in enumerate(chunks):
            if not chunk:
                continue
            title = titles[index - 1]
            story.append(p(f"{index}. {title}" + (" (continued)" if chunk_index else ""), "h1"))
            for paragraph in chunk:
                story.append(p(paragraph))
            if criterion == "c2" and chunk_index == len(chunks) - 1 and spec["type"] != "off_topic":
                story.extend([p("Functional requirements", "h2"), table(requirements(spec), [12 * mm, 75 * mm, 18 * mm, 61 * mm], 5.7)])
            if criterion == "c3" and chunk_index == len(chunks) - 1 and spec["type"] != "off_topic":
                story.extend([p("Evidence-first workflow", "h2"), Diagram(), p("Figure 1. Drafts cannot bypass deterministic checks and human review.", "small")])
            if criterion == "c5" and chunk_index == len(chunks) - 1 and spec["type"] != "off_topic":
                story.extend([p("Risk register", "h2"), table(risk_rows(spec), [42 * mm, 20 * mm, 104 * mm], 6.0)])
            story.append(PageBreak())
    if spec["type"] == "rough_unreferenced":
        story.extend(
            [
                p("some notes not finished", "h1"),
                p(
                    "sources need adding later. some facts came from websites and class discussion but links were not saved. formatting and citation style still to fix."
                ),
            ]
        )
    else:
        story.append(p("References", "h1"))
        for index, reference in enumerate(spec["references"], 1):
            story.extend([p(f"[{index}] {reference}", "small"), Spacer(1, 2 * mm)])
        story.extend(
            [
                Spacer(1, 6 * mm),
                p("GenAI use acknowledgement", "h2"),
                p(
                    "The group used generative AI for language editing and early ideation. All claims, references, requirements and engineering decisions were reviewed by the group, which remains responsible for the submitted work."
                ),
            ]
        )
    return story


def write_case(spec: dict[str, Any]) -> tuple[Path, Path, int]:
    sections = build_sections(spec)
    text = markdown(spec, sections)
    SOURCES.mkdir(parents=True, exist_ok=True)
    PDFS.mkdir(parents=True, exist_ok=True)
    source = SOURCES / f"{spec['id']}.md"
    source.write_text(text, encoding="utf-8")
    output = PDFS / f"{spec['id']}_{product_name(spec).replace(' ', '_')}.pdf"
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=17 * mm,
        title=f"{product_name(spec)} - ELEC5623 Cohort {spec['id']}",
        author=f"ELEC5623 Group {spec['group']}",
    )
    doc.build(
        pdf_story(spec, sections),
        onFirstPage=lambda canvas, d: header_footer(canvas, d, spec),
        onLaterPages=lambda canvas, d: header_footer(canvas, d, spec),
    )
    return source, output, word_count(text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", default="c001,c002,c003,c004,c005,c006,c007,c008,c009,c010")
    args = parser.parse_args()
    wanted = args.only.split(",")
    specs = json.loads((HERE / "specs.json").read_text(encoding="utf-8"))
    by_id = {spec["id"]: spec for spec in specs}
    for submission_id in wanted:
        source, output, words = write_case(by_id[submission_id])
        print(f"{submission_id}: {words} words -> {source} -> {output}")


if __name__ == "__main__":
    main()
