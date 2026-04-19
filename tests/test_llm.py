"""Unit tests for src/llm.py. No AWS calls — client is mocked."""

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from src import llm


class Example(BaseModel):
    x: int
    y: str


def _response(text: str, in_t: int = 10, out_t: int = 5, extra_blocks: list | None = None) -> dict:
    blocks = list(extra_blocks or []) + [{"text": text}]
    return {
        "output": {"message": {"content": blocks}},
        "usage": {"inputTokens": in_t, "outputTokens": out_t},
    }


def _mock_client(monkeypatch, **kwargs) -> MagicMock:
    client = MagicMock(**kwargs)
    monkeypatch.setattr(llm, "_get_client", lambda region: client)
    return client


def test_invoke_parses_and_validates(monkeypatch):
    client = _mock_client(monkeypatch, converse=MagicMock(return_value=_response('{"x": 1, "y": "ok"}')))
    result = llm.invoke(prompt="hi", schema=Example, model_id="anthropic.claude-haiku-4-5")
    assert result.value == Example(x=1, y="ok")
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    client.converse.assert_called_once()


def test_invoke_retries_on_bad_json(monkeypatch):
    client = _mock_client(monkeypatch)
    client.converse.side_effect = [
        _response("not json"),
        _response('{"x": 2, "y": "retry"}'),
    ]
    result = llm.invoke(prompt="hi", schema=Example, model_id="anthropic.claude-haiku-4-5", retries=2)
    assert result.value.x == 2
    assert client.converse.call_count == 2


def test_invoke_strips_markdown_fences(monkeypatch):
    _mock_client(monkeypatch, converse=MagicMock(return_value=_response('```json\n{"x": 3, "y": "fenced"}\n```')))
    result = llm.invoke(prompt="hi", schema=Example, model_id="anthropic.claude-haiku-4-5")
    assert result.value.x == 3


def test_invoke_skips_reasoning_content(monkeypatch):
    reasoning = {"reasoningContent": {"reasoningText": {"text": "let me think..."}}}
    _mock_client(
        monkeypatch,
        converse=MagicMock(return_value=_response('{"x": 4, "y": "after"}', extra_blocks=[reasoning])),
    )
    result = llm.invoke(prompt="hi", schema=Example, model_id="openai.gpt-oss-20b-1:0")
    assert result.value.x == 4


def test_invoke_sets_reasoning_effort_for_gpt_oss(monkeypatch):
    client = _mock_client(monkeypatch, converse=MagicMock(return_value=_response('{"x": 5, "y": "eff"}')))
    llm.invoke(prompt="hi", schema=Example, model_id="openai.gpt-oss-20b-1:0")
    call = client.converse.call_args
    assert call.kwargs["additionalModelRequestFields"] == {"reasoning_effort": "low"}


def test_invoke_omits_reasoning_effort_for_claude(monkeypatch):
    client = _mock_client(monkeypatch, converse=MagicMock(return_value=_response('{"x": 6, "y": "no"}')))
    llm.invoke(prompt="hi", schema=Example, model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0")
    assert "additionalModelRequestFields" not in client.converse.call_args.kwargs


def test_invoke_raises_after_retries(monkeypatch):
    _mock_client(monkeypatch, converse=MagicMock(return_value=_response("not json ever")))
    with pytest.raises(RuntimeError, match="failed after"):
        llm.invoke(prompt="hi", schema=Example, model_id="anthropic.claude-haiku-4-5", retries=2)


def test_invoke_retries_on_schema_violation(monkeypatch):
    client = _mock_client(monkeypatch)
    client.converse.side_effect = [
        _response('{"x": "not an int", "y": "bad"}'),
        _response('{"x": 7, "y": "good"}'),
    ]
    result = llm.invoke(prompt="hi", schema=Example, model_id="anthropic.claude-haiku-4-5", retries=2)
    assert result.value.x == 7
