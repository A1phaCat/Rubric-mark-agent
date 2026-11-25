---
title: "SiteSafe: AI Summaries of Construction Site Safety Reports"
subtitle: "ELEC5623 Group Business Proposal · Track A — AI Agent Product"
team: "Group 3"
---

| Cover information | |
|---|---|
| Track | A — AI Agent Product |
| Group | 3 |
| Members | Ethan Brooks (530311208), Hannah Lee (530298871), Omar Farouk (530305563), Isabella Rossi (530287140), Jack Turner (530316692) |
| Lab tutor and approval | Dr K. Morrison — approved 25 August 2026 |
| Product vision | Site safety managers see the hazards that matter across all their reports without reading every one. |

## 1. Executive Summary

Construction remains one of the higher-risk industries in Australia, and Safe Work Australia identifies it as a priority industry in national work health and safety strategy (Safe Work Australia, n.d.). On a typical medium-sized building site, supervisors complete daily pre-start checklists, hazard reports, toolbox talk records and incident or near-miss reports. A safety manager overseeing several sites receives dozens of these documents each week. Important patterns — the same scaffold issue reported three times, or a near miss that repeats an earlier incident — are easy to miss when reports are read one at a time.

SiteSafe is an AI agent that reads a week of site safety reports, extracts the hazards and incidents described, groups related reports, links each hazard to the relevant section of the applicable code of practice, and produces a weekly briefing for the safety manager with links back to the original reports. The aim is to help safety managers notice recurring and escalating risks earlier.

## 2. Background

### 2.1 Context

Safety reporting on construction sites is largely free text. Supervisors write in their own words, often quickly and with site jargon ("edge pro missing on L3", "EWP near overheads"). Reports are submitted through forms or as PDFs and stored in a document system. Safety managers read them, follow up individual issues and prepare monthly summaries for management.

### 2.2 Why This Is a Problem

When reports are read individually, trends across days and sites are hard to see. A safety manager we spoke to (a family member of one of our team, working for a mid-tier builder) said that "the stuff that worries me is the thing that's been written down four times and nobody joined the dots". Near-miss reporting is widely considered a leading indicator of more serious incidents, so missing repeated near misses is a lost opportunity for prevention.

### 2.2a Types of Safety Documents on a Typical Site

| Document | Who writes it | Frequency | Typical content |
|---|---|---|---|
| Pre-start checklist | Supervisor | Daily | Tick-box items with short free-text comments |
| Hazard report | Any worker or supervisor | As needed | Description of a hazard, location, immediate action taken |
| Toolbox talk record | Supervisor | Weekly | Topic discussed, attendance, issues raised by workers |
| Near-miss report | Supervisor | As needed | What happened, what could have happened, contributing factors |
| Incident report | Supervisor or safety officer | As needed | Injury or damage, sequence of events, corrective actions |
| Subcontractor SWMS review notes | Safety officer | Per activity | Gaps found in safe work method statements |

The free-text parts of these documents contain most of the information that matters for spotting trends, and they are also the parts that are least consistently written.

### 2.3 Why GenAI

Reports are short, informal and inconsistent. Extracting the hazard, location, equipment and severity from text like "spotter left EWP unattended, wind picking up" requires understanding of language and context that keyword rules cannot provide. Grouping reports that describe the same underlying issue in different words is also a semantic task. Large language models can perform this kind of extraction and summarisation, while retrieval of code-of-practice sections can keep the briefing grounded in the relevant guidance (Lewis et al., 2020).

## 3. Problem Statement

Safety managers cannot easily see recurring and escalating hazards across many free-text safety reports, which means preventable incidents may not be identified early enough. The people affected are safety managers, site supervisors and, ultimately, workers on site.

## 8. Evaluation Plan

*(We have placed the evaluation plan here because it guided our requirements.)*

### 8.1 Dataset

