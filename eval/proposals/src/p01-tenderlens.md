---
title: "TenderLens: An Evidence-Linked Compliance Review Agent for Public Tender Responses"
subtitle: "ELEC5623 Group Business Proposal · Track A — AI Agent Product"
team: "Group 7 — Mia Chen, Liam O'Brien, Priya Raman, Tom Nguyen, Sara Haddad"
---

| Cover information | |
|---|---|
| Track | A — AI Agent Product |
| Group | 7 |
| Members | Mia Chen (530112874), Liam O'Brien (530098215), Priya Raman (530145002), Tom Nguyen (530067731), Sara Haddad (530120569) |
| Lab tutor and approval | Dr K. Morrison — approved in the Week 4 lab, 26 August 2026: "Scope limited to the mandatory-compliance stage; approved." |
| Product vision | Every compliance decision on a tender response is backed by a verified quotation the panel can see in one click. |

## 1. Executive Summary

Procurement officers in Australian public agencies evaluate tender responses against published conditions of participation, mandatory requirements and weighted evaluation criteria. A single request for tender (RFT) commonly produces between five and twenty supplier responses of 40 to 150 pages each, and every response must be checked for mandatory compliance before it can be scored. The Commonwealth Procurement Rules require that submissions which do not meet a condition for participation are excluded and that the reasons are documented (Department of Finance, n.d.). In practice this means an evaluation panel member reads each response searching for evidence of dozens of requirements, records where each requirement is addressed and justifies every "non-compliant" finding.

This proposal presents **TenderLens**, a Track A AI Agent Product that supports the compliance-checking stage of tender evaluation. TenderLens does not score tenders and does not recommend a supplier. It (1) extracts a structured requirement register from the RFT, (2) parses each supplier response while preserving page and section locations, (3) locates candidate evidence for each requirement, (4) asks a language model to classify each requirement as *addressed*, *partially addressed* or *not found* with verbatim quotations, (5) verifies every quotation against the source document and (6) presents an evidence matrix that the panel member confirms or overrides. Every finding links to the exact page and paragraph it relies on.

Generative AI is needed because requirements and responses rarely share vocabulary: an RFT may require "a documented business continuity arrangement", while a supplier describes "our tested disaster recovery runbook with a four-hour recovery objective". Keyword search fails on such paraphrases, and the judgement of whether a passage *satisfies* a requirement is semantic. The design keeps the model inside a narrow, verifiable role: it may only cite text that exists in the response, and code rejects any citation that does not match the source.

Evaluation compares TenderLens with two baselines — manual review and direct whole-document LLM review without verification — on 24 synthetic tender responses built from three public RFT templates, with requirement-level labels produced by two annotators. The primary measures are requirement-level classification accuracy (macro-F1), citation precision, evidence recall, the rate of unsupported findings and reviewer time per response (Section 8).

## 2. Introduction and Background

### 2.1 Application Context

Public procurement in Australia follows a staged process: approach to market, receipt of responses, compliance check, detailed evaluation against weighted criteria, value-for-money assessment and recommendation (Department of Finance, n.d.). The compliance check is a gate. A response that fails a mandatory condition is excluded from further evaluation, so an incorrect exclusion can be challenged by the supplier, and an incorrect inclusion wastes panel effort and exposes the agency to complaint. Agencies therefore expect every exclusion decision to be traceable to the response text.

Our partner context is a mid-sized state agency procurement team (described with their permission in anonymised form) that runs roughly 60 open tenders per year. Panels are typically three people, and each panel member performs an independent compliance check before a moderation meeting.

### 2.2 Evidence that the Problem Exists

In a structured interview with two procurement officers and one evaluation panel chair, all three described the compliance check as the most repetitive part of evaluation. The officers estimated 45–90 minutes per response for a medium tender with 30–40 mandatory requirements. In a small timing exercise, two of our team members checked three publicly available sample responses against a 32-requirement template; median time was 52 minutes per response, and the two members disagreed on 6 of 96 requirement decisions, mostly where the response addressed a requirement indirectly in an appendix.

