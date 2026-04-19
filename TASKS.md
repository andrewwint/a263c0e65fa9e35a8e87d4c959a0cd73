# TASKS

Execution checklist. Grouped by phase; check off as completed. Keep in sync with [PLAN.md](PLAN.md) — if a task diverges from the plan, update the plan first.

**Delivery model:** library code lives in `src/`, demo + evaluation lives in `notebooks/movie_system.ipynb` (which imports `src/`). Build the library first, drive it from the notebook second.

## Phase 0 — Setup

- [x] Create `.gitignore` (`.env`, `__pycache__`, `*.pyc`, `data/*.parquet`, `db/*.db`, `.DS_Store`, `*.zip`)
- [x] Create `.env.example` with `AWS_PROFILE=` and `AWS_REGION=us-east-1` (no API keys — boto3 handles auth)
- [x] Create `requirements.txt` (`boto3`, `strands-agents`, `pydantic`, `pandas`, `pyarrow`, `python-dotenv`, `typer`, `pytest`)
- [~] ~~Create `pyproject.toml`~~ — skipped per scope discipline (optional + no functional gain)
- [x] Copy `movies.db` and `ratings.db` into `db/` (gitignored)
- [x] Add `jupyter`, `notebook`, `matplotlib`, `seaborn` to `requirements.txt`
- [x] Create project `README.md` skeleton (setup, run, design notes, AWS prerequisites)
- [x] **USER:** Create virtualenv, install deps, verify `python -c "import sqlite3, boto3, pydantic, jupyter, strands"`
- [x] **USER:** Enable Bedrock model access in AWS console (**us-east-1**) for:
  - `openai.gpt-oss-20b-1:0` — Task 1 enrichment
  - `us.anthropic.claude-haiku-4-5-20251001-v1:0` — Task 2 agent reasoning + Task 1 fallback
- [x] Smoke-test Bedrock + Strands — `python tests/smoke_bedrock.py` passed all 3 checks (boto3 gpt-oss-20b, boto3 Haiku 4.5, Strands+Haiku 4.5). Confirmed: Haiku 3.5 is legacy-locked (switched to 4.5), gpt-oss-20b emits reasoning blocks (handle with `reasoning_effort="low"` in Phase 2)

## Phase 1 — Data exploration (in notebook)

- [x] Write `src/db.py` connection helpers — single `connect()` context manager opens movies.db with ratings.db attached as schema `r`
- [x] Scaffold `notebooks/movie_system.ipynb` with sections: Setup → EDA → Enrichment → Agent+Tools → Findings
- [x] In notebook: row counts (45,430 movies / 100,004 ratings / 671 users / 9,066 rated movies), null-rate table, eligible pool count (5,360), genre distribution, rating + per-movie + per-user distributions
- [x] In notebook: stratify by primary genre via `parse_json_names` helper (documented why — tier reasoning needs genre context)
- [x] Notebook committed with rendered outputs
- [x] **Surprise finding:** `genres` and `productionCompanies` are TMDB-style JSON, not the pipe-separated format documented in the challenge README. Added a defensive parser with pipe-split fallback; flagged in notebook findings.

## Phase 2 — LLM wrapper + Enrichment pipeline (Task 1 — direct invoke, no agent)

### `src/llm.py` — Bedrock wrapper (Lambda-ready, used by Task 1 only)

