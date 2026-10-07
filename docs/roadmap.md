# Roadmap: from capstone demo to evaluated system

*Font Selection Agent began as my capstone for the Google × Kaggle 5-Day AI Agents
Intensive. This is the plan for turning it into a study of one question: **can an AI
agent be trusted to make a design decision?***

## The idea

An agent that picks fonts makes three claims, and each can be wrong:

1. **"This is what your page looks like with font X."** The render can lie. The font may
   never load, some text may fall back to another font, the browser may fake bold, and
   icons can break.
2. **"Font X is a good fit."** The judgment can be wrong. A vision-language model can be
   confidently wrong about design, sensitive to the order it sees options in, or
   inconsistent from one run to the next.
3. **"So I recommend X."** The decision may be no better than a simple baseline, like
   choosing the most popular font.

Each phase makes one claim trustworthy and **checks it against a truth that doesn't
come from the system itself**: the font catalogue, planted flaws, human judgments. This
is the same method as my Homi case study, where every analysis had to find effects
planted on purpose before it was trusted.

| Phase | Question | Truth it's checked against | Status |
|---|---|---|---|
| 1. Trustworthy rendering | How often does a screenshot show something other than what it claims, and can browser checks catch it? | Planted flaws; the Google Fonts catalogue | **Done** |
| 2. A critic that can see | Can a vision-language model spot typography problems, and is it consistent? | Planted flaws; repeated and order-swapped runs | Next |
| 3. Human study | Does the critic agree with people as often as people agree with each other? | Pairwise human preferences (pre-registered) | Planned |
| 4. Multi-agent v3 | Does an agent that renders and critiques choose better than one that doesn't? | Blind human comparison against baselines (pre-registered) | Planned |
| 5. Ship it | Can other developers use it in their own tools? | Install-and-run checks in CI; a deployed demo | Planned |

## Phase 1: Trustworthy rendering (done)

**Problem.** v1 rewrote the user's source file, slept for fixed times, loaded only the
regular (400) weight, and forced the font onto every element with `* { … !important }`.
It reported success whenever a PNG was written.

**Built:**
- A renderer that **never modifies the user's files**. It applies the font inside the
  browser, requests exactly the weights and styles the page uses, and waits for those
  faces to load.
- **Render verification** through Chrome DevTools (`CSS.getPlatformFontsForNode`): for
  every text element, which font actually drew each glyph.
- **Deterministic layout checks** against a baseline render of the original page:
  cut-off text, buttons and labels that wrap, headings that wrap, sideways scrolling,
  icon fonts that get overridden, and a change in page height.
- The **full Google Fonts catalogue** (1,950 families, a dated snapshot) in place of 40
  hard-coded fonts, with filters for script support and real bold faces, and
  did-you-mean suggestions for renamed fonts.
- A **planted-flaw benchmark** (six flaw types plus four kinds of control, with
  held-out seeds) and a **real-font audit** (120 fonts × 5 pages × 2 screen widths ×
  the v1 and v2 pipelines).
- Tests (offline and network), lint and CI.

**Result:**
- **81.6%** of v1's screenshots had problems caused by the pipeline. v2 had **0%**.
- All real limits of a font were reported.
- The detector passed 470/470 development trials and 468/470 held-out trials.
- **4.2%** of real font renders cut off text.

**Output:** [Case study 1](case-study-rendering.md) and `benchmark/results/`.

## Phase 2: A critic that can see (about 1.5 weeks)

**Question.** Can Gemini, given the screenshots and the Phase 1 check results, judge
whether a font fits a page, and is it reliable enough to use?

- A **critic agent** with a fixed rubric: readability at body size, hierarchy, tone
  fit with the page's purpose, and layout damage. It returns structured output (a
  Pydantic schema) with a short reason per score.
- **Two inputs, compared:** the screenshot alone, and the screenshot plus the
  deterministic check results. *Does grounding the model in measurements change its
  judgments?*
- **Reliability tests, before any human data:**
  - *Planted damage:* does it notice a clipped button or a faked bold that Phase 1
    already knows is there? Recall and false-alarm rate, as in Phase 1.
  - *Consistency:* the same input, run 5 times. Report how much the scores vary.
  - *Position bias:* in pairwise comparisons, swap A and B. How often does the
    choice follow the position instead of the font?
  - *Cost and latency* per judgment.
