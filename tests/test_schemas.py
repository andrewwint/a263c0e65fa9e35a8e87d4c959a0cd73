"""Pydantic schema round-trip + validation tests."""

import pytest
from pydantic import ValidationError

from src.schemas import (
    ComparisonRow,
    ComparisonTable,
    EnrichedAttributes,
    QueryFilter,
    RatingPrediction,
    UserPreferenceSummary,
)


def _valid_enriched():
    return EnrichedAttributes(
        overview_sentiment="positive",
        budget_tier="medium",
        revenue_tier="high",
        production_effectiveness_score=8,
        themes=["redemption", "heist", "loyalty"],
    )


def test_enriched_attributes_roundtrip():
    orig = _valid_enriched()
    assert EnrichedAttributes.model_validate_json(orig.model_dump_json()) == orig


def test_enriched_attributes_rejects_score_out_of_range():
    with pytest.raises(ValidationError):
        EnrichedAttributes(
            overview_sentiment="positive", budget_tier="low", revenue_tier="low",
            production_effectiveness_score=11, themes=["a", "b", "c"],
        )


@pytest.mark.parametrize("themes", [["only", "two"], ["a", "b", "c", "d", "e", "f"]])
def test_enriched_attributes_rejects_bad_theme_count(themes):
    with pytest.raises(ValidationError):
        EnrichedAttributes(
            overview_sentiment="positive", budget_tier="low", revenue_tier="low",
            production_effectiveness_score=5, themes=themes,
        )


def test_enriched_attributes_rejects_invalid_sentiment():
    with pytest.raises(ValidationError):
        EnrichedAttributes(
            overview_sentiment="mixed",  # not in Literal
            budget_tier="low", revenue_tier="low",
            production_effectiveness_score=5, themes=["a", "b", "c"],
        )


def test_query_filter_defaults():
    qf = QueryFilter()
    assert qf.genres == []
    assert qf.budget_tier is None
    assert qf.limit == 10


def test_query_filter_roundtrip():
    qf = QueryFilter(
        genres=["Drama"], budget_tier="low", sentiment="positive",
        min_year=1990, max_year=1999, min_score=8, limit=5,
        sort_by="revenue_desc",
    )
    assert QueryFilter.model_validate_json(qf.model_dump_json()) == qf


@pytest.mark.parametrize("kwargs", [
    {"budget_tier": "huge"},        # invalid tier
    {"sentiment": "DROP TABLE"},    # no SQL injection surface — Pydantic rejects the string
    {"limit": 999},                 # out of range
    {"limit": 0},                   # out of range
    {"sort_by": "arbitrary_sql"},   # invalid Literal
    {"min_score": 0},               # below 1
    {"min_score": 11},              # above 10
])
def test_query_filter_rejects_invalid(kwargs):
    with pytest.raises(ValidationError):
        QueryFilter(**kwargs)


def test_user_preference_summary_llm_rejects_too_many_items():
    from src.schemas import _UserPreferenceSummaryLLM
    with pytest.raises(ValidationError):
        _UserPreferenceSummaryLLM(
            favorite_genres=["a", "b", "c", "d", "e", "f"],  # 6 > max_length=5
            favorite_themes=["x"], typical_sentiment="positive", summary="...",
        )
    with pytest.raises(ValidationError):
        _UserPreferenceSummaryLLM(
            favorite_genres=["a"],
            favorite_themes=["1", "2", "3", "4", "5", "6"],  # 6 > max_length=5
            typical_sentiment="neutral", summary="...",
        )


def test_comparison_table_roundtrip():
    t = ComparisonTable(
        movies=[
            ComparisonRow(movieId=1, title="A", budget=1000),
            ComparisonRow(movieId=2, title="B", budget=2000, themes=["x", "y"]),
        ],
        note="test note",
    )
    assert ComparisonTable.model_validate_json(t.model_dump_json()) == t


def test_rating_prediction_roundtrip():
    p = RatingPrediction(
        user_id=42, movie_id=550, predicted_rating=3.5,
        rationale="specific", based_on_n_user_ratings=10,
    )
    assert RatingPrediction.model_validate_json(p.model_dump_json()) == p


@pytest.mark.parametrize("rating", [6.0, -1.0, 0.4])
def test_rating_prediction_rejects_out_of_scale(rating):
    # Note: RatingPrediction itself doesn't constrain predicted_rating — the
    # internal _RatingPredictionLLM does (0.5–5.0). This test asserts the
    # LLM-facing schema is the one with the guard.
    from src.schemas import _RatingPredictionLLM
    with pytest.raises(ValidationError):
        _RatingPredictionLLM(predicted_rating=rating, rationale="x")


def test_user_preference_summary_roundtrip():
    s = UserPreferenceSummary(
        user_id=42, n_ratings=100, mean_rating=3.8,
        favorite_genres=["Drama", "Thriller"], favorite_themes=["redemption"],
        typical_sentiment="positive", summary="test",
    )
    assert UserPreferenceSummary.model_validate_json(s.model_dump_json()) == s
