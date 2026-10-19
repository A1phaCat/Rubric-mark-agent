# AI-assisted marker — UI prototype (USyd layered theme)

Open `00-home.html` in a browser. Keep all files in the same folder (including `rubric-library.js`) — pages link to each other
and pass the saved rubric between them.

| File | Page | Notes |
|---|---|---|
| `00-home.html` | Tutor home | Active batches, confidence breakdown, "Up next" queue. Quiz 3 card opens the finished batch. |
| `01-upload.html` | Set up a marking batch | Rubric: pick one from the library **or** paste rubric text and “Parse with AI”; the criteria appear below to check and edit (weights, all five levels, checks). Submissions: a Canvas assignment **or** a zip. Bottom bar shows rubric, criteria, submissions and time, and enables Start batch when everything checks out. |
| `01a-rubric-import.html` | Import a rubric | Opened from the rubric library. From Canvas / Upload / Paste; edit cells inline, consistency checks. One Export menu (JSON / Markdown / CSV) and one Save → back to the library. |
| `02-batch-status.html` | Batch in progress | Processing progress, filters, submissions table. `#asgn1` shows the batch that is in review. Top right shows which batch (1/3) and its status; footer has Previous batch (left) and Next batch (right). "Start reviewing" sits at the top right of the page heading. |
| `03b-review-split.html` | Review | Submission on the left, criteria on the right; hover to highlight, click to jump, fold criteria, "Highlight all", tutor comments. |
| `04-batch-complete.html` | Finished batch | Locked marks, grade distribution, adjustments by criterion, "Tutor changes" and "Mark report" columns. Same batch footer bar (batch 3 of 3). |
| `07-batches.html` | All marking batches | Every batch grouped by semester: search, filter (active / draft / complete), status, progress and rubric. The three active ones are also on Home. |
| `06-rubrics.html` | Rubric library | Every saved rubric: search, filter by in use, preview (criteria × levels), edit in place, use for a new batch. Home shows the 3 most recent; importing a rubric adds it here. |
| `05-mark-report.html` | Mark report | Final mark, AI summary, tutor comment per criterion. Print / PDF ready. |

Flow: Home → Set up batch → Choose / paste rubric → Batch in progress → Review → Finished batch → Mark report.
Every page shares one top bar: University of Sydney logo · "AI-assisted marker" · "Prototype" tag on the left, a placeholder signed-in user (J. Alvarez · Tutor) on the right, and a breadcrumb right after the "Prototype" tag (e.g. Home › Quiz 3 Short Answers › SID-50102 report) on every page except Home, which shows the main nav there instead. On phones the breadcrumb shrinks to "‹ parent page".
Internal coursework demo only — not an official University of Sydney service.

Top-right avatar (every page) opens Account & connections: AI model (university service on Azure OpenAI by default, or your own key: MiniMax China mainland with a real connection test, Azure, Anthropic, OpenAI). Test calls the provider’s /models endpoint and replaces the suggested model list with what your key can actually use and Canvas (SSO or access token). Kept in this browser for the demo (`account-menu.js`).

Fonts load from Google Fonts (needs internet); offline, the pages fall back to system fonts.
All names, marks and essay text are sample data.

**Review end states (demo URLs):** `03b-review-split.html?demo=single` (one-file batch — confirm → *Batch complete* card), `?demo=last` (last of 48), `?demo=wait` (nothing ready, others still with the AI — waiting card, then *Open next* when the AI finishes one). The batch is marked complete on the last confirm; the tutor opens the results from the card, Home or the batch list.

**Docs for the backend:** `../docs/DEV-GUIDE.md` — Part 1 (§S) specification, Part 2 (§G) implementation guide.
