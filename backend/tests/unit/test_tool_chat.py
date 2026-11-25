"""Tool-calling conversations in the OpenAI-compatible client."""

import asyncio
import json

import httpx
import pytest

from app.llm.openai_compatible import OpenAICompatibleLLM
from app.llm.protocol import ChatResponse, RetryableProviderError, ToolSpec
from app.llm.providers.minimax import MiniMaxLLM
from app.llm.ratelimit import ProviderGate

TOOLS = [ToolSpec("cite", "Record evidence", {"type": "object", "properties": {"quote": {"type": "string"}}})]


def _reply(message: dict, finish: str = "tool_calls", usage: dict | None = None) -> httpx.Response:
    return httpx.Response(200, json={"model": "m", "choices": [{"finish_reason": finish, "message": message}],
                                     "usage": usage or {}})


def _client(handler, cls=OpenAICompatibleLLM) -> OpenAICompatibleLLM:
    return cls("https://provider.test/v1", "key", "m", transport=httpx.MockTransport(handler),
               gate=ProviderGate(4), max_backoff_seconds=1)


def _chat(llm, messages=None):
    return asyncio.run(llm.chat(purpose="evidence_check", messages=messages or [{"role": "user", "content": "x"}],
                                tools=TOOLS))


def test_tool_calls_are_parsed_with_their_raw_arguments() -> None:
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return _reply({"content": "Citing two quotes.", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "cite", "arguments": '{"quote": "a"}'}},
            {"id": "c2", "type": "function", "function": {"name": "cite", "arguments": "{not json"}},
        ]}, usage={"prompt_tokens": 900, "completion_tokens": 40, "prompt_tokens_details": {"cached_tokens": 800}})

    response = _chat(_client(handler))
    assert [(call.id, call.name, call.arguments) for call in response.tool_calls] == [
        ("c1", "cite", {"quote": "a"}), ("c2", "cite", None)]
    assert response.tool_calls[1].raw_arguments == "{not json"
    assert (response.text, response.input_tokens, response.cached_tokens) == ("Citing two quotes.", 900, 800)
    assert sent[0]["tools"][0]["function"]["name"] == "cite" and sent[0]["tool_choice"] == "auto"


def test_the_assistant_turn_is_echoed_back_unchanged() -> None:
    def handler(request):
        return _reply({"content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "cite", "arguments": '{"quote":"a"}'}}]})

    message = _chat(_client(handler)).as_message()
    assert message == {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "cite", "arguments": '{"quote":"a"}'}}]}


def test_a_text_only_answer_is_a_valid_turn() -> None:
    response = _chat(_client(lambda request: _reply({"content": "Nothing to cite."}, finish="stop")))
    assert response.tool_calls == () and response.text == "Nothing to cite."