We will write 120 synthetic safety reports covering two fictional sites over four weeks, based on public examples of hazard report templates. Into these we will plant 15 recurring hazard patterns (for example, the same missing edge protection reported on different days with different wording) and 5 escalation patterns (a near miss followed by a related incident). Two team members will label each report with hazard type and the pattern it belongs to.

### 8.2 Baseline

A team member acting as a safety manager will read each synthetic week of reports and write a briefing manually. We will also compare with a simple keyword-grouping baseline that clusters reports sharing hazard keywords.

### 8.3 Metrics

| Metric | Definition | Target |
|---|---|---|
| Hazard extraction F1 | Extracted hazard type vs label | ≥0.80 |
| Pattern recall | Planted recurring patterns identified in the briefing | ≥80% (keyword baseline expected ≈50%) |
| Escalation recall | Planted escalations flagged | ≥4 of 5 |
| Link accuracy | Briefing items whose report links are correct | ≥95% |
| Code-of-practice relevance | Linked guidance judged relevant by two raters | ≥85% |
| Briefing time | Minutes to produce a weekly briefing vs manual | ≥50% reduction |

### 8.4 Qualitative Evaluation

Two people with construction experience (one site supervisor and one safety adviser, recruited through team contacts) will review two briefings and comment on usefulness. We have not yet confirmed their availability.

### 8.5 Procedure

The development set (weeks 1–2) is used to tune the clustering threshold and prompts. The test set (weeks 3–4) is used once, after prompts and thresholds are frozen. Each system — SiteSafe, the keyword baseline and the manual briefing — produces a briefing for each test week, and two team members who did not write the planted patterns score pattern recall and link accuracy independently. Disagreements are resolved by discussion and reported.

## 4. Requirements

### 4.1 Users

The users are safety managers and maybe also site supervisors and project managers.

### 4.2 Requirements

The system should:

- read safety reports;
- summarise reports well;
- find hazards in the reports;
- group similar hazards;
- link hazards to the codes of practice;
- make a weekly briefing;
- show the original reports;
- be easy to use and look professional;
- be fast enough;
- be accurate;
- keep data secure;
- work on mobile phones;
- support voice reports from supervisors;
- support reports in other languages;
- connect to the builder's document management system;
- detect hazards in site photos.

### 4.3 Scope

The project covers safety reports for construction sites. We will try to include as many features as possible so that the product is useful in practice.

## 5. Proposed Product

### 5.1 Concept

SiteSafe has three parts: a report ingestion pipeline, an analysis agent and a briefing interface. The safety manager selects a week and a set of sites; SiteSafe processes the reports and shows a briefing with sections for recurring hazards, escalations and new high-severity hazards. Each item links to the reports it is based on and to the relevant code-of-practice section.

### 5.2 Innovation

Existing safety software stores reports and checklists; SiteSafe reads them. Its contribution is the cross-report view: grouping semantically similar hazards across days and sites, and flagging escalation from near miss to incident.

## 6. Methodology and System Design

### 6.1 Architecture

| Component | Description |
|---|---|
| Ingestion | Reads PDF and form exports, splits into reports, extracts date, site and author |
| Extraction step | LLM extracts hazard type, location, equipment, severity and a one-line description into JSON |
| Embedding and clustering | Embeds each extracted hazard; clusters by similarity within a time window |
| Escalation detector | Rules over clusters: a near miss followed within 14 days by an incident in the same cluster |
| Guidance retrieval | Retrieves relevant code-of-practice passages for each cluster |
| Briefing writer | LLM writes the briefing from clusters, with report links attached by code |
| Interface | Web page showing the briefing and source reports |

### 6.2 Workflow

Reports are ingested and each is processed by the extraction step with a fixed JSON schema. Extracted hazards are embedded and clustered with a similarity threshold tuned on the development set. The escalation detector runs over clusters. For each cluster above a minimum size, guidance retrieval finds the most relevant code-of-practice passages from a small local index. The briefing writer receives only the cluster summaries, counts, severity and guidance excerpts; report links are attached by code, not generated by the model, so they cannot be invented.

