# PLAN

Direction doc for this project. Source of truth for scope, decisions, and approach.

## Goal

Deliver an LLM-integrated movie system that (1) enriches a 50–100 movie sample with 5 new attributes and (2) serves recommendations, rating predictions, natural-language queries, **and comparative analyses** — with structured outputs and a credible evaluation story. Target effort: **2–3 hours** of focused build time.

## Stack

- **Language:** Python 3.11+
- **LLM provider:** AWS Bedrock (runs in our own AWS account — no OpenAI API keys, no vendor billing setup)
- **Models — two-model split by workload, not by fallback:**
  - `openai.gpt-oss-20b-1:0` — **Task 1 enrichment** (bulk structured extraction; $0.07 / $0.30 per 1M). Chosen for cost + capability fit on high-volume JSON extraction where we control the prompt contract directly.
  - `us.anthropic.claude-haiku-4-5-20251001-v1:0` — **Task 2 agent reasoning** ($0.80 / $4 per 1M). Chosen because Strands' `BedrockModel` is Claude-native: hardcoded `_MODELS_INCLUDE_STATUS = ["anthropic.claude"]` branch for tool-result formatting, default model is Claude Sonnet, every example in the docs uses Claude. Using OpenAI gpt-oss through Strands is unverified and a known 45-min-timebox risk.
  - Same Claude Haiku also serves as **Task 1 fallback** if gpt-oss JSON reliability drops below 90%. One backup model, two roles.
- **Why this split is the right call (not a compromise):** bulk structured extraction and agentic tool-calling are different jobs. gpt-oss is cheaper and fine when we hand-write the prompt and parser. Claude is Strands-native and battle-tested for tool use. Picking the right model per job is better architecture than "one model everywhere" — and it still demonstrates multi-model fluency on AWS.
- **Region:** `us-east-1`. Strands' `BedrockModel` defaults to `us-west-2`, so we pass `region_name="us-east-1"` explicitly in `src/config.py` **and** set `AWS_REGION=us-east-1` in `.env` for belt-and-suspenders (Strands' bedrock.py reads `AWS_REGION` when `region_name` is unset).
- **Auth:** boto3 default credential chain. Local dev uses AWS SDK profile; Lambda uses IAM role. **No API keys, no secrets in env.**
- **Architecture — hybrid:**
  - **Task 1 (enrichment)** — direct `bedrock-runtime.invoke_model` via a thin `src/llm.py` (~30 lines: invoke → parse JSON → Pydantic validate → retry). This is a deterministic 75-row loop — not agentic, no framework needed.
  - **Task 2 (movie system)** — **Strands Agents SDK** with `BedrockModel(model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0", region_name="us-east-1")`. One agent, five tools: `query_movies`, `get_enriched_movie`, `compare_movies`, `predict_user_rating`, `summarize_user_preferences`. Handles recommend / query / compare / predict / user-preference-summary from a single entry point. Tool docstrings are the prompts; system prompt sets movie-assistant persona.
- **Why hybrid, not all-Strands:** enrichment is a batch loop with one prompt shape per row — agent overhead hurts clarity and cost. Task 2 is genuinely tool-using (decide when to filter DB, when to read cache, when to compare) — agent earns its keep and closes the README's "comparative analyses" gap for free.
- **Code Reduction via Strands:** Using Strands for Task 2 collapses `recommend.py`, `query.py`, and `predict.py` into a single agent. It reduces ~300-400 lines of manual invoke/parse/validate/retry logic down to ~80-120 lines of clean tool definitions, with structured output and retries handled natively by the framework.
- **Data:** SQLite (`movies.db`, `ratings.db`) via built-in `sqlite3`; pandas for transforms
- **Structured output:**
  - Task 1: Pydantic schemas + JSON parse + validation retry (Bedrock gpt-oss has no native strict mode)
  - Task 2: Strands tool-return types + final-response Pydantic validation where the agent returns structured results
- **Storage for enrichment cache:** Parquet (`data/enriched_movies.parquet`) so reruns are free
- **CLI:** `typer` entry points: `enrich` (direct), and `ask` (agent — subsumes recommend/query/compare/predict)
- **Testing:** `pytest` — light coverage on prompt contracts, tool I/O, cache behavior

## Data Model

- `movies.db` — 45,430 rows, one table `movies` (see README for columns)
- `ratings.db` — 100,004 rows, `ratings(ratingId, userId, movieId, rating, timestamp)` — **not documented in the source schema but present in the data and useful for rating-prediction + user-preference tasks**

Both DBs are read-only inputs. Enrichment output lands in a separate parquet, not the source DB.

## Sampling (Task 1)

- Sample size: **75 movies**
- Filters: non-null `overview`, `budget > 0`, `revenue > 0`, `status = 'Released'` (so tiering has signal)
- Stratify by genre bucket to avoid a blockbuster-only sample
- Deterministic (`random_state=42`) so results are reproducible

