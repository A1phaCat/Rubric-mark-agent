"""Generate the six-page SID-40219 demo essay used by the review fixture."""

from __future__ import annotations

from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "SID-40219_ASGN2.pdf"


PAGES = [
    (
        "1. Introduction",
        [
            "Over the past decade, decentralised governance has moved from the margins of political theory into the everyday operating models of cooperatives, open-source foundations and blockchain-based organisations. Its appeal is easy to understand: distributing authority promises resilience, legitimacy and a genuine voice for every participant.",
            "This essay argues that decentralised governance models, while promising in theory, consistently underperform in practice due to coordination costs that scale non-linearly with participant count. Section 2 sets out the theoretical case for decentralisation, Section 3 reviews the empirical evidence, and Section 4 considers an alternative explanation before the conclusion returns to the central claim.",
            "The distinction between participation and coordination is central. Participation describes who may contribute to a decision; coordination concerns the time, information and negotiation required to turn those contributions into a coherent choice. A system can broaden participation while simultaneously making coordinated action slower and less predictable. This tension is often obscured when decentralisation is discussed only as a question of legitimacy.",
            "To evaluate the claim, the essay compares evidence from three organisational settings: community governance of shared resources, large open-source projects, and blockchain-based organisations. These settings do not provide a perfect controlled comparison, but together they show how scale, incentives and decision rules interact. The analysis therefore treats decentralisation as a family of institutional arrangements rather than a single fixed model.",
            "The argument is deliberately qualified. Centralised hierarchies also incur substantial administrative costs, and small decentralised groups can coordinate effectively when members share norms and local knowledge. The relevant question is not whether decentralisation ever works, but whether its coordination mechanisms remain effective as participant numbers and organisational complexity grow.",
            "This framing also separates normative preference from empirical performance. A governance model may be attractive because it distributes voice, yet still struggle to produce timely collective action. Conversely, an efficient hierarchy may deliver decisions quickly while offering inadequate accountability. The assessment that follows therefore considers both the quality of participation and the organisation's capacity to decide and implement, rather than treating either democratic access or operational speed as sufficient on its own.",
        ],
    ),
    (
        "2. The theoretical case for decentralisation",
        [
            "Proponents of decentralisation draw heavily on Ostrom's work on common-pool resources, which showed that communities can govern shared assets without a central authority when rules are designed locally and monitored by the people who use them.",
            "Later advocates extended this argument to digital organisations, claiming that transparent protocols could replace managerial hierarchy altogether. On this view, coordination stops being a social problem and becomes a technical one that better tooling can solve.",
            "This position has genuine strengths. Local participants often possess knowledge that a distant manager lacks, and distributed decision-making can prevent a single point of institutional failure. Open records may also make authority easier to audit. When members can see proposals, votes and implementation decisions, they have a clearer basis for challenging unfair or ineffective outcomes.",
            "These claims deserve to be taken seriously. The evidence for this optimism, however, comes mostly from small and stable communities, which, it should be noted, is not to say that the model does not have merit in certain more smaller-scale contexts where trust is already established and membership changes slowly.",
            "Scaling changes the problem. A neighbourhood association can rely on repeated face-to-face interaction, shared context and informal sanctions. A digital organisation with thousands of intermittent participants cannot assume the same conditions. It must communicate proposals to people in different time zones, resolve conflicting interpretations, authenticate participation and maintain attention across a growing stream of decisions.",
            "Consequently, transparent rules are not a substitute for coordination. They may reduce ambiguity about how a decision is made, but they do not ensure that participants have read the same material, understand the trade-offs or are willing to accept the result. Technical infrastructure can record a vote; it cannot by itself create common purpose.",
            "Institutional trust remains important even when the process is encoded. Participants must trust that relevant information has not been withheld, that software behaves as described, and that those implementing a decision will act in good faith. Disputes about interpretation also require human judgement. The digital record can clarify what happened, but legitimacy still depends on whether members regard the process, its representatives and its outcomes as reasonable.",
        ],
    ),
    (
        "3. Evidence of coordination costs at scale",
        [
            "Studies of large open-source projects show that decision latency grows sharply as contributor numbers rise. In one widely cited analysis, the median time to resolve a governance proposal tripled once a project passed two hundred active contributors.",
            "Blockchain-based organisations display a similar pattern. Voter turnout on most proposals falls below ten per cent, and the small group that does vote tends to be the same few large holders each time.",
            "The common thread is that every additional participant adds not one new relationship but many, because each person must, in principle, be informed, consulted and persuaded.",
            "A 2019 study (Kessler & Boone) found similar coordination overhead in cooperative networks, though the sample was limited to twelve organisations. Even so, its findings point in the same direction as the open-source data.",
            "Three mechanisms explain this pattern. First, information costs rise because proposals require background material, discussion and revision. Second, preference aggregation becomes harder as the number of competing priorities grows. Third, responsibility becomes diffuse: participants can assume that someone else will study the proposal or carry out the resulting work.",
            "These mechanisms reinforce one another. When information is expensive to process, fewer members participate consistently. The remaining active minority then accumulates procedural knowledge and informal influence. Although formal access remains decentralised, practical authority concentrates among those with enough time, expertise or financial stake to remain continuously involved.",
            "The evidence does not prove that every large decentralised organisation must fail. It does show that participation rights alone are a weak measure of operational decentralisation. A credible assessment must examine who actually contributes, how long decisions take, whether implementation follows, and whether the same small group repeatedly determines outcomes.",
            "Caution is necessary because the available studies use different definitions and observation periods. Contributor counts do not always distinguish occasional participants from active decision-makers, while turnout measures may omit informal discussion that occurs before a formal vote. Even with these limitations, the convergence across settings matters: larger groups repeatedly face attention scarcity, slower deliberation and concentrated practical influence. The consistency of the pattern strengthens the coordination-cost explanation without making it universal.",
        ],
    ),
    (
        "4. Alternative explanation: incentives and design",
        [
            "Yet this reading understates a second possibility: coordination costs may not be intrinsic to decentralisation itself, but to the specific incentive structures layered on top of it.",
            "Where participants are rewarded for activity rather than outcomes, proposals multiply and attention fragments. Where voting power tracks token holdings, the few who hold the most have little reason to build consensus with everyone else.",
            "If this is right, the underperformance documented in Section 3 says more about how decentralised systems are designed than about decentralisation as such - and better-designed incentives could narrow the gap considerably.",
            "Several design choices support this alternative account. Delegation can allow members to assign their vote to a trusted specialist while retaining the ability to withdraw it. Smaller working groups can investigate proposals before the wider community decides. Clear thresholds can reserve full-participation votes for constitutional questions while routine operational choices remain delegated.",
            "However, each remedy reintroduces some form of hierarchy. Delegates gain agenda-setting power, working groups control which evidence reaches the wider membership, and thresholds determine whose concerns receive collective attention. These arrangements may be sensible, but they weaken the claim that transparent protocols can replace managerial structure altogether.",
            "The alternative explanation therefore modifies rather than overturns the thesis. Poor incentives can magnify coordination costs, and careful institutional design can reduce them. Nevertheless, design succeeds partly by limiting how many people must coordinate directly on every issue. The practical solution is usually selective decentralisation rather than universal participation in all decisions.",
            "Examples of selective decentralisation already appear in mature open-source communities. Maintainers decide routine technical questions, specialist groups review security changes, and the broader community retains influence over leadership or foundational policy. These systems are not fully flat, but their layered authority can remain transparent and revisable. Their relative success suggests that decentralisation works best as a principle for allocating and checking power, not as a requirement that every decision involve every participant equally.",
        ],
    ),
    (
        "5. Counterargument and synthesis",
        [
            "Some critics respond that hierarchies face coordination costs too, and that the comparison is therefore unfair. Large firms spend heavily on meetings, reporting lines and middle management simply to keep their parts aligned.",
            "It is, perhaps, worth considering that the costs that are borne by hierarchical organisations, which are themselves not insignificant, may in some respects be comparable, although not necessarily in every respect, to those that have been described above.",
            "Hierarchies, however, can choose to cap how many people are involved in a decision. Decentralised systems, by design, cannot.",
            "This contrast should not be overstated. Many decentralised organisations already use committees, maintainers and elected councils, while modern firms increasingly rely on autonomous teams. Real institutions occupy a spectrum. The useful comparison is therefore between specific decision architectures: who can initiate a proposal, who must be consulted, who decides, and who is accountable for implementation.",
            "On that comparison, decentralised systems offer stronger safeguards against unilateral control but often pay for those safeguards through slower decisions and uneven participation. Hierarchies can act quickly but risk suppressing local knowledge and concentrating error. Neither model eliminates coordination costs; each distributes those costs differently across members, managers and time.",
            "A balanced design would match the decision rule to the stakes. High-impact constitutional choices warrant broad participation and a slower process. Reversible operational decisions benefit from delegation and clear accountability. Publishing reasons and outcomes can preserve transparency even where authority is temporarily concentrated. Such arrangements retain the normative benefits of decentralisation without pretending that every member can deliberate on every issue.",
            "This synthesis also clarifies the meaning of underperformance. The claim is not merely that decentralised groups make fewer or slower decisions. Performance includes whether decisions are informed, implemented and accepted by those affected. A rapid vote followed by weak execution is not successful coordination, nor is a formally inclusive process dominated by a persistent minority. Evaluation must connect procedural participation to substantive organisational outcomes.",
        ],
    ),
    (
        "6. Conclusion",
        [
            "In conclusion, the evidence reviewed here supports the claim that decentralised governance tends to underperform as it scales, because the cost of coordinating many participants grows faster than the benefit of including them.",
            "This does not make decentralisation a failed idea. It suggests that future designs should treat coordination as the central constraint - limiting the size of decision groups, rewarding outcomes over activity, and accepting that some decisions are better delegated than shared.",
            "The strongest institutions will therefore avoid a simple choice between total hierarchy and total decentralisation. They will distribute authority where local knowledge and legitimacy matter, concentrate it temporarily where rapid execution is required, and make both forms of power visible and contestable. This hybrid approach acknowledges that inclusion, speed and accountability cannot always be maximised at the same time.",
            "Future research should compare decision latency, participation concentration and implementation rates across organisations using different governance rules. Longitudinal evidence would be especially valuable because a structure that works during a small founding phase may become ineffective after rapid growth. Better evidence would allow designers to identify when delegation becomes necessary and which safeguards prevent it from becoming permanent capture.",
            "For practitioners, the immediate implication is to measure coordination before expansion creates a crisis. Organisations can track proposal volume, response time, repeat participation, unresolved disputes and the proportion of approved decisions that are actually implemented. When these indicators deteriorate, leaders should adjust scope, delegation or incentives rather than simply adding another discussion platform. Treating coordination as a designed and measurable capacity makes decentralisation more credible, not less democratic.",
        ],
    ),
]


