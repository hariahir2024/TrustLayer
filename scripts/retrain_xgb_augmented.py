"""
BehaviorShield — XGBoost Augmented Retraining Script (Stream 6C)
Team SOLARIS | CBI Hackathon 2026

Combines real labeled sessions from SQLite (legitimate + intruder)
with the existing 10,000 synthetic training samples to retrain XGBoost
with real behavioral divergence patterns.

Usage:
    python scripts/retrain_xgb_augmented.py

Requirements:
    - At least 20 intruder-labeled sessions in the database
    - Run from the project root directory (not from scripts/)
    - SQLite database must be populated (run the server first, collect data)

Output:
    models/xgboost_fusion_retrained.pkl  (new model — does NOT overwrite original)
    scripts/retrain_results.txt          (accuracy report)
"""

import os
import sys
import json
import pickle
import logging

import numpy as np

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("retrain_xgb")


# =============================================================================
# STEP 1: Load real labeled data from SQLite
# =============================================================================

def load_real_labeled_data() -> tuple:
    """
    Load all sessions with risk scores and intruder labels from SQLite.
    Returns (X_real, y_real) where:
        X_real: ndarray of shape (n, 6) — feature vectors
        y_real: ndarray of shape (n,)   — 0=legitimate, 1=intruder
    """
    import db_sqlite as db
    db.init_db()

    sessions = db.get_labeled_data()
    log.info(f"Found {len(sessions)} labeled sessions in SQLite.")

    X, y = [], []
    for s in sessions:
        # Feature vector (same 6 features as the original XGBoost fusion model)
        # We reconstruct from stored scores + metadata
        score      = s.get("final_score", 0) or 0
        band       = s.get("final_band", "GREEN") or "GREEN"
        device_cls = s.get("device_class", "DESKTOP")

        # Normalize score to [0, 1] for each sub-score proxy
        # (In production you would store per-category scores; for now we derive proxies)
        normalized_score = score / 100.0

        band_risk = {
            "GREEN": 0.1, "AMBER_LOW": 0.3, "AMBER_MID": 0.5,
            "AMBER_HIGH": 0.65, "RED_LOW": 0.75, "RED_HIGH": 0.9, "RED_CRITICAL": 1.0
        }.get(band, 0.5)

        device_risk = 0.0 if device_cls == "DESKTOP" else 0.1

        feature_vector = [
            normalized_score,     # overall_score_norm
            band_risk,            # band_risk_proxy
            normalized_score * 0.62,  # keystroke_score proxy (62% weight)
            normalized_score * 0.25,  # mouse_score proxy (25% weight)
            normalized_score * 0.13,  # metadata_score proxy (13% weight)
            device_risk,          # device_class_risk
        ]

        X.append(feature_vector)
        y.append(int(s.get("is_intruder", 0)))

    X_real = np.array(X, dtype=np.float32)
    y_real = np.array(y, dtype=np.int32)

    n_legit    = int(np.sum(y_real == 0))
    n_intruder = int(np.sum(y_real == 1))
    log.info(f"Real data: {n_legit} legitimate, {n_intruder} intruder sessions.")

    return X_real, y_real


# =============================================================================
# STEP 2: Load original synthetic training data
# =============================================================================

def load_synthetic_data(model_path: str) -> tuple:
    """
    Attempt to load the synthetic training data from the XGBoost model metadata.
    Falls back to generating it if the training set isn't cached.
    """
    synthetic_path = "models/synthetic_training_data.pkl"
    if os.path.exists(synthetic_path):
        with open(synthetic_path, "rb") as f:
            data = pickle.load(f)
        log.info(f"Loaded synthetic training data: {len(data['X'])} samples.")
        return np.array(data["X"], dtype=np.float32), np.array(data["y"], dtype=np.int32)

    # Generate synthetic data if not cached
    log.warning("Synthetic training data not found. Generating 5,000 synthetic samples.")
    return _generate_synthetic_samples(5000)