These observations are consistent with the broader literature on long-document reading: relevant information is often distributed across sections, and readers — human or machine — miss content that appears in unexpected locations (Liu et al., 2024).

### 2.3 Current Practice, Existing Tools and Technical Motivation

Current practice relies on spreadsheets and PDF search. E-procurement platforms (for example the AusTender portal for publishing approaches to market) manage lodgement and deadlines but do not assess content. Commercial contract-analysis tools extract clauses from contracts but are designed for legal agreements rather than for matching a supplier's narrative to a requirement list. General-purpose chat assistants can summarise a response, but their summaries are not linked to verifiable locations and may state that a requirement is met without textual support, a known failure mode of large language models (Ji et al., 2023).

Retrieval-augmented generation (Lewis et al., 2020) and citation-generating models (Gao et al., 2023) suggest a better pattern: ground each statement in retrieved text and make the grounding checkable. TenderLens applies this pattern to a setting where checkability is a legal and administrative requirement rather than a convenience.

## 3. Problem Statement and Motivation

### 3.1 Specific Problem

Given an RFT's list of mandatory requirements and one supplier response, a panel member must determine for each requirement whether the response addresses it, and record where. The task is laborious because evidence is scattered, vocabulary differs between buyer and supplier, and each decision must be justified.

### 3.2 Who Is Affected

Evaluation panel members carry the reading load. Procurement managers carry the risk of challenge if exclusions are poorly documented. Suppliers are affected when a compliant response is wrongly excluded.

### 3.3 Why the Problem Matters

Errors at the compliance gate are costly in both directions. A wrongful exclusion can trigger a complaint under the agency's procurement complaints process and delay contract award; a missed non-compliance can lead to awarding a contract to a supplier who cannot meet a mandatory obligation. Time spent on mechanical searching also reduces time available for the qualitative evaluation that panels are actually expert in.

### 3.4 Why Generative AI Is Appropriate

The core operation — deciding whether a passage satisfies a requirement written in different words — is a semantic judgement over natural language. Rule-based matching and keyword search cannot recognise that "our ISO 27001-certified information security management system" satisfies "the supplier must maintain a recognised information security framework". At the same time, the risks of generative models (fabricated support, overconfidence) are exactly the risks a compliance process cannot accept. The proposal therefore uses GenAI only where semantic judgement is required, and surrounds it with deterministic verification: quotations must exist in the source, every requirement must receive a decision with evidence or an explicit "not found", and the human reviewer decides.

### 3.5 Project Objective and Success Hypothesis

**Objective:** build a working prototype that produces a verified evidence matrix for one RFT and one supplier response within the semester.

**Hypothesis:** compared with direct whole-document LLM review, TenderLens will reduce unsupported findings to below 5% while keeping requirement-level macro-F1 at or above 0.80, and will reduce panel-member time per response by at least 30% compared with manual review.

## 4. Stakeholders and Requirements Engineering

### 4.1 Stakeholders and Needs

| Stakeholder | Role | Primary need |
|---|---|---|
| Panel member | Checks compliance of each response | Find evidence quickly; justify each decision |
| Panel chair | Moderates disagreements | See where members' decisions differ and why |
| Procurement manager | Owns process integrity | Auditable record of every exclusion |
| Supplier | Submits response | Fair, consistent assessment of what they wrote |
| Agency IT security | Approves tools | No confidential tender data sent to unapproved services |

### 4.2 Primary User Stories

- **US1** As a panel member, I want each mandatory requirement listed with the passages that address it, so that I can confirm compliance without reading the whole response linearly.
- **US2** As a panel member, I want to see when no evidence was found, so that I can check the response myself before excluding it.
- **US3** As a panel chair, I want to compare two members' confirmed matrices, so that moderation focuses on disagreements.
- **US4** As a procurement manager, I want an exportable record of decisions with page references, so that exclusions can be defended.

### 4.3 Scope and Boundaries

**In scope:** one RFT and one or more text-based PDF responses at a time; mandatory requirements expressed as discrete statements; English-language documents; evidence matrix review and export.

