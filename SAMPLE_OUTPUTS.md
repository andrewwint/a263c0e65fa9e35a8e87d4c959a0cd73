# Sample Outputs

Reviewer-friendly view of the [notebook](notebooks/movie_system.ipynb)'s 8 agent demo prompts + 5 rating-prediction examples. GitHub renders this file natively — no Jupyter required.

All outputs below are real runs of the Strands agent over `us.anthropic.claude-haiku-4-5-20251001-v1:0` on AWS Bedrock. See commit history for the exact code path at each point.

- **Task 1 enrichment** (75 movies, `openai.gpt-oss-20b-1:0`): see the notebook's §2 for prompt + dry-run + consistency check + cost summary (~$0.0064).

- **Task 2 agent** (demos below): five tools — `query_movies`, `get_enriched_movie`, `compare_movies`, `predict_user_rating`, `summarize_user_preferences`. See [`src/tools.py`](src/tools.py) for tool implementations and [`src/prompts/agent_system.py`](src/prompts/agent_system.py) for the system prompt + tool-selection rules + 3 few-shot prediction examples that calibrate the rating predictor.

- **Honest limitations** are called out inline below and rolled up in the notebook's §4.4.

> **Reproducibility note.** Even at `temperature=0`, the agent's final *rendered* answer can vary across re-runs (the tool output is stable; the Claude Haiku summary wrapper picks slightly different phrasings, truncates different details, or — on rare runs — substitutes a culturally famous title for a less-famous matching row). The version below was captured from one end-to-end clean-kernel run. A reviewer running fresh will see ~the same tool-call sequence and the same top-row titles; the prose around them may differ.

---

## Table of contents

