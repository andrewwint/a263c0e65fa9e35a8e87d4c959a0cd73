"""Pydantic schemas shared by Task 1 (enrichment) and Task 2 (agent tools)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Sentiment = Literal["positive", "negative", "neutral"]
Tier = Literal["low", "medium", "high"]
SortBy = Literal["revenue_desc", "budget_desc", "score_desc", "runtime_desc", "rating_desc"]


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


# ─── Task 2: agent tool schemas ────────────────────────────────────────────

class QueryFilter(BaseModel):
    """Validated filter for query_movies — maps to ? bindings, no raw SQL."""

    genres: list[str] = Field(default_factory=list, description="e.g. ['Action', 'Drama']; OR-matched")
    budget_tier: Tier | None = None
    revenue_tier: Tier | None = None
    sentiment: Sentiment | None = None
    min_score: int | None = Field(default=None, ge=1, le=10)
    min_year: int | None = None
    max_year: int | None = None
    min_budget: int | None = None
    max_budget: int | None = None
    min_runtime: int | None = None
    max_runtime: int | None = None
    sort_by: SortBy | None = None
    limit: int = Field(default=10, ge=1, le=50)


class ComparisonRow(BaseModel):
    movieId: int
    title: str
    release_year: int | None = None
    budget: int | None = None
    revenue: int | None = None
    runtime: int | None = None
    overview_sentiment: Sentiment | None = None
    budget_tier: Tier | None = None
    revenue_tier: Tier | None = None
    production_effectiveness_score: int | None = None
    themes: list[str] = Field(default_factory=list)


class ComparisonTable(BaseModel):
    movies: list[ComparisonRow]
    note: str | None = None


class _RatingPredictionLLM(BaseModel):
    """Internal — what the LLM returns. Tool wraps into RatingPrediction."""
    predicted_rating: float = Field(ge=0.5, le=5.0)
    rationale: str


class RatingPrediction(BaseModel):
    user_id: int
    movie_id: int
    predicted_rating: float
    rationale: str
    based_on_n_user_ratings: int


class _UserPreferenceSummaryLLM(BaseModel):
    """Internal — what the LLM returns. Tool wraps into UserPreferenceSummary."""
    favorite_genres: list[str] = Field(max_length=5)
    favorite_themes: list[str] = Field(max_length=5)
    typical_sentiment: str
    summary: str


class UserPreferenceSummary(BaseModel):
    user_id: int
    n_ratings: int
    mean_rating: float
    favorite_genres: list[str]
    favorite_themes: list[str]
    typical_sentiment: str
    summary: str
