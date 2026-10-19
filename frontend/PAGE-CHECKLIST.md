# Frontend parity checklist

Shared done condition: the page looks and behaves like its counterpart in `prototype/`, receives data through `api.js`, handles loading/empty/error, works at 390 px, and has an accepted visual-diff result.

| Page | API data | Current wiring | Loading / empty / error | Mobile | Visual baseline | Done when |
|---|---|---|---|---|---|---|
| Home | summary, queue, active batches, rubrics | Rubrics real; summary/queue loaded into page state | skeleton / prototype / console+state | prototype baseline | pass; max 0.125% | all panels render API values |
| Setup | rubric CRUD, draft batch, files, patch manifest, start | fixture/settings loaded; actions legacy | prototype partial / partial / missing | prototype baseline | pass; max 0.640% | Fix files, Dry run 3 and Start use API |
| Rubric import | parse, parse-file, rubric create | fixture loaded; save legacy | prototype timer / partial / inline only | prototype baseline | pass; max 11.918% | parse/save use API; Canvas visibly disabled |
| Batch status | batch, submissions, SSE, retry/exclude | batch rows loaded into page state | missing / missing / missing | prototype baseline | pass; max 0.006% | filters, SSE, retry/exclude render API state |
| Review | review, criterion PATCH, confirm, next, events | review load + confirm real | missing / waiting card / request state | prototype baseline | pass; max 0.002% | autosave/claim/all end cards are API-driven |
| Results | results, CSV, finalise/reopen | result fixture loaded into page state | missing / missing / missing | prototype baseline | pass; max 0.003% | Quiz 2 editable and Quiz 3 locked variants work |
| Mark report | report, report.pdf | report fixture loaded into page state | missing / missing / missing | prototype baseline | pass; max 0.003% | audiences and server PDF render dynamically |
| Rubrics | rubric CRUD | list real; mutations legacy | missing / search / missing | prototype baseline | pass; max 7.149% | CRUD and return-to-setup are API-driven |
| All batches | batch list | fixture list loaded into page state | missing / search / missing | prototype baseline | pass; max 0.003% | list/search/filter render API data |

Mock mode uses `?mocks=1`; test-only queue endings are injected as `window.MARKER_TEST_FIXTURE = single|last|wait`, never read from a production URL parameter.