**Out of scope:** weighted scoring and ranking of suppliers; pricing evaluation; scanned image-only documents; integration with AusTender or agency records systems; any automated exclusion decision.

### 4.4 Assumptions

- RFT requirements can be extracted as a numbered list with at most light manual correction.
- Responses are text-based PDFs; scanned pages are flagged rather than processed.
- A cloud model endpoint approved for unclassified data is available for development; production deployment would require an agency-approved endpoint.

### 4.5 Functional Requirements

Each member owns at least three functional requirements (responsibility areas in Section 10.2).

| ID | Requirement | Priority | Owner | Acceptance criterion |
|---|---|---|---|---|
| FR1 | Extract mandatory requirements from an RFT into a numbered register | Must | A1 | ≥95% of requirements in three test RFTs extracted with correct text and numbering |
| FR2 | Let the user correct, merge or split extracted requirements before a check | Must | A1 | Edits saved and used in the next run; original extraction retained |
| FR3 | Version every prompt and record the version with each finding | Must | A1 | Every stored finding carries a prompt version present in the repository |
| FR4 | Parse a response PDF into paragraphs with page and section locators | Must | A2 | 100% of paragraphs carry page and section metadata |
| FR5 | Flag pages without a text layer instead of processing them | Must | A2 | Image-only test pages are listed as "needs manual check" |
| FR6 | Export the confirmed matrix with page references | Should | A2 | Export opens in Excel and contains every confirmed decision |
| FR7 | Retrieve candidate passages for each requirement | Must | A3 | Evidence recall@8 ≥0.85 against annotated evidence |
| FR8 | Allow one additional agent-initiated search per requirement | Should | A3 | Search requests logged; never more than two per requirement |
| FR9 | Run the evaluation harness on a labelled set with one command | Must | A3 | Harness reproduces M1–M7 from logged runs |
| FR10 | Classify each requirement as addressed, partial or not found | Must | A4 | Macro-F1 ≥0.80 against adjudicated labels |
| FR11 | Attach verbatim quotations to every addressed or partial finding | Must | A4 | 100% of displayed quotations match the source text |
| FR12 | Reject findings whose quotations do not match the source | Must | A4 | Zero unverified quotations reach the reviewer view |
| FR13 | Show each quotation in context with one click | Must | A5 | Reviewer reaches the source paragraph in ≤2 interactions |
| FR14 | Let the reviewer confirm or override each finding with a note | Must | A5 | Override stored with reviewer, time and original AI finding |
| FR15 | Compare two reviewers' confirmed matrices | Could | A5 | Disagreements listed per requirement |

### 4.6 Non-Functional Requirements

| ID | Requirement | Measure and target |
|---|---|---|
| NFR1 | Grounding | 0% of displayed quotations absent from source (verified by code) |
| NFR2 | Latency | ≤4 minutes to produce a matrix for a 100-page response with 40 requirements |
| NFR3 | Reproducibility | Prompt version, model identifier and retrieval settings logged for every run |
| NFR4 | Privacy | No response text stored outside the local workspace; provider data retention disabled |
| NFR5 | Usability | System Usability Scale (Brooke, 1996) ≥70 in the reviewer study |
| NFR6 | Cost | ≤A$1.50 model cost per response at list prices |

### 4.7 Constraints

| ID | Constraint |
|---|---|
| C1 | Only public RFT templates and synthetic responses are used; no real supplier data |
| C2 | The prototype runs locally on a team laptop; the only external call is to the model endpoint |
| C3 | Model spend for the semester is capped at A$150 |
| C4 | Eight development weeks, five students |

### 4.8 Requirements-to-Evaluation Traceability

| Requirement | Evaluation metric (Section 8.4) |
|---|---|
| FR1–FR2 | M1 requirement extraction accuracy |
| FR4–FR5 | M2 locator completeness |
| FR7–FR8 | M3 evidence recall@8 |
| FR10 | M4 macro-F1 |
| FR11–FR12, NFR1 | M5 citation precision, M6 unsupported-finding rate |
| FR13–FR14, NFR5 | M8 reviewer time, M9 SUS |
| FR3, FR9, NFR3 | Reproduced runs from logs |
| NFR2, NFR6 | M10 latency and cost |

