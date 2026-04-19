"""Thin Bedrock Converse wrapper for Task 1 (direct-invoke enrichment loop).

Not used by Task 2 — that path goes through Strands Agents. Lambda-ready:
boto3 is in the runtime, credentials come from the function's IAM role,
no env config required.

Behavior:
- Calls bedrock-runtime.converse() with the given model + prompt
- Extracts ONLY text blocks from the response (skips reasoningContent)
- Strips ```json ... ``` fences if present
- Validates against the Pydantic schema; retries up to `retries` times
  on JSON parse error or ValidationError
- For gpt-oss models, sets reasoning_effort="low" to cap thinking tokens
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Generic, Type, TypeVar

import boto3
from botocore.exceptions import ClientError
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

DEFAULT_REGION = "us-east-1"
DEFAULT_MAX_TOKENS = 2000
DEFAULT_TEMPERATURE = 0.0

T = TypeVar("T", bound=BaseModel)


@dataclass
class InvokeResult(Generic[T]):
    value: T
    input_tokens: int
    output_tokens: int
    model_id: str


_clients: dict[str, Any] = {}


def _get_client(region: str):
    if region not in _clients:
        _clients[region] = boto3.client("bedrock-runtime", region_name=region)
    return _clients[region]


def _extract_text(response: dict) -> str:
    blocks = response["output"]["message"]["content"]
    return "".join(b["text"] for b in blocks if "text" in b).strip()


def _strip_json_fences(text: str) -> str:
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = [line for line in t.splitlines() if not line.strip().startswith("```")]
    return "\n".join(lines).strip()


def invoke(
    *,
    prompt: str,
    schema: Type[T],
    model_id: str,
    system: str | None = None,
    region: str = DEFAULT_REGION,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    retries: int = 2,
) -> InvokeResult[T]:
    client = _get_client(region)

    kwargs: dict[str, Any] = {
        "modelId": model_id,
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    if system:
        kwargs["system"] = [{"text": system}]
    if "gpt-oss" in model_id:
        kwargs["additionalModelRequestFields"] = {"reasoning_effort": "low"}

    last_error: Exception | None = None
    last_text: str = ""

    for attempt in range(retries + 1):
        try:
            response = client.converse(**kwargs)
        except ClientError as e:
            err = e.response.get("Error", {})
            code = err.get("Code", "Unknown")
            if code == "AccessDeniedException":
                raise RuntimeError(
                    f"Bedrock model access not enabled for {model_id} in {region}. "
                    "Enable it in AWS Console → Bedrock → Model access."
                ) from e
            raise

        usage = response.get("usage", {})
        in_t = int(usage.get("inputTokens", 0))
        out_t = int(usage.get("outputTokens", 0))
        last_text = _extract_text(response)
        cleaned = _strip_json_fences(last_text)

        try:
            data = json.loads(cleaned)
            value = schema.model_validate(data)
            return InvokeResult(value=value, input_tokens=in_t, output_tokens=out_t, model_id=model_id)
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e
            logger.warning(
                "attempt %d/%d failed for %s: %s | text=%r",
                attempt + 1, retries + 1, model_id, e, cleaned[:200],
            )

    raise RuntimeError(
        f"{model_id} failed after {retries + 1} attempts. "
        f"Last error: {last_error}. Last text: {last_text[:300]!r}"
    )
