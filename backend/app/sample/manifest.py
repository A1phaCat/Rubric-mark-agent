"""Sample library and batches loaded by ``python -m app.sample.seed``.

Everything here is input to the real services: rubrics (from ``rubrics/``) are created
through ``RubricUseCases``, submission files are stored and extracted like uploads, tutor
edits and confirmations go through ``ReviewUseCases`` and the finalised batch goes
through ``BatchUseCases.finalise``. Only the AI grading step is replayed from the
recorded results below instead of calling a provider, so the samples work offline
and look the same on every machine. Every evidence quote must occur verbatim in the
extracted text of its file; the seeder refuses to load a quote it cannot find.
"""

from __future__ import annotations

from typing import Any

# The single local account. Its display name is editable from the account menu (PUT /api/v1/me).
LOCAL_USER = {"id": "usr_jalvarez", "name": "Tutor", "email": ""}
OTHER_MARKER = {"id": "usr_mokafor", "name": "M. Okafor", "email": "m.okafor@sydney.edu.au"}
TERM = {"id": "term_2026s2", "label": "Semester 2, 2026"}

# Library rubrics live as files in ``app/sample/rubrics/`` (one file per rubric; see the
# README there). The batches below refer to them by id: ``shortanswer.json`` → ``rub_shortanswer``.


def ai(
    score: float,
    confidence: str,
    rationale: str,
    evidence: list[tuple[str, str]],
    sufficiency: str = "sufficient",
) -> dict[str, Any]:
    """One recorded AI result: evidence is a list of (exact quote, role)."""

    return {
        "score": score,
        "confidence": confidence,
        "rationale": rationale,
        "evidence": evidence,
        "sufficiency": sufficiency,
    }


# --------------------------------------------------------------------------------------
# Batch 1 — ASGN2 Critical Essay: in review (AI done, one confirmed, one needs manual).
# --------------------------------------------------------------------------------------

