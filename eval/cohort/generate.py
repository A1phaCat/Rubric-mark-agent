"""Write the cohort's submissions from their prompts with any OpenAI-compatible chat API.

    GEN_API_KEY=... .venv/bin/python -m eval.cohort.generate --model gpt-5-mini

Each submission is saved to src/<id>.md as soon as it arrives; running again skips what
exists, so an interrupted run resumes. Near-duplicates are written last, from their source.
A different provider from the one being evaluated avoids a model marking its own writing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from pathlib import Path

import httpx

HERE = Path(__file__).parent
PROMPTS = HERE / "prompts"
SOURCES = HERE / "src"
_FRONT = re.compile(
    r"^\s*(?:```(?:markdown|md)?\s*\n)?(---\n.*?\n---\n.*?)(?:\n```\s*)?$",
    re.DOTALL,
)


def _clean(text: str) -> str:
    """The document itself: without a code fence around it, starting at the front matter."""

    match = _FRONT.match(text)
    return (match.group(1) if match else text).strip() + "\n"


async def _write(client: httpx.AsyncClient, args: argparse.Namespace, sid: str, prompt: str,
                 limit: asyncio.Semaphore) -> None:
    target = SOURCES / f"{sid}.md"
    if target.exists():
        return
    budget = "max_completion_tokens" if "openai.com" in args.base_url else "max_tokens"
    payload = {"model": args.model, "messages": [{"role": "user", "content": prompt}], budget: args.max_tokens}
    async with limit:
        for attempt in range(1, 4):
            try:
                response = await client.post(f"{args.base_url.rstrip('/')}/chat/completions", json=payload)
                if response.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                    await asyncio.sleep(10 * attempt)
                    continue
                response.raise_for_status()
                text = response.json()["choices"][0]["message"]["content"] or ""
                if not text.lstrip().startswith(("---", "```")):
                    raise ValueError("the reply does not start with the front matter")
                target.write_text(_clean(text), encoding="utf-8")
                print(f"  {sid}: {len(text.split())} words")
                return
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                if attempt == 3:
                    print(f"  {sid}: FAILED {type(exc).__name__}: {str(exc)[:160]}")
                    return
                await asyncio.sleep(5 * attempt)


async def run(args: argparse.Namespace) -> None:
    key = os.environ.get("GEN_API_KEY")
    if not key:
        raise SystemExit("set GEN_API_KEY to the writer model's API key")
    SOURCES.mkdir(exist_ok=True)
    specs = json.loads((HERE / "specs.json").read_text(encoding="utf-8"))
    wanted = set(args.only.split(",")) if args.only else None
    limit = asyncio.Semaphore(args.parallel)
    headers = {"Authorization": f"Bearer {key}"}
    async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(600.0, connect=20.0)) as client:
        first = [s for s in specs if s["type"] != "near_duplicate" and (wanted is None or s["id"] in wanted)]
        await asyncio.gather(*(_write(client, args, s["id"], (PROMPTS / f"{s['id']}.txt").read_text(encoding="utf-8"),
                                      limit) for s in first))
        later = []
        for spec in specs:
            if spec["type"] != "near_duplicate" or (wanted is not None and spec["id"] not in wanted):
                continue
            source = SOURCES / f"{spec['source']}.md"
            if not source.exists():
                print(f"  {spec['id']}: skipped, its source {spec['source']} is not written yet")
                continue
            prompt = (PROMPTS / f"{spec['id']}.txt").read_text(encoding="utf-8")
            later.append(_write(client, args, spec["id"],
                                prompt.replace("{SOURCE}", source.read_text(encoding="utf-8")), limit))
        await asyncio.gather(*later)
    done = len(list(SOURCES.glob("c*.md")))
    print(f"{done} of {len(specs)} written → {SOURCES}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="https://api.openai.com/v1")
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=16000)
    parser.add_argument("--only", help="comma-separated ids, e.g. c001,c002 for a trial")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
