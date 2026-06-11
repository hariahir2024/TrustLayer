#!/usr/bin/env python3
# =============================================================================
# BehaviorShield — scripts/train_xgb_fusion.py
# Team SOLARIS | Cyber Security Hackathon 2026 | MNNIT Allahabad
# =============================================================================
# Trains an XGBoost classifier to fuse Keystroke, Mouse, and Metadata scores
# into a final, probability-based Risk Score (0-100).
#
# Generates a synthetic dataset of 10,000 samples simulating:
#   - Legitimate sessions (label 0): low scores, device match, low-risk time
#   - Intruder sessions (label 1): elevated timing scores, device mismatch
#   - Bot sessions (label 1): extreme Timing/Mouse scores, device mismatch
#
# Output:
#   models/xgboost_fusion.pkl             ← trained XGBoost model
#   models/model_metadata.json            ← metadata file updated with fusion stats
# =============================================================================

import os
import sys
import json
import time
import datetime
import pickle
import numpy as np
import pandas as pd

# Force UTF-8 output on Windows (prevents cp1252 UnicodeEncodeError)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Path setup ────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score, confusion_matrix

from constants import (
    MODEL_XGBOOST_PKL,
    MODEL_METADATA_JSON,
    MODEL_DIR,
    SYSTEM_VERSION,
    TEAM_NAME,
    HACKATHON,
)

# ── Resolved paths ────────────────────────────────────────────────────────────
MODEL_OUT     = os.path.join(PROJECT_ROOT, MODEL_XGBOOST_PKL)
METADATA_OUT  = os.path.join(PROJECT_ROOT, MODEL_METADATA_JSON)
MODELS_DIR    = os.path.join(PROJECT_ROOT, MODEL_DIR)


# =============================================================================
# 1. DATASET GENERATION
# =============================================================================

def generate_synthetic_fusion_data(n_samples: int = 10000) -> tuple[pd.DataFrame, np.ndarray]:
    """
    Generate a realistic, balanced synthetic dataset to train the fusion classifier.
    
    Features:
      - keystroke_score (0-100)
      - mouse_score (0-100)
      - metadata_score (0-100)
      - device_match (0 or 1)
      - time_of_day_risk (0 or 1)
      - is_enrolled (0 or 1)
      
    Labels:
      - 0: Legitimate session
      - 1: Malicious (Intruder or Bot) session
    """
    print(f"\n{'='*60}")
    print(f"  Generating synthetic session data for risk fusion...")
    
    rng = np.random.default_rng(seed=42)
    
    # 70% Legitimate sessions, 20% Intruder sessions, 10% Bot sessions
    n_legit    = int(n_samples * 0.70)
    n_intruder = int(n_samples * 0.20)
    n_bot      = int(n_samples * 0.10)
    
    # --- Legitimate Sessions (Label 0) ---
    k_legit  = rng.normal(loc=15.0, scale=8.0, size=n_legit)
    m_legit  = rng.normal(loc=18.0, scale=10.0, size=n_legit)
    md_legit = rng.normal(loc=5.0, scale=5.0, size=n_legit)
    
    dev_legit = rng.binomial(n=1, p=0.95, size=n_legit)
    tod_legit = rng.binomial(n=1, p=0.08, size=n_legit)
    enr_legit = rng.binomial(n=1, p=0.85, size=n_legit)
    y_legit   = np.zeros(n_legit, dtype=int)
    
    # --- Intruder Sessions (Label 1) ---
    k_int  = rng.normal(loc=65.0, scale=18.0, size=n_intruder)
    m_int  = rng.normal(loc=60.0, scale=15.0, size=n_intruder)
    md_int = rng.normal(loc=40.0, scale=20.0, size=n_intruder)
    
    dev_int = rng.binomial(n=1, p=0.15, size=n_intruder)
    tod_int = rng.binomial(n=1, p=0.45, size=n_intruder)
    enr_int = rng.binomial(n=1, p=0.60, size=n_intruder)
    y_int   = np.ones(n_intruder, dtype=int)
    
    # --- Bot Sessions (Label 1) ---
    k_bot  = rng.normal(loc=92.0, scale=5.0, size=n_bot)
    m_bot  = rng.normal(loc=95.0, scale=4.0, size=n_bot)
    md_bot = rng.normal(loc=70.0, scale=15.0, size=n_bot)
    
    dev_bot = rng.binomial(n=1, p=0.02, size=n_bot)
    tod_bot = rng.binomial(n=1, p=0.30, size=n_bot)
    enr_bot = rng.binomial(n=1, p=0.50, size=n_bot)
    y_bot   = np.ones(n_bot, dtype=int)
    
    # Concatenate and clip scores to valid [0, 100] bounds
    k_scores  = np.clip(np.concatenate([k_legit, k_int, k_bot]), 0.0, 100.0)
    m_scores  = np.clip(np.concatenate([m_legit, m_int, m_bot]), 0.0, 100.0)
    md_scores = np.clip(np.concatenate([md_legit, md_int, md_bot]), 0.0, 100.0)
    
    dev_matches = np.concatenate([dev_legit, dev_int, dev_bot])
    tod_risks   = np.concatenate([tod_legit, tod_int, tod_bot])
    enrollments = np.concatenate([enr_legit, enr_int, enr_bot])
    y           = np.concatenate([y_legit, y_int, y_bot])
    
    # Shuffle dataset
    indices = rng.permutation(n_samples)
    
    df = pd.DataFrame({
        "keystroke_score":   k_scores[indices],
        "mouse_score":       m_scores[indices],
        "metadata_score":    md_scores[indices],
        "device_match":      dev_matches[indices],
        "time_of_day_risk":  tod_risks[indices],
        "is_enrolled":       enrollments[indices],
    })
    
    y = y[indices]
    
    print(f"  Dataset shape: {df.shape[0]} rows × {df.shape[1]} columns")
    print(f"  Class balance: Legitimate={np.sum(y==0):,}  |  Malicious={np.sum(y==1):,}")
    print(f"{'='*60}\n")
    
    return df, y


