# Preloaded rubrics

Every file in this folder becomes a rubric in the library when the sample data is loaded
(`make seed`, every API start, or **Reset samples** on Home). Files starting with `_` are
templates and are ignored. The rubric id is `rub_<file name>`: `shortanswer.json` →
`rub_shortanswer` (the sample batches in `../manifest.py` refer to rubrics by this id).

Files are read by the same **local** parser as the import page — no AI call — and the
seed stops with the parser's message if a file is ambiguous (a level without points, an
empty description, a stated total that disagrees with the criteria).

## Formats, best first

1. **JSON** (`_template.json`) — exact: every criterion, level label, points, score range
   and description is taken as written. Also the only format that can set `source`,
   `pinned` (default `true`) and `age_days` (how long ago it was "updated").
   A Canvas rubric export (`criteria[].ratings[]`) is also accepted as-is.
2. **Markdown table** (`.md`) or **CSV/TSV** exported from Excel (`_template.csv`) — one
   row per criterion: `Criterion, Points`, then one column per level. Put each level's
   points either in its header (`Excellent (3)`) or at the end of each cell
   (`Clear thesis (30)`). Rows may have different numbers of levels if you leave cells
   empty.
3. **TXT / DOCX / PDF** — parsed from text using headings like `1. Accuracy — 3 marks`
   followed by lines like `Excellent (3): Correct and complete.` Works for clean layouts;
   tables pasted from PDFs often lose their structure, so prefer 1 or 2.
