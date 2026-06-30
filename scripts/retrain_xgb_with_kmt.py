"""
TRUSTLAYER — XGBoost Retraining Script using KMT Dataset
Team SOLARIS | CBI Hackathon 2026

Parses raw JSON files in behaviour_biometrics_dataset, extracts keystroke
and mouse features using production ml_engine logic, generates fusion
scores, and retrains the XGBoost fusion classifier.

Usage:
    python scripts/retrain_xgb_with_kmt.py
"""

import os
import sys
import json
import pickle
import logging
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

# Path setup
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import ml_engine
import db_sqlite as db
from constants import FEATURES, MODEL_XGBOOST_PKL, MODEL_METADATA_JSON

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("retrain_xgb_kmt")

# Speed up database import by bypassing deep neural network LSTM training
# (we only need the Z-score statistics and Isolation Forest mouse models)
ml_engine._train_individual_keystroke_lstm = lambda *args, **kwargs: None
ml_engine._train_individual_mouse_lstm = lambda *args, **kwargs: None

def map_kmt_key_events(kmt_events):
    """Map raw KMT key pressed/released events to TRUSTLAYER format."""
    mapped = []
    key_to_pos = {}
    pos_counter = 1
    
    for ev in kmt_events:
        key = ev.get("Key") or ev.get("key")
        event_type = ev.get("Event") or ev.get("event")
        epoch_val = ev.get("Epoch") or ev.get("epoch")
        
        if not key or not event_type or not epoch_val:
            continue
            
        key = str(key).lower()
        event_type = str(event_type).lower()
        epoch_ms = float(epoch_val) * 1000.0
        
        if key in ("shift", "tab", "caps lock", "capslock"):
            continue
            
        if key == "backspace":
            mapped.append({
                "timestamp": epoch_ms,
                "event": "down" if (event_type in ("pressed", "down")) else "up",
                "position": -1
            })
            continue
            
        if event_type in ("pressed", "down"):
            # Map pos_counter to 1..11 range using modulo to fit 11-char passphrase boundaries
            pos = ((pos_counter - 1) % 11) + 1
            pos_counter += 1
            key_to_pos[key] = pos
            mapped.append({
                "timestamp": epoch_ms,
                "event": "down",
                "position": pos
            })
        elif event_type in ("released", "up"):
            pos = key_to_pos.get(key, -1)
            if pos != -1:
                mapped.append({
                    "timestamp": epoch_ms,
                    "event": "up",
                    "position": pos
                })
                key_to_pos.pop(key, None)
    return mapped

def map_kmt_mouse_events(kmt_mouse):
    """Map raw KMT mouse movement and click events to TRUSTLAYER format."""
    mapped = []
    for ev in kmt_mouse:
        event_type = ev.get("Event") or ev.get("event")
        epoch_val = ev.get("Epoch") or ev.get("epoch")
        
        if not event_type or not epoch_val:
            continue
            
        event_type = str(event_type).lower()
        epoch_ms = float(epoch_val) * 1000.0
        coords = ev.get("Coordinates") or ev.get("coordinates") or [0, 0]
        
        mapped_event = "move"
        if "press" in event_type or "down" in event_type:
            mapped_event = "click_down"
        elif "release" in event_type or "up" in event_type:
            mapped_event = "click_up"
            
        mapped.append({
            "timestamp": epoch_ms,
            "x": int(coords[0]),
            "y": int(coords[1]),
            "event": mapped_event
        })
    return mapped

def cleanup_kmt_users():
    """Wipe any temporary KMT user profiles and model files from the database."""
    conn = db._get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE username LIKE 'kmt_user_%'")
    cursor.execute("DELETE FROM behavioral_profiles WHERE username LIKE 'kmt_user_%'")
    cursor.execute("DELETE FROM sessions WHERE username LIKE 'kmt_user_%'")
    conn.commit()
    conn.close()
    
    if os.path.exists(db.PROFILES_DIR):
        for f in os.listdir(db.PROFILES_DIR):
            if f.startswith("kmt_user_"):
                try:
                    os.remove(os.path.join(db.PROFILES_DIR, f))
                except Exception:
                    pass
    db._model_cache.clear()
    log.info("Temporary database KMT profiles cleaned up.")

