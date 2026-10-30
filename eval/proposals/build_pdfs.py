"""Render the synthetic proposals in src/ to PDF (needs the Markdown and Playwright packages).

    python eval/proposals/build_pdfs.py

The PDFs, not the Markdown, are what the evaluation grades: they go through the same PDF
extraction as an uploaded submission.
"""

from __future__ import annotations

import re
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
CSS = """
@page { size: A4; margin: 22mm 20mm 20mm 20mm; }
body { font-family: 'Times New Roman', 'Liberation Serif', serif; font-size: 11pt; line-height: 1.38; color: #111; }
h1 { font-size: 17pt; margin: 0 0 4pt; }
.subtitle { font-size: 11.5pt; margin: 0 0 2pt; }
.team { font-size: 10.5pt; color: #333; margin: 0 0 16pt; }
h2 { font-size: 13pt; margin: 16pt 0 5pt; }
h3 { font-size: 11.5pt; margin: 10pt 0 4pt; }
p { margin: 0 0 7pt; text-align: justify; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 9.5pt; page-break-inside: auto; }
th, td { border: 0.6pt solid #666; padding: 3pt 4pt; vertical-align: top; text-align: left; }
th { background: #eee; }
tr { page-break-inside: avoid; }
ul, ol { margin: 0 0 7pt 16pt; padding: 0; }
li { margin: 0 0 2pt; }
"""


def _front_matter(text: str) -> tuple[dict[str, str], str]:
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not match:
        return {}, text
    meta = dict(re.findall(r'^(\w+):\s*"(.*)"\s*$', match.group(1), re.M))
    return meta, text[match.end():]


def render(source: Path, target: Path, page) -> None:
    meta, body = _front_matter(source.read_text(encoding="utf-8"))
    html_body = markdown.markdown(body, extensions=["tables"])
    head = (f"<h1>{meta.get('title', '')}</h1><p class='subtitle'>{meta.get('subtitle', '')}</p>"
            f"<p class='team'>{meta.get('team', '')}</p>")
    page.set_content(f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{head}{html_body}</body></html>")
    page.pdf(path=str(target), format="A4", print_background=True, display_header_footer=True,
             header_template="<span></span>",
             footer_template="<div style='font-size:8pt;width:100%;text-align:center;'>"
                             "<span class='pageNumber'></span></div>",
             margin={"top": "22mm", "bottom": "20mm", "left": "20mm", "right": "20mm"})


def main() -> None:
    out = HERE / "pdf"
    out.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        for source in sorted((HERE / "src").glob("*.md")):
            target = out / f"{source.stem}.pdf"
            render(source, target, page)
            print(f"{source.name} → {target.relative_to(HERE)}")
        browser.close()


if __name__ == "__main__":
    main()
