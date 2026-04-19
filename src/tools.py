"""Task 2 agent tools. Each @tool returns a JSON string (Strands-friendly).

Contract: the LLM sees the docstring. Keep them precise.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

import pandas as pd
from strands import tool

from src import db, enrich, llm
from src.schemas import (
    ComparisonRow,
    ComparisonTable,
    QueryFilter,
    RatingPrediction,
    UserPreferenceSummary,
    _RatingPredictionLLM,
    _UserPreferenceSummaryLLM,
)

logger = logging.getLogger(__name__)

AGENT_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

# Columns the enriched parquet is expected to carry.
_ENRICHED_COLS = [
    "movieId", "title", "overview_sentiment", "budget_tier", "revenue_tier",
    "production_effectiveness_score", "themes",
]


@lru_cache(maxsize=1)
def _enriched() -> pd.DataFrame:
    return pd.read_parquet(enrich.CACHE_PATH)[_ENRICHED_COLS]


def _year(release_date: str | None) -> int | None:
    if not release_date or len(release_date) < 4:
        return None
    try:
        return int(release_date[:4])
    except ValueError:
        return None


@tool
def query_movies(filter_json: str) -> str:
    """Search the movie catalog with a validated JSON filter.

    filter_json must be a JSON string matching QueryFilter:
      {
        "genres": ["Action", "Drama"],        // optional, OR-matched
        "budget_tier": "low" | "medium" | "high" | null,
        "revenue_tier": "low" | "medium" | "high" | null,
        "sentiment": "positive" | "negative" | "neutral" | null,
        "min_score": 1-10 or null,            // from production_effectiveness_score
        "min_year": int or null,              // releaseDate year >= this
        "max_year": int or null,
        "min_budget": int or null,            // USD
        "max_budget": int or null,
        "min_runtime": int (minutes) or null,
        "max_runtime": int (minutes) or null,
        "sort_by": "revenue_desc" | "budget_desc" | "score_desc" | "runtime_desc" | null,
        "limit": int 1-50, default 10
      }

    Tier/sentiment/score filters require enrichment; the enriched set is 75
    movies, so narrow enrichment-filtered queries may return few results.
    Returns a JSON array of movies; each row includes movieId, title, year,
    budget, revenue, runtime, and enriched attrs when available.
    """
    qf = QueryFilter.model_validate_json(filter_json)

    where: list[str] = ["status = 'Released'"]
    params: list[Any] = []

    # Genre matching happens in pandas via parse_json_names — the `genres`
    # column is TMDB JSON and the previous LIKE pattern was fragile to
    # whitespace and LIKE wildcards embedded in the column value.
    if qf.min_year is not None:
        where.append("CAST(substr(releaseDate, 1, 4) AS INTEGER) >= ?")
        params.append(qf.min_year)
    if qf.max_year is not None:
        where.append("CAST(substr(releaseDate, 1, 4) AS INTEGER) <= ?")
        params.append(qf.max_year)
    if qf.min_budget is not None:
        where.append("budget >= ?")
        params.append(qf.min_budget)
    if qf.max_budget is not None:
        where.append("budget <= ?")
        params.append(qf.max_budget)
    if qf.min_runtime is not None:
        where.append("runtime >= ?")
        params.append(qf.min_runtime)
    if qf.max_runtime is not None:
        where.append("runtime <= ?")
        params.append(qf.max_runtime)

    sql = f"""
        SELECT movieId, title, budget, revenue, runtime, genres, releaseDate
        FROM movies
        WHERE {' AND '.join(where)}
    """
    with db.connect() as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    # Post-SQL filters (all operate on in-memory DataFrame)
    if qf.genres:
        genre_set = {g.lower() for g in qf.genres}
        df["_primary_genres"] = df["genres"].apply(
            lambda raw: {n.lower() for n in enrich.parse_json_names(raw)}
        )
        df = df[df["_primary_genres"].apply(lambda names: bool(genre_set & names))]
        df = df.drop(columns=["_primary_genres"])

    needs_enriched = any(
        v is not None for v in (qf.budget_tier, qf.revenue_tier, qf.sentiment, qf.min_score)
    )
    merged = df.merge(_enriched(), on="movieId", how="inner" if needs_enriched else "left")

    if qf.budget_tier:
        merged = merged[merged["budget_tier"] == qf.budget_tier]
    if qf.revenue_tier:
        merged = merged[merged["revenue_tier"] == qf.revenue_tier]
    if qf.sentiment:
        merged = merged[merged["overview_sentiment"] == qf.sentiment]
    if qf.min_score is not None:
        merged = merged[merged["production_effectiveness_score"] >= qf.min_score]

    sort_map = {
        "revenue_desc": ("revenue", False),
        "budget_desc": ("budget", False),
        "score_desc": ("production_effectiveness_score", False),
        "runtime_desc": ("runtime", False),
        "rating_desc": ("production_effectiveness_score", False),
    }
    if qf.sort_by and qf.sort_by in sort_map:
        col, asc = sort_map[qf.sort_by]
        merged = merged.sort_values(col, ascending=asc, na_position="last")

    merged = merged.head(qf.limit)
    merged["release_year"] = merged["releaseDate"].apply(_year)

    out_cols = [
        "movieId", "title", "release_year", "budget", "revenue", "runtime",
        "overview_sentiment", "budget_tier", "revenue_tier",
        "production_effectiveness_score", "themes",
    ]
    present_cols = [c for c in out_cols if c in merged.columns]
    result = merged[present_cols].where(pd.notna(merged[present_cols]), None)
    return result.to_json(orient="records")


@tool
def get_enriched_movie(movie_id: int) -> str:
    """Return enriched attributes for a single movie by movieId.

    Only works for the 75-movie enriched sample. Returns {"error": ...} JSON
    if the movie isn't in the sample.
    """
    enr = _enriched()
    row = enr[enr["movieId"] == movie_id]
    if row.empty:
        return json.dumps({
            "error": f"movieId {movie_id} not in the enriched 75-movie sample",
            "movie_id": movie_id,
        })
    rec = row.iloc[0].to_dict()
    rec["themes"] = list(rec["themes"])
    return json.dumps(rec, default=str)


@tool
def compare_movies(movie_ids_json: str) -> str:
    """Side-by-side comparison of 2 or more movies.

    movie_ids_json: JSON array of movieId integers, e.g. "[238, 769]".
    Returns a JSON ComparisonTable with budget/revenue/runtime/tiers/
    sentiment/themes/effectiveness per movie. Enriched fields are null
    for movies outside the 75-movie enriched sample.
    """
    movie_ids: list[int] = json.loads(movie_ids_json)
    if not isinstance(movie_ids, list) or len(movie_ids) < 2:
        return json.dumps({"error": "need at least 2 movieIds"})

    placeholders = ",".join("?" for _ in movie_ids)
    with db.connect() as conn:
        df = pd.read_sql_query(
            f"""
            SELECT movieId, title, budget, revenue, runtime, releaseDate
            FROM movies
            WHERE movieId IN ({placeholders})
            """,
            conn,
            params=movie_ids,
        )

    enr = _enriched().set_index("movieId")
    rows: list[ComparisonRow] = []
    missing: list[int] = []

    for mid in movie_ids:
        m = df[df["movieId"] == mid]
        if m.empty:
            missing.append(mid)
            continue
        base = m.iloc[0]
        themes: list[str] = []
        sentiment = tier_b = tier_r = score = None
        if mid in enr.index:
            e = enr.loc[mid]
            themes = list(e["themes"])
            sentiment = e["overview_sentiment"]
            tier_b = e["budget_tier"]
            tier_r = e["revenue_tier"]
            score = int(e["production_effectiveness_score"])

        rows.append(ComparisonRow(
            movieId=int(base["movieId"]),
            title=str(base["title"]),
            release_year=_year(base.get("releaseDate")),
            budget=int(base["budget"]) if pd.notna(base["budget"]) else None,
            revenue=int(base["revenue"]) if pd.notna(base["revenue"]) else None,
            runtime=int(base["runtime"]) if pd.notna(base["runtime"]) else None,
            overview_sentiment=sentiment,
            budget_tier=tier_b,
            revenue_tier=tier_r,
            production_effectiveness_score=score,
            themes=themes,
        ))

    unenriched = [r.movieId for r in rows if r.overview_sentiment is None]
    note = None
    if missing:
        note = f"movieId(s) not found: {missing}"
    elif unenriched:
        note = f"movieId(s) outside enriched sample (tier/sentiment/score/themes null): {unenriched}"

    table = ComparisonTable(movies=rows, note=note)
    return table.model_dump_json()


@tool
def predict_user_rating(user_id: int, movie_id: int) -> str:
    """Predict how a specific user would rate a specific movie (0.5–5.0).

    Uses the user's last 10 ratings as context plus, if available, the
    target movie's enrichment. Returns RatingPrediction JSON with
    predicted_rating, rationale, and based_on_n_user_ratings.
    """
    with db.connect() as conn:
        # Exclude the target from history — otherwise we leak ground truth
        # when the user has already rated it (the LLM would just echo).
        history = pd.read_sql_query(
            """
            SELECT rt.rating, rt.movieId, m.title, m.genres
            FROM r.ratings rt JOIN movies m USING (movieId)
            WHERE rt.userId = ? AND rt.movieId != ?
            ORDER BY rt.timestamp DESC
            LIMIT 10
            """,
            conn,
            params=[user_id, movie_id],
        )
        target = conn.execute(
            "SELECT title, overview, genres FROM movies WHERE movieId = ?",
            (movie_id,),
        ).fetchone()

    if target is None:
        return json.dumps({"error": f"movieId {movie_id} not found", "user_id": user_id})
    if len(history) < 3:
        return json.dumps({
            "error": "insufficient_history",
            "user_id": user_id,
            "movie_id": movie_id,
            "n_user_ratings_excluding_target": len(history),
            "note": "need at least 3 other ratings to predict without fabricating a rationale",
        })

    history["genres_clean"] = history["genres"].apply(enrich.parse_json_names)
    hist_lines = "\n".join(
        f"  - {r.rating}/5.0 — {r.title} [{', '.join(r.genres_clean[:3])}]"
        for r in history.itertuples()
    )

    enr = _enriched()
    enr_row = enr[enr["movieId"] == movie_id]
    if not enr_row.empty:
        e = enr_row.iloc[0]
        enriched_str = (
            f"sentiment={e['overview_sentiment']}, "
            f"budget_tier={e['budget_tier']}, revenue_tier={e['revenue_tier']}, "
            f"effectiveness={int(e['production_effectiveness_score'])}, "
            f"themes={list(e['themes'])}"
        )
    else:
        enriched_str = "(outside 75-movie enriched sample — only overview + genre are known)"

    prompt = f"""User {user_id}'s 10 most recent ratings:
{hist_lines}

