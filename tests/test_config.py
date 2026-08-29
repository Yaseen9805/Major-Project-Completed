from config import MODEL_TIERS


def test_all_three_tiers_are_genuinely_distinct_models():
    """Regression guard for the prototype's medium/large aliasing bug
    (Module 3) -- each tier must route to its own model."""
    assert len(set(MODEL_TIERS.values())) == 3
