"""Trains the learned router (Module 4) on real logged routing decisions.

Pulls (query_text, tier_used) pairs from Postgres -- only genuine routing
decisions (cache_hit=false), so the label reflects an actual model-tier
choice, not a cache reuse. Reports held-out accuracy against the current
rule-based router, then refits on the full dataset for deployment.

Run: python train_router.py
"""

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

import db

MODEL_PATH = "router_model.joblib"
MIN_TRAINING_EXAMPLES = 20


def load_training_data() -> tuple[list[str], list[str]]:
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT query_text, tier_used FROM query_log
                WHERE cache_hit = false AND system = 'adaptive'
                """
            )
            rows = cur.fetchall()
    return [r[0] for r in rows], [r[1] for r in rows]


def build_pipeline() -> Pipeline:
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1)),
            ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )


def main() -> None:
    queries, tiers = load_training_data()
    print(f"Loaded {len(queries)} labeled routing decisions from query_log.")

    if len(queries) < MIN_TRAINING_EXAMPLES:
        raise SystemExit(
            f"Need at least {MIN_TRAINING_EXAMPLES} logged routing decisions to train "
            f"(have {len(queries)}). Run seed_traffic.py against a live API first."
        )

    X_train, X_test, y_train, y_test = train_test_split(
        queries, tiers, test_size=0.25, random_state=42, stratify=tiers
    )

    eval_pipeline = build_pipeline()
    eval_pipeline.fit(X_train, y_train)
    predictions = eval_pipeline.predict(X_test)

    print(f"\nHeld-out accuracy: {accuracy_score(y_test, predictions):.0%} (n={len(y_test)})")
    print(classification_report(y_test, predictions, zero_division=0))

    print("Refitting on the full dataset for deployment...")
    final_pipeline = build_pipeline()
    final_pipeline.fit(queries, tiers)
    joblib.dump(final_pipeline, MODEL_PATH)
    print(f"Saved trained router to {MODEL_PATH}")


if __name__ == "__main__":
    main()