Target movie (id={movie_id}):
  Title: {target['title']}
  Overview: {target['overview']}
  Genres: {enrich.parse_json_names(target['genres'])}
  Enriched: {enriched_str}

Return a JSON object with:
  - predicted_rating: float in 0.5..5.0 (decimals ending in 0.5 are fine)
  - rationale: one sentence explaining the prediction based on user history
"""

    system_few_shot = (
        "You predict user movie ratings using their history + the target movie's "
        "attributes. Regress to the user's mean when signals are weak; deviate "
        "only with specific evidence (genre affinity, past similar scores, themes)."
    )

    result = llm.invoke(
        prompt=prompt,
        schema=_RatingPredictionLLM,
        model_id=AGENT_MODEL,
        system=system_few_shot,
        temperature=0.0,
    )

    prediction = RatingPrediction(
        user_id=user_id,
        movie_id=movie_id,
        predicted_rating=result.value.predicted_rating,
        rationale=result.value.rationale,
        based_on_n_user_ratings=len(history),
    )
    return prediction.model_dump_json()


@tool
def summarize_user_preferences(user_id: int) -> str:
    """Summarize a user's movie-watching preferences.

    Uses the user's full rating history joined with genres and enriched
    attributes (where available). Returns UserPreferenceSummary JSON with
    favorite genres/themes, typical sentiment, and a one-paragraph summary.
    """
    with db.connect() as conn:
        df = pd.read_sql_query(
            """
            SELECT rt.rating, rt.movieId, m.title, m.genres
            FROM r.ratings rt JOIN movies m USING (movieId)
            WHERE rt.userId = ?
            ORDER BY rt.rating DESC
            """,
            conn,
            params=[user_id],
        )

    if df.empty:
        return json.dumps({"error": f"no ratings for userId {user_id}"})

    df["genres_clean"] = df["genres"].apply(enrich.parse_json_names)

    enr = _enriched().set_index("movieId")
    df["themes"] = df["movieId"].apply(
        lambda mid: list(enr.loc[mid]["themes"]) if mid in enr.index else []
    )
    df["sentiment"] = df["movieId"].apply(
        lambda mid: enr.loc[mid]["overview_sentiment"] if mid in enr.index else None
    )

    # Top-8 and bottom-5 must not overlap — otherwise middle ratings get
    # double-counted in the prompt and bias the summary.
    top = df.head(8)
    bottom = df.tail(5) if len(df) >= 13 else pd.DataFrame()

    def fmt(rows: pd.DataFrame) -> str:
        return "\n".join(
            f"  - {r.rating}/5.0 — {r.title} [{', '.join(r.genres_clean[:3])}] "
            f"themes={r.themes[:3]} sentiment={r.sentiment}"
            for r in rows.itertuples()
        )

    prompt = f"""User {user_id} stats:
  - total ratings: {len(df)}
  - mean rating: {df['rating'].mean():.2f}
  - highest-rated movies ({len(top)}):
{fmt(top)}

"""
    if not bottom.empty:
        prompt += f"  - lowest-rated movies ({len(bottom)}):\n{fmt(bottom)}\n\n"

    prompt += """Return a JSON object with:
  - favorite_genres: 1-5 genre strings the user rates highly
  - favorite_themes: 1-5 themes from enriched data that recur in their favorites (empty list if no enriched overlap)
  - typical_sentiment: one of "positive", "negative", "neutral", or "mixed"
  - summary: one paragraph (2-3 sentences) describing this user's tastes
"""

    result = llm.invoke(
        prompt=prompt,
        schema=_UserPreferenceSummaryLLM,
        model_id=AGENT_MODEL,
        system="You describe movie-watcher preferences based on their ratings. Be specific about patterns in the data, not generic.",
        temperature=0.0,
    )

    summary = UserPreferenceSummary(
        user_id=user_id,
        n_ratings=len(df),
        mean_rating=round(float(df["rating"].mean()), 2),
        favorite_genres=result.value.favorite_genres,
        favorite_themes=result.value.favorite_themes,
        typical_sentiment=result.value.typical_sentiment,
        summary=result.value.summary,
    )
    return summary.model_dump_json()
