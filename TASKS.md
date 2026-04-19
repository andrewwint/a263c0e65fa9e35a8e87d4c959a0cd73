# TASKS

Execution checklist. Grouped by phase; check off as completed. Keep in sync with [PLAN.md](PLAN.md) — if a task diverges from the plan, update the plan first.

**Delivery model:** library code lives in `src/`, demo + evaluation lives in `notebooks/movie_system.ipynb` (which imports `src/`). Build the library first, drive it from the notebook second.

## Phase 0 — Setup

- [ ] Create `.gitignore` (`.env`, `__pycache__`, `*.pyc`, `data/*.parquet`, `db/*.db`, `.DS_Store`, `*.zip`)
- [ ] Create `.env.example` with `AWS_PROFILE=` and `AWS_REGION=us-east-1` (no API keys — boto3 handles auth)
- [ ] Create `requirements.txt` (`boto3`, `strands-agents`, `pydantic`, `pandas`, `pyarrow`, `python-dotenv`, `typer`, `pytest`)
- [ ] Create `pyproject.toml` (optional, for linting/formatting)
- [ ] Copy `movies.db` and `ratings.db` into `db/` (gitignored)
- [ ] Add `jupyter`, `notebook`, `matplotlib`, `seaborn` to `requirements.txt`
- [ ] Create virtualenv, install deps, verify `python -c "import sqlite3, boto3, pydantic, jupyter, strands"`
- [ ] Enable Bedrock model access in AWS console for `openai.gpt-oss-20b-1:0`, `openai.gpt-oss-120b-1:0`, `us.anthropic.claude-3-5-haiku-20241022-v1:0`
- [ ] Smoke-test Bedrock: `boto3.client('bedrock-runtime').invoke_model(...)` with a one-line prompt
- [ ] Create project `README.md` skeleton (setup, run, design notes, AWS prerequisites)

## Phase 1 — Data exploration (in notebook)

- [ ] Write `src/db.py` connection helpers for both DBs
- [ ] Scaffold `notebooks/movie_system.ipynb` with section headers: Setup → EDA → Enrichment → Recommend → Predict → Query → Findings
- [ ] In notebook: row counts, null rates on key columns, rating distribution histogram
- [ ] In notebook: decide and document stratification buckets for the 75-movie sample
- [ ] Commit exploration findings as markdown cells in the notebook (not a separate file)

## Phase 2 — LLM wrapper + Enrichment pipeline (Task 1 — direct invoke, no agent)

### `src/llm.py` — Bedrock wrapper (Lambda-ready, used by Task 1 only)

- [ ] `invoke(prompt, schema, model_id) -> BaseModel`: bedrock-runtime → text → JSON parse → Pydantic validate → retry up to 2× on `ValidationError`
- [ ] Log input/output token counts per call
- [ ] Surface clear error if Bedrock model access is not enabled
- [ ] Unit test the retry path with a mocked client

### Enrichment (library in `src/`, demo in notebook)

- [ ] Define Pydantic `EnrichedAttributes` schema in `src/schemas.py` (5 fields)
- [ ] Draft enrichment prompt in `src/prompts/enrich.py` (system + user template, JSON-only instruction)
- [ ] Implement `src/enrich.py` functions: `sample_movies(n)`, `enrich_one(movie)`, `enrich_all(movies, cache_path)` — no script-level code
- [ ] In notebook: dry-run on 3 movies with `gpt-oss-20b`, render the prompt + raw response + parsed JSON inline
- [ ] In notebook: if JSON failure rate >10%, swap to `us.anthropic.claude-3-5-haiku-20241022-v1:0` with a markdown note explaining the swap
- [ ] In notebook: full run on 75 movies, render a sample DataFrame preview, verify cache hit on second run
- [ ] In notebook: consistency check at `temperature=0` — render the diff cell (should be empty)
- [ ] In notebook: per-call token log cell + cost summary

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

- [ ] `src/agent.py`: `Agent(model=BedrockModel("openai.gpt-oss-120b-1:0"), tools=[...], system_prompt=...)`
- [ ] System prompt in `src/prompts/agent_system.py` — movie-assistant persona, tool-selection guidance

### Notebook demos — 8 concrete prompts + MAE eval, across all 5 capabilities

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

**Predict (1 + MAE eval)**

- [ ] `"Will user 42 like movie 550?"` _(sample trace)_
- [ ] Hold out 20 ratings, invoke via agent, compute MAE, render comparison table + honest-limitations markdown

### If rollback taken

- [ ] Implement `src/recommend.py`, `src/predict.py`, `src/query.py` with direct `llm.invoke`
- [ ] Add a `compare` function inside `query.py` — text output, no structured table
- [ ] Document the rollback decision in README with one paragraph of reasoning

## Phase 4 — Notebook polish & findings

- [ ] Top-of-notebook: clear setup cell + overview markdown (what this notebook demonstrates)
- [ ] Between phases: short markdown intros explaining _why_ each step exists
- [ ] Bottom of notebook: "Findings" section with: enrichment consistency result, MAE, total cost, honest limitations, "what I'd do with more time"
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
