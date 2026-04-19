"""Pydantic schemas shared by Task 1 (enrichment) and Task 2 (agent tools)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Sentiment = Literal["positive", "negative", "neutral"]
Tier = Literal["low", "medium", "high"]


class EnrichedAttributes(BaseModel):
    """Five LLM-generated attributes, one JSON object per movie."""

    overview_sentiment: Sentiment
    budget_tier: Tier
    revenue_tier: Tier
    production_effectiveness_score: int = Field(
        ge=1, le=10,
        description="1 = poor ROI/quality relative to genre norms, 10 = exceptional",
    )
    themes: list[str] = Field(
        min_length=3, max_length=5,
        description="3–5 specific thematic keywords; avoid genre labels",
    )