## Enrichment Attributes (Task 1 — 5 total)

1. **`overview_sentiment`** — `positive` | `negative` | `neutral` (from overview text)
2. **`budget_tier`** — `low` | `medium` | `high` (LLM reasons over budget + genre norms, not just a quantile cut)
3. **`revenue_tier`** — `low` | `medium` | `high` (same reasoning pattern)
4. **`production_effectiveness_score`** — integer 1–10, combines avg user rating (from `ratings.db`), budget, revenue; LLM produces score + one-line rationale
5. **`themes`** — list of 3–5 thematic keywords (e.g., `["redemption", "heist", "family"]`) — powers semantic-ish recommendations without embeddings

All 5 returned in a single Pydantic-validated JSON call per movie. Cached to parquet.

## System Design (Task 2) — Strands agent with four tools

One agent, one entry point, four capabilities — the agent decides which tools to call based on the user's question.

**Tools (all live in `src/tools.py`):**

- **`query_movies(filter_json) -> list[Movie]`** — translates a validated `QueryFilter` Pydantic model into parameterized SQL against `movies.db` joined with enriched parquet. LLM never writes raw SQL.
- **`get_enriched_movie(movie_id) -> EnrichedMovie`** — reads enriched attributes from parquet cache.
- **`compare_movies(movie_ids) -> ComparisonTable`** — returns a structured side-by-side (budget, revenue, runtime, tiers, sentiment, themes) for 2+ movies. Closes the README's "comparative analyses" requirement.
- **`predict_user_rating(user_id, movie_id) -> RatingPrediction`** — pulls user history from `ratings.db` + target movie enrichment, few-shot prompts, returns predicted rating + rationale.
- **`summarize_user_preferences(user_id) -> UserPreferenceSummary`** — aggregates user's rating history + enriched attributes of rated movies, returns LLM-summarized preference profile (favorite genres, typical sentiment, themes that resonate). Directly addresses the README's "summarize preferences for user" requirement.

**Agent flow (example prompts):**

- _"Recommend action movies with high revenue and positive sentiment"_ → agent calls `query_movies` with filter, ranks top 5 with rationale
- _"Summarize preferences for user 42 based on their ratings and movie overviews"_ → agent calls `summarize_user_preferences(42)`
- _"How does The Godfather compare to Goodfellas?"_ → agent calls `compare_movies([238, 769])`, formats the result
- _"Will user 42 like movie 550?"_ → agent calls `predict_user_rating(42, 550)`
- _"What were the highest-grossing dramas of the 90s?"_ → agent calls `query_movies` with tier + decade filter

All tool inputs/outputs are Pydantic-typed. System prompt + tool docstrings are the only prompt engineering surface.

**Fallback plan (important — 45-min timebox):** Strands is new to us. If the agent isn't running end-to-end within 45 minutes of Task 2 start, we fall back to direct-invoke modules (`recommend.py`, `predict.py`, `query.py`) and accept the compare gap by merging a basic compare into `query`. Decision point, not a failure state.

## Project Structure

```
.
├── PLAN.md, TASKS.md, AGENTS.md, README.md
├── .env.example, .gitignore, requirements.txt, pyproject.toml
├── db/                         # source DBs copied in locally (gitignored)
├── data/
│   └── enriched_movies.parquet # enrichment cache
├── notebooks/
│   └── movie_system.ipynb      # PRIMARY deliverable: EDA → enrichment → recommend → predict → query, with narrative + evaluation
├── src/                        # library code — imported by the notebook AND Lambda
│   ├── config.py               # region, model IDs, paths
│   ├── llm.py                  # Bedrock invoke wrapper for Task 1 (enrichment loop)
│   ├── db.py                   # sqlite helpers
│   ├── enrich.py               # Task 1 logic (functions, not a script)
│   ├── tools.py                # Task 2: Strands @tool functions (query, enriched lookup, compare, predict)
│   ├── agent.py                # Task 2: Strands Agent config + system prompt
│   ├── schemas.py              # Pydantic models (shared by both tasks)
│   ├── cli.py                  # optional typer CLI: `enrich` and `ask`
│   └── prompts/
│       ├── enrich.py           # Task 1 prompt
│       └── agent_system.py     # Task 2 agent system prompt
└── tests/
```

**Two views of the same code:**

- **Reviewer view** — open `notebooks/movie_system.ipynb`, see narrative + prompts + outputs + evaluation inline
- **Engineering view** — `src/` is the library; notebook is a thin driver that imports and orchestrates. No logic duplication.

The notebook replaces the separate `outputs/sample_runs.md` — the rendered cells _are_ the sample runs.

## Deployment (bonus — manual)

`src/llm.py` is Lambda-ready by design. No rewrites, no second language, no API gateway unless we want one.