- [x] `invoke(prompt, schema, model_id) -> InvokeResult[T]`: bedrock-runtime → skip reasoningContent blocks → strip ```json fences → JSON parse → Pydantic validate → retry up to 2× on `JSONDecodeError` or `ValidationError`
- [x] Pass `additionalModelRequestFields={"reasoning_effort": "low"}` for gpt-oss (auto-detected by model_id substring)
- [x] `maxTokens=2000` default, override per-call
- [x] Token counts returned on every successful call via `InvokeResult`
- [x] Clear `RuntimeError` if Bedrock model access is not enabled (AccessDeniedException)
- [x] 8 unit tests covering happy path, retry-on-JSON-error, retry-on-schema-violation, fence stripping, reasoning-block skipping, gpt-oss flag routing, Claude flag absence, and terminal failure. All pass.

### Enrichment (library in `src/`, demo in notebook)

- [x] `EnrichedAttributes` in `src/schemas.py` — 5 fields, `themes` constrained to 3–5 items, score is int 1–10
- [x] Enrichment prompt in `src/prompts/enrich.py` — system prompt explains tier-relative-to-genre reasoning + good/bad theme examples
- [x] `src/enrich.py`: `sample_movies(n)` uses largest-remainder stratified allocation; `enrich_one` + `enrich_all` loop with parquet cache keyed on `movieId`
- [x] In notebook: full prompt rendered, dry-run on 3 movies with tokens shown
- [x] In notebook: full run on 75 movies — **zero JSON failures, no fallback needed**
- [x] In notebook: cache verification — rerun reads parquet only (3s vs. 58s cold)
- [x] In notebook: consistency check at `temperature=0` — **partial determinism honestly reported**: categorical fields stable, `themes` list has minor synonym variation across re-invocations (documented in findings)
- [x] In notebook: token + cost summary — $0.0064 total for 75 movies ($0.00009/movie)

## Phase 3 — System design (Task 2 — Strands agent with 4 tools)

**Covers recommend / query / compare / predict from one agent entry point. Library in `src/`, demo in notebook.**

### Spike + timebox (first 45 min of this phase)

- [x] Minimal Strands agent with `BedrockModel` stood up; single-tool smoke test returned in 2.9s on first try. Spike passed — no rollback.

### Schemas

- [x] `QueryFilter` in `src/schemas.py` — genres, tiers, sentiment, score, year/budget/runtime ranges, sort_by, limit. All map to `?` bindings in `query_movies`.
- [x] `ComparisonRow`, `ComparisonTable`, `RatingPrediction`, `UserPreferenceSummary` in `src/schemas.py`. Split internal `_RatingPredictionLLM` and `_UserPreferenceSummaryLLM` so the LLM fills only the content fields and the tool adds user_id/movie_id/counts server-side (no hallucinated IDs).

### Tools (`src/tools.py`)

- [x] `@tool query_movies(filter_json)` — parses JSON → `QueryFilter`, builds parameterized SQL, merges with enriched parquet. `needs_enriched` inner-join branch means tier/sentiment/score filters strictly respect the 75-movie sample.
- [x] `@tool get_enriched_movie(movie_id)` — parquet lookup; returns `{error}` JSON when the movie is outside the enriched sample.
- [x] `@tool compare_movies(movie_ids_json)` — builds `ComparisonTable` with DB fields for all rows; enriched fields null and noted for rows outside the sample.
- [x] `@tool predict_user_rating(user_id, movie_id)` — **excludes target from user history** (fixed ground-truth leak caught during evaluation). Joined w/ enrichment when available; LLM returns rating + rationale.
- [x] `@tool summarize_user_preferences(user_id)` — full rating history, top/bottom rated, enriched overlap where present.
- [x] Docstrings are thorough — they're the LLM's tool reference.

### Agent

- [x] `src/agent.py`: `build_agent()` factory returns `Agent` over `BedrockModel("us.anthropic.claude-haiku-4-5-20251001-v1:0", region_name="us-east-1")` with all 5 tools.
- [x] System prompt in `src/prompts/agent_system.py` — persona, tool-selection rules, "enriched sample is only 75 movies" guard, 3 few-shot rating-prediction examples, response-formatting guidance (titles, why-this-fits, markdown tables).

### Notebook demos — 8 concrete prompts + illustrative predictions, across all 5 capabilities

All 8 ran end-to-end, rendered tool-call traces + final answers inline.

**Recommend (2)**

- [x] `"Recommend action movies with high revenue and positive sentiment"` — agent honestly flagged the 75-movie enrichment constraint (returned 1 match)
- [x] `"Find a dark comedy with a small budget that made money"` — 4 results with tier-reasoning rationale

**Summarize user preferences (1)**

- [x] `"Summarize preferences for user 42 based on their ratings and movie overviews"` — paragraph summary with specific movie references (*Monsoon Wedding*, *Die Hard 2*)

**Compare (2)**

- [x] `"How does The Godfather compare to Goodfellas?"` — 6-tool-call trace (agent iterated through compare/enriched lookups), final answer correct and noted both films are outside the enriched sample
- [x] `"Compare the 3 highest-grossing 1990s dramas by runtime and effectiveness score"` — clean query → 3× enriched-lookup pattern; honestly reported the three blockbusters aren't in the enriched sample

**NL query (2)**

- [x] `"What were the highest-grossing dramas of the 90s?"` — single query_movies call, top-10 markdown table
- [x] `"Show me movies with effectiveness score ≥ 8 and budget under $10M"` — 10 well-chosen results including *Jaws*, *Reservoir Dogs*, *Insidious*

**Predict (1 trace + 5 illustrative examples)**

- [x] `"Will user 42 like movie 550?"` — predicted 3.75 for *Fight Club*, specific rationale referring to user's drama preference
- [x] 5 (user, movie) pairs table: 2 exact hits, avg |delta| ≈ 1.0. **Leak caught and fixed during eval**: `predict_user_rating` was pulling user's recent ratings *including* the target movie for rows where the user had already seen it. Added `movieId != ?` to the history query. Noted in findings.

### If rollback taken

- [ ] Implement `src/recommend.py`, `src/predict.py`, `src/query.py` with direct `llm.invoke`
- [ ] Add a `compare` function inside `query.py` — text output, no structured table
- [ ] Document the rollback decision in README with one paragraph of reasoning

## Phase 4 — Notebook polish & findings

- [x] Top-of-notebook overview: stack, reading order, prereqs, links to PLAN/TASKS/AGENTS
- [x] Inter-phase markdown intros explain _why_ each step exists
- [x] Stale "MAE" language removed from Phase 1 findings + section 1.5 title
- [x] Bottom of notebook: real Findings section with **cost table**, **consistency table**, **prediction result breakdown**, **honest limitations**, **what I'd do with more time**
- [x] Clean-kernel end-to-end run completed: **53 cells, 0 errors, 203KB rendered**
- [x] Notebook committed with outputs rendered — the rendered cells are the evaluation artifact
- [x] Findings summary mirrored into `README.md`

## Phase 5 — Tests (light)

- [x] `test_schemas.py` — 17 tests covering round-trips, out-of-range rejection, invalid-Literal rejection, theme-count bounds for all Phase 2/3 schemas
- [x] `test_tools.py` — 13 tests: title-merge regression guard, genre filter (case-insensitive, LIKE-wildcard safe), year range, malformed-JSON rejection, `compare_movies` with 2/3 ids + missing-id notation + single-id rejection, `get_enriched_movie` unenriched-error, `predict_user_rating` insufficient-history guard, and the **critical no-ground-truth-leak test** (per AGENTS.md Evaluation hygiene)
- [x] `test_enrich_cache.py` — full cache hit (0 LLM calls) + partial cache (1 LLM call for 1 uncached row)
- [x] Verified the leak test is meaningful: temporarily reverted `AND rt.movieId != ?` from the history query, ran the test, it failed with `AssertionError: target movie title appeared in the user-history portion of the prompt`. Restored the fix; test passes.
- [x] Full suite: **41 tests, all pass in ~3.5s**, no AWS calls (all LLM paths mocked)

## Phase 6 — Submission

- [ ] Final README pass: setup, AWS prerequisites, notebook-first run instructions, design rationale, evaluation results, cost
- [ ] Optional: add `src/cli.py` run examples for reviewers without Jupyter
- [ ] Scrub secrets (grep for `AKIA`, `sk-`; confirm `.env` gitignored)
- [ ] Confirm notebook outputs are rendered and committed (not stripped)
- [ ] Initial commit with sensible history (not one giant commit)
- [ ] Push to GitHub, verify clone + notebook runs top-to-bottom on a fresh checkout
- [ ] Send repo link

## Stretch (only if time allows)

### Lambda deploy (bonus — demonstrates AWS integration without a second language)

- [ ] Create Lambda function in AWS console (Python 3.11, 512 MB, 30s timeout)
- [ ] Attach IAM role with `bedrock:InvokeModel` on the three model IDs
- [ ] Package: `zip -r lambda.zip src/llm.py src/agent.py src/tools.py src/schemas.py src/prompts/` + Pydantic/Strands layer (or bundled)
- [ ] Upload via `aws lambda update-function-code`
- [ ] Test invoke with a sample `{"prompt": "...", "capability": "recommend"}` payload
- [ ] Document the deploy steps + invoke URL/CLI command in README

### Other

- [ ] Simple embedding-based similarity for themes (Bedrock Titan or Cohere embed)
- [ ] `rich` CLI output
- [ ] Dockerfile
