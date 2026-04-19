# Movie System — Aetna AI Engineer Take-Home

LLM-integrated movie recommender, rating predictor, comparator, and NL query system built on AWS Bedrock.

**For reviewers in a hurry:** [**SAMPLE_OUTPUTS.md**](SAMPLE_OUTPUTS.md) renders the 8 agent demo prompts + 5 rating-prediction examples inline on GitHub. No clone, no Jupyter.

**For the full artifact:** [`notebooks/movie_system.ipynb`](notebooks/movie_system.ipynb) — EDA, enrichment pipeline, agent tool traces, evaluation with cost + honest limitations. All cells pre-rendered.

**For design rationale:** [PLAN.md](PLAN.md) (architecture decisions), [TASKS.md](TASKS.md) (execution checklist), [AGENTS.md](AGENTS.md) (contributor guide).

## Architecture at a glance

```
┌─── Task 1: Enrichment (batch, direct invoke) ──────────────────────────────┐
│  src/enrich.py ──► openai.gpt-oss-20b-1:0 (Bedrock, us-east-1)             │
│       │  75 movies × 1 call ≈ $0.006                                       │
│       ▼                                                                    │
│  data/enriched_movies.parquet  (5 attrs × 75 movies, committed to repo)    │
└───────────────────────┬────────────────────────────────────────────────────┘
                        │ parquet read by Task 2 tools
                        ▼
┌─── Task 2: Movie system (interactive, Strands agent) ──────────────────────┐
│  user prompt ──► src/agent.py                                              │
│                  BedrockModel(claude-haiku-4-5, us-east-1)                 │
│                        │ chooses 1+ tools per turn                         │
│                        ▼                                                   │
│  query_movies · get_enriched_movie · compare_movies                        │
│  predict_user_rating · summarize_user_preferences                          │
│                        │ parameterized SQL only (no LLM-written SQL)       │
│                        ▼                                                   │
│  db/movies.db  ·  db/ratings.db  ·  data/enriched_movies.parquet           │
└────────────────────────────────────────────────────────────────────────────┘
```

Three decisions worth noting:

- **Parquet is the bridge** between the two tasks — Task 1 writes once, Task 2 reads. Committed to the repo so reviewers don't need Bedrock access to see Task 1's output or run the tool tests.
- **Two models at Bedrock.** `gpt-oss-20b` is cheap and good enough for structured extraction where we control the prompt directly. Claude Haiku 4.5 is Strands-native for agent tool-calling. See [PLAN.md](PLAN.md) for why not the same model for both.
- **LLM never writes SQL.** Tool inputs are Pydantic-validated JSON filter specs; server-side code translates them to parameterized SQL. Guard-tested in [`tests/test_tools.py`](tests/test_tools.py).

## Prerequisites

- Python 3.11+
- AWS account with an SDK profile (`aws configure` or `aws sso login`)
- Bedrock model access enabled in **us-east-1** for:
  - `openai.gpt-oss-20b-1:0` — Task 1 enrichment
  - `us.anthropic.claude-haiku-4-5-20251001-v1:0` — Task 2 agent reasoning + Task 1 fallback
  - Enable at: AWS Console → Bedrock → Model access

## Setup

```bash
# 1. Clone
git clone <repo-url> && cd a263c0e65fa9e35a8e87d4c959a0cd73

# 2. Virtualenv
python -m venv .venv && source .venv/bin/activate

# 3. Install
pip install -r requirements.txt

# 4. Configure AWS (skip if already done)
aws configure   # or: aws sso login --profile <your-profile>

# 5. Copy the source SQLite databases (not committed)
cp /path/to/AetnaCodeChallenge-AIEngineers/db/movies.db db/
cp /path/to/AetnaCodeChallenge-AIEngineers/db/ratings.db db/

# 6. Run the notebook
jupyter notebook notebooks/movie_system.ipynb
```

## What this delivers

