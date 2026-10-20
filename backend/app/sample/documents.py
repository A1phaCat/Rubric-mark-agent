"""Source text for the sample submissions.

These texts are the input to ``scripts/build_sample_files.py``, which renders them
into the PDF and DOCX files stored in ``app/sample/files``. The seeder never reads
this module: it ingests the rendered files through the normal extraction path, so
everything the UI shows is read back from the database.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------------------
# ASGN2 — Critical Essay
# Prompt: "Critically evaluate the claim that decentralised governance improves
# organisational outcomes." (1,500–2,000 words; shorter drafts accepted for the sample.)
# --------------------------------------------------------------------------------------

SID_40219_SECTIONS: list[tuple[str, list[str]]] = [
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


SID_40219_REFERENCES = [
    "Kessler, J., & Boone, R. (2019). Coordination overhead in cooperative networks. Journal of Organisational Design, 8(3), 41-58.",
    "Ostrom, E. (1990). Governing the Commons: The Evolution of Institutions for Collective Action. Cambridge University Press.",
    "Shirky, C. (2008). Here Comes Everybody: The Power of Organizing Without Organizations. Penguin.",
]

SID_40218_SECTIONS: list[tuple[str, list[str]]] = [
    (
        "1. Introduction",
        [
            "Decentralisation is usually defended as a way to put decisions closer to the people who hold the relevant knowledge. This essay argues that decentralised governance improves organisational outcomes only when three conditions hold: decision rights are matched to local information, the costs of disagreement are bounded by shared rules, and there is a mechanism for coordinating across units when their choices interact.",
            "The argument proceeds in three steps. Section 2 sets out the informational case for decentralisation. Section 3 examines evidence on when that case fails. Section 4 weighs the strongest objection, that centralised organisations simply hide the same costs, before the conclusion states the conditions under which the claim in the question holds.",
        ],
    ),
    (
        "2. The informational case",
        [
            "Hayek (1945) argued that the knowledge needed for good economic decisions is dispersed and often tacit, so it cannot be fully transmitted to a central planner. Ostrom (1990) extended a similar logic to common-pool resources, showing that fisheries and irrigation systems governed by their users frequently outperformed both state control and privatisation.",
            "The common thread is that local actors observe conditions that a central authority sees late or not at all. Where outcomes depend on that information, moving decisions to the local level should improve them, and Ostrom's design principles explain why: users who make the rules also monitor them, so enforcement is cheap and legitimate.",
        ],
    ),
    (
        "3. Where the case fails",
        [
            "The informational advantage weakens when local choices create spillovers. Oates (1972) showed that decentralised provision of public goods is efficient only when their benefits are contained within the deciding jurisdiction; when they spill over, each unit under-provides because it ignores the gains to others.",
            "Organisations face the same problem. A regional office that cuts its training budget saves money locally but weakens the firm's shared talent pool. Ostrom (2010) responded by describing polycentric systems, in which nested units retain autonomy but are linked by higher-level rules for exactly these cross-cutting issues.",
            "The evidence therefore does not support decentralisation as such. It supports polycentric arrangements in which autonomy is the default and coordination is reserved for interactions that local units cannot internalise.",
        ],
    ),
    (
        "4. Objection: centralisation hides the same costs",
        [
            "A strong objection is that critics of decentralisation compare a messy reality with an idealised hierarchy. Central managers also bargain, delay and misread local conditions; their coordination costs are simply less visible because they occur inside a single chain of command.",
            "This objection is partly right, and it changes the comparison rather than settling it. The relevant question is which arrangement makes coordination costs visible and governable. Decentralised systems expose these costs in public votes and negotiations, which is uncomfortable but allows them to be measured and redesigned.",
        ],
    ),
    (
        "5. Conclusion",
        [
            "Decentralised governance improves organisational outcomes when decision rights follow information, shared rules bound conflict, and higher-level coordination is reserved for spillovers. Without those conditions, the informational gains are consumed by under-provision and delay. The claim in the question is therefore conditionally true, and the conditions are institutional design choices rather than properties of decentralisation itself.",
        ],
    ),
]

SID_40218_REFERENCES = [
    "Hayek, F. A. (1945). The use of knowledge in society. American Economic Review, 35(4), 519-530.",
    "Oates, W. E. (1972). Fiscal Federalism. Harcourt Brace Jovanovich.",
    "Ostrom, E. (1990). Governing the Commons: The Evolution of Institutions for Collective Action. Cambridge University Press.",
    "Ostrom, E. (2010). Beyond markets and states: Polycentric governance of complex economic systems. American Economic Review, 100(3), 641-672.",
]

SID_40222_SECTIONS: list[tuple[str, list[str]]] = [
    (
        "1. Introduction",
        [
            "Decentralised governance means that power is shared between many people instead of one leader or a small group at the top. Many organisations are now trying this approach, including cooperatives and online communities. In this essay I will discuss whether decentralisation improves organisational outcomes.",
        ],
    ),
    (
        "2. Advantages",
        [
            "There are many advantages of decentralised governance. Firstly, more people are involved in making decisions, which makes them feel included and motivated. Secondly, decisions can be made faster because people do not need to wait for approval from the top. Thirdly, decentralised organisations are more democratic.",
            "For example, Wikipedia is written by volunteers all over the world and does not have a boss who tells everyone what to write. It has become one of the most visited websites, which shows that decentralisation can be very successful.",
        ],
    ),
    (
        "3. Disadvantages",
        [
            "However, there are also some disadvantages. When many people are involved it can be hard to agree, and some decisions can take a long time. Some people may not participate at all and leave the work to others.",
            "Also, there can be problems with responsibility because it is not clear who is in charge when something goes wrong. Many experts believe that this is the biggest problem with decentralised organisations.",
        ],
    ),
    (
        "4. Conclusion",
        [
            "In conclusion, decentralised governance has both advantages and disadvantages. It can improve outcomes by including more people, but it can also make decisions slower. Overall I think decentralisation is a good idea if it is used in the right way.",
        ],
    ),
]

SID_40222_REFERENCES = [
    "Wikipedia. (2024). Wikipedia: About. Retrieved from https://en.wikipedia.org/wiki/Wikipedia:About",
]

SID_40225_SECTIONS: list[tuple[str, list[str]]] = [
    (
        "1. Introduction",
        [
            "Supporters of decentralised governance claim that spreading authority across many participants leads to better and fairer decisions. This essay evaluates that claim using two cases, community management of shared resources and open-source software projects, and argues that decentralisation improves outcomes in small, stable groups but struggles as organisations grow.",
        ],
    ),
    (
        "2. Shared resources",
        [
            "Ostrom (1990) studied communities that manage forests, fisheries and irrigation systems without central control. She found that many of these communities sustained their resources for generations because users designed their own rules, monitored one another and applied graduated sanctions.",
            "These cases show that decentralised governance can work well. However, most of the communities Ostrom studied were small, had stable membership and had interacted for a long time, which made trust and monitoring easier.",
        ],
    ),
    (
        "3. Open-source projects",
        [
            "Open-source software is often presented as a modern example of decentralisation. Thousands of contributors can propose changes, and projects such as Linux have produced highly reliable software. At the same time, large projects usually rely on maintainers who have the final say over what is merged.",
            "This suggests that successful open-source projects are not purely decentralised. They combine open participation with a small group that coordinates and makes final decisions, which reduces the delays that would come from requiring everyone to agree.",
        ],
    ),
    (
        "4. Discussion",
        [
            "Both cases point to the same pattern. Decentralisation brings in local knowledge and gives participants a sense of ownership, but as the number of participants grows, agreeing on decisions becomes slower and more costly. Freeman (1972) also warned that groups without formal structure often develop hidden leaders who are not accountable.",
            "One limitation of this analysis is that it compares only two types of organisation, so it may not apply to companies or governments.",
        ],
    ),
    (
        "5. Conclusion",
        [
            "Decentralised governance can improve organisational outcomes, but mostly in small groups with shared norms. In larger organisations some central coordination is needed, which suggests that the best results come from a mix of decentralised participation and clear decision-making roles.",
        ],
    ),
]

SID_40225_REFERENCES = [
    "Freeman, J. (1972). The tyranny of structurelessness. Berkeley Journal of Sociology, 17, 151-164.",
    "Ostrom, E. (1990). Governing the Commons: The Evolution of Institutions for Collective Action. Cambridge University Press.",
]

# A scanned, image-only submission: the rendered PDF contains no text layer, so
# extraction finds nothing and the submission is routed to manual marking.
SID_40231_SCANNED_LINES = [
    "ASGN2 Critical Essay - SID-40231",
    "",
    "Does decentralised governance improve organisational outcomes?",
    "",
    "Decentralised governance moves decisions closer to the people affected",
    "by them. In this handwritten draft I argue that this improves outcomes",
    "when members share information and trust each other, but that large",
    "organisations still need a way to coordinate between units.",
    "",
    "(Scanned from a handwritten submission.)",
]

# --------------------------------------------------------------------------------------
# ASGN1 — Literature Review
# Prompt: "Review the literature on how remote and hybrid work affect productivity
# and employee wellbeing, and identify a gap for further research."
# --------------------------------------------------------------------------------------

SID_31301_PARAGRAPHS = [
    "Remote Work, Productivity and Wellbeing: A Review of the Evidence",
    "1. Scope and search strategy",
    "This review covers peer-reviewed studies and working papers published between 2007 and 2022 on remote and hybrid work. Sources were located through Google Scholar and EconLit using the terms \"telecommuting\", \"working from home\" and \"hybrid work\", and were included only if they reported measured productivity or wellbeing outcomes.",
    "2. Productivity",
    "The strongest causal evidence comes from field experiments. Bloom et al. (2015) randomly assigned call-centre employees at a Chinese travel agency to work from home and found a 13 per cent increase in performance, mostly from more calls per minute and fewer breaks. Choudhury et al. (2021) found that patent examiners allowed to work from anywhere increased output by 4.4 per cent. Both studies, however, examine routine and individually measurable tasks.",
    "Evidence on collaborative work is less positive. Yang et al. (2022) analysed communication data for more than 60,000 Microsoft employees and found that firm-wide remote work made collaboration networks more static and siloed. Read together, these studies suggest that remote work raises the productivity of independent tasks while weakening the informal ties that support complex, collaborative work.",
    "3. Wellbeing",
    "Gajendran and Harrison's (2007) meta-analysis of 46 studies found that telecommuting was associated with greater perceived autonomy, lower work-family conflict and higher job satisfaction. These benefits were not uniform: high-intensity telecommuting, more than two and a half days a week, harmed relationships with co-workers.",
    "Golden et al. (2008) identified professional isolation as the main mechanism through which remote work can reduce performance and increase turnover intentions, especially for employees with little face-to-face contact. Allen et al. (2015) concluded that the benefits of telecommuting are real but modest, and depend heavily on how much time is spent away from the office.",
    "4. Evaluation of the evidence",
    "The experimental studies offer clean identification but cover narrow occupations, so their results may not generalise to professional or creative roles. The wellbeing literature relies mainly on cross-sectional self-reports, which cannot separate the effect of remote work from the fact that more autonomous workers are more likely to be allowed to work remotely.",
    "5. Research gap",
    "Most studies predate the large-scale shift to hybrid work after 2020 and compare fully remote with fully office-based arrangements. There is little longitudinal evidence on how specific hybrid schedules, such as two versus three office days, affect both collaboration and wellbeing for the same employees over time. Such a study would directly address the trade-off identified in Sections 2 and 3.",
    "References",
    "Allen, T. D., Golden, T. D., & Shockley, K. M. (2015). How effective is telecommuting? Assessing the status of our scientific findings. Psychological Science in the Public Interest, 16(2), 40-68.",
    "Bloom, N., Liang, J., Roberts, J., & Ying, Z. J. (2015). Does working from home work? Evidence from a Chinese experiment. Quarterly Journal of Economics, 130(1), 165-218.",
    "Choudhury, P., Foroughi, C., & Larson, B. (2021). Work-from-anywhere: The productivity effects of geographic flexibility. Strategic Management Journal, 42(4), 655-683.",
    "Gajendran, R. S., & Harrison, D. A. (2007). The good, the bad, and the unknown about telecommuting. Journal of Applied Psychology, 92(6), 1524-1541.",
    "Golden, T. D., Veiga, J. F., & Dino, R. N. (2008). The impact of professional isolation on teleworker job performance and turnover intentions. Journal of Applied Psychology, 93(6), 1412-1421.",
    "Yang, L., Holtz, D., Jaffe, S., et al. (2022). The effects of remote work on collaboration among information workers. Nature Human Behaviour, 6, 43-54.",
]

SID_31302_PARAGRAPHS = [
    "Literature Review: Working From Home",
    "1. Introduction",
    "Working from home became very common during the COVID-19 pandemic. This literature review looks at what researchers have found about how working from home affects productivity and wellbeing.",
    "2. Summary of sources",
    "Bloom et al. (2015) did an experiment with a travel company in China. Workers who worked from home were 13 per cent more productive and were less likely to quit the company.",
    "Gajendran and Harrison (2007) did a meta-analysis and found that telecommuting has mostly positive effects on job satisfaction and on work-family conflict.",
    "Golden et al. (2008) found that people who work from home can feel isolated from their colleagues and that this can make their performance worse.",
    "Barrero et al. (2021) surveyed American workers and found that many people want to keep working from home after the pandemic, and that employers are planning to allow it.",
    "3. Discussion",
    "Overall the studies show that working from home is mostly good for productivity and wellbeing, but some people feel isolated. More research is needed on working from home.",
    "References",
    "Barrero, J. M., Bloom, N., & Davis, S. J. (2021). Why working from home will stick (NBER Working Paper No. 28731). National Bureau of Economic Research.",
    "Bloom, N. et al. (2015). Does working from home work? Quarterly Journal of Economics.",
    "Gajendran, R. S., & Harrison, D. A. (2007). The good, the bad, and the unknown about telecommuting. Journal of Applied Psychology, 92(6), 1524-1541.",
    "Golden, T. D. et al (2008). Professional isolation. Journal of Applied Psychology.",
]

SID_31303_PARAGRAPHS = [
    "Hybrid Work and the Collaboration Problem: A Literature Review",
    "1. Scope",
    "This review focuses on hybrid and remote arrangements for knowledge workers. It draws on studies identified through Scopus searches for \"remote work\" combined with \"collaboration\", \"productivity\" or \"isolation\", limited to English-language studies from 2007 onwards.",
    "2. Themes in the literature",
    "Two themes dominate the literature. The first is a productivity theme, in which remote work improves output on focused tasks. Bloom et al. (2015) and Choudhury et al. (2021) both report gains when workers control their environment and avoid commuting, although both studied tasks that are easy to measure individually.",
    "The second is a connection theme. Yang et al. (2022) show that remote work reduced cross-group communication and shifted employees towards asynchronous channels, while Golden et al. (2008) link professional isolation to weaker performance. These studies suggest that the costs of remote work fall on collaboration rather than on individual effort.",
    "3. Critical evaluation",
    "The productivity studies are persuasive within their settings but their samples are narrow. The collaboration evidence is broader but mostly observational; Yang et al. study a single firm during a forced, firm-wide shift, which may exaggerate the effect compared with voluntary hybrid arrangements.",
    "4. Gap",
    "Few studies measure collaboration outcomes, such as the quality of joint work, rather than communication volume. Future research should test whether coordinated office days for whole teams restore the cross-group ties that fully remote work weakens.",
    "References",
    "Bloom, N., Liang, J., Roberts, J., & Ying, Z. J. (2015). Does working from home work? Evidence from a Chinese experiment. Quarterly Journal of Economics, 130(1), 165-218.",
    "Choudhury, P., Foroughi, C., & Larson, B. (2021). Work-from-anywhere: The productivity effects of geographic flexibility. Strategic Management Journal, 42(4), 655-683.",
    "Golden, T. D., Veiga, J. F., & Dino, R. N. (2008). The impact of professional isolation on teleworker job performance and turnover intentions. Journal of Applied Psychology, 93(6), 1412-1421.",
    "Yang, L., Holtz, D., Jaffe, S., et al. (2022). The effects of remote work on collaboration among information workers. Nature Human Behaviour, 6, 43-54.",
]

SID_31304_PARAGRAPHS = [
    "Remote Work and Employee Wellbeing",
    "1. Introduction and approach",
    "This review examines whether remote work improves employee wellbeing. I searched PsycINFO for studies of telecommuting and wellbeing and selected the most cited empirical studies and reviews.",
    "2. Benefits for wellbeing",
    "Gajendran and Harrison (2007) found that telecommuting increased perceived autonomy, and that autonomy explained much of its positive effect on job satisfaction and work-family conflict. Allen et al. (2015) reached a similar conclusion in a larger review, but stressed that the size of the benefits is modest.",
    "3. Risks for wellbeing",
    "Golden et al. (2008) showed that professional isolation increases turnover intentions. Gajendran and Harrison (2007) also found that relationships with co-workers suffered when employees telecommuted for most of the week, which suggests a threshold beyond which remote work becomes harmful.",
    "4. Evaluation",
    "Most of these studies rely on self-reported wellbeing measured at one point in time. Employees who already enjoy autonomy may be more likely to be offered remote work, so the positive associations may partly reflect selection rather than a causal effect.",
    "5. Gap",
    "The research does not tell us how wellbeing changes when an employee moves from office-based to hybrid work. A longitudinal study following the same workers would help separate the effect of remote work from selection.",
    "References",
    "Allen, T. D., Golden, T. D., & Shockley, K. M. (2015). How effective is telecommuting? Assessing the status of our scientific findings. Psychological Science in the Public Interest, 16(2), 40-68.",
    "Gajendran, R. S., & Harrison, D. A. (2007). The good, the bad, and the unknown about telecommuting. Journal of Applied Psychology, 92(6), 1524-1541.",
    "Golden, T. D., Veiga, J. F., & Dino, R. N. (2008). The impact of professional isolation on teleworker job performance and turnover intentions. Journal of Applied Psychology, 93(6), 1412-1421.",
]

# --------------------------------------------------------------------------------------
# Quiz 3 — Short Answer (ECON2001)
# Q1 Define opportunity cost and comparative advantage, with an example of each.
# Q2 Use a supply and demand model to analyse a binding rent ceiling in a city rental
#    market, in the short run and the long run.
# Q3 Evaluate the trade-offs between a rent ceiling and targeted housing vouchers.
# --------------------------------------------------------------------------------------

QUIZ3_ANSWERS: dict[str, list[tuple[str, str]]] = {
    "SID-50101": [
        (
            "Q1",
            "Opportunity cost is the value of the next best alternative given up when a choice is made. If I spend Saturday working a shift that pays $150 instead of studying, the opportunity cost of studying is the $150 I would have earned. Comparative advantage means producing a good at a lower opportunity cost than someone else. If Australia gives up less wine than New Zealand to produce one tonne of wool, Australia has the comparative advantage in wool even if New Zealand is better at producing both.",
        ),
        (
            "Q2",
            "A rent ceiling set below the equilibrium rent is binding. At the ceiling, quantity demanded rises above quantity supplied, so there is a shortage of rental housing. In the short run supply is fairly inelastic because the number of apartments is fixed, so the shortage is small. In the long run supply becomes more elastic as landlords convert apartments to other uses and fewer new apartments are built, so the shortage grows and quality may decline.",
        ),
        (
            "Q3",
            "A rent ceiling helps current tenants at no budget cost, but it causes shortages, queues and lower housing quality, and it helps tenants regardless of income. Vouchers target low-income households and do not reduce supply, but they cost the government money and may raise rents if supply is inelastic. Overall vouchers are better because they help the people who need it without shrinking the housing stock.",
        ),
    ],
    "SID-50102": [
        (
            "Q1",
            "Opportunity cost is what you give up when you choose something, for example going to university instead of working full time. Comparative advantage is when a country can produce something more efficiently than another country, so it should specialise in that good and trade.",
        ),
        (
            "Q2",
            "If the government sets a maximum rent below the market rent, demand for apartments increases and supply decreases, which causes a shortage. Some people who want to rent cannot find an apartment. In the long run the shortage gets bigger because landlords build fewer apartments.",
        ),
        (
            "Q3",
            "Rent ceilings make housing cheaper for tenants, but they cause shortages. Vouchers give money to poor people to pay rent, which is fairer, but they cost the government money. I think vouchers are better.",
        ),
    ],
    "SID-50103": [
        (
            "Q1",
            "Opportunity cost is the value of the best alternative forgone. For a firm that uses its own warehouse, the opportunity cost includes the rent it could have earned by leasing the warehouse to someone else. Comparative advantage exists when one producer has a lower opportunity cost of producing a good than another. A lawyer who types faster than her assistant should still let the assistant type, because the lawyer's opportunity cost of typing, in lost legal fees, is much higher.",
        ),
        (
            "Q2",
            "With a binding ceiling, the legal rent is held below equilibrium, so quantity demanded exceeds quantity supplied. In the short run the supply curve is steep, so quantity supplied falls only slightly and the shortage is mainly caused by higher quantity demanded. In the long run supply is flatter, so landlords withdraw units and reduce maintenance, and the shortage widens. Because price cannot ration apartments, non-price rationing appears, such as waiting lists, key money and discrimination.",
        ),
        (
            "Q3",
            "The ceiling transfers surplus from landlords to the tenants who obtain apartments, but creates deadweight loss and misallocation, because apartments do not go to those who value them most. Vouchers raise demand rather than capping price, so they avoid shortages and can be targeted by income, but they require taxation and, if supply is inelastic in the short run, part of the subsidy is captured by landlords through higher rents. On balance vouchers are preferable, provided supply can respond, for example through planning reforms.",
        ),
    ],
    "SID-50104": [
        (
            "Q1",
            "Opportunity cost is the next best alternative that is given up. For example, if a farmer uses land to grow wheat, the opportunity cost is the barley that could have been grown. Comparative advantage is the ability to produce a good at a lower opportunity cost than others.",
        ),
        (
            "Q2",
            "A binding rent ceiling creates excess demand, because at the lower rent more people want apartments and landlords supply fewer. The shortage is larger in the long run because supply is more elastic and fewer new apartments are built.",
        ),
        (
            "Q3",
            "The rent ceiling is cheap for the government but leads to shortages and poor maintenance. Vouchers are targeted at low-income tenants and avoid shortages, but they are costly and could push up rents. Vouchers are generally the better policy because they target need.",
        ),
    ],
    "SID-50105": [
        (
            "Q1",
            "Opportunity cost is the cost of something in money. Comparative advantage is being the best at producing something.",
        ),
        (
            "Q2",
            "A rent ceiling means rents cannot go above a certain level. This makes renting cheaper so more people can afford housing, and the market will reach a new equilibrium at the ceiling price.",
        ),
        (
            "Q3",
            "Rent ceilings are good because they make rent affordable. Vouchers are also good but they cost money.",
        ),
    ],
}

QUIZ3_QUESTIONS = {
    "Q1": "Define opportunity cost and comparative advantage, giving an example of each.",
    "Q2": "Use a supply and demand model to analyse a binding rent ceiling in a city rental market, in the short run and the long run.",
    "Q3": "Evaluate the trade-offs between a rent ceiling and targeted housing vouchers.",
}


def essay_documents() -> dict[str, dict[str, Any]]:
    """Return every sample submission keyed by its file name."""

    documents: dict[str, dict[str, Any]] = {
        "SID-40219_ASGN2.pdf": {
            "kind": "essay_pdf",
            "title": "Decentralised Governance and the Hidden Cost of Coordination",
            "meta": "SID-40219 | ASGN2 Critical Essay",
            "sections": SID_40219_SECTIONS,
            "references": SID_40219_REFERENCES,
            "page_break_each_section": True,
        },
        "SID-40218_ASGN2.pdf": {
            "kind": "essay_pdf",
            "title": "Polycentric Governance: When Decentralisation Works",
            "meta": "SID-40218 | ASGN2 Critical Essay",
            "sections": SID_40218_SECTIONS,
            "references": SID_40218_REFERENCES,
        },
        "SID-40222_ASGN2.pdf": {
            "kind": "essay_pdf",
            "title": "Is Decentralised Governance Better?",
            "meta": "SID-40222 | ASGN2 Critical Essay",
            "sections": SID_40222_SECTIONS,
            "references": SID_40222_REFERENCES,
        },
        "SID-40225_ASGN2.pdf": {
            "kind": "essay_pdf",
            "title": "Decentralisation in Practice: Commons and Code",
            "meta": "SID-40225 | ASGN2 Critical Essay",
            "sections": SID_40225_SECTIONS,
            "references": SID_40225_REFERENCES,
        },
        "SID-40231_ASGN2.pdf": {"kind": "scanned_pdf", "lines": SID_40231_SCANNED_LINES},
        "SID-31301_ASGN1.docx": {"kind": "docx", "paragraphs": SID_31301_PARAGRAPHS},
        "SID-31302_ASGN1.docx": {"kind": "docx", "paragraphs": SID_31302_PARAGRAPHS},
        "SID-31303_ASGN1.docx": {"kind": "docx", "paragraphs": SID_31303_PARAGRAPHS},
        "SID-31304_ASGN1.docx": {"kind": "docx", "paragraphs": SID_31304_PARAGRAPHS},
    }
    for sid, answers in QUIZ3_ANSWERS.items():
        documents[f"{sid}_QUIZ3.pdf"] = {
            "kind": "quiz_pdf",
            "title": "Quiz 3 — Short Answer",
            "meta": f"{sid} | ECON2001 Quiz 3",
            "answers": [(label, QUIZ3_QUESTIONS[label], text) for label, text in answers],
        }
    return documents