## 5. Proposed Product and Innovation

### 5.1 Product Concept

TenderLens is a local web application. A panel member uploads the RFT and a response, reviews the extracted requirement register, starts the check, and receives an evidence matrix: one row per requirement, with a status, one to three quotations, their page locations and a short rationale. The member confirms or overrides each row and exports the result.

### 5.2 Major Features and User Workflow

1. Upload RFT → requirement register extracted and shown for correction.
2. Upload response → parsed into located paragraphs.
3. Run check → for each requirement, candidate passages retrieved and assessed.
4. Review matrix → each finding shows quotations highlighted in the document view.
5. Confirm or override → reasons recorded.
6. Export → spreadsheet with decisions and page references.

### 5.3 Innovation and Distinction from a Generic Chatbot

A chatbot answers questions about a document. TenderLens produces a complete, structured decision record in which every positive finding is backed by verified text, and every absence is explicit. Three design choices distinguish it: (a) requirement-by-requirement processing so no requirement is skipped; (b) deterministic quotation verification before anything is shown; (c) separation of AI findings from human decisions in the stored record. These choices respond directly to documented weaknesses of LLM output — unsupported claims and positional blind spots (Ji et al., 2023; Liu et al., 2024).

## 6. Proposed Methodology and System Design

### 6.1 System Architecture

The system has six components (Appendix A): a document parser (PyMuPDF), a requirement extractor (LLM with structured output, followed by human correction), a hybrid retriever (BM25 (Robertson & Zaragoza, 2009) plus dense embeddings with reciprocal-rank fusion), an assessment agent, a verifier, and a review interface (FastAPI back end, React front end, SQLite store).

### 6.2 Data Flow and Structured Output Contract

For each requirement the assessment agent receives the requirement text and the eight best candidate passages, each with an identifier. It must return JSON with `status` (addressed | partial | not_found), `quotes` (each with passage identifier and verbatim text) and `rationale`. The verifier checks that each quotation is a substring of the identified passage after whitespace normalisation; failing quotations are removed, and a finding left with no valid quotation is downgraded to *not found — needs manual check*. The agent may request one additional search with its own query when the first candidates are insufficient, following a bounded tool-use pattern (Yao et al., 2023) with a hard limit of two searches.

### 6.3 Model Strategy

Development uses a hosted model through an OpenAI-compatible interface at temperature 0. We will compare one frontier model and one smaller open-weight model on the development set and select on macro-F1 and cost. Prompts are versioned in the repository.

### 6.4 Development Method

Two-week iterations with a fixed demo at the end of each. Each iteration ends with a run of the evaluation harness on the development set; regressions block merging.

### 6.5 Data, Evaluation Material and Tools

Three public RFT templates (ICT services, facilities maintenance, consultancy) provide requirement lists. We will write 24 synthetic responses (8 per template) with deliberately varied compliance: fully compliant, indirect compliance in appendices, partial compliance and clear omissions. No real supplier data is used.

## 7. Business and Product Analysis

### 7.1 Value Proposition

For procurement panels that must justify every exclusion, TenderLens turns a linear reading task into a verification task: the reviewer checks proposed evidence instead of searching for it, and the record of where each requirement is addressed is produced as a by-product.

### 7.2 Intended Users and Customers

Primary users are evaluation panel members in public agencies and large private organisations with formal procurement. Customers are procurement branches, which purchase tools centrally.

### 7.3 Alternatives and Competitors

| Alternative | Strength | Limitation for compliance checking |
|---|---|---|
| Manual reading with PDF search | Trusted, no new tools | Slow; keyword search misses paraphrase |
| E-procurement platforms | Manage lodgement and deadlines | Do not assess response content |
| Contract-analysis tools | Strong clause extraction | Built for contracts, not requirement-to-narrative matching |
| General chat assistants | Fast summaries | No verified locations; may assert unsupported compliance |
| TenderLens | Verified, located evidence per requirement | Requires requirement extraction step; text PDFs only |

