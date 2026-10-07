"""A vision-language critic: Gemini looks at screenshots and judges the typography.

Every call returns a `Judgment` with the parsed answer, the token counts and the time it
took. Answers are cached on disk (one JSON line per call), keyed by everything that went
into the call, so a benchmark run can be resumed or re-analyzed without paying twice.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

DEFAULT_MODEL = os.getenv("FONT_CRITIC_MODEL", "gemini-2.5-flash")

# Published paid prices per million tokens, as of 2026-10-07
# (https://ai.google.dev/gemini-api/docs/pricing). Output includes thinking tokens.
PRICES = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
}

ProblemKind = Literal["cut_off_text", "wrapped_label", "icon_shown_as_text", "mixed_fonts",
                      "faked_bold", "overlapping_text", "illegible_text", "other"]

PROBLEM_GUIDE = """\
- cut_off_text: letters or words are hidden because the text doesn't fit its box (cut at an
  edge, half a line missing, a label ending abruptly).
- wrapped_label: a short label that should be on one line (a button, badge, tab, menu item)
  breaks onto two or more lines.
- icon_shown_as_text: an icon appears as a plain word such as "search", "lock" or "check".
- mixed_fonts: some letters or words in one piece of text are in a visibly different typeface.
- faked_bold: bold text looks like the regular weight smeared thicker: blurry, spaced
  oddly, or letter shapes that don't look designed to be bold.
- overlapping_text: text overlaps other text or elements.
- illegible_text: text that is hard to read at its size (too thin, too ornate, too small).
- other: any other clear typographic problem."""

SYSTEM = f"""You are a senior product designer reviewing typography on a web page.
You will be shown screenshots and asked about the page rendered with a candidate font.

Report a problem only if you can actually see it in the candidate screenshot. Do not
guess, and do not report a matter of taste as a problem. If you see none, return an
empty list. Problem kinds:
{PROBLEM_GUIDE}

