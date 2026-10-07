"""Run the Phase 2 critic evaluation (see docs/preregistration-phase2.md).

Every judgment is appended to results/critic_judgments.jsonl as it arrives, and a rerun
skips the ones already there, so a run stopped by a quota can simply be started again.

    python -m benchmark.critic_eval --dry-run          # count the calls, spend nothing
    python -m benchmark.critic_eval --rpm 8            # stay under 8 requests a minute
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import random
from pathlib import Path

from fontagent.critic import DEFAULT_MODEL, Critic

ROOT = Path(__file__).parent
CASES = ROOT / "critic_cases"
JUDGMENTS = ROOT / "results" / "critic_judgments.jsonl"
CONDITIONS = ("A", "B", "C")
REPEATS = 5  # Q4: total runs per consistency case, including the Q1 run
SEED = 11


def load_cases() -> list[dict]:
    return json.loads((CASES / "manifest.json").read_text(encoding="utf-8"))


def consistency_cases(cases: list[dict]) -> list[dict]:
    """Q4: 10 clean and 10 damaged cases, chosen with the pre-registered seed."""
    rng = random.Random(SEED)
    clean = [c for c in cases if c["damage"] is None]
    damaged = [c for c in cases if c["damage"]]
    return rng.sample(clean, 10) + rng.sample(damaged, 10)


def pairs(cases: list[dict]) -> list[tuple[dict, dict, str]]:
    """Q5: every pair of clean fonts on a page, and each damaged render with its twin."""
    clean = [c for c in cases if c["damage"] is None]
    by_id = {c["id"]: c for c in cases}
    out = []
    for page in sorted({c["page"] for c in clean}):
        out += [(a, b, "clean_vs_clean")
                for a, b in itertools.combinations([c for c in clean if c["page"] == page], 2)]
    out += [(by_id[c["clean_twin"]], c, "clean_vs_damaged") for c in cases if c["damage"]]
    return out


def plan(cases: list[dict]) -> list[tuple[str, dict]]:
    """Every call the evaluation makes, as (stage, arguments)."""
    calls = [("detect", {"case": c, "condition": cond}) for c in cases for cond in CONDITIONS]
    calls += [("consistency", {"case": c, "condition": "B", "repeat": r})
              for c in consistency_cases(cases) for r in range(1, REPEATS)]
    for a, b, kind in pairs(cases):
        calls += [("compare", {"first": a, "second": b, "kind": kind}),
                  ("compare", {"first": b, "second": a, "kind": kind})]
    return calls


def _png(name: str) -> bytes:
    return (CASES / name).read_bytes()


async def one(critic: Critic, stage: str, args: dict):
    if stage == "compare":
        a, b = args["first"], args["second"]
        return await critic.compare(_png(a["candidate"]), _png(b["candidate"]),
                                    purpose=a["purpose"],
                                    meta={"stage": stage, "pair": args["kind"],
                                          "a": a["id"], "b": b["id"]})
    case, condition = args["case"], args["condition"]
    return await critic.critique(
        _png(case["candidate"]), purpose=case["purpose"],
        original=_png(case["original"]) if condition in ("B", "C") else None,
        checks=case["checks"] if condition == "C" else None,
        repeat=args.get("repeat", 0),
        meta={"stage": stage, "case": case["id"], "condition": condition})


async def run(model: str, rpm: float | None, concurrency: int, limit: int | None) -> None:
    calls = plan(load_cases())[:limit]
    critic = Critic(model, cache=JUDGMENTS, requests_per_minute=rpm, concurrency=concurrency)
    done = failed = 0

    async def go(stage, args):
        nonlocal done, failed
        judgment = await one(critic, stage, args)
        done += 1
        failed += judgment.answer is None
        if done % 20 == 0 or judgment.answer is None:
            note = f" (last error: {judgment.error})" if judgment.answer is None else ""
            print(f"{done}/{len(calls)} calls, {failed} failed{note}", flush=True)

    await asyncio.gather(*(go(stage, args) for stage, args in calls))
    print(f"Finished: {done - failed} answered, {failed} failed. Rerun to retry failures.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--rpm", type=float, default=None, help="requests per minute cap")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None, help="only the first N calls")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        calls = plan(load_cases())
        stages = {s: sum(1 for st, _ in calls if st == s) for s in ("detect", "consistency", "compare")}
        print(f"{len(calls)} calls: {stages}")
        return
    asyncio.run(run(args.model, args.rpm, args.concurrency, args.limit))


if __name__ == "__main__":
    main()