The closest competitor in capability is a general chat assistant with document upload. Our evaluation includes exactly this as a baseline (direct whole-document review) so that the benefit of verification is measured rather than asserted.

### 7.4 Benefits

Reduced search time; consistent coverage of every requirement; documented evidence for exclusions; faster moderation because disagreements are visible.

### 7.5 Feasibility and Adoption Pathway

A local prototype avoids integration barriers during evaluation. Adoption in an agency would require an approved model endpoint and a security assessment; the design keeps all data local except calls to that endpoint.

### 7.6 Cost and Operational Considerations

A 100-page response is approximately 60,000 tokens. With retrieval limiting each requirement's context to eight passages, a 40-requirement check uses roughly 200,000 input tokens. At current list prices for mid-tier hosted models this is below one Australian dollar per response.

## 8. Evaluation Plan

### 8.1 Dataset Construction and Labelling

The 24 synthetic responses are split into 8 development and 16 test responses, stratified by template. Two team members independently label each requirement in each response (status and evidence passages); disagreements are adjudicated by a third member. Inter-annotator agreement (Cohen's kappa) is reported before adjudication.

### 8.2 Baselines

- **B1 Manual review:** a team member checks test responses with PDF search only; time and decisions recorded.
- **B2 Direct LLM review:** the same model receives the full response and the full requirement list in one prompt and returns statuses and quotations, without retrieval or verification.

### 8.3 Test Scenarios

Fully compliant responses; evidence located only in appendices; paraphrased compliance; partial compliance; clear omission; and adversarial text (a sentence claiming "this response meets all mandatory requirements").

### 8.4 Metrics and Targets

| ID | Metric | Definition | Target |
|---|---|---|---|
| M1 | Requirement extraction accuracy | Requirements extracted with correct text and number | ≥95% |
| M2 | Locator completeness | Paragraphs with page and section | 100% |
| M3 | Evidence recall@8 | Annotated evidence passages among top-8 candidates | ≥0.85 |
| M4 | Status macro-F1 | Agreement of status with adjudicated labels | ≥0.80 |
| M5 | Citation precision | Displayed quotations judged to support the finding | ≥0.95 |
| M6 | Unsupported-finding rate | Addressed findings with no valid supporting quotation | ≤5% (B2 expected higher) |
| M7 | Adversarial robustness | Adversarial sentence never cited as evidence | 100% |
| M8 | Reviewer time | Minutes per response, TenderLens vs B1 | ≥30% reduction |
| M9 | Usability | SUS score | ≥70 |
| M10 | Latency and cost | Per response | ≤4 min; ≤A$1.50 |

### 8.5 Procedure and Reporting

Prompts are frozen before the test set is used. Each system is run three times on the test set to report variance. Reviewer-time measurement uses a within-subject design with three volunteer reviewers, counterbalancing the order of tools. Results are reported per metric with confidence intervals and with failure cases illustrated.

## 9. Risks, Ethics and Responsible AI

TenderLens is decision support: it never excludes a supplier, and AI findings are stored separately from confirmed decisions.

| ID | Risk | L / I | Mitigation | Trigger and fallback |
|---|---|---|---|---|
| R1 | Missed evidence leads to wrongful "not found" | M / H | Hybrid retrieval; second search allowed; "not found" always marked for manual check | Recall@8 <0.80 on dev → increase candidates to 12 |
| R2 | Fabricated or misattributed quotation | M / H | Verifier rejects non-matching quotations | Any unverified quote in review view → block release |
| R3 | Automation bias: reviewer accepts wrong finding | M / H | Evidence shown before status; override one click | Override rate <2% in study → add confirmation step |
| R4 | Confidential data leakage | L / H | Synthetic data only; provider retention disabled | Any real tender data → stop and remove |
| R5 | Prompt injection in response text | M / M | Response treated as quoted data; adversarial tests (M7) | M7 <100% → strengthen delimiting and add filter |
| R6 | Scope creep into scoring | M / M | Scoring explicitly out of scope | New scoring request → backlog only |

## 10. Semester Plan and Team Responsibilities

### 10.1 Milestones

| Week | Milestone | Deliverable |
|---|---|---|
| 6 | Parsing and requirement extraction | FR1–FR5 working on three RFTs |
| 7 | Synthetic dataset and labels | 24 responses, adjudicated labels |
| 8 | Retrieval and assessment agent | FR7–FR12 on dev set; first M3–M6 results |
| 9 | Review interface | FR13–FR14; internal usability check |
| 10 | Export and comparison | FR6, FR15 |
| 11 | Test-set evaluation | M1–M10 results |
| 12 | Reviewer study and refinement | M8–M9; final report draft |
| 13 | Presentation | Live demo and report |

### 10.2 Responsibility Areas

| Area | Member | Responsibilities |
|---|---|---|
| A1 | Mia Chen | Requirement extraction, prompt versioning |
| A2 | Liam O'Brien | Document parsing, export, dataset construction |
| A3 | Priya Raman | Retrieval, evaluation harness |
| A4 | Tom Nguyen | Assessment agent, verifier |
| A5 | Sara Haddad | Review interface, reviewer study |

### 10.3 Dependencies and De-scoping Order

Retrieval (A3) and parsing (A2) must be ready before the agent (A4) can be evaluated. If behind schedule, we de-scope in this order: FR15 comparison, FR6 export formatting, the second model comparison.

## 11. References

Brooke, J. (1996). SUS: A "quick and dirty" usability scale. In P. W. Jordan, B. Thomas, B. A. Weerdmeester, & I. L. McClelland (Eds.), *Usability evaluation in industry* (pp. 189–194). Taylor & Francis.

Department of Finance. (n.d.). *Commonwealth Procurement Rules*. Australian Government.

Gao, T., Yen, H., Yu, J., & Chen, D. (2023). Enabling large language models to generate text with citations. In *Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing* (pp. 6465–6488).

Ji, Z., Lee, N., Frieske, R., Yu, T., Su, D., Xu, Y., Ishii, E., Bang, Y. J., Madotto, A., & Fung, P. (2023). Survey of hallucination in natural language generation. *ACM Computing Surveys, 55*(12), 1–38.

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W., Rocktäschel, T., Riedel, S., & Kiela, D. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. *Advances in Neural Information Processing Systems, 33*, 9459–9474.

Liu, N. F., Lin, K., Hewitt, J., Paranjape, A., Bevilacqua, M., Petroni, F., & Liang, P. (2024). Lost in the middle: How language models use long contexts. *Transactions of the Association for Computational Linguistics, 12*, 157–173.

Robertson, S., & Zaragoza, H. (2009). The probabilistic relevance framework: BM25 and beyond. *Foundations and Trends in Information Retrieval, 3*(4), 333–389.

Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., & Cao, Y. (2023). ReAct: Synergizing reasoning and acting in language models. In *International Conference on Learning Representations*.

## Appendix A — System Architecture

| Component | Input | Output | Technology |
|---|---|---|---|
| Document parser | RFT and response PDFs | Located paragraphs | PyMuPDF |
| Requirement extractor | RFT paragraphs | Numbered requirement register | LLM structured output + human correction |
| Hybrid retriever | Requirement, response paragraphs | Top-8 candidate passages | BM25 + embeddings, rank fusion |
| Assessment agent | Requirement, candidates | Status, quotations, rationale | LLM, temperature 0, ≤2 searches |
| Verifier | Agent output, source paragraphs | Verified findings | Deterministic substring matching |
| Review interface | Verified findings | Confirmed matrix, export | FastAPI, React, SQLite |

## Appendix B — Reviewer Workflow

The reviewer opens a response and sees the requirement list on the left and the document on the right. Selecting a requirement highlights its quotations in the document. The reviewer confirms the status or chooses another, adds a note when overriding, and moves to the next requirement. Requirements marked "not found" are listed first, because they carry the highest consequence and require the reviewer's own search before any exclusion is recorded.