ASGN2_SUBMISSIONS: list[dict[str, Any]] = [
    {
        "file": "SID-40218_ASGN2.pdf",
        "sid": "SID-40218",
        "outcome": "confirmed",
        "marker": "usr_jalvarez",
        "ai": [
            ai(27, "high", "States a conditional thesis with three explicit conditions in the introduction and returns to exactly those conditions in the conclusion; each section advances one step of the argument.", [
                ("This essay argues that decentralised governance improves organisational outcomes only when three conditions hold", "primary"),
                ("Decentralised governance improves organisational outcomes when decision rights follow information, shared rules bound conflict, and higher-level coordination is reserved for spillovers.", "supporting"),
            ]),
            ai(21.5, "high", "Uses Hayek, Oates and two Ostrom works to support specific steps of the argument rather than listing them; each source is tied to a claim.", [
                ("Oates (1972) showed that decentralised provision of public goods is efficient only when their benefits are contained within the deciding jurisdiction", "primary"),
                ("Hayek (1945) argued that the knowledge needed for good economic decisions is dispersed and often tacit, so it cannot be fully transmitted to a central planner.", "supporting"),
            ]),
            ai(26, "high", "Engages the strongest objection directly and explains how it reframes the comparison; distinguishes decentralisation from polycentric design.", [
                ("This objection is partly right, and it changes the comparison rather than settling it.", "primary"),
                ("The evidence therefore does not support decentralisation as such.", "supporting"),
            ]),
            ai(13, "high", "Concise, well-signposted prose with no mechanical errors found.", [
                ("The argument proceeds in three steps.", "primary"),
            ]),
        ],
        "review": [
            (27, "A precise, conditional thesis that the essay carries all the way through. The roadmap in the introduction makes the structure easy to follow."),
            (22.5, "Excellent integration of sources — each one does work in the argument. I've raised this slightly because the Oates spillover point is used particularly well."),
            (26, "The objection in Section 4 is handled thoughtfully. To go further, give a concrete example of a coordination cost becoming visible in a decentralised system."),
            (13, "Clear, economical writing throughout."),
        ],
        "feedback": {
            "summary": "A tightly argued essay that defends a conditional version of the claim and supports each step with well-chosen sources.",
            "strengths": ["Conditional thesis stated early and carried through to the conclusion", "Sources are integrated into the argument rather than listed"],
            "improvements": ["Illustrate the objection in Section 4 with a concrete case"],
            "next_steps": ["Practise pairing each abstract claim with one specific organisational example"],
        },
    },
    {
        "file": "SID-40219_ASGN2.pdf",
        "sid": "SID-40219",
        "outcome": "ai_done",
        "ai": [
            ai(26, "high", "Thesis is stated in the introduction and restated in the conclusion; the section roadmap matches the essay's structure.", [
                ("This essay argues that decentralised governance models, while promising in theory, consistently underperform in practice due to coordination costs that scale non-linearly with participant count.", "primary"),
                ("In conclusion, the evidence reviewed here supports the claim that decentralised governance tends to underperform as it scales, because the cost of coordinating many participants grows faster than the benefit of including them.", "supporting"),
            ]),
            ai(15, "low", "One study is integrated with its limitation noted, but a central empirical claim about open-source projects is made without a citation. Confidence is low because the reference list is short and the AI could not tell whether the uncited claim is common knowledge in the unit.", [
                ("A 2019 study (Kessler & Boone) found similar coordination overhead in cooperative networks, though the sample was limited to twelve organisations.", "primary"),
                ("Studies of large open-source projects show that decision latency grows sharply as contributor numbers rise.", "supporting"),
            ], sufficiency="partial"),
            ai(27, "high", "Weighs an alternative explanation — incentive design rather than decentralisation itself — and draws out its consequence for the main claim.", [
                ("Yet this reading understates a second possibility: coordination costs may not be intrinsic to decentralisation itself, but to the specific incentive structures layered on top of it.", "primary"),
                ("If this is right, the underperformance documented in Section 3 says more about how decentralised systems are designed than about decentralisation as such", "supporting"),
            ]),
            ai(12, "medium", "Generally clear, but several sentences are long and heavily qualified, which slows the reader.", [
                ("which, it should be noted, is not to say that the model does not have merit in certain more smaller-scale contexts where", "primary"),
                ("It is, perhaps, worth considering that the costs that are borne by hierarchical organisations, which are themselves not insignificant, may in some respects be comparable, although not necessarily in every respect, to those that have been described above.", "supporting"),
            ]),
        ],
    },
    {
        "file": "SID-40222_ASGN2.pdf",
        "sid": "SID-40222",
        "outcome": "ai_done",
        "ai": [
            ai(18, "medium", "The introduction announces a discussion rather than a position, and the essay is organised as lists of advantages and disadvantages; the conclusion gives a hedged opinion.", [
                ("In this essay I will discuss whether decentralisation improves organisational outcomes.", "primary"),
                ("Overall I think decentralisation is a good idea if it is used in the right way.", "supporting"),
            ]),
            ai(11, "low", "Only one non-academic source; key claims are attributed to unnamed experts. Confidence is low because the essay contains so little evidence that the AI may be missing context from the assignment brief.", [
                ("Many experts believe that this is the biggest problem with decentralised organisations.", "primary"),
                ("It has become one of the most visited websites, which shows that decentralisation can be very successful.", "supporting"),
            ], sufficiency="insufficient"),
            ai(16, "low", "Advantages and disadvantages are listed but not weighed against each other, and the Wikipedia example is not analysed.", [
                ("There are many advantages of decentralised governance.", "primary"),
                ("In conclusion, decentralised governance has both advantages and disadvantages.", "supporting"),
            ], sufficiency="partial"),
            ai(11.5, "medium", "Simple, clear sentences with few errors; meaning is always easy to follow.", [
                ("When many people are involved it can be hard to agree, and some decisions can take a long time.", "primary"),
            ]),
        ],
    },
    {
        "file": "SID-40225_ASGN2.pdf",
        "sid": "SID-40225",
        "outcome": "in_review",
        "ai": [
            ai(23, "medium", "Takes a clear position in the introduction and organises the essay around two cases that both feed the discussion; the conclusion follows from the cases.", [
                ("and argues that decentralisation improves outcomes in small, stable groups but struggles as organisations grow.", "primary"),
                ("Both cases point to the same pattern.", "supporting"),
            ]),
            ai(19, "medium", "Ostrom is summarised accurately and Freeman is used to support a specific point, but the open-source section makes claims without sources.", [
                ("She found that many of these communities sustained their resources for generations because users designed their own rules, monitored one another and applied graduated sanctions.", "primary"),
                ("Freeman (1972) also warned that groups without formal structure often develop hidden leaders who are not accountable.", "supporting"),
            ]),
            ai(21, "medium", "Moves beyond description by showing that successful open-source projects are not purely decentralised, and acknowledges a limitation, but does not weigh an alternative explanation.", [
                ("This suggests that successful open-source projects are not purely decentralised.", "primary"),
                ("One limitation of this analysis is that it compares only two types of organisation, so it may not apply to companies or governments.", "supporting"),
            ], sufficiency="partial"),
            ai(12, "high", "Clear and direct prose with no significant errors.", [
                ("Decentralised governance can improve organisational outcomes, but mostly in small groups with shared norms.", "primary"),
            ]),
        ],
    },
    {
        "file": "SID-40231_ASGN2.pdf",
        "sid": "SID-40231",
        "outcome": "needs_manual",
    },
]


