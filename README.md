# Movie System — Aetna AI Engineer Take-Home

LLM-integrated movie recommender, rating predictor, comparator, and NL query system built on AWS Bedrock. Primary deliverable is [`notebooks/movie_system.ipynb`](notebooks/movie_system.ipynb) — run top-to-bottom to see prompts, outputs, and evaluation inline.

See [PLAN.md](PLAN.md) for architecture decisions and [TASKS.md](TASKS.md) for the execution checklist.

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

*(Populated after the notebook runs; mirrors the notebook's Findings section.)*

- Enrichment consistency: TBD
- Rating prediction MAE: TBD
- Total tokens / cost: TBD
- Honest limitations: TBD

## Repository layout

```
notebooks/movie_system.ipynb   primary deliverable
src/                           library code (imported by notebook + Lambda)
db/                            source SQLite (gitignored — copy manually)
data/                          enrichment cache (gitignored)
tests/                         pytest
PLAN.md / TASKS.md / AGENTS.md planning artifacts
```
