"""Cache hit path — rerunning enrich_all on the same sample makes zero LLM calls."""

from unittest.mock import MagicMock

import pandas as pd

from src import enrich, llm


def test_enrich_all_hits_cache_on_second_run(tmp_path, monkeypatch):
    cache_path = tmp_path / "enriched.parquet"

    cached_df = pd.DataFrame([
        {
            "movieId": 1, "title": "A",
            "overview_sentiment": "positive", "budget_tier": "low",
            "revenue_tier": "low", "production_effectiveness_score": 5,
            "themes": ["a", "b", "c"],
            "input_tokens": 100, "output_tokens": 50,
            "model": "openai.gpt-oss-20b-1:0",
        },
        {
            "movieId": 2, "title": "B",
            "overview_sentiment": "neutral", "budget_tier": "medium",
            "revenue_tier": "medium", "production_effectiveness_score": 6,
            "themes": ["x", "y", "z"],
            "input_tokens": 120, "output_tokens": 60,
            "model": "openai.gpt-oss-20b-1:0",
        },
    ])
    cached_df.to_parquet(cache_path, index=False)

    invoke_spy = MagicMock(side_effect=AssertionError("llm.invoke must not be called on a full cache hit"))
    monkeypatch.setattr(llm, "invoke", invoke_spy)

    movies = pd.DataFrame([
        {"movieId": 1, "title": "A", "overview": "x", "budget": 1_000_000, "revenue": 1_000_000,
         "runtime": 90, "genres": "[]", "releaseDate": "2000-01-01",
         "avg_rating": None, "n_ratings": 0},
        {"movieId": 2, "title": "B", "overview": "y", "budget": 2_000_000, "revenue": 2_000_000,
         "runtime": 95, "genres": "[]", "releaseDate": "2001-01-01",
         "avg_rating": None, "n_ratings": 0},
    ])

    result = enrich.enrich_all(movies, cache_path=cache_path)

    assert len(result) == 2
    assert invoke_spy.call_count == 0
    assert set(result["movieId"]) == {1, 2}


def test_enrich_all_calls_llm_only_for_uncached_rows(tmp_path, monkeypatch):
    cache_path = tmp_path / "enriched.parquet"

    cached_df = pd.DataFrame([{
        "movieId": 1, "title": "A",
        "overview_sentiment": "positive", "budget_tier": "low",
        "revenue_tier": "low", "production_effectiveness_score": 5,
        "themes": ["a", "b", "c"],
        "input_tokens": 100, "output_tokens": 50,
        "model": "openai.gpt-oss-20b-1:0",
    }])
    cached_df.to_parquet(cache_path, index=False)

    fake_result = MagicMock()
    fake_result.value.model_dump.return_value = {
        "overview_sentiment": "neutral", "budget_tier": "medium", "revenue_tier": "medium",
        "production_effectiveness_score": 6, "themes": ["one", "two", "three"],
    }
    fake_result.input_tokens = 200
    fake_result.output_tokens = 80

    invoke_spy = MagicMock(return_value=fake_result)
    monkeypatch.setattr(llm, "invoke", invoke_spy)

    movies = pd.DataFrame([
        {"movieId": 1, "title": "A", "overview": "x", "budget": 1_000_000, "revenue": 1_000_000,
         "runtime": 90, "genres": "[]", "releaseDate": "2000-01-01",
         "avg_rating": None, "n_ratings": 0},
        {"movieId": 2, "title": "B", "overview": "y", "budget": 2_000_000, "revenue": 2_000_000,
         "runtime": 95, "genres": "[]", "releaseDate": "2001-01-01",
         "avg_rating": None, "n_ratings": 0},
    ])

    result = enrich.enrich_all(movies, cache_path=cache_path)
    assert len(result) == 2
    assert invoke_spy.call_count == 1