REFERENCES = [
    "Kessler, J., & Boone, R. (2019). Coordination overhead in cooperative networks. Journal of Organisational Design, 8(3), 41-58.",
    "Ostrom, E. (1990). Governing the Commons: The Evolution of Institutions for Collective Action. Cambridge University Press.",
    "Shirky, C. (2008). Here Comes Everybody: The Power of Organizing Without Organizations. Penguin.",
]


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D8D1C9"))
    canvas.line(22 * mm, 15 * mm, A4[0] - 22 * mm, 15 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#6E655E"))
    canvas.drawString(22 * mm, 10 * mm, "SID-40219 | ASGN2 Critical Essay")
    canvas.drawRightString(A4[0] - 22 * mm, 10 * mm, f"Page {doc.page} of 6")
    canvas.restoreState()


def build() -> Path:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    font_path = Path("/System/Library/Fonts/Supplemental/Times New Roman.ttf")
    bold_path = Path("/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf")
    if font_path.exists() and bold_path.exists():
        pdfmetrics.registerFont(TTFont("EssaySerif", font_path))
        pdfmetrics.registerFont(TTFont("EssaySerif-Bold", bold_path))
        body_font, bold_font = "EssaySerif", "EssaySerif-Bold"
    else:
        body_font, bold_font = "Times-Roman", "Times-Bold"

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "EssayTitle",
        parent=styles["Title"],
        fontName=bold_font,
        fontSize=20,
        leading=24,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#2F2F2F"),
        spaceAfter=9,
    )
    meta = ParagraphStyle(
        "Meta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#6E655E"),
        spaceAfter=14,
    )
    heading = ParagraphStyle(
        "Heading",
        parent=styles["Heading1"],
        fontName=bold_font,
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#8F3F24"),
        spaceBefore=2,
        spaceAfter=8,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName=body_font,
        fontSize=10.1,
        leading=13.5,
        textColor=colors.HexColor("#333333"),
        alignment=0,
        spaceAfter=7,
    )
    refs = ParagraphStyle(
        "References",
        parent=body,
        fontSize=9,
        leading=12,
        leftIndent=8 * mm,
        firstLineIndent=-8 * mm,
        spaceAfter=4,
    )

    story = []
    for page_index, (section, paragraphs) in enumerate(PAGES):
        if page_index == 0:
            story.extend(
                [
                    Paragraph(
                        "Decentralised Governance and the Hidden Cost of Coordination", title
                    ),
                    Paragraph("SID-40219 | ASGN2 Critical Essay | Demonstration submission", meta),
                ]
            )
        story.append(Paragraph(escape(section), heading))
        for paragraph in paragraphs:
            story.append(Paragraph(escape(paragraph), body))
        if page_index == len(PAGES) - 1:
            story.append(Spacer(1, 3))
            story.append(Paragraph("References", heading))
            for reference in REFERENCES:
                story.append(Paragraph(escape(reference), refs))
        if page_index < len(PAGES) - 1:
            story.append(PageBreak())

    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=22 * mm,
        leftMargin=22 * mm,
        topMargin=19 * mm,
        bottomMargin=21 * mm,
        title="Decentralised Governance and the Hidden Cost of Coordination",
        author="SID-40219",
        subject="ASGN2 Critical Essay demonstration submission",
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return OUTPUT


if __name__ == "__main__":
    print(build())