- **boto3** is in the Lambda Python runtime — nothing to package for auth
- **Bedrock access** comes from the Lambda's IAM role (`bedrock:InvokeModel` on our chosen model IDs) — **no API keys, no env secrets**
- **Packaging:** `zip -r llm.zip src/llm.py src/schemas.py src/prompts/ -x '*__pycache__*'` (Pydantic is the only non-stdlib dep; ship as a Lambda layer or in the zip)
- **Upload:** AWS Console or `aws lambda update-function-code --function-name <name> --zip-file fileb://llm.zip`
- **Why this matters:** same code runs locally and in Lambda — demonstrates production-ready LLM integration in the user's AWS account without a second project. Resume signal without the tax.

Local dev flow is identical: boto3 picks up `~/.aws/credentials` or `AWS_PROFILE`. No code branch.

## Evaluation Strategy

All evaluation lives inline in `notebooks/movie_system.ipynb` so reviewers see prompts, raw outputs, and judgments in one artifact.

- **Enrichment quality:** manual spot-check on 10 samples (sentiment + tier + themes sanity). Consistency check: run twice at `temperature=0`, diff should be empty. Both visible in the notebook.
- **Agent behavior (Task 2):** 8–10 example prompts covering recommend, compare, predict, and NL query. For each, render the agent's tool-call trace + final answer. Reviewers can see _which_ tool was chosen and judge whether the agent's reasoning was sound.
- **Rating prediction:** **reframed as illustrative examples, not MAE evaluation.** Phase 1 EDA surfaced genuine sparsity — most movies have single-digit ratings (*The Godfather* has 5 total). A 20-row MAE on that base has confidence intervals wider than the 0.5–5.0 rating scale, which would be statistical theater. Instead: show 5–10 worked prediction examples with predicted rating + actual rating + one-line rationale + delta. Satisfies the README's "5–10 example ratings for prediction tasks" requirement directly, and is more honest than a number we can't defend.
- **Cost:** per-call token log; total cost summary cell at notebook end; mirrored in README.

## Non-Goals (to protect the time budget)

- No fine-tuning, no embeddings/vector DB (themes list is our cheap semantic layer)
- No web UI — CLI only
- No full 45k-row enrichment
- No auth, no deployment

## Risks

- **Strands region default is us-west-2, not us-east-1** — `BedrockModel` falls back to `us-west-2` if neither `region_name` arg nor `AWS_REGION` env var is set. Mitigation: pass `region_name="us-east-1"` explicitly in `src/config.py` **and** set `AWS_REGION` in `.env`. Double coverage.
- **Bedrock model access must be enabled** in the AWS console (Bedrock → Model access) before invoke will succeed. First-run check in `llm.py` surfaces this clearly.
- **gpt-oss JSON reliability on Bedrock** — no native strict mode for these models. Mitigation: Pydantic-validate and retry up to 2×; if >10% failure rate, switch to `claude-haiku-4-5` via the same `llm.py` interface (Haiku is already our Task 2 model, so the fallback path is proven).
- **Strands learning curve** — first-time use under 2–3 hour budget. Mitigation: **45-minute timebox** on the initial spike. If the agent + one tool isn't returning a validated response end-to-end by then, fall back to direct-invoke modules and merge `compare` into `query` as a best-effort text response.
- **Strands + structured output** — agent final-response validation less direct than a single invoke. Verify during the spike; if fighting, accept plain-text agent responses for non-critical capabilities (recommend, compare) and keep Pydantic on `predict` + `query` tool returns.
- **Notebook legibility with agent traces** — tool-call sequences are noisier than linear prompts. Mitigation: configure Strands to stream decisions, render traces in a collapsible format, keep the 8–10 examples short.
- **Ratings DB not in README** — will note in our README that we opted to use it, with rationale
- **Rating-prediction accuracy** — likely mediocre; plan is to report honestly, not hide it
- **Scope creep** — AGENTS.md enforces scope discipline

## Decisions (resolved during planning)

- ~~Drop `predict-rating`?~~ — **kept**, essentially free as an agent tool.
- ~~Framework vs. direct invoke?~~ — **hybrid**: direct for Task 1 (enrichment loop), Strands for Task 2 (tool-using agent).
- ~~Model choice?~~ — **revised after Strands SDK research:** `openai.gpt-oss-20b-1:0` for Task 1 enrichment (direct invoke we control); `us.anthropic.claude-haiku-4-5-20251001-v1:0` for Task 2 agent reasoning (Strands is Claude-native, hardcoded tool-result branching for `anthropic.claude` model IDs). Same Haiku doubles as Task 1 fallback. Rejected `openai.gpt-oss-120b-1:0` for Task 2 because Strands' OpenAI-on-Bedrock path is unverified.
- ~~Commit `db/`?~~ — **gitignored.** README documents the one-line copy step. Committing a 45k-row SQLite signals we didn't think about repo hygiene.
- ~~Lambda deploy: core or stretch?~~ — **stretch.** Core is notebook + CLI. Lambda is resume signal, not a deliverable.
