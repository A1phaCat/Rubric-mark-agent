"""Check whether the configured AI provider supports OpenAI-style tool (function) calling.

Uses the provider, base URL, model and key saved in the app (account menu → AI model).
Nothing is printed or saved that contains the key.

    .venv/bin/python scripts/check_tool_calling.py

Writes the raw responses (no key) to data/cache/tool_check.json.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import httpx
from app.config import settings
from app.db.session import SessionLocal
from app.services.settings_service import load_ai_settings

DOCUMENT = {
    "1 Introduction": "[p1] This report proposes a campus food-waste tracker for student kitchens.",
    "3 Evaluation": (
        "[p7] We compare the tracker against a manual paper log used in two kitchens.\n"
        "[p8] Over four weeks, logged waste fell by 18% in the tracker kitchen and 3% in the control."
    ),
    "4 Limitations": "[p11] The tracker fails when items are thrown away without being scanned.",
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "outline",
            "description": "List the section headings of the submission.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_section",
            "description": "Read every paragraph of one section, with paragraph ids.",
            "parameters": {
                "type": "object",
                "properties": {"heading": {"type": "string", "description": "Exact heading from outline"}},
                "required": ["heading"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cite",
            "description": "Record one piece of evidence: an exact quote from one paragraph.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paragraph_id": {"type": "string"},
                    "quote": {"type": "string", "description": "Verbatim text from that paragraph"},
                    "aspect": {"type": "string", "enum": ["baseline", "metrics", "failure_analysis"]},
                },
                "required": ["paragraph_id", "quote", "aspect"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Call when no more evidence is needed.",
            "parameters": {
                "type": "object",
                "properties": {"notes": {"type": "string"}},
                "required": ["notes"],
            },
        },
    },
]

SYSTEM = (
    "You find evidence in a student submission for one rubric criterion. You cannot see the "
    "submission directly: use the tools. Start with outline, read the relevant sections, cite "
    "exact quotes for each aspect you find, then call finish. Do not answer in prose."
)
TASK = (
    "Criterion: Evaluation, evidence and critical analysis. Aspects: baseline (a comparison "
    "against a baseline), metrics (quantitative results), failure_analysis (failure cases or "
    "limitations). Find evidence for each aspect."
)


def run_tool(name: str, args: dict) -> str:
    if name == "outline":
        return json.dumps(list(DOCUMENT))
    if name == "read_section":
        return DOCUMENT.get(args.get("heading", ""), "No such section. Use a heading from outline.")
    if name == "cite":
        text = "\n".join(DOCUMENT.values())
        ok = args.get("quote", "") and args["quote"] in text
        return "valid" if ok else "invalid: that quote is not in the submission"
    if name == "finish":
        return "done"
    return "unknown tool"


def main() -> None:
    with SessionLocal() as session:
        load_ai_settings(session, settings)
    if settings.llm in {"fake", "university"} and not settings.ai_base_url:
        sys.exit(f"Provider is '{settings.llm}' with no base URL; pick MiniMax in the account menu first.")
    if not settings.ai_base_url or not settings.ai_api_key:
        sys.exit("No base URL or API key saved; set them in the account menu (AI model) first.")
    base = settings.ai_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.ai_api_key}", "Content-Type": "application/json"}
    print(f"Provider: {settings.llm} · model: {settings.ai_model} · base: {base}\n")

    log: list[dict] = []
    variants = [("with reasoning_effort=low (as the app sends to MiniMax)", {"reasoning_effort": "low"}),
                ("without reasoning_effort", {})]
    summary = []
    for label, extra in variants:
        print(f"== Run {label}")
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": TASK}]
        calls: list[str] = []
        cites: list[tuple[str, str]] = []
        problems: list[str] = []
        parallel = False
        finished = False
        for step in range(1, 11):
            payload = {"model": settings.ai_model, "messages": messages, "tools": TOOLS,
                       "tool_choice": "auto", "temperature": 0, "max_tokens": 2000, **extra}
            started = time.perf_counter()
            try:
                response = httpx.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=120)
            except httpx.HTTPError as exc:
                problems.append(f"step {step}: request failed: {exc}")
                break
            elapsed = int((time.perf_counter() - started) * 1000)
            body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"text": response.text[:500]}
            log.append({"run": label, "step": step, "status": response.status_code, "ms": elapsed, "response": body})
            if response.status_code >= 400:
                problems.append(f"step {step}: HTTP {response.status_code}: {json.dumps(body)[:300]}")
                break
            choice = body["choices"][0]
            message = choice.get("message", {})
            tool_calls = message.get("tool_calls") or []
            print(f"  step {step}: {elapsed} ms · finish_reason={choice.get('finish_reason')} · tool calls: "
                  + (", ".join(call['function']['name'] for call in tool_calls) or "none"))
            if not tool_calls:
                text = (message.get("content") or "")[:200]
                problems.append(f"step {step}: answered in text instead of calling a tool: {text!r}")
                break
            parallel = parallel or len(tool_calls) > 1
            messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
            for call in tool_calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    problems.append(f"step {step}: {name} arguments are not valid JSON")
                    args = {}
                calls.append(name)
                result = run_tool(name, args)
                if name == "cite":
                    cites.append((args.get("aspect", "?"), result))
                messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": result})
                if name == "finish":
                    finished = True
            if finished:
                break
        valid = sum(1 for _, result in cites if result == "valid")
        aspects = sorted({aspect for aspect, result in cites if result == "valid"})
        summary.append({
            "run": label,
            "tool_calling": bool(calls),
            "multi_turn": len(set(calls)) > 1,
            "parallel_calls": parallel,
            "finished": finished,
            "tool_sequence": calls,
            "valid_citations": valid,
            "invalid_citations": len(cites) - valid,
            "aspects_found": aspects,
            "problems": problems,
        })
        print()

    out = ROOT / "data/cache/tool_check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"model": settings.ai_model, "base_url": base, "summary": summary, "log": log},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print("== Summary")
    for item in summary:
        verdict = "SUPPORTED" if item["tool_calling"] and item["multi_turn"] and not item["problems"] else "CHECK"
        print(f"  [{verdict}] {item['run']}")
        print(f"     tools used in order: {' → '.join(item['tool_sequence']) or '—'}")
        print(f"     citations valid/invalid: {item['valid_citations']}/{item['invalid_citations']} · aspects: {', '.join(item['aspects_found']) or '—'}"
              f" · parallel calls: {item['parallel_calls']} · finished: {item['finished']}")
        for problem in item["problems"]:
            print(f"     ! {problem}")
    print(f"\nRaw responses (no key) saved to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
