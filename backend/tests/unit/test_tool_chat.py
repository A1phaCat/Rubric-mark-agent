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
