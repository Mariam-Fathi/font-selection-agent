"""Critic and Phase 2 analysis, with a fake Gemini client: no key, no cost."""

import json
from types import SimpleNamespace

import pytest

from benchmark import analyze_critic
from fontagent.critic import Critic, Judgment

PNG = b"\x89PNG fake image bytes"


class FakeModels:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0

    async def generate_content(self, model, contents, config):
        self.calls += 1
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        usage = SimpleNamespace(prompt_token_count=1000, candidates_token_count=100,
                                thoughts_token_count=300)
        return SimpleNamespace(text=answer, usage_metadata=usage)


def fake_client(*answers):
    models = FakeModels(answers)
    return SimpleNamespace(aio=SimpleNamespace(models=models)), models


def critique_json(problems=(), overall=4):
    return json.dumps({"problems": [{"kind": k, "where": w, "evidence": "seen"} for k, w in problems],
                       "readability": 4, "hierarchy": 4, "tone_fit": 4, "overall": overall,
                       "summary": "fine"})


async def test_critique_is_parsed_costed_and_cached(tmp_path):
    client, models = fake_client(critique_json([("cut_off_text", "Get started")]))
    cache = tmp_path / "judgments.jsonl"
    critic = Critic("gemini-2.5-flash", client=client, cache=cache)
    j = await critic.critique(PNG, purpose="a pricing page", original=PNG)
    assert j.answer["problems"][0]["kind"] == "cut_off_text"
    assert j.output_tokens == 400  # answer plus thinking
    assert j.cost_usd == pytest.approx((1000 * 0.30 + 400 * 2.50) / 1e6)
    again = await critic.critique(PNG, purpose="a pricing page", original=PNG)
    assert again.key == j.key and models.calls == 1  # served from memory
    reloaded = Critic("gemini-2.5-flash", client=client, cache=cache)
    await reloaded.critique(PNG, purpose="a pricing page", original=PNG)
    assert models.calls == 1  # served from the file


async def test_condition_changes_the_cache_key(tmp_path):
    client, models = fake_client(critique_json(), critique_json(), critique_json())
    critic = Critic(client=client)
    a = await critic.critique(PNG, purpose="p")
    b = await critic.critique(PNG, purpose="p", original=PNG)
    c = await critic.critique(PNG, purpose="p", original=PNG, checks=["x is cut off"])
    assert len({a.key, b.key, c.key}) == 3 and models.calls == 3


async def test_scores_are_clamped_and_bad_answers_retried():
    client, models = fake_client("not json", critique_json(overall=9))
    j = await Critic(client=client).critique(PNG, purpose="p")
    assert models.calls == 2 and j.answer["overall"] == 5


async def test_quota_errors_are_retried_and_others_are_not(monkeypatch):
    async def no_sleep(_):
        pass
    monkeypatch.setattr("fontagent.critic.asyncio.sleep", no_sleep)
    quota = Exception("Resource exhausted")
    quota.code = 429
    client, models = fake_client(quota, critique_json())
    assert (await Critic(client=client).critique(PNG, purpose="p")).answer is not None
    bad_key = Exception("API key not valid")
    bad_key.code = 400
    client, models = fake_client(bad_key)
    failed = await Critic(client=client).critique(PNG, purpose="p")
    assert failed.answer is None and models.calls == 1 and "API key" in failed.error


async def test_compare_returns_a_preference():
    answer = json.dumps({"better": "B", "confidence": 4, "reason": "cleaner"})
    client, _ = fake_client(answer)
    j = await Critic(client=client).compare(PNG, PNG, purpose="p")
    assert j.task == "compare" and j.answer["better"] == "B"


def judgment(case, condition, problems, overall=4, stage="detect"):
    answer = json.loads(critique_json(problems, overall))
    return Judgment(key=f"{case}{condition}{stage}", task="critique", model="m", answer=answer,
                    meta={"stage": stage, "case": case, "condition": condition})


def test_detection_scoring_matches_the_preregistered_rules():
    cases = {
        "p__f": {"id": "p__f", "page": "p", "font": "F", "damage": None, "clean_twin": None,
                 "element_text": ""},
        "p__f__cut": {"id": "p__f__cut", "page": "p", "font": "F", "damage": "cut_off_text",
                      "clean_twin": "p__f", "element_text": "Get started"},
    }
    js = [judgment("p__f", "A", [("other", "x")]),  # any problem on clean = false alarm
          judgment("p__f__cut", "A", [("wrapped_label", "Get started")]),  # wrong kind = miss
          judgment("p__f", "B", []),
          judgment("p__f__cut", "B", [("cut_off_text", "the Get started button")], overall=2)]
    df = analyze_critic.detection_rows(js, cases)
    a = df[df.condition == "A"].set_index("damage")
    b = df[df.condition == "B"].set_index("damage")
    assert a.loc["clean", "any_problem"] and not a.loc["cut_off_text", "detected"]
    assert not b.loc["clean", "any_problem"] and b.loc["cut_off_text", "detected"]
    assert b.loc["cut_off_text", "located"]
    q3 = "\n".join(analyze_critic.q3(df))
    assert "1/1 = 100%" in q3  # the damaged twin scored lower
