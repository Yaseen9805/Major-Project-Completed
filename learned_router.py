"""Learned complexity router (Module 4).

Same interface as router.py's route(), backed by a classifier trained on
real logged routing decisions (see train_router.py) instead of hand-written
rules. Not swapped in by default -- see ROUTER_MODE in config.py -- so it
can be A/B'd against the rule-based router before a full cutover.
"""

import joblib

from router import route as rule_based_route

MODEL_PATH = "router_model.joblib"

_model = None
_load_attempted = False


def _get_model():
    global _model, _load_attempted
    if not _load_attempted:
        _load_attempted = True
        try:
            _model = joblib.load(MODEL_PATH)
        except FileNotFoundError:
            _model = None
    return _model


def is_available() -> bool:
    return _get_model() is not None


def route(query: str) -> str:
    """Return the tier name for a query using the trained classifier.

    Falls back to the rule-based router if no trained model is on disk yet
    (e.g. before train_router.py has been run) -- this router is never
    allowed to hard-fail a request.
    """
    model = _get_model()
    if model is None:
        return rule_based_route(query)
    return model.predict([query])[0]
