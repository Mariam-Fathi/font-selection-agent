# Font Selection Agent: project summary

*A one-page overview for reviewers. Details are in the [README](../README.md), the
[case study](case-study-rendering.md) and the [roadmap](roadmap.md).*

## The problem

AI agents are increasingly asked to make judgment calls, not just fetch data. Before
trusting one with a decision, you have to ask: **is what it sees true, is its judgment
sound, and is its choice better than a simple rule?**

I'm studying that question on a small, concrete task: **choosing a font for a web
page.** The task is visual, so it's easy to check, and subjective, so judgment matters.
It began as my capstone for the **Google × Kaggle 5-Day AI Agents Intensive**: an agent
(Google ADK, Gemini) that tries fonts on a developer's real page and shows them
screenshots.

## The story so far

**1. I tested the capstone's own assumption, and it failed.** Every later step depends
on the screenshot labelled "Lora" actually showing Lora. Measured on 38 real fonts and
5 test pages, **81.6% of version 1's screenshots** showed something the font didn't
cause:
- bold that the browser faked, even for families that have a real bold face;
- icons turned into words like `query_stats`.

v1 reported success on all of them, because it had no checks.

**2. I rebuilt the measurement layer.**
- The renderer applies fonts inside the browser and never modifies the user's files.
- It asks Chrome which font drew **each glyph** of each element.
- It compares the layout with the original page, pixel by pixel.

Result: **0%** of renders had problems caused by the pipeline (95% CI 0–1.0%). Real
limits of a font (no bold face, no Arabic glyphs) were reported every time, in 256 of
256 cases.

**3. I tested the checks before trusting them.**
- **Planted flaws:** a benchmark breaks pages in six known ways at known elements and
  includes four kinds of control.
- **It caught my own bugs:**
  - two in the detector (nested text counted twice; a 2px invisible overflow that hid
    real clipping);
  - three in the benchmark itself;
  - one in the renderer, found by the audit (an italic-only font that never loaded).
- **After fixes,** all 470 development trials pass. On **10 held-out seeds run once
  with no changes**, all 280 planted flaws were found and 188 of 190 controls stayed
  clean. Both misses were a real missing punctuation glyph that the control's label
  didn't account for.
- **Agreement with an independent source:** on a bilingual Arabic/English page, the
  verifier agreed with the catalogue's script data on all 234 renders.

**4. Real fonts break real layouts.** Across 1,178 renders of 118 fonts:
- **4.2%** cut off text. That rises to **12% for handwriting fonts on mobile**.
- 22 of 118 fonts broke at least one page.
- Tall fonts overflow fixed-height boxes (58 of 89 clipped elements); wide fonts
  overflow fixed-width labels (31).
- The 200 most popular fonts broke four times less often than the rest (1.2% vs 5.3%).

## What's next

Rendering correctly isn't the same as looking right. The next phases ask whether a
model's *judgment* can be trusted, using the same method: a truth that doesn't come from
the system. ([Roadmap](roadmap.md))

| Phase | Question | Checked against |
|---|---|---|
| 2 | Can a vision-language model spot bad typography, and is it consistent and free of position bias? | Planted damage; repeated and order-swapped runs |
| 3 | Does it agree with people as often as people agree with each other? | A pre-registered pairwise human study, published as a Kaggle dataset and notebook |
| 4 | Does an agent that renders and critiques choose better than one that doesn't? | A blind human comparison against popularity and random baselines |
| 5 | Can other developers use it? | An MCP server and a cloud deployment |

## Methods

Browser automation (Playwright, Chrome DevTools Protocol) · glyph-level render
verification · layout regression testing against a baseline · fault injection with
planted ground truth · positive and negative controls · held-out evaluation · stratified
sampling · Wilson confidence intervals · agreement with an independent source ·
agentic tool design (Google ADK, Gemini) · reproducible pipelines and CI.

## What I took from it

- **Test the assumption everything else stands on.** The capstone looked like it worked.
  Measuring its output showed most screenshots were wrong, and nothing in the demo
  would have revealed it.
- **A benchmark is only useful if it can fail.** The planted-flaw benchmark failed
  first. The misses found real bugs in the detector and in the benchmark itself.
- **Keep data you didn't tune on.** The held-out seeds turned "passes my tests" into
  "passes tests it hasn't seen", and gave an honest 188/190.
- **Separate what you caused from what you can only report.** "Misleading screenshot"
  hid two very different things: pipeline errors, which I can fix, and font
  limitations, which I can only report.