- Course concepts: structured output, context engineering (which evidence goes into
  the prompt), evaluation.

**Output:** case study 2, "Can a model see bad typography?"

## Phase 3: Human study (about 1.5 weeks, partly waiting for responses)

**Question.** Does the critic agree with people as often as people agree with each
other?

- **Pre-registration first** (like Homi's experiments): hypotheses, primary metric,
  sample size from a power analysis, and the analysis plan, written before any data.
- A small **pairwise voting app** ("which looks better for this page?", shown in
  random order, with the font names hidden). It can reuse the FastAPI and React skills
  from Homi.
- Target: 25–40 raters (colleagues, mentees, designers) and about 800 pairwise votes
  across the 5 pages.
- **Analysis:**
  - *Human–human agreement* (Krippendorff's α) is the ceiling. A critic can't be
    expected to agree with people more than people agree with each other.
  - *Critic–human agreement*, compared with that ceiling and with baselines (random
    choice, "pick the more popular font").
  - *Bradley–Terry rankings* of fonts per page, with bootstrap confidence intervals.
  - *Designers vs non-designers*, if enough raters of each.
- **Kaggle:**
  - publish the dataset (screenshots, check results, votes) as a **Kaggle Dataset**;
  - publish the analysis as a **Kaggle Notebook**.

**Output:** case study 3, the Kaggle dataset and notebook.

## Phase 4: Multi-agent v3 (about 1.5 weeks)

**Question.** Does an agent that looks at its work choose better than one that doesn't?

- An **ADK multi-agent pipeline**:
  1. *Brief* reads the page: its purpose, scripts, current fonts, bold and italic use.
  2. *Retriever* does semantic search over the catalogue (Gemini embeddings of font
     descriptions), e.g. "warm, trustworthy, for a fintech dashboard".
  3. *Renderer* runs candidates in parallel (`ParallelAgent`).
  4. *Critic* is the Phase 2 critic.
  5. A *refine loop* (`LoopAgent`) tries new candidates until enough pass.
  6. Finally the user approves the pick (human in the loop).
- **Memory** of the user's past picks and rejections across sessions.
- **Observability:** traces, and tokens, cost and latency per run.
- **ADK evalsets** that check the agent calls the right tools in the right order.
- **The experiment** (pre-registered, blind). Four ways to choose a font, judged by
  people against each other:
  - (a) the full agent;
  - (b) the same model choosing *without* rendering;
  - (c) the most popular font in the category;
  - (d) a random font from the category.
- Course concepts: multi-agent systems, tools, sessions and memory, context
  engineering, observability, evaluation.

**Output:** case study 4, the agent's design and the ablation result.

## Phase 5: Ship it (about 1 week)

- An **MCP server** exposing `search_fonts`, `render_fonts` and `critique`, so the
  tool works inside Claude Code, Cursor and other MCP clients.
- **Deployment:** Cloud Run (or Vertex AI Agent Engine), with a public demo.
- A **demo video** (about 2 minutes), an architecture diagram, and a final pass on the
  README, summary and case studies.
- An **update to the Kaggle writeup** that links the v2 results, the dataset and the
  notebook.
- Course concepts: deployment, interoperability (MCP; A2A optional).

## How each phase maps to the course

| Course concept (5-Day AI Agents Intensive) | Where it shows up |
|---|---|
| Agent architectures, multi-agent systems | Phase 4 pipeline: sequential, parallel and loop agents |
| Tools and MCP | Phase 1 tools, Phase 5 MCP server |
| Context engineering | Phase 2: what evidence the critic sees |
| Sessions and memory | Phase 4 preference memory |
| Agent quality: evaluation | Phases 1–4: planted flaws, reliability tests, human study, ADK evalsets |
| Agent quality: observability | Phase 4 tracing and per-run cost |
| Prototype to production | Phase 5 deployment |

## Rules I'm keeping throughout

- **Decide before looking.** Each experiment has a written plan before its data exists.
- **Report what failed.** Misses and false alarms go in the case studies, not only wins.
- **Reproducible.** Every number in the docs is regenerated by a command in the repo.
