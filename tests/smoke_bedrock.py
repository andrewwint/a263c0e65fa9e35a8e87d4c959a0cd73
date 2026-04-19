"""Bedrock + Strands smoke test.

Not a pytest test (no `test_` prefix on purpose — this hits real AWS and
would break CI). Run manually after `aws configure` to confirm:

    1. Both models answer via raw boto3 Converse (gpt-oss-20b for Task 1,
       Claude Haiku 4.5 for Task 2 + Task 1 fallback).
    2. Strands Agent + BedrockModel wires up correctly against Claude Haiku 4.5.

Usage:
    python tests/smoke_bedrock.py

Exits 0 on full pass, 1 on any failure.
"""

from __future__ import annotations

import sys

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
ENRICH_MODEL = "openai.gpt-oss-20b-1:0"
AGENT_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
PROMPT = "Reply with exactly: OK"


def heading(title: str) -> None:
    print(f"\n{'─' * 60}\n{title}\n{'─' * 60}")


def converse_test(model_id: str, client) -> bool:
    print(f"  → {model_id}")
    try:
        response = client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": PROMPT}]}],
            # 500 gives reasoning models (gpt-oss) headroom to think AND reply.
            inferenceConfig={"maxTokens": 500, "temperature": 0.0},
        )
        # Models with reasoning (gpt-oss) emit a reasoningContent block
        # before the text block — iterate to find the answer.
        blocks = response["output"]["message"]["content"]
        text = next((b["text"] for b in blocks if "text" in b), "").strip()
        has_reasoning = any("reasoningContent" in b for b in blocks)
        usage = response.get("usage", {})
        if not text:
            print("    FAIL empty text block")
            print("    hint: maxTokens may have been consumed by reasoning,")
            print("          or content blocks have an unexpected shape")
            return False
        reasoning_tag = " (+reasoning)" if has_reasoning else ""
        print(f"    response: {text!r}{reasoning_tag}")
        print(
            f"    tokens:   in={usage.get('inputTokens')} "
            f"out={usage.get('outputTokens')}"
        )
        return True
    except ClientError as e:
        err = e.response.get("Error", {})
        code, msg = err.get("Code", "Unknown"), err.get("Message", str(e))
        print(f"    FAIL {code}: {msg}")
        if code == "AccessDeniedException":
            print(f"    hint: request access in Bedrock console (region {REGION})")
        elif code == "ValidationException":
            print("    hint: model id may need an inference-profile prefix (us./global.)")
        return False
    except Exception as e:
        print(f"    FAIL {type(e).__name__}: {e}")
        return False


def strands_test() -> bool:
    print(f"  → Strands Agent + BedrockModel({AGENT_MODEL})")
    try:
        from strands import Agent
        from strands.models import BedrockModel

        model = BedrockModel(
            model_id=AGENT_MODEL,
            region_name=REGION,
            temperature=0,
            max_tokens=50,
        )
        agent = Agent(model=model, system_prompt="Reply with exactly: OK")
        response = agent("Hello")
        text = str(response).strip()
        preview = text[:120] + ("…" if len(text) > 120 else "")
        print(f"    response: {preview!r}")
        return True
    except Exception as e:
        print(f"    FAIL {type(e).__name__}: {e}")
        return False


def main() -> None:
    print(f"Bedrock smoke test — region={REGION}")

    heading("1. Raw boto3 Converse")
    client = boto3.client("bedrock-runtime", region_name=REGION)
    raw = [converse_test(m, client) for m in (ENRICH_MODEL, AGENT_MODEL)]

    heading("2. Strands wiring")
    strands = strands_test()

    heading("Summary")
    rows = [
        ("boto3 gpt-oss-20b      ", raw[0]),
        ("boto3 Haiku 4.5        ", raw[1]),
        ("Strands + Haiku 4.5    ", strands),
    ]
    for label, ok in rows:
        print(f"  {label}  {'PASS' if ok else 'FAIL'}")
    print()
    if all(r for _, r in rows):
        print("All checks passed. Ready to build.")
        sys.exit(0)
    else:
        print("One or more checks failed. See errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
