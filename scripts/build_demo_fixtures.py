"""Generate the one deterministic fixture set used by mock UI, DB seed and contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "demo"
NOW = "2026-10-18T01:00:00Z"


def write(relative: str, value: Any) -> None:
    path = OUT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def criterion(
    rubric: str, pos: int, name: str, weight: int, descriptions: list[str]
) -> dict[str, Any]:
    labels = ["HD", "DI", "CR", "PS", "FL"]
    ratios = [1, 0.84, 0.74, 0.64, 0.49]
    return {
        "id": f"crt_{rubric}_{pos}",
        "name": name,
        "weight": weight,
        "description": "",
        "levels": [
            {
                "id": label.lower(),
                "label": label,
                "points": round(weight * ratios[index], 2),
                "min_score": 0,
                "max_score": weight,
                "description": descriptions[index],
            }
            for index, label in enumerate(labels)
        ],
    }


def rubric(
    rid: str,
    title: str,
    source: str,
    used: int,
    specs: list[tuple[str, int, list[str]]],
) -> dict[str, Any]:
    return {
        "id": rid,
        "version": 1,
        "title": title,
        "source": source,
        "criteria_count": len(specs),
        "total_weight": sum(item[1] for item in specs),
        "used_by_count": used,
        "updated_at": NOW,
        "criteria": [
            criterion(rid.removeprefix("rub_"), i + 1, *item)
            for i, item in enumerate(specs)
        ],
        "created_at": "2026-07-01T00:00:00Z",
    }


BANDS = {
    "argument": [
        "Clear, well-sequenced thesis throughout.",
        "Clear thesis with minor gaps.",
        "Generally coherent argument.",
        "Basic argument with gaps.",
        "No sustained argument.",
    ],
    "evidence": [
        "Current, credible sources are integrated.",
        "Credible sources are mostly integrated.",
        "Adequate sources, sometimes listed.",
        "Few weakly connected sources.",
        "Little or no evidence.",
    ],
    "critical": [
        "Insightfully weighs competing explanations.",
        "Strong analysis with alternatives.",
        "Some analysis beyond description.",
        "Mostly descriptive.",
        "No meaningful analysis.",
    ],
    "writing": [
        "Precise, concise and nearly error-free.",
        "Clear with minor errors.",
        "Generally readable.",
        "Frequent clarity problems.",
        "Unclear throughout.",
    ],
}


def build_rubrics() -> list[dict[str, Any]]:
    return [
        rubric(
            "rub_criticalessay",
            "Critical Essay — HD/D/C/P",
            "Uploaded PDF · parsed by AI",
            1,
            [
                ("Argument structure", 30, BANDS["argument"]),
                ("Evidence & sources", 25, BANDS["evidence"]),
                ("Critical analysis", 30, BANDS["critical"]),
                ("Writing clarity", 15, BANDS["writing"]),
            ],
        ),
        rubric(
            "rub_literaturereview",
            "Literature Review",
            "From Canvas · local snapshot",
            1,
            [
                ("Scope & question", 15, BANDS["argument"]),
                ("Synthesis", 30, BANDS["critical"]),
                ("Source quality", 25, BANDS["evidence"]),
                ("Structure", 15, BANDS["argument"]),
                ("Academic writing", 15, BANDS["writing"]),
            ],
        ),
        rubric(
            "rub_shortanswer",
            "Short Answer (quiz)",
            "Pasted text · parsed by AI",
            2,
            [
                ("Concept accuracy", 30, BANDS["argument"]),
                ("Application", 40, BANDS["critical"]),
                ("Clarity", 30, BANDS["writing"]),
            ],
        ),
        rubric(
            "rub_finalproject",
            "Final Project Report",
            "From Canvas · local snapshot",
            0,
            [
                ("Introduction", 5, BANDS["argument"]),
                (
                    "System Specifications and Architecture Design",
                    25,
                    BANDS["critical"],
                ),
                ("Quality of Work", 40, BANDS["evidence"]),
                (
                    "Quality of Group Processes and Individual Contributions",
                    20,
                    BANDS["critical"],
                ),
                ("Presentation", 5, BANDS["writing"]),
                ("Documentation Organization & Writing", 5, BANDS["writing"]),
            ],
        ),
        rubric(
            "rub_grouppresentation",
            "Group Presentation",
            "From Canvas · local snapshot",
            0,
            [
                ("Content", 35, BANDS["evidence"]),
                ("Structure", 20, BANDS["argument"]),
                ("Delivery", 25, BANDS["writing"]),
                ("Teamwork", 20, BANDS["critical"]),
            ],
        ),
        rubric(
            "rub_reflectivejournal",
            "Reflective Journal",
            "Uploaded DOCX · parsed by AI",
            0,
            [
                ("Depth of reflection", 50, BANDS["critical"]),
                ("Use of evidence", 30, BANDS["evidence"]),
                ("Writing", 20, BANDS["writing"]),
            ],
        ),
    ]


def batch(
    bid: str,
    name: str,
    unit: str,
    status: str,
    rubric_item: dict[str, Any],
    counts: dict[str, int],
    **times: Any,
) -> dict[str, Any]:
    return {
        "id": bid,
        "name": name,
        "unit": unit,
        "term": {"id": "term_2026s2", "label": "Semester 2, 2026"},
        "due_at": times.get("due_at"),
        "status": status,
        "display_status": "processing" if counts["processing"] else status,
        "rubric": {
            key: rubric_item[key]
            for key in (
                "id",
                "version",
                "title",
                "source",
                "criteria_count",
                "total_weight",
                "used_by_count",
                "updated_at",
            )
        },
        "counts": counts,
        "eta_seconds": times.get("eta_seconds"),
        "created_at": times.get("created_at", "2026-10-01T00:00:00Z"),
        "started_at": times.get("started_at"),
        "completed_at": times.get("completed_at"),
        "finalised_at": times.get("finalised_at"),
        "version": 1,
    }


def row(
    bid: str,
    index: int,
    sid: str,
    status: str,
    *,
    confidence: str | None,
    ai: int | None,
    final: int | None,
    flags: list[str],
    marker: str = "J. Alvarez",
    mock: bool = True,
) -> dict[str, Any]:
    return {
        "id": f"sub_{bid.removeprefix('bat_')}_{index:06d}",
        "batch_id": bid,
        "sid": sid,
        "filename": f"{sid}_{bid.removeprefix('bat_').upper()}.pdf",
        "status": status,
        "ai_total": ai,
        "final_total": final,
        "confidence": confidence,
        "marker": {
            "id": "usr_mokafor" if marker == "M. Okafor" else "usr_jalvarez",
            "name": marker,
        },
        "flags": flags,
        "error": None,
        "updated_at": NOW,
        "version": 1,
        "_mock": mock,
    }


def build_submissions() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    featured = [
        "SID-40219",
        "SID-40218",
        "SID-40220",
        "SID-40222",
        "SID-40225",
        "SID-40227",
    ]
    for i in range(825):
        sid = featured[i] if i < len(featured) else f"SID-{40300 + i:05d}"
        confidence = "low" if i < 44 else ("medium" if i < 284 else "high")
        rows.append(
            row(
                "bat_asgn2",
                i + 1,
                sid,
                "ai_done",
                confidence=confidence,
                ai=55 + i % 36,
                final=None,
                flags=[],
                marker="M. Okafor" if i in {2, 4} else "J. Alvarez",
                mock=i >= 6,
            )
        )
    for i in range(411):
        rows.append(
            row(
                "bat_asgn2",
                826 + i,
                f"SID-{42000 + i:05d}",
                "marking",
                confidence=None,
                ai=None,
                final=None,
                flags=[],
                mock=True,
            )
        )
    for i in range(11):
        rows.append(
            row(
                "bat_asgn2",
                1237 + i,
                f"SID-{43000 + i:05d}",
                "needs_ocr",
                confidence="none",
                ai=None,
                final=None,
                flags=["needs_manual", "scanned"],
                mock=True,
            )
        )
    for i in range(312):
        rows.append(
            row(
                "bat_asgn1",
                i + 1,
                f"SID-{31000 + i:05d}",
                "confirmed",
                confidence="high",
                ai=60 + i % 29,
                final=60 + i % 29,
                flags=[],
                mock=True,
            )
        )
    for i in range(28):
        rows.append(
            row(
                "bat_asgn1",
                313 + i,
                f"SID-{31312 + i:05d}",
                "ai_done",
                confidence="low" if i < 6 else "high",
                ai=58 + i % 25,
                final=None,
                flags=[],
                mock=i >= 6,
            )
        )
    for i in range(1198):
        final = 35 + i % 61
        ai = final + (-4 if i % 19 == 0 else 0)
        sid = "SID-50102" if i == 1 else f"SID-{50101 + i:05d}"
        rows.append(
            row(
                "bat_quiz3",
                i + 1,
                sid,
                "confirmed",
                confidence="high",
                ai=72 if i == 1 else ai,
                final=68 if i == 1 else final,
                flags=["adjusted", "grade_changed"] if i % 19 == 0 else [],
                marker="M. Okafor" if i % 2 else "J. Alvarez",
                mock=i >= 6,
            )
        )
    for i in range(1203):
        final = 40 + i % 56
        rows.append(
            row(
                "bat_quiz2",
                i + 1,
                f"SID-{60101 + i:05d}",
                "confirmed",
                confidence="high",
                ai=final,
                final=final,
                flags=[],
                mock=i >= 6,
            )
        )
    return rows


ESSAY_PARAGRAPHS = [
    (
        1,
        "¶1",
        "Over the past decade, decentralised governance has moved from the margins of political theory into the everyday operating models of cooperatives, open-source foundations and blockchain-based organisations. Its appeal is easy to understand: distributing authority promises resilience, legitimacy and a genuine voice for every participant.",
    ),
    (
        1,
        "¶2",
        "This essay argues that decentralised governance models, while promising in theory, consistently underperform in practice due to coordination costs that scale non-linearly with participant count. Section 2 sets out the theoretical case for decentralisation, Section 3 reviews the empirical evidence, and Section 4 considers an alternative explanation before the conclusion returns to the central claim.",
    ),
    (
        2,
        "¶1",
        "Proponents of decentralisation draw heavily on Ostrom's work on common-pool resources, which showed that communities can govern shared assets without a central authority when rules are designed locally and monitored by the people who use them.",
    ),
    (
        2,
        "¶2",
        "Later advocates extended this argument to digital organisations, claiming that transparent protocols could replace managerial hierarchy altogether. On this view, coordination stops being a social problem and becomes a technical one that better tooling can solve.",
    ),
    (
        2,
        "¶3",
        "These claims deserve to be taken seriously. The evidence for this optimism, however, comes mostly from small and stable communities, which, it should be noted, is not to say that the model does not have merit in certain more smaller-scale contexts where trust is already established and membership changes slowly.",
    ),
    (
        3,
        "¶1",
        "Studies of large open-source projects show that decision latency grows sharply as contributor numbers rise. In one widely cited analysis, the median time to resolve a governance proposal tripled once a project passed two hundred active contributors.",
    ),
    (
        3,
        "¶2",
        "Blockchain-based organisations display a similar pattern. Voter turnout on most proposals falls below ten per cent, and the small group that does vote tends to be the same few large holders each time.",
    ),
    (
        3,
        "¶3",
        "The common thread is that every additional participant adds not one new relationship but many, because each person must, in principle, be informed, consulted and persuaded.",
    ),
    (
        3,
        "¶4",
        "A 2019 study (Kessler & Boone) found similar coordination overhead in cooperative networks, though the sample was limited to twelve organisations. Even so, its findings point in the same direction as the open-source data.",
    ),
    (
        4,
        "¶1",
        "Yet this reading understates a second possibility: coordination costs may not be intrinsic to decentralisation itself, but to the specific incentive structures layered on top of it.",
    ),
    (
        4,
        "¶2",
        "Where participants are rewarded for activity rather than outcomes, proposals multiply and attention fragments. Where voting power tracks token holdings, the few who hold the most have little reason to build consensus with everyone else.",
    ),
    (
        4,
        "¶3",
        "If this is right, the underperformance documented in Section 3 says more about how decentralised systems are designed than about decentralisation as such — and better-designed incentives could narrow the gap considerably.",
    ),
    (
        5,
        "¶1",
        "Some critics respond that hierarchies face coordination costs too, and that the comparison is therefore unfair. Large firms spend heavily on meetings, reporting lines and middle management simply to keep their parts aligned.",
    ),
    (
        5,
        "¶2",
        "It is, perhaps, worth considering that the costs that are borne by hierarchical organisations, which are themselves not insignificant, may in some respects be comparable, although not necessarily in every respect, to those that have been described above.",
    ),
    (
        5,
        "¶3",
        "Hierarchies, however, can choose to cap how many people are involved in a decision. Decentralised systems, by design, cannot.",
    ),
    (
        6,
        "¶1",
        "In conclusion, the evidence reviewed here supports the claim that decentralised governance tends to underperform as it scales, because the cost of coordinating many participants grows faster than the benefit of including them.",
    ),
    (
        6,
        "¶2",
        "This does not make decentralisation a failed idea. It suggests that future designs should treat coordination as the central constraint — limiting the size of decision groups, rewarding outcomes over activity, and accepting that some decisions are better delegated than shared.",
    ),
]


def review_bundle(
    submission_id: str,
    sid: str,
    batch_id: str,
    batch_name: str,
    rubric_item: dict[str, Any],
    mock: bool,
) -> dict[str, Any]:
    text = "\n\n".join(item[2] for item in ESSAY_PARAGRAPHS)
    quotes = [
        (
            "e1",
            1,
            "¶2",
            ESSAY_PARAGRAPHS[1][2].split(" Section 2")[0],
            "crt_criticalessay_1",
            "primary",
        ),
        ("e2", 6, "¶1", ESSAY_PARAGRAPHS[15][2], "crt_criticalessay_1", "supporting"),
        (
            "e3",
            3,
            "¶4",
            ESSAY_PARAGRAPHS[8][2].split(" Even so")[0],
            "crt_criticalessay_2",
            "primary",
        ),
        (
            "e4",
            3,
            "¶1",
            ESSAY_PARAGRAPHS[5][2].split(" In one")[0],
            "crt_criticalessay_2",
            "supporting",
        ),
        ("e5", 4, "¶1", ESSAY_PARAGRAPHS[9][2], "crt_criticalessay_3", "primary"),
        (
            "e6",
            4,
            "¶3",
            ESSAY_PARAGRAPHS[11][2].split(" —")[0],
            "crt_criticalessay_3",
            "supporting",
        ),
        (
            "e7",
            2,
            "¶3",
            "which, it should be noted, is not to say that the model does not have merit in certain more smaller-scale contexts where",
            "crt_criticalessay_4",
            "primary",
        ),
        ("e8", 5, "¶2", ESSAY_PARAGRAPHS[13][2], "crt_criticalessay_4", "supporting"),
    ]
    evidence = []
    for eid, page, para, quote, cid, role in quotes:
        start = text.find(quote)
        evidence.append(
            {
                "id": eid,
                "criterion_id": cid,
                "document_version": 1,
                "page": page,
                "paragraph": para,
                "start_offset": start,
                "end_offset": start + len(quote),
                "quote": quote,
                "label": role,
            }
        )
    if rubric_item["id"] == "rub_criticalessay":
        scores = [26, 15, 27, 12]
        confidences = ["high", "low", "high", "medium"]
        reasons = [
            "Thesis is stated early and returned to in the conclusion.",
            "One direct source is integrated; an important claim lacks a citation.",
            "Weighs an alternative explanation and draws out its consequence.",
            "Generally clear, with two long and heavily qualified sentences.",
        ]
    else:
        for index, item in enumerate(evidence):
            item["criterion_id"] = rubric_item["criteria"][
                index % len(rubric_item["criteria"])
            ]["id"]
        scores = [round(item["weight"] * 0.75, 1) for item in rubric_item["criteria"]]
        confidences = ["high", "medium", "high", "medium", "high"][: len(scores)]
        reasons = ["Deterministic full demo result for this criterion."] * len(scores)
    return {
        "submission": {
            "id": submission_id,
            "batch_id": batch_id,
            "sid": sid,
            "filename": f"{sid}_{batch_id.removeprefix('bat_').upper()}.pdf",
            "status": "ai_done",
            "version": 1,
        },
        "batch": {"id": batch_id, "name": batch_name, "status": "in_review"},
        "document": {
            "id": f"doc_{submission_id}",
            "version": 1,
            "page_count": 6,
            "word_count": 2180,
            "content_url": f"/api/v1/submissions/{submission_id}/file",
            "mime_type": "application/pdf",
            "title": "Decentralised Governance and the Hidden Cost of Coordination",
            "paragraphs": [
                {"page": p, "label": para, "text": value}
                for p, para, value in ESSAY_PARAGRAPHS
            ],
        },
        "rubric": {
            "id": rubric_item["id"],
            "version": 1,
            "title": rubric_item["title"],
            "criteria": [
                {
                    "definition": definition,
                    "ai_score": scores[i],
                    "score": scores[i],
                    "confidence": confidences[i],
                    "status": "ai_suggested",
                    "rationale": reasons[i],
                    "comment": "",
                    "evidence_ids": [
                        e["id"]
                        for e in evidence
                        if e["criterion_id"] == definition["id"]
                    ],
                    "version": 1,
                }
                for i, definition in enumerate(rubric_item["criteria"])
            ],
        },
        "evidence": evidence,
        "can_edit": True,
        "claim": None,
        "demo_banner": "Demo sample content — not this student's real work"
        if mock
        else None,
        "_mock": mock,
    }


def main() -> None:
    reviews_dir = OUT / "reviews"
    if reviews_dir.exists():
        for stale in reviews_dir.glob("sub_*.json"):
            stale.unlink()
    rubrics = build_rubrics()
    batches = [
        batch(
            "bat_asgn2",
            "ASGN2 — Critical Essay",
            "ECON2001",
            "in_review",
            rubrics[0],
            {
                "total": 1247,
                "processed": 836,
                "ready": 825,
                "low_confidence": 44,
                "needs_manual": 11,
                "processing": 411,
                "confirmed": 0,
                "adjusted": 0,
                "failed": 0,
                "excluded": 0,
            },
            due_at="2026-10-24T12:00:00Z",
            started_at="2026-10-18T00:46:00Z",
            eta_seconds=1080,
        ),
        batch(
            "bat_asgn1",
            "ASGN1 — Literature Review",
            "ECON2001",
            "in_review",
            rubrics[1],
            {
                "total": 340,
                "processed": 340,
                "ready": 28,
                "low_confidence": 6,
                "needs_manual": 0,
                "processing": 0,
                "confirmed": 312,
                "adjusted": 9,
                "failed": 0,
                "excluded": 0,
            },
            due_at="2026-10-18T12:00:00Z",
            started_at="2026-10-15T00:00:00Z",
        ),
        batch(
            "bat_quiz3",
            "Quiz 3 — Short Answer",
            "ECON2001",
            "finalised",
            rubrics[2],
            {
                "total": 1198,
                "processed": 1198,
                "ready": 0,
                "low_confidence": 0,
                "needs_manual": 0,
                "processing": 0,
                "confirmed": 1198,
                "adjusted": 64,
                "failed": 0,
                "excluded": 0,
            },
            started_at="2026-10-09T00:00:00Z",
            completed_at="2026-10-11T04:00:00Z",
            finalised_at="2026-10-12T05:18:00Z",
        ),
        batch(
            "bat_quiz2",
            "Quiz 2 — Short Answer",
            "ECON2001",
            "completed",
            rubrics[2],
            {
                "total": 1203,
                "processed": 1203,
                "ready": 0,
                "low_confidence": 0,
                "needs_manual": 0,
                "processing": 0,
                "confirmed": 1203,
                "adjusted": 0,
                "failed": 0,
                "excluded": 0,
            },
            started_at="2026-09-20T00:00:00Z",
            completed_at="2026-09-22T02:00:00Z",
        ),
    ]
    submissions = build_submissions()
    write("rubrics.json", rubrics)
    write("batches.json", batches)
    write("submissions/index.json", submissions)
    write(
        "settings.json",
        {
            "user": {
                "id": "usr_jalvarez",
                "name": "J. Alvarez",
                "email": "j.alvarez@sydney.edu.au",
                "role": "tutor",
            },
            "markers": [
                {"id": "usr_jalvarez", "name": "J. Alvarez"},
                {"id": "usr_mokafor", "name": "M. Okafor"},
            ],
            "ai": {
                "provider": "university",
                "model": "gpt-4.1",
                "uses_university_gateway": True,
            },
            "canvas": {"enabled": False, "label": "Not available in local MVP"},
        },
    )
    write(
        "home.json",
        {
            "summary": {
                "ready_for_review": {
                    "count": 853,
                    "by_batch": [
                        {
                            "batch_id": "bat_asgn2",
                            "batch_name": "ASGN2 — Critical Essay",
                            "count": 825,
                        },
                        {
                            "batch_id": "bat_asgn1",
                            "batch_name": "ASGN1 — Literature Review",
                            "count": 28,
                        },
                    ],
                    "next_submission_id": "sub_asgn2_000001",
                },
                "low_confidence": {
                    "count": 50,
                    "by_batch": [
                        {
                            "batch_id": "bat_asgn2",
                            "batch_name": "ASGN2 — Critical Essay",
                            "count": 44,
                        },
                        {
                            "batch_id": "bat_asgn1",
                            "batch_name": "ASGN1 — Literature Review",
                            "count": 6,
                        },
                    ],
                },
                "needs_manual": {
                    "count": 11,
                    "by_batch": [
                        {
                            "batch_id": "bat_asgn2",
                            "batch_name": "ASGN2 — Critical Essay",
                            "count": 11,
                        }
                    ],
                },
                "confirmed_this_week": {
                    "count": 312,
                    "average_seconds": 144,
                    "week_started_at": "2026-10-12T13:00:00Z",
                },
            },
            "queue": [
                {
                    "submission_id": f"sub_asgn2_{i:06d}",
                    "sid": sid,
                    "batch_id": "bat_asgn2",
                    "batch_name": "ASGN2 — Critical Essay",
                    "reason": "low_confidence" if i in {1, 4} else "ready",
                    "criterion_id": None,
                    "criterion_name": None,
                    "confidence": "low" if i in {1, 4} else "high",
                    "ai_total": score,
                }
                for i, sid, score in [
                    (1, "SID-40219", 80),
                    (4, "SID-40222", 55),
                    (5, "SID-40225", 70),
                    (6, "SID-40227", 66),
                    (2, "SID-40218", 74),
                ]
            ],
        },
    )
    for bid, batch_name, rubric_item in (
        ("asgn2", "ASGN2 — Critical Essay", rubrics[0]),
        ("asgn1", "ASGN1 — Literature Review", rubrics[1]),
    ):
        subset = [
            item
            for item in submissions
            if item["batch_id"] == f"bat_{bid}" and not item["_mock"]
        ]
        for item in subset:
            write(
                f"reviews/{item['id']}.json",
                review_bundle(
                    item["id"],
                    item["sid"],
                    f"bat_{bid}",
                    batch_name,
                    rubric_item,
                    False,
                ),
            )
    write(
        "reviews/shared-sample.json",
        review_bundle("sub_demo", "DEMO", "bat_demo", "Demo batch", rubrics[0], True),
    )
    report = {
        "submission": {
            "id": "sub_quiz3_000002",
            "sid": "SID-50102",
            "filename": "SID-50102_Quiz3.pdf",
        },
        "batch": {
            "id": "bat_quiz3",
            "name": "Quiz 3 — Short Answer",
            "unit": "ECON2001",
        },
        "status": "confirmed",
        "locked": True,
        "audience": "internal",
        "final_total": 68,
        "band": "CR",
        "ai_total": 72,
        "adjustment": -4,
        "confirmed_at": "2026-10-12T05:18:00Z",
        "marker": {"id": "usr_jalvarez", "name": "J. Alvarez"},
        "summary": "A sound response with accurate concepts; the final application needs more explicit reasoning.",
        "strengths": ["Accurate core concepts"],
        "improvements": ["Explain the causal link in Q3"],
        "next_steps": ["Use one concrete example for each applied claim"],
        "criteria": [
            {
                "criterion_id": "crt_shortanswer_1",
                "name": "Concept accuracy",
                "score": 24,
                "max_score": 30,
                "comment": "Accurate and concise.",
                "ai_score": 24,
                "confidence": "high",
                "internal_rationale": "Evidence matches.",
                "evidence": [
                    {"page": 1, "quote": "The response defines the concept accurately."}
                ],
            },
            {
                "criterion_id": "crt_shortanswer_2",
                "name": "Application",
                "score": 29,
                "max_score": 40,
                "comment": "Relevant application.",
                "ai_score": 29,
                "confidence": "high",
                "internal_rationale": "Application is relevant.",
                "evidence": [
                    {
                        "page": 1,
                        "quote": "The example applies the concept to the scenario.",
                    }
                ],
            },
            {
                "criterion_id": "crt_shortanswer_3",
                "name": "Clarity",
                "score": 15,
                "max_score": 30,
                "comment": "Make the final reasoning explicit.",
                "ai_score": 19,
                "confidence": "medium",
                "internal_rationale": "Tutor reduced score by four.",
                "evidence": [
                    {
                        "page": 2,
                        "quote": "The final conclusion is asserted rather than explained.",
                    }
                ],
            },
        ],
    }
    write("reports/sub_quiz3_000002.json", report)
    write(
        "reports/shared-sample.json",
        {
            **report,
            "submission": {"id": "sub_demo", "sid": "DEMO", "filename": "demo.pdf"},
            "batch": {"id": "bat_demo", "name": "Demo batch", "unit": None},
            "locked": False,
        },
    )
    for batch_item in batches[2:]:
        bid = batch_item["id"]
        batch_rows = [item for item in submissions if item["batch_id"] == bid]
        write(
            f"reports/results-{bid}.json",
            {
                "batch": batch_item,
                "locked": batch_item["status"] == "finalised",
                "released_at": batch_item["finalised_at"],
                "released_to": "Canvas"
                if batch_item["status"] == "finalised"
                else None,
                "summary": {
                    "average_final": 71.4 if bid == "bat_quiz3" else 67.5,
                    "average_ai": 72.1 if bid == "bat_quiz3" else 67.5,
                    "adjusted_count": 64 if bid == "bat_quiz3" else 0,
                    "adjusted_percent": 5.3 if bid == "bat_quiz3" else 0,
                    "comments_count": len(batch_rows),
                    "marker_count": 2,
                },
                "distribution": [
                    {"band": "HD", "min_score": 85, "max_score": 100, "count": 142},
                    {"band": "DI", "min_score": 75, "max_score": 84.99, "count": 318},
                    {"band": "CR", "min_score": 65, "max_score": 74.99, "count": 371},
                    {"band": "PS", "min_score": 50, "max_score": 64.99, "count": 289},
                    {
                        "band": "FL",
                        "min_score": 0,
                        "max_score": 49.99,
                        "count": max(0, len(batch_rows) - 1120),
                    },
                ],
                "criteria": [],
                "submissions": {
                    "items": batch_rows[:6],
                    "page": 1,
                    "page_size": 50,
                    "total": len(batch_rows),
                },
            },
        )
    write(
        "llm/rubric_parse.json",
        {
            "id": "rub_parsed_demo",
            "version": 1,
            "title": "Parsed demo rubric",
            "source": "FakeLLM",
            "criteria": rubrics[0]["criteria"],
            "created_at": NOW,
            "updated_at": NOW,
        },
    )
    write(
        "llm/criterion_grade.json",
        {
            "criterion_id": "crt_criticalessay_1",
            "score": 26,
            "level": "HD",
            "rationale": "The thesis is explicit and sustained.",
            "confidence": "high",
            "evidence": [],
        },
    )
    write(
        "llm/report_text.json",
        {
            "summary": "A coherent argument with clear room to strengthen source integration.",
            "strengths": ["Clear thesis"],
            "improvements": ["Integrate more sources"],
            "next_steps": ["Cite empirical claims"],
        },
    )
    write(
        "FIXES.json",
        {
            "changes": [
                "ASGN2 reconciled to 825 ready + 411 processing + 11 needs_manual = 1247; low confidence is a 44-item subset and processed is 836.",
                "ASGN2 review queue uses ASGN2 IDs and counts; prototype 48-item modes moved to e2e fixtures.",
                "Quiz 3 is finalised and locked; Quiz 2 is completed and editable.",
                "Every route preserves batch/submission identity.",
                "Lightweight rows are explicitly _mock=true and use a visible Demo sample content banner.",
                "Canvas fixture data was removed; settings say enabled=false.",
            ]
        },
    )


if __name__ == "__main__":
    main()