def _generate_synthetic_samples(n: int) -> tuple:
    """Generate synthetic training samples (legitimate + intruder)."""
    rng = np.random.RandomState(42)
    n_each = n // 2

    # Legitimate users: low scores
    X_legit = np.column_stack([
        rng.uniform(0.0, 0.25, n_each),   # overall score low
        rng.uniform(0.05, 0.20, n_each),  # band proxy low
        rng.uniform(0.0, 0.15, n_each),   # keystroke score low
        rng.uniform(0.0, 0.10, n_each),   # mouse score low
        rng.uniform(0.0, 0.05, n_each),   # metadata score low
        rng.choice([0.0, 0.1], n_each),   # device risk
    ]).astype(np.float32)
    y_legit = np.zeros(n_each, dtype=np.int32)

    # Intruders: higher scores
    X_fraud = np.column_stack([
        rng.uniform(0.45, 1.0, n_each),   # overall score high
        rng.uniform(0.40, 1.0, n_each),   # band proxy high
        rng.uniform(0.30, 1.0, n_each),   # keystroke score high
        rng.uniform(0.20, 0.90, n_each),  # mouse score high
        rng.uniform(0.15, 0.80, n_each),  # metadata score high
        rng.choice([0.0, 0.1, 0.2], n_each),  # device risk
    ]).astype(np.float32)
    y_fraud = np.ones(n_each, dtype=np.int32)

    X = np.vstack([X_legit, X_fraud])
    y = np.concatenate([y_legit, y_fraud])
    return X, y


# =============================================================================
# STEP 3: Combine and retrain
# =============================================================================

def retrain(real_sample_weight: float = 5.0) -> dict:
    """
    Retrain XGBoost using real + synthetic data.
    Real samples are weighted `real_sample_weight` times higher than synthetic.

    Returns evaluation report dict.
    """
    try:
        import xgboost as xgb
    except ImportError:
        log.error("XGBoost not installed. Run: pip install xgboost")
        sys.exit(1)

    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

    # ── Load data ──
    X_real, y_real = load_real_labeled_data()
    n_intruder = int(np.sum(y_real == 1))

    if n_intruder < 20:
        log.error(
            f"Only {n_intruder} intruder sessions found. "
            f"Need at least 20. Label more sessions via the dashboard first."
        )
        sys.exit(1)

    X_syn, y_syn = load_synthetic_data("models/xgboost_fusion.pkl")

    # ── Combine with sample weights ──
    X = np.vstack([X_syn, X_real])
    y = np.concatenate([y_syn, y_real])

    w_syn  = np.ones(len(X_syn))
    w_real = np.full(len(X_real), real_sample_weight)
    weights = np.concatenate([w_syn, w_real])

    # ── Split (stratified, keeping real data in both splits) ──
    X_train, X_test, y_train, y_test, w_train, _ = train_test_split(
        X, y, weights, test_size=0.2, stratify=y, random_state=42
    )

    log.info(f"Training set: {len(X_train)} samples | Test set: {len(X_test)} samples")

    # ── Train XGBoost ──
    pos_count = int(np.sum(y_train == 1))
    neg_count = int(np.sum(y_train == 0))
    scale_pos_weight = neg_count / max(pos_count, 1)

    model = xgb.XGBClassifier(
        n_estimators       = 200,
        max_depth          = 5,
        learning_rate      = 0.05,
        subsample          = 0.8,
        colsample_bytree   = 0.8,
        scale_pos_weight   = scale_pos_weight,
        eval_metric        = "logloss",
        random_state       = 42,
        use_label_encoder  = False,
    )
    model.fit(X_train, y_train, sample_weight=w_train, verbose=True)

    # ── Evaluate ──
    y_pred = model.predict(X_test)
    report = {
        "accuracy":  round(float(accuracy_score(y_test, y_pred)), 4),
        "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
        "recall":    round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
        "f1":        round(float(f1_score(y_test, y_pred, zero_division=0)), 4),
        "train_size": len(X_train),
        "test_size":  len(X_test),
        "real_samples": len(X_real),
        "intruder_sessions": n_intruder,
    }

    log.info("=" * 50)
    log.info("RETRAINING RESULTS")
    log.info(f"  Accuracy:  {report['accuracy']:.1%}")
    log.info(f"  Precision: {report['precision']:.1%}")
    log.info(f"  Recall:    {report['recall']:.1%}")
    log.info(f"  F1 Score:  {report['f1']:.1%}")
    log.info("=" * 50)

    # ── Save retrained model ──
    output_path = "models/xgboost_fusion_retrained.pkl"
    os.makedirs("models", exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(model, f)
    log.info(f"Retrained model saved to: {output_path}")

    # ── Save results report ──
    results_path = "scripts/retrain_results.txt"
    with open(results_path, "w") as f:
        f.write("BehaviorShield XGBoost Retraining Report\n")
        f.write("=" * 50 + "\n")
        for k, v in report.items():
            f.write(f"{k}: {v}\n")
    log.info(f"Results saved to: {results_path}")

    return report


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    log.info("BehaviorShield XGBoost Augmented Retraining")
    log.info("=" * 50)
    retrain(real_sample_weight=5.0)