def main():
    log.info("TRUSTLAYER XGBoost Retraining with KMT Dataset")
    log.info("=" * 60)

    dataset_path = os.path.join(PROJECT_ROOT, "datasets", "behaviour_biometrics_dataset", "raw_kmt_dataset")
    if not os.path.exists(dataset_path):
        log.error(f"Dataset path not found: {dataset_path}")
        return

    # Initialize database
    db.init_db()
    
    # Pre-cleanup to ensure a clean state
    cleanup_kmt_users()

    X_real = []
    y_real = []

    run_rng = np.random.RandomState(42)

    user_files = [f for f in os.listdir(dataset_path) if f.startswith("raw_kmt_user_") and f.endswith(".json")]
    log.info(f"Parsing {len(user_files)} user data files...")

    for filename in user_files:
        user_id_str = filename.replace("raw_kmt_user_", "").replace(".json", "")
        username = f"kmt_user_{user_id_str}"
        filepath = os.path.join(dataset_path, filename)
        
        with open(filepath, "r") as f:
            data = json.load(f)

        db.create_user(username)
        
        # --- 1. Enrollment phase (Legitimate tests 1 to 5) ---
        for attempt in range(1, 6):
            test_data = data["true_data"][f"test_{attempt}"]
            key_events = map_kmt_key_events(test_data["key_events"])
            mouse_events = map_kmt_mouse_events(test_data["mouse_events"])
            
            # Extract features
            k_feat = ml_engine.extract_keystroke_features(key_events, field_focus_ts=None)
            timestamps = [e["timestamp"] for e in key_events] + [m["timestamp"] for m in mouse_events]
            session_duration_ms = (max(timestamps) - min(timestamps)) if timestamps else 1000.0
            m_feat = ml_engine.extract_mouse_features(mouse_events, session_duration_ms)
            
            # Save features to DB
            if k_feat:
                db.add_enrollment_sample(username, k_feat, "DESKTOP")
            if m_feat:
                ml_engine.add_mouse_training_sample(username, m_feat, mouse_events, "DESKTOP")

        # Build user baselines
        ml_engine._build_user_keystroke_baseline(username, "DESKTOP")
        ml_engine._train_individual_mouse_model(username, "DESKTOP")

        # --- 2. Legitimate evaluation phase (Legitimate tests 6 to 10) ---
        for attempt in range(6, 11):
            test_data = data["true_data"][f"test_{attempt}"]
            key_events = map_kmt_key_events(test_data["key_events"])
            mouse_events = map_kmt_mouse_events(test_data["mouse_events"])
            
            k_feat = ml_engine.extract_keystroke_features(key_events, field_focus_ts=None)
            timestamps = [e["timestamp"] for e in key_events] + [m["timestamp"] for m in mouse_events]
            session_duration_ms = (max(timestamps) - min(timestamps)) if timestamps else 1000.0
            m_feat = ml_engine.extract_mouse_features(mouse_events, session_duration_ms)

            k_score, _ = ml_engine.score_keystrokes(username, k_feat, key_events)
            m_score, _ = ml_engine.score_mouse(username, m_feat, mouse_events)
            
            # Legitimate session: device matches (90%), low risk time (90%), enrolled
            dev_match = int(run_rng.binomial(n=1, p=0.90))
            tod_risk = int(run_rng.binomial(n=1, p=0.10))
            if dev_match == 1:
                metadata_score = float(run_rng.uniform(0.0, 10.0))
            else:
                metadata_score = float(run_rng.uniform(30.0, 70.0))
                
            vector = [k_score, m_score, metadata_score, 1]
            X_real.append(vector)
            y_real.append(0)

        # --- 3. Intruder evaluation phase (Intruder tests 1 to 10) ---
        for attempt in range(1, 11):
            test_data = data["false_data"][f"test_{attempt}"]
            key_events = map_kmt_key_events(test_data["key_events"])
            mouse_events = map_kmt_mouse_events(test_data["mouse_events"])
            
            k_feat = ml_engine.extract_keystroke_features(key_events, field_focus_ts=None)
            timestamps = [e["timestamp"] for e in key_events] + [m["timestamp"] for m in mouse_events]
            session_duration_ms = (max(timestamps) - min(timestamps)) if timestamps else 1000.0
            m_feat = ml_engine.extract_mouse_features(mouse_events, session_duration_ms)

            k_score, _ = ml_engine.score_keystrokes(username, k_feat, key_events)
            m_score, _ = ml_engine.score_mouse(username, m_feat, mouse_events)

            # Intruder session: device mismatch (50%), high risk time (50%), enrolled
            # Crucially: 50% are same-device takeovers (device_match=1, metadata_score is low)
            dev_match = int(run_rng.binomial(n=1, p=0.50))
            tod_risk = int(run_rng.binomial(n=1, p=0.50))
            if dev_match == 1:
                metadata_score = float(run_rng.uniform(0.0, 10.0))
            else:
                metadata_score = float(run_rng.uniform(30.0, 70.0))
                
            vector = [k_score, m_score, metadata_score, 1]
            X_real.append(vector)
            y_real.append(1)

    X_real = np.array(X_real, dtype=np.float32)
    y_real = np.array(y_real, dtype=np.int32)
    log.info(f"Extracted {len(X_real)} real sessions from KMT dataset.")
    log.info(f"Legitimate samples: {np.sum(y_real == 0)} | Intruder samples: {np.sum(y_real == 1)}")

    # Load synthetic training samples
    # Generate 5,000 synthetic samples to combine with the 1,320 real samples
    log.info("Generating stratified synthetic training samples...")
    rng = np.random.RandomState(42)
    n_syn = 5000
    
    n_clearly_legit = int(n_syn * 0.50)   # label 0 — clearly safe
    n_amber_legit   = int(n_syn * 0.15)   # label 0 — legitimate but elevated (wide overlap zone)
    n_mod_intruder  = int(n_syn * 0.20)   # label 1 — moderate intruder (overlap zone)
    n_red_intruder  = int(n_syn * 0.10)   # label 1 — clear intruder
    n_bot           = n_syn - n_clearly_legit - n_amber_legit - n_mod_intruder - n_red_intruder  # 5%

    # Tier 0: Clearly Legitimate (label 0)
    k_cl  = rng.normal(loc=10.0, scale=5.0,  size=n_clearly_legit)
    m_cl  = rng.normal(loc=13.0, scale=7.0,  size=n_clearly_legit)
    md_cl = rng.normal(loc=3.0,  scale=3.0,  size=n_clearly_legit)
    dev_cl = rng.binomial(n=1, p=0.96, size=n_clearly_legit)
    tod_cl = rng.binomial(n=1, p=0.07, size=n_clearly_legit)
    enr_cl = rng.binomial(n=1, p=0.88, size=n_clearly_legit)
    y_cl   = np.zeros(n_clearly_legit, dtype=np.int32)

    # Tier 1: Amber-Zone Legitimate (label 0)
    k_al  = rng.normal(loc=42.0, scale=14.0, size=n_amber_legit)
    m_al  = rng.normal(loc=68.0, scale=12.0, size=n_amber_legit)
    md_al = rng.normal(loc=5.0,  scale=4.0,  size=n_amber_legit)
    dev_al = rng.binomial(n=1, p=0.78, size=n_amber_legit)
    tod_al = rng.binomial(n=1, p=0.15, size=n_amber_legit)
    enr_al = rng.binomial(n=1, p=0.80, size=n_amber_legit)
    y_al   = np.zeros(n_amber_legit, dtype=np.int32)

    # Tier 2: Moderate Intruder (label 1)
    k_mi  = rng.normal(loc=65.0, scale=12.0, size=n_mod_intruder)
    m_mi  = rng.normal(loc=72.0, scale=10.0, size=n_mod_intruder)
    md_mi = rng.normal(loc=5.0,  scale=4.0,  size=n_mod_intruder)
    dev_mi = rng.binomial(n=1, p=0.70, size=n_mod_intruder)   # same-device takeover is common
    tod_mi = rng.binomial(n=1, p=0.40, size=n_mod_intruder)
    enr_mi = rng.binomial(n=1, p=0.65, size=n_mod_intruder)
    y_mi   = np.ones(n_mod_intruder, dtype=np.int32)

    # Tier 3: Clear Intruder / Red Zone (label 1)
    k_ri  = rng.normal(loc=82.0, scale=7.0,  size=n_red_intruder)
    m_ri  = rng.normal(loc=80.0, scale=7.0,  size=n_red_intruder)
    md_ri = rng.normal(loc=55.0, scale=14.0, size=n_red_intruder)
    dev_ri = rng.binomial(n=1, p=0.06, size=n_red_intruder)
    tod_ri = rng.binomial(n=1, p=0.55, size=n_red_intruder)
    enr_ri = rng.binomial(n=1, p=0.55, size=n_red_intruder)
    y_ri   = np.ones(n_red_intruder, dtype=np.int32)

    # Tier 4: Bot (label 1)
    k_bt  = rng.normal(loc=96.0, scale=2.0,  size=n_bot)
    m_bt  = rng.normal(loc=97.0, scale=1.5,  size=n_bot)
    md_bt = rng.normal(loc=72.0, scale=8.0,  size=n_bot)
    dev_bt = rng.binomial(n=1, p=0.02, size=n_bot)
    tod_bt = rng.binomial(n=1, p=0.28, size=n_bot)
    enr_bt = rng.binomial(n=1, p=0.45, size=n_bot)
    y_bt   = np.ones(n_bot, dtype=np.int32)

    k_scores  = np.clip(np.concatenate([k_cl, k_al, k_mi, k_ri, k_bt]), 0.0, 100.0)
    m_scores  = np.clip(np.concatenate([m_cl, m_al, m_mi, m_ri, m_bt]), 0.0, 100.0)
    md_scores = np.clip(np.concatenate([md_cl, md_al, md_mi, md_ri, md_bt]), 0.0, 100.0)

    dev_matches = np.concatenate([dev_cl, dev_al, dev_mi, dev_ri, dev_bt])
    tod_risks   = np.concatenate([tod_cl, tod_al, tod_mi, tod_ri, tod_bt])
    enrollments = np.concatenate([enr_cl, enr_al, enr_mi, enr_ri, enr_bt])

    X_syn = np.column_stack([k_scores, m_scores, md_scores, enrollments])
    y_syn = np.concatenate([y_cl, y_al, y_mi, y_ri, y_bt])

    # Combine with sample weighting
    X_combined = np.vstack([X_syn, X_real])
    y_combined = np.concatenate([y_syn, y_real])

    # Real KMT samples are weighted 10x higher to make the model prioritize real biometrics
    w_syn = np.ones(len(X_syn))
    w_real = np.full(len(X_real), 10.0)
    w_combined = np.concatenate([w_syn, w_real])

    # Train / test split
    X_train, X_test, y_train, y_test, w_train, _ = train_test_split(
        X_combined, y_combined, w_combined, test_size=0.20, random_state=42, stratify=y_combined
    )

    log.info(f"Training set size: {len(X_train)} | Test set size: {len(X_test)}")
    
    # Train XGBoost
    model = xgb.XGBClassifier(
        n_estimators=150,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric="logloss",
        use_label_encoder=False,
    )
    
    model.fit(X_train, y_train, sample_weight=w_train)

    # Evaluate
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)

    log.info("=" * 60)
    log.info("RETRAINING RESULTS (KMT REAL DATASET + SYNTHETIC)")
    log.info(f"  Accuracy  : {acc*100:.2f}%")
    log.info(f"  Precision : {prec*100:.2f}%")
    log.info(f"  Recall    : {rec*100:.2f}%")
    log.info(f"  F1 Score  : {f1*100:.2f}%")
    log.info("=" * 60)

    # Save model and update metadata
    with open(MODEL_XGBOOST_PKL, "wb") as f:
        pickle.dump(model, f)
    log.info(f"Model saved to: {MODEL_XGBOOST_PKL}")

    # Overwrite models/xgboost_fusion_retrained.pkl as well
    retrained_path = "models/xgboost_fusion_retrained.pkl"
    with open(retrained_path, "wb") as f:
        pickle.dump(model, f)
    log.info(f"Retrained backup saved to: {retrained_path}")

    # Save metadata
    feature_names = ["keystroke_score", "mouse_score", "metadata_score", "is_enrolled"]
    importances = model.feature_importances_.tolist()
    feat_importances_dict = {name: round(imp, 6) for name, imp in zip(feature_names, importances)}
    
    try:
        with open(MODEL_METADATA_JSON, "r") as f:
            meta = json.load(f)
    except Exception:
        meta = {}

    meta["fusion_model"] = {
        "model_file": MODEL_XGBOOST_PKL,
        "trained_at": pd.Timestamp.now().isoformat() + "Z",
        "dataset": "KMT Real Behavioral Biometrics Dataset (1,760 sessions) + 5,000 Synthetic sessions",
        "performance": {
            "accuracy": round(acc, 6),
            "precision": round(prec, 6),
            "recall": round(rec, 6),
            "f1_score": round(f1, 6)
        },
        "feature_importances": feat_importances_dict
    }

    with open(MODEL_METADATA_JSON, "w") as f:
        json.dump(meta, f, indent=2)
    log.info(f"Metadata updated in: {MODEL_METADATA_JSON}")

    # Save text report
    with open("scripts/retrain_results_kmt.txt", "w") as f:
        f.write("TRUSTLAYER KMT Retraining Report\n")
        f.write("=" * 60 + "\n")
        f.write(f"Accuracy  : {acc*100:.2f}%\n")
        f.write(f"Precision : {prec*100:.2f}%\n")
        f.write(f"Recall    : {rec*100:.2f}%\n")
        f.write(f"F1 Score  : {f1*100:.2f}%\n")
        f.write(f"Real Samples: {len(X_real)}\n")
        f.write(f"Synthetic Samples: {len(X_syn)}\n")
        f.write("Feature Importances:\n")
        for k, v in feat_importances_dict.items():
            f.write(f"  {k}: {v*100:.2f}%\n")

    # Cleanup temporary users from SQLite database
    cleanup_kmt_users()
    log.info("Retraining sequence complete successfully!")

if __name__ == "__main__":
    main()
