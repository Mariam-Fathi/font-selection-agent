"""Phase 2 analysis, exactly as pre-registered in docs/preregistration-phase2.md.

    python -m benchmark.analyze_critic        # writes results/phase2_report.md
"""

from __future__ import annotations

import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

import pandas as pd
from scipy.stats import binomtest

from benchmark.analyze import table, wilson
from benchmark.critic_eval import JUDGMENTS, consistency_cases, load_cases
from fontagent.critic import Judgment

RESULTS = Path(__file__).parent / "results"
DAMAGES = ["cut_off_text", "wrapped_label", "icon_shown_as_text", "mixed_fonts", "faked_bold"]
RECALL_BAR, FALSE_ALARM_BAR = 0.80, 0.10  # decision rule 1
ORDER_BAR = 0.80  # decision rule 2
UNSTABLE_BAR = 0.20  # decision rule 3


def load_judgments(path: Path = JUDGMENTS) -> list[Judgment]:
    """The latest answered judgment per call (a failed attempt followed by a retry keeps the retry)."""
    latest: dict[str, Judgment] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        j = Judgment(**json.loads(line))
        if j.answer is not None:
            latest[j.key] = j
    return list(latest.values())


def pct(k: int, n: int) -> str:
    if n == 0:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.0%} (95% CI {lo:.0%} to {hi:.0%})"


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", text.lower()) if len(w) >= 3}