# --------------------------------------------------------------------------------------
# Batch 2 — ASGN1 Literature Review: every submission confirmed (completed, editable).
# --------------------------------------------------------------------------------------

ASGN1_SUBMISSIONS: list[dict[str, Any]] = [
    {
        "file": "SID-31301_ASGN1.docx",
        "sid": "SID-31301",
        "outcome": "confirmed",
        "marker": "usr_jalvarez",
        "ai": [
            ai(13.5, "high", "Databases, search terms, date range and an inclusion rule are all stated.", [
                ("and were included only if they reported measured productivity or wellbeing outcomes.", "primary"),
            ]),
            ai(27, "high", "Groups the studies into productivity and wellbeing themes and draws a synthesis across them rather than summarising each in turn.", [
                ("Read together, these studies suggest that remote work raises the productivity of independent tasks while weakening the informal ties that support complex, collaborative work.", "primary"),
                ("Evidence on collaborative work is less positive.", "supporting"),
            ]),
            ai(22, "high", "Evaluates both bodies of work for generalisability and identification, naming the selection problem in the wellbeing studies.", [
                ("The experimental studies offer clean identification but cover narrow occupations, so their results may not generalise to professional or creative roles.", "primary"),
                ("which cannot separate the effect of remote work from the fact that more autonomous workers are more likely to be allowed to work remotely.", "supporting"),
            ]),
            ai(13.5, "high", "The gap is specific and follows from the trade-off the review identified.", [
                ("There is little longitudinal evidence on how specific hybrid schedules, such as two versus three office days, affect both collaboration and wellbeing for the same employees over time.", "primary"),
            ]),
            ai(13, "high", "Complete, consistent APA references with matching in-text citations.", [
                ("Bloom, N., Liang, J., Roberts, J., & Ying, Z. J. (2015). Does working from home work? Evidence from a Chinese experiment. Quarterly Journal of Economics, 130(1), 165-218.", "primary"),
            ]),
        ],
        "review": [
            (13.5, "Transparent and well-bounded search — exactly what this criterion asks for."),
            (27, "The synthesis across the two themes is the strongest part of the review."),
            (22, "Good attention to identification and selection. You could also note that most samples are from large firms."),
            (14, "The gap follows directly from your two themes — excellent. Raised slightly from the AI suggestion."),
            (13, "Accurate referencing throughout."),
        ],
        "feedback": {
            "summary": "A well-organised review that synthesises the evidence into two themes and identifies a precise, well-motivated gap.",
            "strengths": ["Clear search strategy", "Genuine synthesis across studies"],
            "improvements": ["Comment on the kinds of firms the studies sample"],
            "next_steps": ["Consider sketching the design of the study your gap calls for"],
        },
    },
    {
        "file": "SID-31302_ASGN1.docx",
        "sid": "SID-31302",
        "outcome": "confirmed",
        "marker": "usr_mokafor",
        "ai": [
            ai(8, "medium", "States the topic but gives no search method, databases or inclusion criteria.", [
                ("This literature review looks at what researchers have found about how working from home affects productivity and wellbeing.", "primary"),
            ], sufficiency="partial"),
            ai(15, "medium", "Each source is summarised in its own paragraph; there is little comparison between them.", [
                ("Bloom et al. (2015) did an experiment with a travel company in China.", "primary"),
                ("Golden et al. (2008) found that people who work from home can feel isolated from their colleagues and that this can make their performance worse.", "supporting"),
            ], sufficiency="partial"),
            ai(11, "low", "No evaluation of study design or limitations was found; the discussion restates the findings.", [
                ("Overall the studies show that working from home is mostly good for productivity and wellbeing, but some people feel isolated.", "primary"),
            ], sufficiency="insufficient"),
            ai(7, "low", "The gap is a general call for more research rather than a specific question.", [
                ("More research is needed on working from home.", "primary"),
            ], sufficiency="insufficient"),
            ai(9, "medium", "Several references are incomplete (missing titles, volumes or pages).", [
                ("Golden, T. D. et al (2008). Professional isolation. Journal of Applied Psychology.", "primary"),
            ]),
        ],
        "review": [
            (8, "Add a short paragraph on how you found and selected your sources."),
            (16, "There is a little more synthesis than the AI suggested — the discussion does connect isolation to the productivity findings. Aim to organise by theme rather than by source."),
            (12, "Start evaluating: what kind of workers did Bloom et al. study, and does that limit the conclusion?"),
            (7, "Turn \"more research is needed\" into a specific question your review shows is unanswered."),
            (9, "Complete every reference with title, volume and page numbers."),
        ],
        "feedback": {
            "summary": "Accurate summaries of relevant studies, but the review needs a search method, thematic synthesis and evaluation of the evidence.",
            "strengths": ["Relevant, credible sources"],
            "improvements": ["Organise by theme rather than by source", "Evaluate the design and limits of each study"],
            "next_steps": ["Rewrite the gap as a specific research question"],
        },
    },
    {
        "file": "SID-31303_ASGN1.docx",
        "sid": "SID-31303",
        "outcome": "confirmed",
        "marker": "usr_jalvarez",
        "ai": [
            ai(12, "high", "Search source, terms and limits are given, though inclusion criteria are brief.", [
                ("limited to English-language studies from 2007 onwards.", "primary"),
            ]),
            ai(25, "high", "Organises the literature into two themes and states what connects them.", [
                ("Two themes dominate the literature.", "primary"),
                ("These studies suggest that the costs of remote work fall on collaboration rather than on individual effort.", "supporting"),
            ]),
            ai(20, "medium", "Evaluates sample breadth and the forced-shift setting of the collaboration study; evaluation of the productivity studies is brief.", [
                ("Yang et al. study a single firm during a forced, firm-wide shift, which may exaggerate the effect compared with voluntary hybrid arrangements.", "primary"),
            ]),
            ai(12, "medium", "A clear measurement gap with a testable proposal.", [
                ("Few studies measure collaboration outcomes, such as the quality of joint work, rather than communication volume.", "primary"),
            ]),
            ai(13, "high", "Complete and consistent references.", [
                ("Choudhury, P., Foroughi, C., & Larson, B. (2021). Work-from-anywhere: The productivity effects of geographic flexibility. Strategic Management Journal, 42(4), 655-683.", "primary"),
            ]),
        ],
        "review": [
            (12, "Clear search description."),
            (25, "Nice framing of productivity versus connection."),
            (21, "Your point about the forced shift is sharp; I've raised this slightly."),
            (12, "A good, testable gap."),
            (13, "Referencing is accurate."),
        ],
        "feedback": {
            "summary": "A focused review with a clear thematic structure and a testable gap about how hybrid schedules affect collaboration.",
            "strengths": ["Thematic organisation", "Sharp evaluation of the collaboration evidence"],
            "improvements": ["Evaluate the productivity studies as carefully as the collaboration study"],
            "next_steps": ["Link your gap to a specific outcome measure"],
        },
    },
    {
        "file": "SID-31304_ASGN1.docx",
        "sid": "SID-31304",
        "outcome": "confirmed",
        "marker": "usr_mokafor",
        "ai": [
            ai(10.5, "medium", "Names a database but selects sources by citation count without stating criteria.", [
                ("I searched PsycINFO for studies of telecommuting and wellbeing and selected the most cited empirical studies and reviews.", "primary"),
            ], sufficiency="partial"),
            ai(23, "medium", "Connects findings across studies on autonomy and on the threshold effect of high-intensity remote work.", [
                ("Allen et al. (2015) reached a similar conclusion in a larger review, but stressed that the size of the benefits is modest.", "primary"),
            ]),
            ai(19, "high", "Identifies reliance on cross-sectional self-reports and the resulting selection problem.", [
                ("so the positive associations may partly reflect selection rather than a causal effect.", "primary"),
            ]),
            ai(12, "high", "A clear gap that follows from the evaluation.", [
                ("A longitudinal study following the same workers would help separate the effect of remote work from selection.", "primary"),
            ]),
            ai(12.5, "high", "Accurate references; minor inconsistency in in-text citation style.", [
                ("Gajendran, R. S., & Harrison, D. A. (2007). The good, the bad, and the unknown about telecommuting. Journal of Applied Psychology, 92(6), 1524-1541.", "primary"),
            ]),
        ],
        "review": [
            (10.5, "State your inclusion criteria rather than relying on citation counts."),
            (23, "Good synthesis around autonomy and intensity."),
            (19, "The selection argument is well made."),
            (12, "Clear gap that follows from your evaluation."),
            (12.5, "Accurate referencing."),
        ],
        "feedback": {
            "summary": "A clear review of the wellbeing evidence with a well-reasoned point about selection bias.",
            "strengths": ["Identifies the selection problem in the evidence"],
            "improvements": ["Document how sources were chosen"],
            "next_steps": ["Broaden the review to include productivity outcomes"],
        },
    },
]


