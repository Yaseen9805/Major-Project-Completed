"""Requires router_model.joblib to already exist -- run train_router.py
against a populated query_log first (see seed_traffic.py)."""

import learned_router


def test_model_is_available():
    assert learned_router.is_available() is True


def test_route_returns_a_valid_tier():
    for query in [
        "What is the capital of Spain?",
        "Explain the causes of World War I in detail.",
        "How does a car engine work?",
    ]:
        assert learned_router.route(query) in ("small", "medium", "large")


def test_falls_back_to_rule_based_when_no_model_on_disk(monkeypatch, tmp_path):
    missing_path = tmp_path / "does_not_exist.joblib"
    monkeypatch.setattr(learned_router, "MODEL_PATH", str(missing_path))
    monkeypatch.setattr(learned_router, "_model", None)
    monkeypatch.setattr(learned_router, "_load_attempted", False)

    assert learned_router.is_available() is False
    assert learned_router.route("What is 2+2?") == "small"