### 6.3 Model Choice

A hosted LLM at temperature 0 for extraction; the same model for briefing writing. A small open-source embedding model runs locally.

### 6.4 Extraction Schema

| Field | Type | Example |
|---|---|---|
| hazard_type | One of 14 categories (falls from height, falling objects, mobile plant, electrical, excavation, manual handling, …) | falls from height |
| location | Free text normalised to site zone where possible | Level 3, east edge |
| equipment | Free text | edge protection |
| severity | low / medium / high, from report wording and hazard type | high |
| event | hazard observed / near miss / incident | hazard observed |
| action_taken | Free text or "none recorded" | area barricaded |
| summary | One sentence | Edge protection missing on Level 3 east edge; area barricaded. |

Each extracted record keeps the identifier of the source report and the sentence the fields were taken from, so that the briefing can link back to the exact wording.

### 6.5 Grouping and Escalation Logic

Hazard records are embedded using the summary and hazard type. Records are grouped when their similarity exceeds a threshold and they share a hazard category or a site zone; the threshold is chosen on the development weeks to maximise pattern recall at a precision of at least 0.8. A group becomes a *recurring hazard* when it contains three or more reports on different days. An *escalation* is flagged when a group contains a near miss followed within 14 days by an incident report. These rules are deliberately simple so that safety managers can understand why an item appears in the briefing.

### 6.6 Briefing Layout

The weekly briefing has four sections: (1) escalations, (2) recurring hazards ordered by count and severity, (3) new high-severity hazards reported once, and (4) a count of reports processed and any reports that could not be read. Each item shows a two-sentence summary written by the model, the number of reports, the dates and sites, links to each source report with the relevant sentence highlighted, and up to two relevant code-of-practice excerpts.

## 7. Business Analysis

### 7.1 Value

Safety managers save time and see patterns earlier. Builders reduce the risk of serious incidents and demonstrate proactive safety management.

### 7.2 Competitors

| Product | What it does | Gap |
|---|---|---|
| Procore (safety module) | Construction management platform with inspections and incident records | Stores and tracks records; limited cross-report analysis of free text |
| SafetyCulture (iAuditor) | Mobile checklists and inspections with analytics on checklist answers | Analytics focus on structured checklist responses rather than free-text narratives |
| Spreadsheet trackers | Manual hazard registers | Depend on someone reading and coding every report |

SiteSafe is complementary: it could read exports from these systems rather than replace them.

### 7.3 Costs

Model costs are small for 100–200 short reports per week. The main cost in practice would be integration with a builder's systems.

### 7.4 Adoption Considerations

Builders already hold safety records in existing platforms, so SiteSafe would need to read their exports rather than ask supervisors to change how they report. Safety records can contain names of injured workers, so any real deployment would require privacy review and agreement with the builder on where data is processed. For the semester we use synthetic reports only.

## 9. Next Steps

We will build the system during weeks 5 to 12 and present it in week 13. Everyone in the group will work on all parts of the system together.

## Appendix — Example Report and Extracted Record

*Report (synthetic):* "L3 east side edge pro still not back after the formwork crew pulled it yesterday arvo. Barricaded with tape for now. Told the formwork leading hand again."

*Extracted record:* hazard_type = falls from height; location = Level 3, east edge; equipment = edge protection; severity = high; event = hazard observed; action_taken = area barricaded with tape, formwork leading hand notified; summary = "Edge protection on Level 3 east edge still missing after removal by formwork crew; temporary tape barricade."

## References

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W., Rocktäschel, T., Riedel, S., & Kiela, D. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. *Advances in Neural Information Processing Systems, 33*.

Safe Work Australia. (n.d.). Australian Work Health and Safety Strategy 2023–2033.

SafetyCulture, website, accessed 2026.
