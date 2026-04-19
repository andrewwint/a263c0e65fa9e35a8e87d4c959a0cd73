"""SQLite helpers for movies.db and ratings.db.

Both databases are read-only inputs from the challenge. The `connect()`
context manager opens movies.db as the main schema with ratings.db
attached as `r`, so queries can join across both:

    with db.connect() as conn:
        rows = conn.execute('''
            SELECT m.title, AVG(r2.rating) AS avg_rating, COUNT(r2.rating) AS n
            FROM movies m
            LEFT JOIN r.ratings r2 USING (movieId)
            GROUP BY m.movieId
            ORDER BY avg_rating DESC NULLS LAST
            LIMIT 5
        ''').fetchall()
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
MOVIES_DB = REPO_ROOT / "db" / "movies.db"
RATINGS_DB = REPO_ROOT / "db" / "ratings.db"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open movies.db with ratings.db attached as schema `r`."""
    for path, name in ((MOVIES_DB, "movies.db"), (RATINGS_DB, "ratings.db")):
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found. Copy {name} from "
                "AetnaCodeChallenge-AIEngineers/db/ into this repo's db/ directory."
            )
    # SQLite doesn't support bound parameters on ATTACH DATABASE across all
    # driver builds. Path is a module-level constant we control; assert it
    # can't break out of the SQL literal, then interpolate.
    ratings_path = str(RATINGS_DB)
    assert "'" not in ratings_path, f"unsafe db path: {ratings_path!r}"
    conn = sqlite3.connect(str(MOVIES_DB))
    try:
        conn.row_factory = sqlite3.Row
        conn.execute(f"ATTACH DATABASE '{ratings_path}' AS r")
        yield conn
    finally:
        conn.close()
