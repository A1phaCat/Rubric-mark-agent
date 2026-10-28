"""Token-metering stand-in for a real provider, for cost estimates without an API key.

``MeteredDryRunLLM`` receives exactly the prompts and tool-calling conversations the
marking pipeline would send to the real model, counts their tokens with the model's
tokenizer (tiktoken ``o200k_base``, used by the GPT-4.1/4o/5 families), and answers with
scripted, well-formed replies so the pipeline runs end to end. Nothing leaves the machine.

Provider prompt caching is modelled the way OpenAI documents automatic caching: a request
whose leading tokens repeat an earlier request (for ≥1024 tokens, counted in 128-token
steps) has that prefix billed at the cached-input price. Set ``model_cache=False`` for the
no-cache upper bound.

What the numbers mean:
- input tokens: an estimate of what the provider would bill for these prompts (the real
  count differs by the few tokens of chat-format overhead per message, added below);
- output tokens: the length of the scripted replies, NOT of a real model's answer
  (a real model usually writes longer rationales and may take more tool rounds);
- scores: placeholders. They are not a judgement of the submission.

The reported model name is ``<model>-dryrun`` so the price table prices it as ``<model>``
while every stored record and screen shows that it was a dry run.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any, Mapping, Sequence

from app.llm.fake import FakeLLM
from app.llm.protocol import ChatResponse, LLMResponse, ToolSpec

_PER_MESSAGE_OVERHEAD = 4  # role/separator tokens per chat message (OpenAI chat format)


def _encoder() -> Any:
    import tiktoken

    return tiktoken.get_encoding("o200k_base")


class MeteredDryRunLLM:
    def __init__(self, model: str = "gpt-4.1", model_cache: bool = True) -> None:
        self.model = f"{model}-dryrun"
        self._encoding = _encoder()
        self._fake = FakeLLM()
        self._model_cache = model_cache
        self._recent: list[list[int]] = []
        self.calls: list[dict[str, Any]] = []

    def _cached(self, ids: list[int]) -> int:
        """Tokens of ``ids`` an automatic prefix cache would serve from earlier requests."""

        best = 0
        for previous in self._recent:
            limit = min(len(previous), len(ids))
            n = 0
            while n < limit and previous[n] == ids[n]:
                n += 1
            best = max(best, n)
        self._recent = (self._recent + [ids])[-64:]
        if not self._model_cache or best < 1024:
            return 0
        return best // 128 * 128

    def tokens(self, text: str) -> int:
        return len(self._encoding.encode(text, disallowed_special=()))

    async def list_models(self) -> Sequence[str]:
        return [self.model]

    def _log(self, purpose: str, input_tokens: int, output_tokens: int, metadata: Mapping[str, str] | None) -> None:
        self.calls.append({"purpose": purpose, "input_tokens": input_tokens, "output_tokens": output_tokens,
                           "submission_id": (metadata or {}).get("submission_id")})

    async def chat(
        self,
        *,
        purpose: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[ToolSpec],
        metadata: Mapping[str, str] | None = None,
    ) -> ChatResponse:
        scripted = await self._fake.chat(purpose=purpose, messages=messages, tools=tools, metadata=metadata)
        # tools first, then the conversation: the order the provider serialises them in
        ids = self._encoding.encode(json.dumps([asdict(t) for t in tools]) + json.dumps(list(messages), ensure_ascii=False),
                                    disallowed_special=())
        input_tokens = len(ids) + _PER_MESSAGE_OVERHEAD * len(messages)
        cached = self._cached(ids)
        output_tokens = sum(self.tokens(call.name + call.raw_arguments) for call in scripted.tool_calls)
        self._log(purpose, input_tokens, output_tokens, metadata)
        return ChatResponse(text=scripted.text, tool_calls=scripted.tool_calls, model=self.model,
                            finish_reason=scripted.finish_reason, input_tokens=input_tokens,
                            output_tokens=output_tokens, cached_tokens=cached)

    async def complete(
        self, *, purpose: str, prompt: str, metadata: Mapping[str, str] | None = None
    ) -> LLMResponse:
        if purpose == "criterion_grade":
            reply = _scripted_grade(prompt)
        elif purpose == "b2_whole_report":
            reply = _scripted_whole_report(prompt)
        else:
            reply = json.loads((await self._fake.complete(purpose=purpose, prompt=prompt)).text)
        text = json.dumps(reply, ensure_ascii=False)
        ids = self._encoding.encode(prompt, disallowed_special=())
        input_tokens = len(ids) + _PER_MESSAGE_OVERHEAD
        cached = self._cached(ids)
        output_tokens = self.tokens(text)
        self._log(purpose, input_tokens, output_tokens, metadata)
        return LLMResponse(text=text, model=self.model, input_tokens=input_tokens, output_tokens=output_tokens,
                           cached_tokens=cached)


def _first_json(text: str, start_marker: str) -> Any:
    start = text.find(start_marker)
    if start < 0:
        return None
    brace = min([i for i in (text.find("{", start), text.find("[", start)) if i >= 0], default=-1)
    if brace < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text[brace:])
    except json.JSONDecodeError:
        return None
    return value


def _second_level(levels: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(levels, key=lambda level: float(level.get("points") or 0), reverse=True)
    return ordered[1] if len(ordered) > 1 else (ordered[0] if ordered else {"label": "suggested", "points": 0})


def _scripted_grade(prompt: str) -> dict[str, Any]:
    rubric = _first_json(prompt, "best first):") or {}
    level = _second_level(list(rubric.get("levels") or []))
    return {"score": float(level.get("points") or 0), "level": str(level.get("label") or "suggested"),
            "rationale": "Dry-run placeholder: no model was called, so this is not a judgement.",
            "confidence": "low"}


def _scripted_whole_report(prompt: str) -> dict[str, Any]:
    criteria = _first_json(prompt, "RUBRIC:") or []
    out = []
    for criterion in criteria:
        level = _second_level(list(criterion.get("levels") or []))
        out.append({"criterion_id": criterion.get("id"), "level": level.get("label"),
                    "score": float(level.get("points") or 0),
                    "rationale": "Dry-run placeholder: no model was called."})
    return {"criteria": out}


def is_dry_run_model(name: str | None) -> bool:
    return bool(name and re.search(r"-dryrun$", name))
