# Pre-registration: Phase 2, can a model see bad typography?

*Written on 2026-10-07, before any critic judgment was collected. The commit history
shows this file was committed before `benchmark/results/critic_judgments.jsonl` existed.
Changes after data collection will be listed at the end, with reasons.*

## Why

Phase 1 showed that deterministic browser checks can catch measurable defects: cut-off
text, faked bold, missing glyphs. But the agent's real job is a **judgment**: does this
font suit this page? Only a model, or a person, can make that call. Before a model's
judgment is used, it has to pass the same kind of test the checks passed: can it see
damage that is known to be there, and does it stay quiet when there is none?

## Questions

| | Question | Primary metric |
|---|---|---|
| Q1 | Can the model see each kind of damage? | Recall per damage type, and false-alarm rate on clean renders |
| Q2 | Does showing it the original page help? Does giving it the check results help? | Q1's metrics in three conditions (below) |
| Q3 | Does damage lower its scores? | Share of pairs where the damaged render's `overall` score is lower than the clean render's |
| Q4 | Is it consistent? | Agreement of `overall` scores and problem lists over 5 repeats of the same input |
| Q5 | Does it prefer whichever option it sees first? | Agreement of pairwise choices when A and B are swapped |
| Q6 | What does a judgment cost? | Tokens, dollars and seconds per call |

## The critic

- **Model:** `gemini-2.5-flash`, with default temperature and default thinking, which
  is how an agent would normally call it.
- **Output:** structured JSON, enforced by a schema:
  - a list of `problems`, each with a `kind` from a fixed list, `where` (the visible text
    affected) and `evidence`;
  - 1–5 scores for `readability`, `hierarchy`, `tone_fit` and `overall`;
  - a one-sentence `summary`.
- **Problem kinds:** `cut_off_text`, `wrapped_label`, `icon_shown_as_text`,
  `mixed_fonts`, `faked_bold`, `overlapping_text`, `illegible_text`, `other`.
- **The prompt** describes each kind in plain words, says what the page is for (one
  sentence per test page), and tells the model to report only problems it can see.

### Conditions

| Condition | The model sees |
|---|---|
| **A: candidate only** | The page rendered with the font |
| **B: with original** | The page with its original fonts, and the page with the new font |
| **C: with checks** | As in B, plus the Phase 1 check results in plain text |

Condition C is a sanity check, not a test of vision: the check results name the damage.
It measures whether the model reports what it is told without inventing more.

## Cases

Desktop width (1280 px) on the 5 Phase 1 test pages.

- **Clean renders:** 4 fonts per page, 20 cases in all. Fonts are tried in a seeded
  random order (seed 11) and kept if their render is clean:
  - for four pages, from the fonts whose v2 render of that page was `clean` in the
    Phase 1 audit;
  - for the bilingual page, where only one audited font was clean (few cover Arabic),
    from catalogue families with Arabic, Latin and a bold face.
- **Damaged renders:** each clean render, with one flaw planted where the page allows it:

| Damage | How it's planted | Expected difficulty |
|---|---|---|
| `cut_off_text` | A button's box shrunk to half its text width, overflow hidden (Phase 1 planting) | Easy |
| `wrapped_label` | A button narrowed so its label wraps (Phase 1 planting) | Easy |
| `icon_shown_as_text` | The icon font replaced, so icons render as words | Easy |
| `mixed_fonts` | The letters a, e and o in one text element drawn in Times New Roman, which is what a missing glyph looks like | Medium |
| `faked_bold` | Only the font's regular face loaded, so the browser fakes every bold | Hard |

Pages without buttons or icons skip those damages. The exact case count is fixed by the
case builder (`benchmark/critic_cases.py`) before any judgment is collected, and is
reported in the results.

## Analysis plan

- **Q1/Q2, detection.** A damaged case counts as *detected* if the critic reports at
  least one problem of the matching kind. Location is not required, but is reported as
  a secondary metric: the `where` text shares a word with the planted element's text.
  A clean case is a *false alarm* if the critic reports any problem at all.
  - Report recall per damage type and false-alarm rate, each with a Wilson 95% CI, for
    every condition.
  - A vs B, paired on the same case, uses McNemar's exact test.
- **Q3.** For each damaged case paired with its clean case (condition B), the share
  where `overall` is lower, with a 95% CI, and the mean drop.
- **Q4.** 20 cases (10 clean, 10 damaged, chosen with seed 11), condition B, 5 repeats
  each. Report:
  - the share of cases whose `overall` score never varies by more than 1 point;
  - the mean standard deviation of `overall`;
  - the share of repeats where the detection decision matches the majority decision.
- **Q5.** Pairwise "which font suits this page better?" on:
  - all 6 pairs of clean fonts per page (30 pairs);
  - each damaged render against its clean twin (all damaged cases).

  Each pair is asked in both orders. Report:
  - **order consistency**, the share of pairs with the same winner both ways;
  - **first-position rate**, the share of all answers choosing whichever came first
    (0.5 means no bias), with a binomial test.

  For clean-vs-damaged pairs, also report how often the clean render wins in both orders.
- **Q6.** The mean and 95th percentile of tokens, dollars (at the published paid prices
  for the model, as of the run date) and seconds per call.

## Decision rules, fixed now

These decide how Phase 4's agent uses the critic:

1. **Damage detection.** For each damage type, the critic counts as a *reliable
   detector* in a condition if recall ≥ 0.80 **and** the condition's false-alarm rate
   ≤ 0.10. For damage types where it isn't reliable, the agent relies on the
   deterministic checks only, and the critic's problem reports for that type are
   ignored.
2. **Pairwise judgments.** If order consistency is ≥ 0.80, the agent may ask for single
   pairwise judgments. Otherwise every comparison is asked in both orders, and a pair
   whose answers disagree counts as a tie.
3. **Scores.** If more than 20% of the Q4 cases vary by more than 1 point in `overall`,
   the agent averages 3 repeats instead of using one score.

## What would change my mind

If condition A is as good as B, the original screenshot isn't worth its tokens. If the
critic finds `faked_bold` reliably, the most subtle Phase 1 problem would be visible to a
model, which I don't expect. If the false-alarm rate is high in every condition, the
critic is unsuitable for finding defects and is used only for preference judgments,
whose quality Phase 3 tests against people.

## Changes after data collection

*None yet.*
