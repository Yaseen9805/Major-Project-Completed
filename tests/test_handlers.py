"""These tests call the real local Ollama models, so they need `ollama serve`
running with qwen2.5:0.5b, phi3:mini, and mistral:7b-instruct-q4_0 pulled --
same requirement as the rest of the prototype.
"""

from adaptive import ask_adaptive
from baseline import ask_baseline
from cache import clear_cache

EXPECTED_KEYS = {"answer", "latency_ms", "tier_used", "cache_hit", "estimated_cost"}


def test_baseline_result_shape():
    result = ask_baseline("What is 2+2?")
    assert set(result.keys()) == EXPECTED_KEYS
    assert result["tier_used"] == "baseline"
    assert result["cache_hit"] is False


def test_adaptive_result_shape_matches_baseline():
    clear_cache()
    result = ask_adaptive("What is 3+3?")
    assert set(result.keys()) == EXPECTED_KEYS
    assert result["tier_used"] in ("small", "medium", "large")
    assert result["cache_hit"] is False


def test_adaptive_cache_hit_on_repeat():
    clear_cache()
    first = ask_adaptive("What is the capital of Germany?")
    second = ask_adaptive("What is the capital of Germany?")

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert second["latency_ms"] < first["latency_ms"]


def test_reasoning_query_reaches_the_large_tier_model():
    """Module 3 regression guard: 'large' must be a genuinely distinct,
    working model -- not the medium/large aliasing bug from the prototype."""
    clear_cache()
    result = ask_adaptive("Explain why the sky is blue and compare it to why sunsets are red.")

    assert result["tier_used"] == "large"
    assert result["cache_hit"] is False
    assert len(result["answer"]) > 0


def test_router_mode_flag_switches_which_router_is_used(monkeypatch):
    """Module 4: ROUTER_MODE must actually gate which router ask_adaptive
    uses, so the learned router can be A/B'd without a hard cutover."""
    import adaptive

    calls = {"rule_based": 0, "learned": 0}
    monkeypatch.setattr(adaptive.router, "route", lambda q: (calls.__setitem__("rule_based", calls["rule_based"] + 1), "small")[1])
    monkeypatch.setattr(adaptive.learned_router, "route", lambda q: (calls.__setitem__("learned", calls["learned"] + 1), "small")[1])

    monkeypatch.setattr(adaptive, "ROUTER_MODE", "rule_based")
    adaptive._route("some query")
    assert calls == {"rule_based": 1, "learned": 0}

    monkeypatch.setattr(adaptive, "ROUTER_MODE", "learned")
    adaptive._route("some query")
    assert calls == {"rule_based": 1, "learned": 1}
