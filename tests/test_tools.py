"""Tests for src/tools.py.

Uses the real movies.db + ratings.db for DB-backed tools (they are
read-only inputs). LLM calls are mocked. The most important test in
this file is `test_predict_user_rating_no_ground_truth_leak` — per
AGENTS.md Evaluation hygiene, this is the leak-adjacent case that
catches the bug we found during Phase 3 eval.
"""

import json
from unittest.mock import MagicMock

import pytest

from src import db, llm
from src.tools import (
    compare_movies,
    get_enriched_movie,
    predict_user_rating,
    query_movies,
)

pytestmark = pytest.mark.skipif(
    not db.MOVIES_DB.exists() or not db.RATINGS_DB.exists(),
    reason="db files not present in db/ (copy source .db files per README)",
)


# ─── query_movies ─────────────────────────────────────────────────────────

def test_query_movies_returns_titles():
    """Regression guard — title must flow through the movies/enriched merge."""
    result = json.loads(query_movies(filter_json='{"limit": 3}'))
    assert len(result) == 3
    for row in result:
        assert isinstance(row.get("title"), str) and row["title"]
        assert isinstance(row.get("movieId"), int)


def test_query_movies_genre_case_insensitive():
    upper = json.loads(query_movies(filter_json='{"genres": ["Drama"], "limit": 5}'))
    lower = json.loads(query_movies(filter_json='{"genres": ["drama"], "limit": 5}'))
    assert {r["movieId"] for r in upper} == {r["movieId"] for r in lower}


def test_query_movies_year_range():
    r = json.loads(query_movies(filter_json='{"min_year": 1990, "max_year": 1999, "limit": 20}'))
    assert len(r) > 0
    for row in r:
        assert 1990 <= row["release_year"] <= 1999


def test_query_movies_rejects_invalid_tier():
    """LLM can't inject arbitrary SQL — QueryFilter rejects unknown tier values."""
    with pytest.raises(Exception):
        query_movies(filter_json='{"budget_tier": "DROP TABLE movies"}')


def test_query_movies_rejects_malformed_json():
    with pytest.raises(Exception):
        query_movies(filter_json="{not json")


def test_query_movies_genre_with_special_chars_is_safe():
    """Genre containing LIKE wildcards (% or _) can't trigger silent matches.
    The old `LIKE '%"name": "..."%'` path was vulnerable; the pandas path isn't."""
    r = json.loads(query_movies(filter_json='{"genres": ["%"], "limit": 5}'))
    # Literal '%' shouldn't match any real genre — expect 0 hits
    assert r == []


# ─── compare_movies ───────────────────────────────────────────────────────

def test_compare_movies_two_ids():
    r = json.loads(compare_movies(movie_ids_json="[238, 769]"))
    assert len(r["movies"]) == 2


def test_compare_movies_three_ids():
    r = json.loads(compare_movies(movie_ids_json="[238, 769, 550]"))
    assert len(r["movies"]) == 3


def test_compare_movies_rejects_single_id():
    r = json.loads(compare_movies(movie_ids_json="[238]"))
    assert "error" in r


def test_compare_movies_notes_missing_ids():
    r = json.loads(compare_movies(movie_ids_json="[238, 999999999]"))
    assert len(r["movies"]) == 1
    assert r.get("note") and "999999999" in r["note"]


# ─── get_enriched_movie ───────────────────────────────────────────────────

def test_get_enriched_movie_returns_error_for_unenriched():
    r = json.loads(get_enriched_movie(movie_id=999999999))
    assert "error" in r


# ─── predict_user_rating ──────────────────────────────────────────────────

def test_predict_user_rating_insufficient_history():
    """Non-existent user → 0 history → structured insufficient_history error."""
    r = json.loads(predict_user_rating(user_id=999999999, movie_id=238))
    assert r.get("error") == "insufficient_history"


def test_predict_user_rating_no_ground_truth_leak(monkeypatch):
    """CRITICAL (per AGENTS.md Evaluation hygiene):

    If a user has already rated the target movie, that rating must NOT
    appear in the user-history portion of the LLM prompt — otherwise the
    LLM can echo the ground truth and inflate measured accuracy.
    """
    captured = []

    fake_value = MagicMock()
    fake_value.predicted_rating = 3.0
    fake_value.rationale = "mock"

    fake_result = MagicMock()
    fake_result.value = fake_value
    fake_result.input_tokens = 10
    fake_result.output_tokens = 5

    def fake_invoke(**kwargs):
        captured.append(kwargs["prompt"])
        return fake_result

    monkeypatch.setattr(llm, "invoke", fake_invoke)

    # Pick a (user, movie) pair that exists in ratings.db, where:
    # - user has ≥20 other ratings (so the tool doesn't hit the insufficient-history guard)
    # - the movie's title is UNIQUE in the catalog (so a title-based leak assertion
    #   can't fire on an unrelated same-titled movie being legitimately in history)
    with db.connect() as conn:
        pair = conn.execute("""
            SELECT r1.userId, r1.movieId, m.title
            FROM r.ratings r1 JOIN movies m USING (movieId)
            WHERE r1.userId IN (
                SELECT userId FROM r.ratings GROUP BY userId HAVING COUNT(*) >= 20
            )
            AND m.title IN (
                SELECT title FROM movies GROUP BY title HAVING COUNT(*) = 1
            )
            LIMIT 1
        """).fetchone()
    if pair is None:
        pytest.skip("no eligible (user, unique-titled movie) pair in DB")
    user_id, movie_id, target_title = int(pair["userId"]), int(pair["movieId"]), pair["title"]

    predict_user_rating(user_id=user_id, movie_id=movie_id)
    assert len(captured) == 1
    prompt = captured[0]

    history_section = prompt.split("Target movie")[0]
    # Title is unique in the catalog by construction above, so if it appears in
    # the history section, it's the target — and we've leaked ground truth.
    assert target_title not in history_section, (
        f"LEAK: target movie title {target_title!r} appeared in the user-history "
        "portion of the prompt. predict_user_rating must exclude the target from "
        "the user's history."
    )