Scores are integers from 1 (poor) to 5 (excellent):
- readability: how easy the body text and labels are to read.
- hierarchy: how clearly headings, labels and body text are distinguished.
- tone_fit: how well the typeface suits the page's purpose and audience.
- overall: your overall judgment of the candidate font on this page, including any problems.
"""


class Problem(BaseModel):
    kind: ProblemKind
    where: str = Field(description="The visible text of the affected element, quoted.")
    evidence: str = Field(description="What exactly you see, in one sentence.")


class Critique(BaseModel):
    problems: list[Problem]
    readability: int
    hierarchy: int
    tone_fit: int
    overall: int
    summary: str = Field(description="One sentence on how the font suits the page.")


class Preference(BaseModel):
    better: Literal["A", "B"]
    confidence: int = Field(description="1 (a coin flip) to 5 (certain).")
    reason: str


@dataclass
class Judgment:
    key: str
    task: str  # "critique" or "compare"
    model: str
    answer: dict | None
    error: str | None = None
    prompt_tokens: int = 0
    output_tokens: int = 0  # visible answer plus thinking
    seconds: float = 0.0
    meta: dict = field(default_factory=dict)

    @property
    def cost_usd(self) -> float | None:
        if self.model not in PRICES:
            return None
        price_in, price_out = PRICES[self.model]
        return (self.prompt_tokens * price_in + self.output_tokens * price_out) / 1e6


def _clamp_scores(critique: dict) -> dict:
    for name in ("readability", "hierarchy", "tone_fit", "overall"):
        critique[name] = min(5, max(1, int(critique[name])))
    return critique


class Critic:
    """Ask Gemini to critique one render or compare two, with caching and retries."""

    def __init__(self, model: str = DEFAULT_MODEL, *, client=None, cache: Path | None = None,
                 requests_per_minute: float | None = None, concurrency: int = 4):
        self.model = model
        self._client = client
        self.cache = cache
        self._done: dict[str, Judgment] = self._load_cache()
        self._gate = asyncio.Semaphore(concurrency)
        self._interval = 60.0 / requests_per_minute if requests_per_minute else 0.0
        self._next_slot = 0.0
        self._slot_lock = asyncio.Lock()

    @property
    def client(self):
        if self._client is None:  # imported lazily so tests and offline use need no key
            from google import genai
            self._client = genai.Client()
        return self._client

    def _load_cache(self) -> dict[str, Judgment]:
        if not self.cache or not self.cache.exists():
            return {}
        done = {}
        for line in self.cache.read_text(encoding="utf-8").splitlines():
            j = Judgment(**json.loads(line))
            if j.answer is not None:  # failed calls are retried on the next run
                done[j.key] = j
        return done

    def _save(self, judgment: Judgment) -> None:
        if self.cache:
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(judgment), ensure_ascii=False) + "\n")

    async def critique(self, candidate: bytes, *, purpose: str, original: bytes | None = None,
                       checks: list[str] | None = None, repeat: int = 0,
                       meta: dict | None = None) -> Judgment:
        """Judge one render. `original` and `checks` add context (conditions B and C)."""
        parts: list = [f"The page: {purpose}"]
        if original is not None:
            parts += ["Screenshot 1: the page with its ORIGINAL fonts, for reference.",
                      _image(original), "Screenshot 2: the page with the CANDIDATE font."]
        else:
            parts += ["Screenshot: the page with the CANDIDATE font."]
        parts.append(_image(candidate))
        if checks is not None:
            found = "\n".join(f"- {c}" for c in checks) if checks else "- none"
            parts.append("Automated browser checks on the candidate render reported:\n" + found)
        parts.append("Critique the candidate font on this page.")
        return await self._call("critique", parts, Critique, repeat, meta)

    async def compare(self, a: bytes, b: bytes, *, purpose: str, repeat: int = 0,
                      meta: dict | None = None) -> Judgment:
        """Which of two renders of the same page suits it better?"""
        parts = [f"The page: {purpose}",
                 "Here is the same page in two candidate fonts.", "Candidate A:", _image(a),
                 "Candidate B:", _image(b),
                 "Which candidate font suits this page better, considering readability, "
                 "hierarchy, tone and any visible problems? Answer A or B."]
        return await self._call("compare", parts, Preference, repeat, meta)

    async def _call(self, task: str, parts: list, schema: type[BaseModel], repeat: int,
                    meta: dict | None) -> Judgment:
        key = _key(self.model, task, parts, repeat)
        if key in self._done:
            return self._done[key]
        from google.genai import types

        config = types.GenerateContentConfig(system_instruction=SYSTEM,
                                             response_mime_type="application/json",
                                             response_schema=schema)
        judgment = Judgment(key=key, task=task, model=self.model, answer=None,
                            meta={**(meta or {}), "repeat": repeat})
        async with self._gate:
            started = time.perf_counter()
            for attempt in range(6):
                await self._wait_for_slot()
                try:
                    response = await self.client.aio.models.generate_content(
                        model=self.model, contents=parts, config=config)
                    answer = schema.model_validate_json(response.text).model_dump()
                    judgment.answer = _clamp_scores(answer) if task == "critique" else answer
                    usage = response.usage_metadata
                    judgment.prompt_tokens = usage.prompt_token_count or 0
                    judgment.output_tokens = ((usage.candidates_token_count or 0)
                                              + (usage.thoughts_token_count or 0))
                    judgment.error = None
                    break
                except ValidationError as e:  # malformed answer: ask again, it's rare
                    judgment.error = f"invalid answer: {e.errors()[0]['msg']}"
                except Exception as e:
                    judgment.error = f"{type(e).__name__}: {e}"[:300]
                    if not _retryable(e):
                        break
                    await asyncio.sleep(min(60, 2 ** attempt + random.random()))
            judgment.seconds = round(time.perf_counter() - started, 2)
        self._save(judgment)
        if judgment.answer is not None:
            self._done[key] = judgment
        return judgment

    async def _wait_for_slot(self) -> None:
        """Space requests out to stay under a requests-per-minute quota."""
        if not self._interval:
            return
        async with self._slot_lock:
            now = time.monotonic()
            wait = self._next_slot - now
            self._next_slot = max(now, self._next_slot) + self._interval
        if wait > 0:
            await asyncio.sleep(wait)


def _image(png: bytes):
    from google.genai import types
    return types.Part.from_bytes(data=png, mime_type="image/png")


def _key(model: str, task: str, parts: list, repeat: int) -> str:
    h = hashlib.sha256(f"{model}|{task}|{repeat}|{SYSTEM}".encode())
    for part in parts:
        h.update(part.encode() if isinstance(part, str) else part.inline_data.data)
    return h.hexdigest()[:24]


def _retryable(error: Exception) -> bool:
    code = getattr(error, "code", None)
    return code in (429, 500, 502, 503, 504) or "timeout" in str(error).lower()