# --------------------------------------------------------------------------------------
# Batch 3 — Quiz 3 Short Answer: every submission confirmed, then finalised (locked).
# --------------------------------------------------------------------------------------

QUIZ3_SUBMISSIONS: list[dict[str, Any]] = [
    {
        "file": "SID-50101_QUIZ3.pdf",
        "sid": "SID-50101",
        "outcome": "confirmed",
        "marker": "usr_jalvarez",
        "ai": [
            ai(27, "high", "Both terms defined precisely, each with a correct example.", [
                ("Opportunity cost is the value of the next best alternative given up when a choice is made.", "primary"),
                ("Australia has the comparative advantage in wool even if New Zealand is better at producing both.", "supporting"),
            ]),
            ai(33, "high", "Identifies the shortage and contrasts short- and long-run supply elasticity; does not mention non-price rationing.", [
                ("In the long run supply becomes more elastic as landlords convert apartments to other uses and fewer new apartments are built, so the shortage grows and quality may decline.", "primary"),
            ]),
            ai(24, "medium", "Weighs targeting, budget cost and supply effects and reaches a position.", [
                ("Overall vouchers are better because they help the people who need it without shrinking the housing stock.", "primary"),
            ]),
        ],
        "review": [
            (27, "Precise definitions and a well-chosen trade example."),
            (35, "Your short-run versus long-run elasticity explanation is excellent — raised to HD. Mention non-price rationing for full marks."),
            (24, "Good weighing of both policies."),
        ],
        "feedback": {
            "summary": "Accurate concepts and a strong application of the model, with a well-justified policy judgement.",
            "strengths": ["Clear use of elasticity to explain the long-run shortage"],
            "improvements": ["Mention how apartments are rationed when price cannot adjust"],
            "next_steps": ["Practise naming the welfare effects (surplus and deadweight loss) in policy answers"],
        },
    },
    {
        "file": "SID-50102_QUIZ3.pdf",
        "sid": "SID-50102",
        "outcome": "confirmed",
        "marker": "usr_mokafor",
        "ai": [
            ai(18, "medium", "Opportunity cost is defined loosely; comparative advantage is described as producing more efficiently, which is closer to absolute advantage.", [
                ("Comparative advantage is when a country can produce something more efficiently than another country, so it should specialise in that good and trade.", "primary"),
            ], sufficiency="partial"),
            ai(26, "medium", "Identifies the shortage and long-run widening, but describes shifts of the curves rather than movements along them.", [
                ("demand for apartments increases and supply decreases, which causes a shortage.", "primary"),
            ], sufficiency="partial"),
            ai(18, "medium", "Names one trade-off for each policy but reaches a position without justifying it.", [
                ("Vouchers give money to poor people to pay rent, which is fairer, but they cost the government money.", "primary"),
            ], sufficiency="partial"),
        ],
        "review": [
            (17, "Comparative advantage is about lower opportunity cost, not producing more efficiently — that is absolute advantage."),
            (26, "Right outcome. Be careful: a price ceiling causes movements along the curves, not shifts."),
            (18, "Explain why vouchers are better, not only that they are."),
        ],
        "feedback": {
            "summary": "The main outcomes are correct, but key concepts need to be stated more precisely and the evaluation needs reasons.",
            "strengths": ["Identifies the shortage and its long-run growth"],
            "improvements": ["Distinguish comparative from absolute advantage", "Describe movements along curves rather than shifts"],
            "next_steps": ["End evaluation answers with a judgement and the reason for it"],
        },
    },
    {
        "file": "SID-50103_QUIZ3.pdf",
        "sid": "SID-50103",
        "outcome": "confirmed",
        "marker": "usr_jalvarez",
        "ai": [
            ai(28.5, "high", "Precise definitions with insightful, correct examples.", [
                ("A lawyer who types faster than her assistant should still let the assistant type", "primary"),
            ]),
            ai(37, "high", "Complete application including elasticity and non-price rationing.", [
                ("Because price cannot ration apartments, non-price rationing appears, such as waiting lists, key money and discrimination.", "primary"),
            ]),
            ai(27, "high", "Weighs surplus transfer, deadweight loss and incidence of the voucher, and reaches a qualified position.", [
                ("part of the subsidy is captured by landlords through higher rents.", "primary"),
            ]),
        ],
        "review": [
            (28.5, "Excellent — the lawyer example shows you understand opportunity cost, not only the definition."),
            (37, "Complete and precise analysis."),
            (27, "Sophisticated evaluation, including incidence. Well done."),
        ],
        "feedback": {
            "summary": "An excellent set of answers that applies the model completely and evaluates the policies with precision.",
            "strengths": ["Insightful examples", "Considers who bears the cost of each policy"],
            "improvements": ["Quantify the deadweight loss on a diagram where possible"],
            "next_steps": ["Keep using incidence arguments in policy questions"],
        },
    },
    {
        "file": "SID-50104_QUIZ3.pdf",
        "sid": "SID-50104",
        "outcome": "confirmed",
        "marker": "usr_mokafor",
        "ai": [
            ai(24, "high", "Correct definitions; one example only.", [
                ("Comparative advantage is the ability to produce a good at a lower opportunity cost than others.", "primary"),
            ]),
            ai(30, "medium", "Correct shortage and long-run argument, briefly stated.", [
                ("The shortage is larger in the long run because supply is more elastic and fewer new apartments are built.", "primary"),
            ]),
            ai(23, "medium", "Weighs both policies and reaches a position based on targeting.", [
                ("Vouchers are targeted at low-income tenants and avoid shortages, but they are costly and could push up rents.", "primary"),
            ]),
        ],
        "review": [
            (24, "Correct; add an example of comparative advantage."),
            (30, "Correct and concise."),
            (23, "Good balance of costs and benefits."),
        ],
        "feedback": {
            "summary": "Correct and concise answers throughout; more development would lift them into the higher bands.",
            "strengths": ["Accurate core concepts"],
            "improvements": ["Give an example for every definition"],
            "next_steps": ["Explain the mechanism behind each effect, not only the effect"],
        },
    },
    {
        "file": "SID-50105_QUIZ3.pdf",
        "sid": "SID-50105",
        "outcome": "confirmed",
        "marker": "usr_jalvarez",
        "ai": [
            ai(9, "medium", "Opportunity cost is defined as a money cost and comparative advantage as being best at something; both are incorrect.", [
                ("Opportunity cost is the cost of something in money.", "primary"),
            ], sufficiency="insufficient"),
            ai(12, "high", "States that the market reaches equilibrium at the ceiling, which misses the shortage entirely.", [
                ("the market will reach a new equilibrium at the ceiling price.", "primary"),
            ], sufficiency="insufficient"),
            ai(10, "medium", "Names one benefit of each policy without weighing them.", [
                ("Rent ceilings are good because they make rent affordable.", "primary"),
            ], sufficiency="insufficient"),
        ],
        "review": [
            (9, "Review the definitions in Week 2 — opportunity cost is the next best alternative given up."),
            (14, "You correctly note that rents are capped; the key result you need is the shortage. Raised slightly for the correct starting point."),
            (10, "Compare the two policies directly and reach a judgement."),
        ],
        "feedback": {
            "summary": "The answers show a starting understanding, but the core concepts and the shortage result need revision.",
            "strengths": ["Recognises that a rent ceiling caps the price"],
            "improvements": ["Revise the definitions of opportunity cost and comparative advantage", "Show the shortage created by a binding ceiling"],
            "next_steps": ["Book a consultation before the final exam"],
        },
    },
]


BATCHES: list[dict[str, Any]] = [
    {
        "id": "bat_sample_asgn2",
        "name": "ASGN2 — Critical Essay",
        "unit": "ECON2001",
        "rubric_id": "rub_criticalessay",
        "state": "in_review",
        "created_days_ago": 12,
        "started_days_ago": 2,
        "due_in_days": 4,
        "submissions": ASGN2_SUBMISSIONS,
    },
    {
        "id": "bat_sample_asgn1",
        "name": "ASGN1 — Literature Review",
        "unit": "ECON2001",
        "rubric_id": "rub_literaturereview",
        "state": "completed",
        "created_days_ago": 19,
        "started_days_ago": 5,
        "due_in_days": -2,
        "submissions": ASGN1_SUBMISSIONS,
    },
    {
        "id": "bat_sample_quiz3",
        "name": "Quiz 3 — Short Answer",
        "unit": "ECON2001",
        "rubric_id": "rub_shortanswer",
        "state": "finalised",
        "created_days_ago": 26,
        "started_days_ago": 11,
        "due_in_days": -12,
        "submissions": QUIZ3_SUBMISSIONS,
    },
]