- **Task 1 — Enrichment:** 5 LLM-generated attributes for a stratified sample of 75 movies (sentiment, budget tier, revenue tier, production effectiveness score, themes). Cached to `data/enriched_movies.parquet`.
- **Task 2 — Movie system:** A single Strands agent with five tools covering recommendations, comparative analyses, NL queries, rating prediction, and user preference summaries.

## Design at a glance

| Decision | Choice | Why |
|---|---|---|
| LLM provider | AWS Bedrock | Runs in our account; no third-party keys |
| Task 1 enrichment | `openai.gpt-oss-20b-1:0` | Cheap, sufficient for structured extraction under our direct-invoke control |
| Task 2 agent reasoning | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Strands is Claude-native (hardcoded tool-result branching); gpt-oss via Strands is unverified |
| Task 1 fallback | Same Claude Haiku | Proven JSON reliability; one backup model, two roles |
| Task 1 architecture | Direct `invoke_model` + Pydantic retry | Deterministic batch loop — no agent overhead |
| Task 2 architecture | Strands Agents SDK with 5 `@tool` functions | Genuinely tool-using; closes the compare requirement |
| Auth | boto3 default credential chain | One code path for local + Lambda |

## Evaluation

Full detail: [notebook §4](notebooks/movie_system.ipynb). Summary:

### Cost

| Workload | Model | Cost |
|---|---|---:|
| Task 1 enrichment (75 movies) | `openai.gpt-oss-20b-1:0` | $0.0064 |
| Task 1 consistency check (10 × 2) | `openai.gpt-oss-20b-1:0` | ~$0.0017 |
| Task 2 agent demos + predictions | `claude-haiku-4-5` | ~$0.05 |
| **Total for the full rendered notebook** | | **~$0.06** |

### Consistency (Task 1, temperature=0, 10 movies × 2 runs)

- Categorical fields (sentiment, tiers, score): **1 drift in 40 comparisons = 2.5%**
- `themes` free-form list: **5 of 10 movies showed some synonym variation** (same core keywords, 1–2 swapped)
- Parquet cache sidesteps this for the submission; fresh reviewer runs will see categorical fields match ~97%, themes ~50%.

### Rating prediction (Task 2, illustrative)

5 (user, movie) pairs where both have ≥20 other ratings + enriched target:

- **2 exact hits**, 3 within 1.0, 5 within 2.5. Mean |delta| ≈ 1.0.
- Framing is "sensible predictions with specific rationales," not MAE — n=5 can't defend an aggregate metric.

### Honest limitations

- Enrichment coverage is **75 of 45,430 movies** (0.16% of catalog). Task 2 queries that filter on enriched fields will return few results.
- Per-movie rating counts are too sparse for an MAE (e.g. *The Godfather* has 5 total ratings). Illustrative examples instead.
- Free-form `themes` not fully deterministic at temp=0 (~50% of fresh re-invocations show synonym-level drift).
- Short-term AWS SSO sessions expire mid-run (12h default). Re-auth before `jupyter nbconvert --execute`.

### What I'd do with more time

1. Full-catalog enrichment (~$4 on gpt-oss-20b) so enriched filters return 50+ candidates.
2. Embedding-based theme similarity (captures "redemption" ≈ "forgiveness" without brittle synonym matching).
3. Per-call token instrumentation for the Strands agent → exact Task 2 cost instead of estimate.
4. Deploy `src/agent.py` as a Lambda behind API Gateway (code is already Lambda-ready).
5. Rating prediction via collaborative filtering as a baseline, compared head-to-head against the LLM.

## Tests

```bash
pytest
```

44 tests, ~3.5s, no AWS calls (all LLM paths mocked). The `tests/test_tools.py` tests are skipped automatically if `db/movies.db` and `db/ratings.db` are not present — run the setup step above to include them.

## Repository layout

```
notebooks/movie_system.ipynb   primary deliverable
src/                           library code (imported by notebook + Lambda)
db/                            source SQLite (gitignored — copy manually)
data/                          enrichment cache (gitignored)
tests/                         pytest
PLAN.md / TASKS.md / AGENTS.md planning artifacts
```
