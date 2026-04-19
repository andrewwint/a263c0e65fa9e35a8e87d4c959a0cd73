"""Task 2 Strands agent — one agent, five tools.

Build via `build_agent()` rather than a module-level instance so imports
don't trigger Bedrock calls during tests.
"""

from __future__ import annotations

from strands import Agent
from strands.models import BedrockModel

from src.prompts.agent_system import SYSTEM
from src.tools import (
    compare_movies,
    get_enriched_movie,
    predict_user_rating,
    query_movies,
    summarize_user_preferences,
)

AGENT_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
REGION = "us-east-1"


def build_agent(temperature: float = 0.0, max_tokens: int = 4000) -> Agent:
    return Agent(
        model=BedrockModel(
            model_id=AGENT_MODEL,
            region_name=REGION,
            temperature=temperature,
            max_tokens=max_tokens,
        ),
        tools=[
            query_movies,
            get_enriched_movie,
            compare_movies,
            predict_user_rating,
            summarize_user_preferences,
        ],
        system_prompt=SYSTEM,
    )