def detection_rows(judgments: list[Judgment], cases: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for j in judgments:
        m = j.meta
        if m.get("stage") != "detect":
            continue
        case = cases[m["case"]]
        kinds = [p["kind"] for p in j.answer["problems"]]
        located = any(words(p["where"]) & words(case["element_text"])
                      for p in j.answer["problems"] if p["kind"] == case["damage"])
        rows.append({"case": case["id"], "page": case["page"], "font": case["font"],
                     "damage": case["damage"] or "clean", "twin": case["clean_twin"],
                     "condition": m["condition"],
                     "detected": case["damage"] in kinds if case["damage"] else None,
                     "located": located if case["damage"] else None,
                     "any_problem": bool(kinds), "overall": j.answer["overall"]})
    return pd.DataFrame(rows)


def q1_q2(df: pd.DataFrame) -> list[str]:
    out = ["## Q1–Q2. Can the model see each kind of damage?", "",
           "*Detected* means the critic reported a problem of the planted kind. A *false alarm* "
           "is any problem reported on a clean render.", ""]
    rows, verdicts = [], []
    for damage in DAMAGES + ["clean"]:
        row = {"damage": damage if damage != "clean" else "clean (false alarms)"}
        for cond in ("A", "B", "C"):
            part = df[(df.damage == damage) & (df.condition == cond)]
            if damage == "clean":
                row[cond] = pct(int(part.any_problem.sum()), len(part))
            else:
                row[cond] = pct(int(part.detected.sum()), len(part))
        rows.append(row)
    out += ["| damage | A: candidate only | B: with original | C: with checks |",
            "|---|---|---|---|"]
    out += [f"| {r['damage']} | {r['A']} | {r['B']} | {r['C']} |" for r in rows]
    out += ["", "**Decision rule 1:** reliable if recall ≥ 80% and that condition's false-alarm "
            "rate ≤ 10%.", ""]
    for cond in ("A", "B", "C"):
        clean = df[(df.damage == "clean") & (df.condition == cond)]
        fa = clean.any_problem.mean() if len(clean) else float("nan")
        reliable = [d for d in DAMAGES
                    if df[(df.damage == d) & (df.condition == cond)].detected.mean() >= RECALL_BAR
                    and fa <= FALSE_ALARM_BAR]
        verdicts.append(f"- **{cond}:** reliable for {', '.join(reliable) or 'no damage type'}"
                        f" (false alarms {fa:.0%}).")
    out += verdicts + [""]
    # Paired A vs B: McNemar's exact test on damaged cases.
    damaged = df[df.damage != "clean"].pivot_table(index="case", columns="condition",
                                                    values="detected", aggfunc="first")
    if {"A", "B"} <= set(damaged.columns):
        both = damaged[["A", "B"]].dropna().astype(bool)
        only_b = int((~both.A & both.B).sum())
        only_a = int((both.A & ~both.B).sum())
        p = binomtest(only_b, only_a + only_b, 0.5).pvalue if only_a + only_b else 1.0
        out += [f"**A vs B (paired, McNemar exact):** {only_b} cases detected only with the "
                f"original, {only_a} only without it; p = {p:.3g}.", ""]
    loc = df[(df.damage != "clean") & (df.detected == True)]  # noqa: E712
    shares = []
    for c in ("A", "B", "C"):
        part = loc[loc.condition == c]
        shares.append(f"{c} {pct(int(part.located.sum()), len(part))}")
    out += ["**Secondary: location.** Of detections, the share whose `where` names the planted "
            "element: " + ", ".join(shares), ""]
    return out


def q3(df: pd.DataFrame) -> list[str]:
    b = df[df.condition == "B"]
    clean = b[b.damage == "clean"].set_index("case").overall
    damaged = b[b.damage != "clean"].copy()
    damaged["clean_overall"] = damaged.twin.map(clean)
    damaged = damaged.dropna(subset=["clean_overall"])
    lower = damaged.overall < damaged.clean_overall
    rows = []
    for damage in DAMAGES:
        part = damaged[damaged.damage == damage]
        drop = (part.clean_overall - part.overall).mean()
        rows.append({"damage": damage, "scored lower than its clean twin":
                     pct(int((part.overall < part.clean_overall).sum()), len(part)),
                     "mean drop in overall": f"{drop:.2f}"})
    return ["## Q3. Does damage lower the score? (condition B)", "",
            f"Across all damage types: {pct(int(lower.sum()), len(damaged))}.", "",
            table(pd.DataFrame(rows)), ""]


def q4(judgments: list[Judgment], cases: list[dict]) -> list[str]:
    chosen = {c["id"]: c for c in consistency_cases(cases)}
    runs: dict[str, list[dict]] = defaultdict(list)
    for j in judgments:
        m = j.meta
        if (m.get("case") in chosen and m.get("condition") == "B"
                and m.get("stage") in ("detect", "consistency")):
            runs[m["case"]].append(j.answer)
    complete = {k: v for k, v in runs.items() if len(v) >= 5}
    if not complete:
        return ["## Q4. Is it consistent?", "", "No complete cases yet.", ""]
    spread, sds, agree, total = 0, [], 0, 0
    for case_id, answers in complete.items():
        scores = [a["overall"] for a in answers]
        spread += max(scores) - min(scores) > 1
        sds.append(statistics.pstdev(scores))
        damage = chosen[case_id]["damage"]
        calls = [(damage in [p["kind"] for p in a["problems"]]) if damage else bool(a["problems"])
                 for a in answers]
        majority = sum(calls) * 2 > len(calls)
        agree += sum(c == majority for c in calls)
        total += len(calls)
    unstable = spread / len(complete)
    rule = ("**Decision rule 3:** more than 20% vary by more than 1 point, so the agent averages "
            "3 repeats." if unstable > UNSTABLE_BAR else
            "**Decision rule 3:** at most 20% vary by more than 1 point, so one score is used.")
    return ["## Q4. Is it consistent? (5 runs of the same input, condition B)", "",
            f"- Cases whose `overall` varies by more than 1 point: {pct(spread, len(complete))}",
            f"- Mean standard deviation of `overall`: {statistics.mean(sds):.2f}",
            f"- Runs whose detection decision matches that case's majority: {pct(agree, total)}",
            "", rule, ""]


def q5(judgments: list[Judgment], cases: dict[str, dict]) -> list[str]:
    answers: dict[tuple, dict] = {}
    for j in judgments:
        m = j.meta
        if m.get("stage") == "compare":
            winner = m["a"] if j.answer["better"] == "A" else m["b"]
            answers[(m["a"], m["b"])] = {"kind": m["pair"], "winner": winner,
                                         "first": j.answer["better"] == "A"}
    seen, rows = set(), []
    for (a, b), ans in answers.items():
        key = frozenset((a, b))
        if key in seen or (b, a) not in answers:
            continue
        seen.add(key)
        other = answers[(b, a)]
        rows.append({"kind": ans["kind"], "consistent": ans["winner"] == other["winner"],
                     "clean_won_both": (ans["kind"] == "clean_vs_damaged"
                                        and ans["winner"] == other["winner"]
                                        and cases[ans["winner"]]["damage"] is None)})
    df = pd.DataFrame(rows)
    firsts = [ans["first"] for ans in answers.values()]
    p_first = binomtest(sum(firsts), len(firsts), 0.5).pvalue if firsts else float("nan")
    out = ["## Q5. Does it favour whichever option comes first?", ""]
    for kind in ("clean_vs_clean", "clean_vs_damaged"):
        part = df[df.kind == kind] if len(df) else df
        out.append(f"- {kind.replace('_', ' ')}: same winner in both orders "
                   f"{pct(int(part.consistent.sum()), len(part)) if len(part) else 'n/a'}")
    cvd = df[df.kind == "clean_vs_damaged"] if len(df) else df
    if len(cvd):
        out.append(f"- clean vs damaged: the clean render won in both orders "
                   f"{pct(int(cvd.clean_won_both.sum()), len(cvd))}")
    out.append(f"- Answers choosing the first option shown: {pct(sum(firsts), len(firsts))}, "
               f"binomial test against 50%: p = {p_first:.3g}")
    if len(df):
        overall = df.consistent.mean()
        out += ["", f"**Decision rule 2:** order consistency is {overall:.0%}, so the agent "
                + ("may ask once." if overall >= ORDER_BAR else
                   "asks in both orders and treats disagreements as ties.")]
    return out + [""]


def q6(judgments: list[Judgment]) -> list[str]:
    rows = []
    for task in ("critique", "compare"):
        js = [j for j in judgments if j.task == task]
        if not js:
            continue
        s = pd.Series
        cost = s([j.cost_usd or 0.0 for j in js])
        rows.append({"task": task, "calls": len(js),
                     "input tokens (mean)": f"{s([j.prompt_tokens for j in js]).mean():,.0f}",
                     "output + thinking tokens (mean)": f"{s([j.output_tokens for j in js]).mean():,.0f}",
                     "cost per call (mean / p95)": f"${cost.mean():.4f} / ${cost.quantile(0.95):.4f}",
                     "seconds (mean / p95)": f"{s([j.seconds for j in js]).mean():.1f} / "
                                             f"{s([j.seconds for j in js]).quantile(0.95):.1f}"})
    total = sum(j.cost_usd or 0.0 for j in judgments)
    return ["## Q6. What does a judgment cost?", "", table(pd.DataFrame(rows)), "",
            f"Total for this evaluation: ${total:.2f} at published paid prices.", ""]


def main() -> None:
    cases = load_cases()
    by_id = {c["id"]: c for c in cases}
    judgments = load_judgments()
    model = judgments[0].model if judgments else "n/a"
    df = detection_rows(judgments, by_id)
    sections = ["# Phase 2 report: can a model see bad typography?", "",
                f"Generated by `python -m benchmark.analyze_critic` from {len(judgments)} "
                f"judgments by `{model}` on {len(cases)} cases. Do not edit by hand.", ""]
    sections += q1_q2(df) + q3(df) + q4(judgments, cases) + q5(judgments, by_id) + q6(judgments)
    report = "\n".join(sections)
    (RESULTS / "phase2_report.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
