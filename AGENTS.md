# AGENTS.md

Operating guidelines for any AI agent (Claude, Cursor, Copilot, etc.) contributing to this repo.

## Source of truth

- **[PLAN.md](PLAN.md)** — direction, scope, decisions. Read it before starting any non-trivial task. If your work would diverge from the plan, update the plan first (or flag the conflict) — do not silently drift.
- **[TASKS.md](TASKS.md)** — the checklist. Mark `- [ ]` → `- [x]` as each item completes. If a task isn't listed, add it before doing it.
- **Challenge spec** — [AetnaCodeChallenge-AIEngineers/README.md](../AetnaCodeChallenge-AIEngineers/README.md). Authoritative for requirements; PLAN.md is our interpretation of it.

## Honest feedback — required

- **Push back when you disagree.** If the user's plan has a flaw, a better approach exists, or a task is the wrong priority, say so plainly before acting. Sycophancy wastes time.
- **Flag what's missing.** If a request is ambiguous, under-scoped, or ignores a real constraint (cost, time, data quality), raise it up front rather than discovering it mid-implementation.
- **Report results truthfully.** If rating prediction has a 1.2 MAE, say so — do not hide, round, or caveat away poor numbers. "Honest limitations" is a section in the README for a reason.
- **Don't claim success you can't verify.** If tests weren't run, say so. If the pipeline worked on 3 rows but not 75, say so.
- **Surface cost.** Token usage and $ spend are first-class concerns on a take-home — always report them.

## Scope discipline

- This is a **2–3 hour assessment**. Every abstraction, helper, or "nice-to-have" must earn its place.
- No speculative features, no future-proofing, no premature config systems.
- Prefer editing existing files over creating new ones. Prefer deleting code over adding flags.
- If a task is outside PLAN.md's scope, do not do it — propose a plan change first.

## Code style

- Write no comments by default. Only add one when the *why* is non-obvious.
- Use type hints + Pydantic at LLM/DB boundaries; skip them for obvious internal glue.
- No emojis in code, prompts, or docs unless the user asks.
- Use `pathlib`, `with` blocks for DB connections, and parameterized SQL always.

## Prompt engineering conventions

- All prompts live in `src/prompts/` — one module per capability.
- Every LLM call that returns data must go through a Pydantic schema.
- `temperature=0` for enrichment and structured extraction. Higher only with justification.
- Never let the LLM generate raw SQL — always JSON filter specs that we translate.
- Log prompt version + token counts.

## Tooling etiquette

- Don't commit `.env`, DB files, or parquet caches unless explicitly approved.
- Don't run destructive git commands (`reset --hard`, force push, branch delete) without asking.
- Before marking a phase done, run `pytest` and the relevant CLI command end-to-end.
- When in doubt about blast radius, confirm with the user before acting.

## Review loop

Expect multiple rounds of review on PLAN.md and TASKS.md *before* implementation starts. Do not begin Phase 2+ work until the user signals alignment.
