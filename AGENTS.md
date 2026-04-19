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

## Evaluation hygiene

Bugs that only surface during a live eval run are not "edge cases" — they are usually predictable leaks or thin-data cases that a pre-run review would catch. Treat the first end-to-end eval as part of review, not the final validation.

Rules:

- **Enumerate ground-truth paths before writing eval code.** If you're evaluating a model, write down (1) what goes into the model's prompt and (2) what the ground truth is. Any join, lookup, or history-pull that touches the ground truth is a leak candidate. Exclude it explicitly.
- **Write a test for the leak-adjacent case.** If a prediction tool queries a user's rating history to predict their rating on movie M, write a test where the user has already rated M — verify the prediction isn't just an echo of the known rating.
- **Don't predict on thin evidence with a confident-sounding rationale.** If a prediction function gets <3 rating samples after exclusions, return a structured error (`{"error": "insufficient_history", "n": N}`) instead of fabricating a rationale. The LLM will otherwise write a confident sentence from nothing.
- **Quote exact counts, not vibes.** "2 of 5 exact hits, mean |delta| 1.0" beats "mostly accurate." "1 drift in 40 comparisons" beats "fully deterministic." Sample size matters; n<10 is anecdote.
- **Categorize bugs caught mid-eval honestly in the fix commit.** Was it runtime-only discoverable, or should code review have caught it? If the latter, note what review practice would have caught it. Don't just fix and move on — the framing is a lesson.

Project-local precedent: `predict_user_rating` originally pulled the user's 10 most recent ratings *including the target movie*. For any pair where the user had already rated the movie, the LLM saw the ground-truth answer in its prompt and echoed it. Fix: `AND rt.movieId != ?` in the history query. Category: should have been caught at code review — classic data-leakage pattern in recsys code. A test case for "user has rated the target movie" would have surfaced it without burning eval budget.