1. [Recommend action movies with high revenue and positive sentiment](#1-recommend-action-movies-with-high-revenue-and-positive-sentiment)
2. [Find a dark comedy with a small budget that made money](#2-find-a-dark-comedy-with-a-small-budget-that-made-money)
3. [Summarize preferences for user 42 based on their ratings and movie overviews](#3-summarize-preferences-for-user-42-based-on-their-ratings-and-movie-overviews)
4. [How does The Godfather compare to Goodfellas?](#4-how-does-the-godfather-compare-to-goodfellas)
5. [Compare the 3 highest-grossing 1990s dramas by runtime and effectiveness score](#5-compare-the-3-highest-grossing-1990s-dramas-by-runtime-and-effectiveness-score)
6. [What were the highest-grossing dramas of the 90s?](#6-what-were-the-highest-grossing-dramas-of-the-90s)
7. [Show me movies with effectiveness score >= 8 and budget under $10M](#7-show-me-movies-with-effectiveness-score-8-and-budget-under-10m)
8. [Will user 42 like movie 550?](#8-will-user-42-like-movie-550)
9. [Rating-prediction examples (5 pairs)](#9-rating-prediction-examples-5-pairs)
10. [Prompting techniques (what the LLM actually sees)](#10-prompting-techniques-what-the-llm-actually-sees)

## 1. Recommend action movies with high revenue and positive sentiment

**Tools called (1):** `query_movies`

**Response:**

```
Based on your criteria, I found **1 action movie** with high revenue and positive sentiment in the enriched sample:

**The Golden Child** (1986)
- **Budget:** $25M | **Revenue:** $79.8M | **Runtime:** 94 min
- **Effectiveness Score:** 7/10
- **Why this fits:** High-grossing action film with positive sentiment, featuring mystical adventure and cult-themed storytelling.
- **Themes:** Missing children, mystical powers, cult, booby-trapped chamber

The enriched sample is limited to 75 movies, so this query returned only one result. If you'd like to see more action films with high revenue (without the sentiment filter), or explore other combinations, let me know!
```

---

## 2. Find a dark comedy with a small budget that made money

**Tools called (1):** `query_movies`

**Response:**

```
Great finds! Here are **2 dark comedies** with small budgets that made money:

**Soodhu Kavvum** (2013)
- **Budget:** $310K | **Revenue:** $12M | **Runtime:** 138 min
- **Effectiveness Score:** 9/10
- **Why this fits:** Exceptional ROI on a micro-budget; a comedic thriller about small-time crime and kidnapping with dark humor.
- **Themes:** Kidnapping, rule-breaking, chase, small-time crime, comedic thriller

**The Cherry Orchard** (1999)
- **Budget:** $5 | **Revenue:** $135 | **Runtime:** 141 min
- **Effectiveness Score:** 8/10
- **Why this fits:** Minimal budget with strong thematic depth; explores aristocratic decline and family dysfunction with dark undertones.
- **Themes:** Aristocracy decline, family denial, property loss, class conflict, past vs present

*Soodhu Kavvum* is the standout—a 9/10 effectiveness score on a shoestring budget with a 38x return. Both are enriched-sample films with negative sentiment (dark tone) and proven commercial success.
```

---

## 3. Summarize preferences for user 42 based on their ratings and movie overviews

**Tools called (1):** `summarize_user_preferences`

**Response:**

```
**User 42 Preference Summary**

- **Ratings:** 26 movies | **Mean Rating:** 4.08/5.0
- **Favorite Genres:** Drama, Thriller, Action, Romance, Western
- **Typical Sentiment:** Neutral

**Profile:**
User 42 is an eclectic viewer with a strong appreciation for character-driven dramas and classic thrillers, as evidenced by their perfect ratings for films like *Monsoon Wedding*, *The Passion of Joan of Arc*, and *Sissi* alongside action-packed fare like *Terminator 3* and *5 Card Stud*. They show particular affinity for films with emotional depth or historical/cultural significance, though they're less forgiving of straightforward action sequels (rating *Die Hard 2* and *Rambo III* notably lower). Their 4.08 mean rating suggests they're selective but not overly critical, rewarding films that blend genre entertainment with substantive storytelling.
```

---

## 4. How does The Godfather compare to Goodfellas?

**Tools called (4):** `query_movies, query_movies, query_movies, compare_movies`

**Response:**

```
Here's the comparison of **The Godfather** (1972) vs **GoodFellas** (1990):

| Metric | The Godfather | GoodFellas |
|--------|---------------|-----------|
| **Release Year** | 1972 | 1990 |
| **Budget** | $6M | $25M |
| **Revenue** | $245.1M | $46.8M |
| **Runtime** | 175 min | 145 min |
| **ROI** | 40.8x | 1.9x |

**Key Takeaways:**
- **The Godfather** is the far more commercially successful film, earning over 5× the revenue on a quarter of the budget—a legendary box-office performance.
- **GoodFellas** required a larger budget but still turned a solid profit; it's a more intimate, character-driven crime narrative.
- **The Godfather** is 30 minutes longer, reflecting its epic scope and operatic storytelling.
- Both are crime classics but represent different eras and approaches: *The Godfather* is an institutional saga, while *GoodFellas* is a visceral insider's account.

Note: Neither film is in the enriched sample, so sentiment, themes, and effectiveness scores aren't available for this comparison.
```

---

## 5. Compare the 3 highest-grossing 1990s dramas by runtime and effectiveness score

**Tools called (4):** `query_movies, get_enriched_movie, get_enriched_movie, get_enriched_movie`

**Response:**

```
Here's the comparison of the **3 highest-grossing 1990s dramas** by runtime and effectiveness score:

| Movie | Year | Runtime | Effectiveness Score | Revenue |
|-------|------|---------|----------------------|----------|
| **Titanic** | 1997 | 194 min | *Not available* | $1.85B |
| **The Lion King** | 1994 | 89 min | *Not available* | $788.2M |
| **Forrest Gump** | 1994 | 142 min | *Not available* | $677.9M |

**Note:** Unfortunately, none of these three films are in the enriched 75-movie sample, so effectiveness scores are not available. However, I can tell you:

- **Titanic** is by far the longest and highest-grossing, with an epic 194-minute runtime that matches its sweeping narrative scope.
- **The Lion King** is the shortest at 89 minutes—a lean, animated adventure that still achieved massive commercial success.
- **Forrest Gump** sits in the middle at 142 minutes, balancing narrative ambition with accessibility.

If you'd like to see effectiveness scores, I can search for other 1990s dramas that *are* in the enriched sample, or compare these films on other available metrics like budget and ROI.
```

---

## 6. What were the highest-grossing dramas of the 90s?

**Tools called (1):** `query_movies`

**Response:**

```
Here are the **highest-grossing dramas of the 1990s**:

| Rank | Movie | Year | Revenue | Budget | Runtime |
|------|-------|------|---------|--------|---------|
| 1 | **Titanic** | 1997 | $1.85B | $200M | 194 min |
| 2 | **The Lion King** | 1994 | $788.2M | $45M | 89 min |
| 3 | **Forrest Gump** | 1994 | $677.9M | $55M | 142 min |
| 4 | **The Sixth Sense** | 1999 | $672.8M | $40M | 107 min |
| 5 | **Ghost** | 1990 | $505M | $22M | 127 min |
| 6 | **Twister** | 1996 | $494.5M | $92M | 113 min |
| 7 | **Saving Private Ryan** | 1998 | $481.8M | $70M | 169 min |
| 8 | **Tarzan** | 1999 | $448M | $150M | 88 min |
| 9 | **Mrs. Doubtfire** | 1993 | $441.3M | $25M | 125 min |
| 10 | **Dances with Wolves** | 1990 | $424.2M | $22M | 181 min |

**Standouts:**
- **Titanic** dominates by a massive margin—nearly $1.2B more than #2.
- **The Lion King** and **Forrest Gump** are the only other films to cross $600M.
- **Ghost** and **Mrs. Doubtfire** achieved exceptional ROI on modest budgets ($22M and $25M respectively).
- **The Sixth Sense** (1999) is a late-decade phenomenon, earning $672.8M on just $40M.
```

---

## 7. Show me movies with effectiveness score >= 8 and budget under $10M

**Tools called (1):** `query_movies`

**Response:**

```
Here are **movies with effectiveness score ≥ 8 and budget under $10M**:

| Movie | Year | Budget | Revenue | Runtime | Score | Sentiment | Why This Fits |
|-------|------|--------|---------|---------|-------|-----------|--------------|
| **Jaws** | 1975 | $7M | $470.7M | 124 min | **10** | Negative | Masterpiece thriller; highest effectiveness score with exceptional ROI (67x). |
| **Paranormal Activity 2** | 2010 | $3M | $177.5M | 91 min | **9** | Negative | Horror sequel with phenomenal ROI (59x); low-budget blockbuster. |
| **Soodhu Kavvum** | 2013 | $310K | $12M | 138 min | **9** | Negative | Dark comedic thriller; 38x ROI on micro-budget. |
| **Reservoir Dogs** | 1992 | $1.2M | $14.7M | 99 min | **8** | Negative | Tarantino's debut; crime thriller with 12x ROI. |
| **Transamerica** | 2005 | $1M | $13.4M | 103 min | **8** | Neutral | Character-driven indie; 13x ROI on minimal budget. |
| **A Nightmare on Elm Street 3: Dream Warriors** | 1987 | $5M | $44.8M | 96 min | **8** | Negative | Horror sequel; 9x ROI. |
| **The Return of the Pink Panther** | 1975 | $5M | $41.8M | 113 min | **8** | Neutral | Comedy classic; 8x ROI. |
| **The Kids Are All Right** | 2010 | $3.5M | $34.7M | 106 min | **8** | Positive | Family drama; 10x ROI with positive sentiment. |
| **The Admiral: Roaring Currents** | 2014 | $9.5M | $112.2M | 126 min | **8** | Neutral | Historical epic; 12x ROI. |
| **The Kid Stays in the Picture** | 2002 | $40K | $1.4M | 93 min | **8** | Neutral | Documentary; ultra-micro-budget. |
| **The Cherry Orchard** | 1999 | $5 | $135 | 141 min | **8** | Negative | Theatrical adaptation; minimal budget. |

**Top Picks:**
- **Jaws** is the standout—a 10/10 effectiveness score with legendary commercial success.
- **Paranormal Activity 2** and **Soodhu Kavvum** are exceptional value plays with 9/10 scores.
- **The Kids Are All Right** is the only positive-sentiment film in this set, making it unique.
```

---

## 8. Will user 42 like movie 550?

**Tools called (1):** `predict_user_rating`

**Response:**

```
**Prediction for User 42 and Fight Club (movieId 550):**

- **Predicted Rating:** 3.75 / 5.0
- **Rationale:** User 42's mean rating is 3.85 with strong affinity for Drama (avg 4.17 across films like *Beauty and the Beast*, *Joan of Arc*, *On Guard*, *Mere Brother Ki Dulhan*), but *Fight Club*'s dark psychological thriller tone and male-centric violence narrative diverge from their preference for character-driven or romantic dramas, warranting a slight downward adjustment to 3.75.
- **Based on:** 10 of user 42's prior ratings

**Bottom line:** User 42 will likely find *Fight Club* moderately enjoyable but not a standout—it's outside their typical wheelhouse of emotionally resonant, character-focused stories. They'd probably rate it a solid 3.75, appreciating its craft but missing the dramatic depth they prefer.
```

---

## 9. Rating-prediction examples (5 pairs)

5 (user, movie) pairs where the user has ≥20 other ratings AND the movie is in the 75-movie enriched sample — so we have both prompt context and ground-truth.

**Not an MAE.** n=5 is anecdote, not a metric. The framing is *"does the tool produce sensible predictions with specific rationales?"*

**Result:** 2 exact hits, 3 within 1.0, 5 within 2.5. Mean |delta| ≈ 1.0.

> **Eval note (per AGENTS.md Evaluation hygiene).** An earlier iteration of `predict_user_rating` pulled the user's 10 most recent ratings *including* the target movie. For any pair where the user had already rated the target, the LLM saw ground truth in its own prompt and echoed it — inflating accuracy. Fixed before these numbers were recorded: `AND rt.movieId != ?` in the history query. A unit test (`test_predict_user_rating_no_ground_truth_leak` in `tests/test_tools.py`) now guards against regression.

| user | movie | predicted | actual | delta |
|---:|---|---:|---:|---:|
| 15 | The Next Best Thing | **2.0** | **2.0** | **0.0** |
| 15 | Mere Brother Ki Dulhan | 1.5 | 0.5 | 1.0 |
| 2  | Reservoir Dogs | 2.5 | 4.0 | 1.5 |
| 85 | Transamerica | 3.5 | 1.0 | 2.5 |
| 15 | Star Wars: Episode III — Revenge of the Sith | **2.5** | **2.5** | **0.0** |

**Full rationales for the two exact-hit rows** (strongest evidence the tool reads the user's history and makes use of it rather than regressing to a generic mean):

> **User 15 → *The Next Best Thing* (predicted 2.0, actual 2.0):**
> User 15's mean rating is 2.15, and while they show modest tolerance for comedy (3.0 on *Taxi 3* and *Murder by Death*), *The Next Best Thing*'s drama-heavy tone, emotional custody battle themes, and romance subplot align poorly with their pattern of rating character-driven dramas very low (0.5–2.0), suggesting regression to their baseline with slight downward adjustment for the dramatic weight.

> **User 15 → *Star Wars: Episode III — Revenge of the Sith* (predicted 2.5, actual 2.5):**
> User 15 shows moderate engagement with action-heavy films (*Taxi 3*: 3.0, *The Wild Geese*: 3.5) but consistently rates drama-forward narratives poorly (0.5–2.0), and *Revenge of the Sith*'s heavy dramatic arc centered on a hero's fall and political intrigue aligns more with the latter pattern; the high-budget spectacle and action elements provide modest upside, but the dark, character-driven story pulls the prediction toward the user's mean (2.1) rather than their action-thriller ceiling.

Both rationales reference specific films from the user's history by title and rating — the LLM is reading the history, not fabricating. See the notebook's §3.9 for all 5 rationales.

---

## 10. Prompting techniques (what the LLM actually sees)

The challenge asks to "demonstrate prompting techniques." Three distinct prompt surfaces drive this system — each lives in its own file:

### Task 1 enrichment — structured extraction with genre-relative reasoning

[`src/prompts/enrich.py`](src/prompts/enrich.py). Key technique: the system prompt asks the model to reason about budget/revenue tiers **relative to genre norms** with concrete examples, and it uses good/bad exemplars to steer the `themes` field away from generic labels:

```text
- `budget_tier` and `revenue_tier`: judge relative to norms within the genre,
  not absolute dollars. A $50M budget is "high" for a romance,
  "medium" for a sci-fi tentpole...

- `themes`: 3 to 5 specific, searchable thematic keywords.
  Good: "redemption", "heist", "cold-war paranoia", "coming-of-age", "sibling rivalry"
  Bad:  "drama", "exciting", "story", "action-packed"
```

See the notebook's §2.1 for the prompt rendered against a real movie, and §2.7 for the measured consistency result (categorical fields 97.5% stable at temp=0, themes show ~50% synonym drift per the 10×2 check).

### Task 2 agent — tool-selection rules + few-shot rating calibration

[`src/prompts/agent_system.py`](src/prompts/agent_system.py). Key techniques: explicit tool-selection rules + 3 worked rating-prediction examples that calibrate regression-to-mean behavior so the model doesn't fabricate confident ratings from sparse evidence. Excerpt:

```text
TOOL SELECTION:
- "recommend X" / "find me X" → query_movies with a JSON QueryFilter.
- "compare A and B" / "A vs B" → query_movies by title to get IDs, then compare_movies.
- "highest-grossing dramas of the 90s" → query_movies with
  min_year=1990, max_year=1999, genres=["Drama"], sort_by="revenue_desc".
...

RATING-PREDICTION FEW-SHOT:

Example A
  User history: 5 × heist/crime films rated 4.0–5.0; almost never watches romance.
  Target: a new crime drama, positive sentiment, effectiveness_score 8.
  Predicted: 4.5 — "matches documented crime preference and high-quality enrichment signal"

Example B
  User history: 2.0–3.0 ratings on comedies; 5.0 ratings on psychological thrillers.
  Target: a lighthearted romantic comedy.
  Predicted: 2.5 — "user consistently rates comedies low; genre mismatch with thriller preference"

Example C (regression-to-mean calibration)
  User history: broad, 2.5–4.0 across many genres, mean ≈ 3.4; no dominant pattern.
  Target: an average-effectiveness drama (score 5, neutral sentiment).
  Predicted: 3.5 — "regresses to this user's mean; no specific signal to push higher or lower"
```

### Task 2 tools — docstrings as the LLM-facing contract

[`src/tools.py`](src/tools.py). Each `@tool` function's docstring is the prompt the agent sees for that capability. Key technique: the filter schema for `query_movies` is documented inline in the docstring as a typed JSON shape, so the LLM emits valid JSON that `QueryFilter.model_validate_json()` accepts without the LLM ever writing raw SQL. Excerpt from `query_movies`:

```text
filter_json must be a JSON string matching QueryFilter:
  {
    "genres": ["Action", "Drama"],
    "budget_tier": "low" | "medium" | "high" | null,
    "revenue_tier": "low" | "medium" | "high" | null,
    "sentiment": "positive" | "negative" | "neutral" | null,
    "min_score": 1-10 or null,
    "min_year": int or null,
    ...
    "limit": int 1-50, default 10
  }
```

### Why this split

- **Task 1** is deterministic extraction — one prompt, one schema, no agent. Direct-invoke loop with JSON validation + retry.
- **Task 2** is agentic — the LLM chooses which tool to call. Docstrings carry the per-tool contract; the system prompt carries global routing rules + calibration examples.
- **Tools never let the LLM write SQL.** Filter specs are typed JSON → Pydantic-validated → translated to parameterized SQL server-side.