def test_rate_limits_are_retried_for_tool_chats_too() -> None:
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, text="slow down")
        return _reply({"content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "cite", "arguments": "{}"}}]})

    llm = _client(handler)
    assert _chat(llm).tool_calls[0].name == "cite"
    assert llm.retries == 1


def test_an_empty_turn_is_retried_then_reported() -> None:
    llm = _client(lambda request: _reply({"content": ""}, finish="stop"))
    llm.max_retries = 1
    with pytest.raises(RetryableProviderError, match="no text content"):
        _chat(llm)


def test_minimax_keeps_low_reasoning_effort_for_tool_chats() -> None:
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return _reply({"content": "ok"}, finish="stop")

    _chat(_client(handler, MiniMaxLLM))
    assert sent[0]["reasoning_effort"] == "low"


def test_chat_response_has_no_tool_calls_message_without_them() -> None:
    assert ChatResponse(text="hi", tool_calls=(), model="m").as_message() == {"role": "assistant", "content": "hi"}


def test_parameters_a_reasoning_model_rejects_are_learned_and_dropped() -> None:
    from app.llm import openai_compatible

    openai_compatible._LEARNED.clear()
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        if "max_tokens" in body:
            return httpx.Response(400, json={"error": {
                "message": "Unsupported parameter: 'max_tokens' is not supported with this model. "
                           "Use 'max_completion_tokens' instead.", "code": "unsupported_parameter"}})
        if "temperature" in body:
            return httpx.Response(400, json={"error": {
                "message": "Unsupported value: 'temperature' does not support 0 with this model. "
                           "Only the default (1) value is supported.", "code": "unsupported_value"}})
        return _reply({"content": "{}"}, finish="stop")

    llm = _client(handler)
    assert asyncio.run(llm.complete(purpose="criterion_grade", prompt="x")).text == "{}"
    assert "max_completion_tokens" in sent[-1] and "temperature" not in sent[-1] and len(sent) == 3
    _chat(llm)  # learned once per endpoint and model: the next call goes straight through
    assert len(sent) == 4 and "max_tokens" not in sent[-1]


def test_other_bad_requests_are_not_resent() -> None:
    from app.llm import openai_compatible
    from app.llm.protocol import FatalProviderError

    openai_compatible._LEARNED.clear()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "Invalid model name"}})

    with pytest.raises(FatalProviderError):
        asyncio.run(_client(handler).complete(purpose="criterion_grade", prompt="x"))
    assert len(calls) == 1


def test_tool_chats_turn_reasoning_off_when_the_model_requires_it() -> None:
    from app.llm import openai_compatible

    openai_compatible._LEARNED.clear()
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        if body.get("tools") and body.get("reasoning_effort") != "none":
            return httpx.Response(400, json={"error": {
                "message": "Function tools with reasoning_effort are not supported for gpt-6-astra in "
                           "/v1/chat/completions. To use function tools, use /v1/responses or set "
                           "reasoning_effort to 'none'.", "param": "reasoning_effort"}})
        return _reply({"content": "{}"}, finish="stop")

    llm = _client(handler)
    _chat(llm)
    assert len(sent) == 2 and sent[-1]["reasoning_effort"] == "none"
    asyncio.run(llm.complete(purpose="criterion_grade", prompt="x"))
    assert "reasoning_effort" not in sent[-1]  # grading without tools keeps the model's own reasoning


def _tool_rules(sent: list, supported: list[str], tools_ok: set[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        effort = body.get("reasoning_effort")
        if effort is not None and effort not in supported:
            listed = ", ".join(f"'{value}'" for value in supported)
            return httpx.Response(400, json={"error": {
                "message": f"Unsupported value: 'reasoning_effort' does not support '{effort}' with this model. "
                           f"Supported values are: {listed}.", "param": "reasoning_effort"}})
        if body.get("tools") and effort not in tools_ok:
            return httpx.Response(400, json={"error": {
                "message": "Function tools with reasoning_effort are not supported for this model in "
                           "/v1/chat/completions. Use /v1/responses or set reasoning_effort to 'none'.",
                "param": "reasoning_effort"}})
        return _reply({"content": "{}"}, finish="stop")

    return handler


def test_without_none_the_lowest_supported_reasoning_is_tried() -> None:
    from app.llm import openai_compatible

    openai_compatible._LEARNED.clear()
    sent: list = []
    _chat(_client(_tool_rules(sent, ["minimal", "low", "medium", "high"], {"minimal"})))
    assert [body.get("reasoning_effort") for body in sent] == [None, "none", "minimal"]


def test_a_model_that_never_allows_tools_is_reported_once_and_not_retried() -> None:
    from app.llm import openai_compatible
    from app.llm.protocol import FatalProviderError

    openai_compatible._LEARNED.clear()
    sent: list = []
    llm = _client(_tool_rules(sent, ["low", "medium", "high", "xhigh"], set()))
    with pytest.raises(FatalProviderError, match="does not accept function tools"):
        _chat(llm)
    assert [body.get("reasoning_effort") for body in sent] == [None, "none", "low"]
    with pytest.raises(FatalProviderError):
        _chat(llm)
    assert len(sent) == 3  # known now: no request is sent
