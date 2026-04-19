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

- [ ] `src/agent.py`: stand up a minimal Strands agent with `BedrockModel` + **one** tool (`query_movies` stub)
- [ ] Run one prompt end-to-end ("list 3 action movies"), confirm tool call + response
- [ ] **Decision point:** if not working after 45 min → rollback to direct-invoke: `recommend.py`, `predict.py`, `query.py` modules (original plan), merge `compare` into `query` as best-effort
- [ ] If working: proceed below

### Schemas

- [ ] `QueryFilter` in `src/schemas.py` — validated filter spec (no raw SQL from LLM)
- [ ] `EnrichedMovie`, `ComparisonTable`, `RatingPrediction`, `UserPreferenceSummary` in `src/schemas.py`

### Tools (`src/tools.py`)

- [ ] `@tool query_movies(filter: QueryFilter) -> list[Movie]` — parameterized SQL against movies.db + enriched parquet
- [ ] `@tool get_enriched_movie(movie_id: int) -> EnrichedMovie` — parquet cache read
- [ ] `@tool compare_movies(movie_ids: list[int]) -> ComparisonTable` — side-by-side on budget/revenue/runtime/tiers/sentiment/themes
- [ ] `@tool predict_user_rating(user_id: int, movie_id: int) -> RatingPrediction` — user history + target enrichment + few-shot
- [ ] `@tool summarize_user_preferences(user_id: int) -> UserPreferenceSummary` — rating history + enriched attrs → preference profile (addresses README "user preference summaries")
- [ ] Clear, specific docstrings on every tool (these are the prompts)

### Agent

- [ ] `src/agent.py`: `Agent(model=BedrockModel(model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0", region_name="us-east-1"), tools=[...], system_prompt=...)` — Claude Haiku (Strands-native, see PLAN.md decision)
- [ ] System prompt in `src/prompts/agent_system.py` — movie-assistant persona, tool-selection guidance

### Notebook demos — 8 concrete prompts + illustrative predictions, across all 5 capabilities

For each: render the tool-call trace + final structured answer inline. Prompts are pre-chosen so we don't invent them under time pressure.

**Recommend (2)**

- [ ] `"Recommend action movies with high revenue and positive sentiment"` _(README example)_
- [ ] `"Find a dark comedy with a small budget that made money"` _(custom — exercises tier reasoning)_

**Summarize user preferences (1)**

- [ ] `"Summarize preferences for user 42 based on their ratings and movie overviews"` _(README example)_

**Compare (2)**

- [ ] `"How does The Godfather compare to Goodfellas?"` _(named titles — exercises movie-id lookup)_
- [ ] `"Compare the 3 highest-grossing 1990s dramas by runtime and effectiveness score"` _(chained query → compare)_

**NL query (2)**

- [ ] `"What were the highest-grossing dramas of the 90s?"`
- [ ] `"Show me movies with effectiveness score ≥ 8 and budget under $10M"`

**Predict (1 trace + 5–10 illustrative examples)**

- [ ] `"Will user 42 like movie 550?"` _(sample trace)_
- [ ] Pick 5–10 (user, movie) pairs where both ends have enough context (user ≥20 ratings, movie ≥3 ratings), invoke via agent, render a table with predicted rating / actual rating / delta / one-line rationale. Skip the MAE — per-movie rating counts are too sparse to defend a number (Phase 1 finding: _The Godfather_ has 5 total ratings). Write an honest-limitations markdown cell explaining why we're showing examples instead of an aggregate metric.

### If rollback taken

- [ ] Implement `src/recommend.py`, `src/predict.py`, `src/query.py` with direct `llm.invoke`
- [ ] Add a `compare` function inside `query.py` — text output, no structured table
- [ ] Document the rollback decision in README with one paragraph of reasoning

## Phase 4 — Notebook polish & findings

- [ ] Top-of-notebook: clear setup cell + overview markdown (what this notebook demonstrates)
- [ ] Between phases: short markdown intros explaining _why_ each step exists
- [ ] Bottom of notebook: "Findings" section with: enrichment consistency result, prediction examples summary, total cost, honest limitations (including why we didn't compute a rating-prediction MAE), "what I'd do with more time"
- [ ] Run notebook top-to-bottom on a clean kernel; verify it completes without errors
- [ ] Commit the notebook **with outputs rendered** — those outputs are the evaluation artifact
- [ ] Mirror the findings summary into `README.md`

## Phase 5 — Tests (light)

- [ ] `test_schemas.py` — Pydantic validation round-trips for all schemas
- [ ] `test_tools.py` — `query_movies` produces parameterized SQL (no injection); `compare_movies` handles 2 and 3 ids
- [ ] `test_enrich_cache.py` — second run hits cache, zero Bedrock calls

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
