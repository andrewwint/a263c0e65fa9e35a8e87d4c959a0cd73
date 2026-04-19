"""Task 1: 5-attribute enrichment pipeline.

Samples movies from the eligible pool, calls the LLM per row, caches
results to parquet so reruns are free.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src import db, llm
from src.prompts.enrich import SYSTEM, USER_TEMPLATE
from src.schemas import EnrichedAttributes

logger = logging.getLogger(__name__)

ENRICH_MODEL = "openai.gpt-oss-20b-1:0"
FALLBACK_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

CACHE_PATH = db.REPO_ROOT / "data" / "enriched_movies.parquet"

ELIGIBLE_WHERE = """
    overview IS NOT NULL AND overview != ''
    AND budget > 0 AND revenue > 0
    AND status = 'Released'
    AND genres IS NOT NULL AND genres != ''
"""


def parse_json_names(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            names = [i["name"] for i in parsed if isinstance(i, dict) and "name" in i]
            if names:
                return names
    except (json.JSONDecodeError, TypeError):
        pass
    parts = [s.strip() for s in raw.split("|") if s.strip()]
    return parts or [raw.strip()]


def sample_movies(n: int = 75, random_state: int = 42) -> pd.DataFrame:
    """Proportional stratified sample by primary genre, with avg_rating joined."""
    sql = f"""
        SELECT
            m.movieId, m.title, m.overview, m.budget, m.revenue, m.runtime,
            m.language, m.genres, m.productionCompanies, m.releaseDate, m.imdbId,
            AVG(r2.rating) AS avg_rating,
            COUNT(r2.rating) AS n_ratings
        FROM movies m
        LEFT JOIN r.ratings r2 USING (movieId)
        WHERE {ELIGIBLE_WHERE}
        GROUP BY m.movieId
    """
    with db.connect() as conn:
        pool = pd.read_sql_query(sql, conn)

    pool["primary_genre"] = pool["genres"].apply(
        lambda raw: (parse_json_names(raw) or ["Unknown"])[0]
    )

    # For small n, stratification is noise (every genre would floor to 1).
    if n < pool["primary_genre"].nunique() / 2:
        return pool.sample(n=min(n, len(pool)), random_state=random_state).reset_index(drop=True)

    # Largest-remainder method: proportional allocation that sums exactly to n.
    shares = pool["primary_genre"].value_counts() / len(pool)
    floats = shares * n
    floors = floats.astype(int)
    residual = int(n - floors.sum())
    remainders = (floats - floors).sort_values(ascending=False)
    for g in remainders.head(residual).index:
        floors[g] += 1
    floors = floors[floors > 0]

    samples = []
    for g, k in floors.items():
        group = pool[pool["primary_genre"] == g]
        samples.append(group.sample(n=min(int(k), len(group)), random_state=random_state))
    return pd.concat(samples).reset_index(drop=True)


def _build_user_prompt(movie: dict[str, Any]) -> str:
    genres = parse_json_names(movie.get("genres")) or ["Unknown"]
    budget = int(movie["budget"]) if movie.get("budget") else 0
    revenue = int(movie["revenue"]) if movie.get("revenue") else 0
    roi = (revenue / budget) if budget else None
    avg = movie.get("avg_rating")
    n = int(movie.get("n_ratings") or 0)

    if avg is not None and not pd.isna(avg):
        rating_str = f"{float(avg):.2f} avg across {n} user ratings"
    else:
        rating_str = "no user ratings"

    return USER_TEMPLATE.format(
        title=movie["title"],
        overview=movie["overview"],
        genres=", ".join(genres),
        budget=f"${budget:,}",
        revenue=f"${revenue:,}",
        roi=f"{roi:.1f}x" if roi else "n/a",
        runtime=int(movie["runtime"]) if movie.get("runtime") else "unknown",
        rating_str=rating_str,
    )


def enrich_one(
    movie: dict[str, Any],
    model_id: str = ENRICH_MODEL,
    temperature: float = 0.0,
) -> llm.InvokeResult[EnrichedAttributes]:
    """Enrich a single movie. Returns the InvokeResult with .value, .input_tokens, .output_tokens."""
    user_prompt = _build_user_prompt(movie)
    return llm.invoke(
        prompt=user_prompt,
        schema=EnrichedAttributes,
        model_id=model_id,
        system=SYSTEM,
        temperature=temperature,
    )


def enrich_all(
    movies: pd.DataFrame,
    cache_path: Path = CACHE_PATH,
    model_id: str = ENRICH_MODEL,
) -> pd.DataFrame:
    """Run enrichment for all `movies`, merging with any cached rows.

    Cache is keyed on movieId. Rerunning with the same sample is free.

    Cache schema is not versioned: if `EnrichedAttributes` gains fields,
    cached rows from an earlier schema will merge in without the new fields.
    For this project's scope this is fine — delete `data/enriched_movies.parquet`
    on schema change to force a fresh run.
    """
    cache_path = Path(cache_path)

    cached: dict[int, dict] = {}
    if cache_path.exists():
        cached_df = pd.read_parquet(cache_path)
        cached = {int(r["movieId"]): dict(r) for _, r in cached_df.iterrows()}
        logger.info("loaded %d cached rows from %s", len(cached), cache_path)

    out_rows: list[dict] = []
    total_in = total_out = 0
    failures: list[tuple[int, str]] = []

    for _, row in movies.iterrows():
        mid = int(row["movieId"])
        if mid in cached:
            out_rows.append(cached[mid])
            continue

        try:
            r = enrich_one(row.to_dict(), model_id=model_id)
            total_in += r.input_tokens
            total_out += r.output_tokens
            out_rows.append({
                "movieId": mid,
                "title": row["title"],
                **r.value.model_dump(),
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "model": model_id,
            })
        except Exception as e:
            failures.append((mid, str(e)))
            logger.error("enrich_one failed for movieId=%d: %s", mid, e)

    df = pd.DataFrame(out_rows)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    logger.info(
        "wrote %d rows to %s (new calls: in=%s out=%s, failures=%d)",
        len(df), cache_path, f"{total_in:,}", f"{total_out:,}", len(failures),
    )
    if failures:
        logger.warning("failures: %s", failures[:5])
    return df