# =============================================================================
# 2. SAVE OUTPUTS
# =============================================================================

def save_metadata(
    path:          str,
    accuracy:      float,
    auc_score:     float,
    feature_importances: dict,
    n_samples:     int,
    train_time_sec: float,
) -> None:
    """Save XGBoost model metadata alongside existing LSTMs metadata."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    existing = {}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                existing = json.load(f)
        except Exception:
            pass
            
    existing["fusion_model"] = {
        "model_file":        MODEL_XGBOOST_PKL,
        "trained_at":        datetime.datetime.utcnow().isoformat() + "Z",
        "system_version":    SYSTEM_VERSION,
        "team":              TEAM_NAME,
        "hackathon":         HACKATHON,
        "dataset":           "Synthetic Behavioral Scoring Dataset (10k sessions)",
        "n_training_samples": n_samples,
        "algorithm":         "XGBoost Classifier (XGBClassifier)",
        "performance": {
            "accuracy":            round(accuracy, 6),
            "roc_auc":             round(auc_score, 6),
            "training_time_sec":   round(train_time_sec, 3),
        },
        "feature_importances": feature_importances,
    }
    
    with open(path, "w") as f:
        json.dump(existing, f, indent=2)
        
    print(f"  Metadata updated: {path}")


# =============================================================================
# 3. MAIN
# =============================================================================

def main():
    print(f"\n{'='*60}")
    print(f"  BehaviorShield — XGBoost Risk Fusion Model Training")
    print(f"  Team {TEAM_NAME} | {HACKATHON}")
    print(f"{'='*60}")
    
    # Generate data
    X, y = generate_synthetic_fusion_data(10000)
    
    # Train / test split (80% / 20%)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )
    
    # Create XGBoost Classifier
    # Tuned for fast, deterministic training and high generalization
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric="logloss",
        use_label_encoder=False,
    )
    
    t_start = time.time()
    model.fit(X_train, y_train)
    t_elapsed = time.time() - t_start
    
    # Predict and evaluate
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    
    acc  = accuracy_score(y_test, y_pred)
    auc  = roc_auc_score(y_test, y_prob)
    cm   = confusion_matrix(y_test, y_pred)
    
    print(f"  Training complete in {t_elapsed*1000.1:.1f}ms")
    print(f"\n  Evaluation Metrics:")
    print(f"    Accuracy  : {acc*100:.2f}%")
    print(f"    ROC-AUC   : {auc:.6f}")
    
    print(f"\n  Confusion Matrix:")
    print(f"    True Negatives  (Legit classified as Legit) : {cm[0,0]}")
    print(f"    False Positives (Legit flagged as Fraud)    : {cm[0,1]} (FP rate: {cm[0,1]/np.sum(y_test==0)*100:.2f}%)")
    print(f"    False Negatives (Fraud missed)              : {cm[1,0]}")
    print(f"    True Positives  (Fraud classified as Fraud) : {cm[1,1]}")
    
    print(f"\n  Classification Report:")
    print(classification_report(y_test, y_pred, target_names=["Legitimate", "Malicious"]))
    
    # Extract feature importances
    feature_names = X.columns.tolist()
    importances = model.feature_importances_.tolist()
    feat_importances_dict = {
        name: round(imp, 6) for name, imp in zip(feature_names, importances)
    }
    
    # Sort feature importances
    sorted_importances = sorted(feat_importances_dict.items(), key=lambda item: item[1], reverse=True)
    print("  Feature Importances:")
    for feat, imp in sorted_importances:
        print(f"    {feat:<20} : {imp*100:.2f}%")
    print(f"{'='*60}\n")
    
    # Save the model pickle
    os.makedirs(os.path.dirname(MODEL_OUT), exist_ok=True)
    with open(MODEL_OUT, "wb") as f:
        pickle.dump(model, f)
    print(f"  Model saved: {MODEL_OUT}  ({os.path.getsize(MODEL_OUT)/1024:.2f} KB)")
    
    # Save metadata
    save_metadata(
        path                = METADATA_OUT,
        accuracy            = acc,
        auc_score           = auc,
        feature_importances = feat_importances_dict,
        n_samples           = len(X_train),
        train_time_sec      = t_elapsed,
    )
    
    print(f"\n{'='*60}")
    print(f"  [OK] DONE - XGBoost Risk Fusion Model Training Complete")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
