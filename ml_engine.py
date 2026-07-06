# =============================================================================
# TRUSTLAYER — ml_engine.py
# Team SOLARIS | Cyber Security Hackathon 2026 | MNNIT Allahabad
# =============================================================================
# Contains:
#   1. Cold-start loader  — CMU keystroke baseline, BALABIT mouse model
#   2. Feature extractor  — 28 behavioral features from raw SDK events
#   3. Enrollment engine  — build individual baseline from 5 passphrase samples
#   4. Z-Score profiler   — keystroke anomaly scoring
#   5. Isolation Forest   — mouse anomaly scoring
#   6. Metadata scorer    — rule-based session context scoring
#   7. Risk fusion        — combine three category scores (0-100)
#   8. SHAP-lite          — top-N feature contribution breakdown
#   9. Bot detector       — heuristic pre-screening before ML scoring
#  10. Decision engine    — determine action from score + velocity
# =============================================================================

import os
import math
import time
import logging
import json

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

import db_sqlite as db
from constants import (
    FEATURES, KEYSTROKE_FEATURES, MOUSE_FEATURES, METADATA_FEATURES,
    CATEGORY_WEIGHTS, EXPLAINABILITY_TOP_N,
    VELOCITY_JUMP_THRESHOLD,
    AMBER_LOW_MAX, AMBER_MID_MAX, AMBER_HIGH_MAX,
    BOT_SIGNATURES, BOT_SCORE_OVERRIDE,
    DATASET_PATHS, CMU_COLUMNS, BALABIT_COLUMNS,
    get_score_band, get_time_of_day_risk,
    DEVICE_MISMATCH_RISK_POINTS,
    ENROLLMENT_REQUIRED_SAMPLES,
    ENROLLMENT_PASSPHRASE_LENGTH,
    AMBER_LOW_SCORING_INTERVAL_SEC,
    DEFAULT_SCORING_INTERVAL_SEC,
    LSTM_INPUT_SIZE, LSTM_HIDDEN_SIZE, LSTM_NUM_LAYERS, LSTM_LATENT_DIM,
    LSTM_SEQ_LEN_KEYSTROKE, LSTM_SEQ_LEN_MOUSE,
    MODEL_KEYSTROKE_PT, MODEL_MOUSE_PT, MODEL_XGBOOST_PKL, MODEL_METADATA_JSON,
)
import constants as _c

log = logging.getLogger("ml_engine")

# =============================================================================
# MODULE-LEVEL CACHE — loaded once at startup
# =============================================================================
_generic_keystroke_baseline: dict = {}   # {means: {}, stds: {}} from CMU dataset
_generic_mouse_model: IsolationForest = None  # trained on BALABIT data

_keystroke_sequences_cache = {}  # (username, device_class) -> list of np.ndarray
_mouse_sequences_cache = {}      # (username, device_class) -> list of list


import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import pickle

# =============================================================================
# PYTORCH LSTM AUTOENCODER MODEL
# =============================================================================
class LSTMAutoencoder(nn.Module):
    """Sequence-to-sequence LSTM Autoencoder for behavioral modeling."""
    def __init__(
        self,
        input_size:  int = LSTM_INPUT_SIZE,
        hidden_size: int = LSTM_HIDDEN_SIZE,
        num_layers:  int = LSTM_NUM_LAYERS,
        latent_dim:  int = LSTM_LATENT_DIM,
        seq_len:     int = LSTM_SEQ_LEN_KEYSTROKE,
        dropout:     float = 0.1,
    ):
        super().__init__()
        self.seq_len     = seq_len
        self.hidden_size = hidden_size
        self.num_layers  = num_layers
        self.latent_dim  = latent_dim

        # Encoder
        self.encoder_lstm = nn.LSTM(
            input_size  = input_size,
            hidden_size = hidden_size,
            num_layers  = num_layers,
            batch_first = True,
            dropout     = dropout if num_layers > 1 else 0.0,
        )
        self.encoder_proj = nn.Linear(hidden_size, latent_dim)

        # Decoder
        self.decoder_proj = nn.Linear(latent_dim, hidden_size)
        self.decoder_lstm = nn.LSTM(
            input_size  = hidden_size,
            hidden_size = hidden_size,
            num_layers  = num_layers,
            batch_first = True,
            dropout     = dropout if num_layers > 1 else 0.0,
        )
        self.decoder_out  = nn.Linear(hidden_size, input_size)

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        _, (hidden, _) = self.encoder_lstm(x)
        latent = self.encoder_proj(hidden[-1])
        return latent

    def decode(self, latent: torch.Tensor) -> torch.Tensor:
        expanded = self.decoder_proj(latent)
        decoder_input = expanded.unsqueeze(1).expand(-1, self.seq_len, -1)
        output, _ = self.decoder_lstm(decoder_input)
        reconstruction = self.decoder_out(output)
        return reconstruction

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        latent = self.encode(x)
        reconstruction = self.decode(latent)
        return reconstruction, latent


# Global model caches
_generic_keystroke_lstm: LSTMAutoencoder = None
_generic_mouse_lstm:     LSTMAutoencoder = None
_xgb_fusion_model = None
_ml_metadata:            dict = {}


# =============================================================================
# 1. COLD-START DATA LOADERS
# =============================================================================

def load_generic_baselines() -> None:
    """
    Load datasets at startup and build generic population baselines.
    Also loads the trained PyTorch LSTM models and XGBoost fusion model.
    Called once when app.py starts. Results cached in module globals.
    """
    global _generic_keystroke_baseline, _generic_mouse_model
    global _generic_keystroke_lstm, _generic_mouse_lstm, _xgb_fusion_model, _ml_metadata

    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Load generic keystroke baseline (from cached json or CMU dataset)
    cmu_cache_path = os.path.join(base_dir, "models", "cmu_keystroke_baseline.json")
    if os.path.exists(cmu_cache_path):
        try:
            with open(cmu_cache_path, "r", encoding="utf-8") as f:
                _generic_keystroke_baseline = json.load(f)
            log.info("Generic CMU keystroke baseline loaded from cache successfully.")
        except Exception as e:
            log.error(f"Failed to load cached CMU baseline: {e}")
            _generic_keystroke_baseline = _load_cmu_baseline()
    else:
        log.info("Loading generic keystroke baseline from CMU dataset...")
        _generic_keystroke_baseline = _load_cmu_baseline()

    # 2. Load generic mouse Isolation Forest model (from cached pkl or BALABIT dataset)
    mouse_cache_path = os.path.join(base_dir, "models", "mouse_iso_forest_pretrained.pkl")
    if os.path.exists(mouse_cache_path):
        try:
            with open(mouse_cache_path, "rb") as f:
                _generic_mouse_model = pickle.load(f)
            log.info("Generic BALABIT mouse model loaded from cache successfully.")
        except Exception as e:
            log.error(f"Failed to load cached BALABIT mouse model: {e}")
            _generic_mouse_model = _load_balabit_model()
    else:
        log.info("Loading generic mouse model from BALABIT dataset...")
        _generic_mouse_model = _load_balabit_model()

    # 1. Load metadata
    metadata_path = os.path.join(base_dir, MODEL_METADATA_JSON)
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r") as f:
                _ml_metadata = json.load(f)
            log.info("Model metadata loaded successfully.")
        except Exception as e:
            log.error(f"Failed to load model metadata: {e}")

    # 2. Load pre-trained Keystroke LSTM Autoencoder
    keystroke_pt_path = os.path.join(base_dir, MODEL_KEYSTROKE_PT)
    if os.path.exists(keystroke_pt_path):
        try:
            checkpoint = torch.load(keystroke_pt_path, map_location=torch.device("cpu"), weights_only=True)
            cfg = checkpoint["model_config"]
            _generic_keystroke_lstm = LSTMAutoencoder(
                input_size  = cfg["input_size"],
                hidden_size = cfg["hidden_size"],
                num_layers  = cfg["num_layers"],
                latent_dim  = cfg["latent_dim"],
                seq_len     = cfg["seq_len"],
                dropout     = cfg["dropout"],
            )
            _generic_keystroke_lstm.load_state_dict(checkpoint["model_state_dict"])
            _generic_keystroke_lstm.eval()
            log.info("Generic LSTM Keystroke model loaded successfully.")
        except Exception as e:
            log.error(f"Failed to load generic LSTM keystroke model: {e}")

    # 3. Load pre-trained Mouse LSTM Autoencoder
    mouse_pt_path = os.path.join(base_dir, MODEL_MOUSE_PT)
    if os.path.exists(mouse_pt_path):
        try:
            checkpoint = torch.load(mouse_pt_path, map_location=torch.device("cpu"), weights_only=True)
            cfg = checkpoint["model_config"]
            _generic_mouse_lstm = LSTMAutoencoder(
                input_size  = cfg["input_size"],
                hidden_size = cfg["hidden_size"],
                num_layers  = cfg["num_layers"],
                latent_dim  = cfg["latent_dim"],
                seq_len     = cfg["seq_len"],
                dropout     = cfg["dropout"],
            )
            _generic_mouse_lstm.load_state_dict(checkpoint["model_state_dict"])
            _generic_mouse_lstm.eval()
            log.info("Generic LSTM Mouse model loaded successfully.")
        except Exception as e:
            log.error(f"Failed to load generic LSTM mouse model: {e}")

    # 4. Load XGBoost Fusion Classifier
    xgb_path = os.path.join(base_dir, MODEL_XGBOOST_PKL)
    if os.path.exists(xgb_path):
        try:
            with open(xgb_path, "rb") as f:
                _xgb_fusion_model = pickle.load(f)
            log.info("XGBoost Fusion model loaded successfully.")
        except Exception as e:
            log.error(f"Failed to load XGBoost Fusion model: {e}")

    log.info("Generic baselines and deep models loaded and ready.")


def restore_all_user_profiles() -> None:
    """
    Reload all enrolled behavioral profiles from SQLite into ml_engine memory.
    Called at server startup so user baselines survive server restarts.
    Each (username, device_class) profile is loaded into the in-memory cache
    so scoring can happen immediately without re-enrollment.
    """
    import db_sqlite as db
    profiles = db.load_all_profiles()
    for (username, device_class), profile in profiles.items():
        if profile["enrolled"] and profile["keystroke_means"]:
            # Restore the keystroke LSTM from disk if present
            lstm = db.get_keystroke_lstm(username, device_class)
            if lstm:
                log.debug(f"Restored keystroke LSTM: {username}/{device_class}")
    log.info(f"Restored {len(profiles)} enrolled user profile(s) from SQLite.")


def _load_cmu_baseline() -> dict:
    """
    Load CMU keystroke dataset and compute population-level means and stds.
    Used as cold-start baseline for new users who haven't enrolled yet.
    Returns: {"means": {feature: float}, "stds": {feature: float}}
    """
    path = DATASET_PATHS["cmu_keystroke"]

    if not os.path.exists(path):
        log.warning(f"CMU dataset not found at {path}. Using hardcoded fallback.")
        return _hardcoded_keystroke_fallback()

    try:
        df = pd.read_csv(path)

        # CMU hold columns: H.period, H.t, H.i, etc. (11 total)
        # CMU flight cols : UD.period.t, UD.t.i, etc. (10 total)
        hold_cols   = [c for c in df.columns if c.startswith(CMU_COLUMNS["hold_prefix"])]
        flight_cols = [c for c in df.columns if c.startswith(CMU_COLUMNS["flight_prefix"])]

        # Convert to milliseconds (CMU data is in seconds)
        all_holds   = df[hold_cols].values.flatten() * 1000    # → ms
        all_flights = df[flight_cols].values.flatten() * 1000  # → ms

        # Remove negative values (artifact of dataset format)
        all_holds   = all_holds[all_holds > 0]
        all_flights = all_flights[all_flights > 0]

        # Compute typing speed from completion_time proxy
        # CMU: each row is one passphrase rep — total time ≈ sum of all hold + flight cols
        total_times = (df[hold_cols].sum(axis=1) + df[flight_cols].sum(axis=1)) * 1000  # ms
        typing_speeds = ENROLLMENT_PASSPHRASE_LENGTH / (total_times / 1000)  # cps

        means = {
            "mean_hold_time":    float(np.mean(all_holds)),
            "std_hold_time":     float(np.std(all_holds)),
            "mean_flight_time":  float(np.mean(all_flights)),
            "std_flight_time":   float(np.std(all_flights)),
            "typing_speed_cps":  float(np.mean(typing_speeds)),
            "backspace_rate":    0.05,   # population average estimate
            "rhythm_consistency": float(np.std(all_flights) / max(np.mean(all_flights), 1)),
            "burst_ratio":       0.3,    # population average estimate
            "first_key_latency": 350.0,  # ms — population average
            "completion_time":   float(np.mean(total_times)),
            # Positional digraphs — approximate from overall flight time mean
            "digraph_pos_1_2":   float(np.mean(all_flights)),
            "digraph_pos_4_5":   float(np.mean(all_flights) * 1.15),  # name junction (uppercase)
            "digraph_pos_7_8":   float(np.mean(all_flights) * 0.95),  # end-of-name succession
            "digraph_pos_8_9":   float(np.mean(all_flights) * 1.25),  # letter → @ (reach pause)
            "digraph_pos_9_10":  float(np.mean(all_flights) * 1.10),  # @ → digit recovery
        }

        # Population stds — natural variation between people
        stds = {
            "mean_hold_time":    float(np.std(all_holds)),
            "std_hold_time":     float(np.std(all_holds) * 0.5),
            "mean_flight_time":  float(np.std(all_flights)),
            "std_flight_time":   float(np.std(all_flights) * 0.5),
            "typing_speed_cps":  float(np.std(typing_speeds)),
            "backspace_rate":    0.08,
            "rhythm_consistency": 0.15,
            "burst_ratio":       0.2,
            "first_key_latency": 200.0,
            "completion_time":   float(np.std(total_times)),
            "digraph_pos_1_2":   float(np.std(all_flights)),
            "digraph_pos_4_5":   float(np.std(all_flights) * 1.1),
            "digraph_pos_7_8":   float(np.std(all_flights)),
            "digraph_pos_8_9":   float(np.std(all_flights) * 1.2),
            "digraph_pos_9_10":  float(np.std(all_flights)),
        }

        log.info(f"CMU baseline: mean_hold={means['mean_hold_time']:.1f}ms, "
                 f"mean_flight={means['mean_flight_time']:.1f}ms, "
                 f"typing_speed={means['typing_speed_cps']:.2f}cps")
        return {"means": means, "stds": stds}

    except Exception as e:
        log.error(f"Failed to load CMU dataset: {e}. Using fallback.")
        return _hardcoded_keystroke_fallback()


def _hardcoded_keystroke_fallback() -> dict:
    """
    Hardcoded population-level keystroke stats based on known literature values.
    Used if CMU dataset file is missing.
    (Source: CMU DSN-2009 paper summary statistics)
    """
    return {
        "means": {
            "mean_hold_time":    84.0,   # ms
            "std_hold_time":     22.0,
            "mean_flight_time":  115.0,  # ms
            "std_flight_time":   35.0,
            "typing_speed_cps":  4.5,    # characters per second
            "backspace_rate":    0.05,
            "rhythm_consistency": 0.30,
            "burst_ratio":       0.30,
            "first_key_latency": 350.0,
            "completion_time":   2800.0, # ms
            "digraph_pos_1_2":   115.0,
            "digraph_pos_4_5":   132.0,   # name junction slightly slower
            "digraph_pos_7_8":   109.0,
            "digraph_pos_8_9":   145.0,   # @ reach pause
            "digraph_pos_9_10":  118.0,   # @ → digit recovery
        },
        "stds": {
            "mean_hold_time":    28.0,
            "std_hold_time":     14.0,
            "mean_flight_time":  40.0,
            "std_flight_time":   20.0,
            "typing_speed_cps":  2.0,
            "backspace_rate":    0.08,
            "rhythm_consistency": 0.15,
            "burst_ratio":       0.20,
            "first_key_latency": 200.0,
            "completion_time":   900.0,
            "digraph_pos_1_2":   40.0,
            "digraph_pos_4_5":   44.0,
            "digraph_pos_7_8":   40.0,
            "digraph_pos_8_9":   48.0,
            "digraph_pos_9_10":  42.0,
        }
    }


def _load_balabit_model() -> IsolationForest:
    """
    Train a generic Isolation Forest on BALABIT legitimate mouse sessions.
    Used as cold-start mouse model for new users.
    """
    training_path = os.path.join(DATASET_PATHS["balabit_mouse"], "training_files")

    if not os.path.exists(training_path):
        log.warning("BALABIT dataset not found. Using untrained generic mouse model.")
        return _create_default_isolation_forest()

    try:
        vectors = []
        for user_dir in os.listdir(training_path):
            user_path = os.path.join(training_path, user_dir)
            if not os.path.isdir(user_path):
                continue
            for session_file in os.listdir(user_path):
                session_path = os.path.join(user_path, session_file)
                try:
                    df = pd.read_csv(session_path)
                    vec = _extract_mouse_features_from_balabit(df)
                    if vec is not None:
                        vectors.append(vec)
                except Exception:
                    continue

        if len(vectors) < 5:
            log.warning("Too few BALABIT sessions loaded. Using default model.")
            return _create_default_isolation_forest()

        X = np.array(vectors)
        model = IsolationForest(
            n_estimators=100,
            contamination=0.1,   # 10% assumed outlier rate
            random_state=42,
        )
        model.fit(X)
        log.info(f"BALABIT model trained on {len(vectors)} legitimate sessions.")
        return model

    except Exception as e:
        log.error(f"Failed to train BALABIT model: {e}. Using default.")
        return _create_default_isolation_forest()


def _extract_mouse_features_from_balabit(df: pd.DataFrame) -> list | None:
    """Extract 8 mouse feature values from a BALABIT session dataframe."""
    try:
        # BALABIT columns use spaces
        x_col  = BALABIT_COLUMNS["x"]
        y_col  = BALABIT_COLUMNS["y"]
        ts_col = BALABIT_COLUMNS["client_timestamp"]
        btn    = BALABIT_COLUMNS["button"]
        state  = BALABIT_COLUMNS["state"]

        xs  = df[x_col].values.astype(float)
        ys  = df[y_col].values.astype(float)
        ts  = df[ts_col].values.astype(float)

        if len(xs) < 10:
            return None

        # Velocities (px/ms)
        dists = np.sqrt(np.diff(xs)**2 + np.diff(ys)**2)
        dts   = np.diff(ts)
        dts   = np.where(dts == 0, 0.001, dts)  # prevent division by zero
        vels  = dists / dts

        # Accelerations
        accels = np.abs(np.diff(vels)) / dts[1:] if len(vels) > 1 else np.array([0.0])

        # Click events
        if btn in df.columns and state in df.columns:
            clicks = df[df[state].isin(["Pressed", "Released"])]
            click_times = clicks[ts_col].values.astype(float)
            click_count = len(click_times) // 2
            duration_min = (ts[-1] - ts[0]) / 60000  # ms → minutes
            click_freq = click_count / max(duration_min, 0.1)
            click_intervals = np.diff(click_times) if len(click_times) > 1 else np.array([1000.0])
            click_interval_std = float(np.std(click_intervals))
        else:
            click_freq = 0.0
            click_interval_std = 0.0

        # Idle ratio (velocity < 0.01 px/ms)
        idle_frames = np.sum(vels < 0.01)
        idle_ratio = idle_frames / max(len(vels), 1)

        # Trajectory straightness
        total_path = float(np.sum(dists))
        straight   = math.sqrt((xs[-1] - xs[0])**2 + (ys[-1] - ys[0])**2)
        straightness = straight / max(total_path, 0.001)

        return [
            float(np.mean(vels)),            # mouse_mean_velocity
            float(np.std(vels)),             # mouse_std_velocity
            float(np.mean(accels)),          # mouse_mean_acceleration
            float(click_freq),               # click_frequency
            float(click_interval_std),       # click_interval_consistency
            float(idle_ratio),               # idle_time_ratio
            0.0,                             # scroll_speed_mean (not in BALABIT)
            float(straightness),             # trajectory_straightness
        ]
    except Exception:
        return None


def _create_default_isolation_forest() -> IsolationForest:
    """Create a pre-fitted IF with synthetic normal data as emergency fallback."""
    rng = np.random.RandomState(42)
    # Simulate 200 normal mouse sessions
    X_fake = rng.randn(200, 8) * np.array([0.3, 0.2, 0.05, 5, 300, 0.3, 10, 0.2]) \
           + np.array([0.5, 0.3, 0.02, 10, 500, 0.2, 5, 0.5])
    model = IsolationForest(n_estimators=100, contamination=0.1, random_state=42)
    model.fit(X_fake)
    return model


# =============================================================================
# 2. FEATURE EXTRACTION
# =============================================================================

def extract_keystroke_features(key_events: list, field_focus_ts: float = None) -> dict | None:
    """
    Extract 15 keystroke behavioral features from raw keydown/keyup events.

    key_events format (from sdk.js):
        [{"timestamp": float_ms, "event": "down"|"up", "position": int}, ...]

    Returns feature dict or None if insufficient data.
    Privacy: No key identities used — timing only.
    """
    if not key_events or len(key_events) < 4:
        return None

    # Separate down and up events, indexed by position
    downs = {}   # {position: timestamp}
    ups   = {}   # {position: timestamp}
    backspace_count = 0
    total_keys = 0

    for ev in key_events:
        pos = ev.get("position", 0)
        ts  = ev.get("timestamp", 0)
        typ = ev.get("event", "")

        if pos == -1:   # SDK signals backspace with position=-1
            backspace_count += 1
            continue
        if pos < 1 or pos > ENROLLMENT_PASSPHRASE_LENGTH:
            continue

        total_keys += 1
        if typ == "down":
            downs[pos] = ts
        elif typ == "up":
            ups[pos] = ts

    # Need at least positions 1 through ~10 to extract meaningful features
    common_positions = sorted(set(downs.keys()) & set(ups.keys()))
    if len(common_positions) < 5:
        return None

    # Hold times (ms) — how long each key was pressed
    holds = [ups[p] - downs[p] for p in common_positions if ups[p] > downs[p]]

    # Flight times (ms) — gap from key-up to next key-down
    flights = []
    sorted_positions = sorted(common_positions)
    for i in range(len(sorted_positions) - 1):
        curr = sorted_positions[i]
        nxt  = sorted_positions[i + 1]
        if curr in ups and nxt in downs:
            flight = downs[nxt] - ups[curr]
            if flight > 0:
                flights.append((curr, nxt, flight))  # (from_pos, to_pos, ms)

    if not holds or not flights:
        return None

    holds_arr   = np.array(holds)
    flights_arr = np.array([f[2] for f in flights])

    # Timing boundaries
    first_down = min(downs.values())
    last_up    = max(ups.values()) if ups else first_down + 1
    completion = last_up - first_down  # total field time in ms

    if completion <= 0:
        return None

    # Typing speed
    typing_speed_cps = (len(common_positions) / (completion / 1000))

    # Rhythm consistency (coefficient of variation of all inter-key intervals)
    all_intervals = flights_arr
    rhythm_cv = (float(np.std(all_intervals)) / float(np.mean(all_intervals))
                 if np.mean(all_intervals) > 0 else 0.0)

    # Burst ratio: fast keystrokes (<50ms) to slow ones (>150ms)
    fast  = np.sum(flights_arr < 50)
    slow  = np.sum(flights_arr > 150)
    burst_ratio = float(fast) / max(float(slow), 1.0)

    # First key latency
    if field_focus_ts and field_focus_ts < first_down:
        first_key_latency = first_down - field_focus_ts
    else:
        first_key_latency = 300.0  # default estimate

    # Backspace rate
    backspace_rate = backspace_count / max(total_keys, 1)

    # Helper: get digraph flight for a specific position pair
    flight_dict = {(f[0], f[1]): f[2] for f in flights}

    def _get_digraph(p1: int, p2: int) -> float:
        """Return digraph timing for position pair, or mean flight if not found."""
        return float(flight_dict.get((p1, p2), np.mean(flights_arr)))

    return {
        # Aggregate features
        "mean_hold_time":     float(np.mean(holds_arr)),
        "std_hold_time":      float(np.std(holds_arr)),
        "mean_flight_time":   float(np.mean(flights_arr)),
        "std_flight_time":    float(np.std(flights_arr)),
        "typing_speed_cps":   float(typing_speed_cps),
        "backspace_rate":     float(backspace_rate),
        "rhythm_consistency": float(rhythm_cv),
        "burst_ratio":        float(burst_ratio),
        "first_key_latency":  float(first_key_latency),
        "completion_time":    float(completion),
        # Positional digraphs
        "digraph_pos_1_2":    _get_digraph(1, 2),
        "digraph_pos_4_5":    _get_digraph(4, 5),   # name junction — uppercase transition
        "digraph_pos_7_8":    _get_digraph(7, 8),   # end of last name
        "digraph_pos_8_9":    _get_digraph(8, 9),   # letter → @
        "digraph_pos_9_10":   _get_digraph(9, 10),  # @ → digit
    }


def extract_mouse_features(mouse_samples: list, session_duration_ms: float) -> dict | None:
    """
    Extract 8 mouse behavioral features from browser mouse samples.

    mouse_samples format (from sdk.js):
        [{"timestamp": float_ms, "x": int, "y": int,
          "event": "move"|"click_down"|"click_up"|"scroll",
          "scroll_delta": float (for scroll events)}, ...]

    Returns feature dict or None if insufficient data.
    """
    if not mouse_samples or len(mouse_samples) < 5:
        return None

    # Separate by event type
    moves  = [s for s in mouse_samples if s.get("event") == "move"]
    clicks_down = [s for s in mouse_samples if s.get("event") == "click_down"]
    clicks_up   = [s for s in mouse_samples if s.get("event") == "click_up"]
    scrolls     = [s for s in mouse_samples if s.get("event") == "scroll"]

    if len(moves) < 3:
        return None

    # Sort moves by timestamp
    moves_sorted = sorted(moves, key=lambda s: s["timestamp"])
    xs  = np.array([m["x"] for m in moves_sorted], dtype=float)
    ys  = np.array([m["y"] for m in moves_sorted], dtype=float)
    ts  = np.array([m["timestamp"] for m in moves_sorted], dtype=float)

    # Velocities
    dists = np.sqrt(np.diff(xs)**2 + np.diff(ys)**2)
    dts   = np.diff(ts)
    dts   = np.where(dts == 0, 0.1, dts)
    vels  = dists / dts

    # Accelerations
    accels = np.abs(np.diff(vels)) / dts[1:] if len(vels) > 1 else np.array([0.0])

    # Click frequency (clicks per minute)
    duration_min = session_duration_ms / 60000
    click_freq   = len(clicks_down) / max(duration_min, 0.1)

    # Click interval consistency (std of time between successive click-downs)
    if len(clicks_down) > 1:
        click_ts  = sorted([c["timestamp"] for c in clicks_down])
        click_intervals = np.diff(click_ts)
        click_interval_std = float(np.std(click_intervals))
    else:
        click_interval_std = 500.0

    # Idle ratio (mouse stationary — velocity < 0.01 px/ms)
    idle_frames = int(np.sum(vels < 0.01))
    idle_ratio  = idle_frames / max(len(vels), 1)

    # Scroll speed mean
    if scrolls:
        scroll_deltas = [abs(s.get("scroll_delta", 0)) for s in scrolls]
        scroll_speed_mean = float(np.mean(scroll_deltas)) if scroll_deltas else 0.0
    else:
        scroll_speed_mean = 0.0

    # Trajectory straightness
    total_path = float(np.sum(dists))
    straight   = math.sqrt((xs[-1] - xs[0])**2 + (ys[-1] - ys[0])**2)
    straightness = straight / max(total_path, 0.001)

    return {
        "mouse_mean_velocity":        float(np.mean(vels)),
        "mouse_std_velocity":         float(np.std(vels)),
        "mouse_mean_acceleration":    float(np.mean(accels)),
        "click_frequency":            float(click_freq),
        "click_interval_consistency": float(click_interval_std),
        "idle_time_ratio":            float(idle_ratio),
        "scroll_speed_mean":          float(scroll_speed_mean),
        "trajectory_straightness":    float(straightness),
    }


def extract_mouse_features_public(mouse_samples: list, session_duration_ms: float = 3000) -> dict:
    """Public accessor for mouse feature extraction (used by enrollment endpoint)."""
    return extract_mouse_features(mouse_samples, session_duration_ms)


def extract_metadata_features(session: dict, device_fp_enrolled: str | None) -> dict:
    """
    Extract session metadata features from session state.
    All rule-based — no ML scoring here.
    """
    now = time.time()
    hour = int(time.strftime("%H", time.localtime(now)))

    username = session.get("username", "")
    device_class = session.get("device_class", "DESKTOP")

    # Session duration in seconds
    duration_sec = now - session.get("created_at", now)
    duration_min = max(duration_sec / 60, 0.01)

    # Action speed
    action_count = session.get("action_count", 0)
    session_action_speed = action_count / duration_min

    # Transaction initiation delay
    first_action = session.get("first_action_at")
    created_at   = session.get("created_at", now)
    tx_delay = (first_action - created_at) if first_action else 30.0

    # Device fingerprint mismatch logic
    session_fp = session.get("device_fingerprint", "")
    if device_fp_enrolled is None:
        device_mismatch = 0.4   # First device ever for this class — moderate suspicion
    elif session_fp == device_fp_enrolled:
        device_mismatch = 0.0   # Known enrolled device — fully trusted
    else:
        device_mismatch = 1.0   # Unknown device — full risk contribution

    # Per-user time-of-day risk (or population fallback)
    hist = db.get_user_login_hour_history(username, device_class)
    total_logins = sum(hist.values()) if hist else 0
    if total_logins >= 5:
        count = hist.get(str(hour), 0)
        frequency = count / total_logins
        if frequency >= 0.05:
            tod_risk = 0.0
        else:
            tod_risk = 15.0 * (1.0 - (frequency / 0.05))
    else:
        tod_risk = float(get_time_of_day_risk(hour))

    # Click dwell time (passed in session if SDK collects it)
    click_dwell = session.get("click_dwell_mean", 120.0)  # ms — default to human average

    return {
        "time_of_day_risk":            float(tod_risk),
        "device_fingerprint_match":    float(device_mismatch),
        "session_action_speed":        float(session_action_speed),
        "transaction_initiation_delay": float(tx_delay),
        "click_dwell_time_mean":       float(click_dwell),
    }


# =============================================================================
# 3. ENROLLMENT ENGINE
# =============================================================================

def _extract_keystroke_sequence(key_events: list) -> np.ndarray | None:
    """
    Extract a sequence of shape (ENROLLMENT_PASSPHRASE_LENGTH, 2) [hold_ms, flight_ms] for positions 1 to ENROLLMENT_PASSPHRASE_LENGTH.
    """
    if not key_events:
        return None
    
    downs = {}
    ups = {}
    for ev in key_events:
        pos = ev.get("position", 0)
        ts = ev.get("timestamp", 0)
        typ = ev.get("event", "")
        if pos < 1 or pos > ENROLLMENT_PASSPHRASE_LENGTH:
            continue
        if typ == "down":
            downs[pos] = ts
        elif typ == "up":
            ups[pos] = ts
            
    seq = np.zeros((ENROLLMENT_PASSPHRASE_LENGTH, 2), dtype=np.float32)
    
    default_hold = 100.0
    default_flight = 150.0
    
    if _ml_metadata and "keystroke_model" in _ml_metadata:
        norm = _ml_metadata["keystroke_model"].get("normalization", {})
        default_hold = norm.get("hold_mean", default_hold)
        default_flight = norm.get("flight_mean", default_flight)
        
    for p in range(1, ENROLLMENT_PASSPHRASE_LENGTH + 1):
        i = p - 1
        if p in downs and p in ups and ups[p] > downs[p]:
            seq[i, 0] = ups[p] - downs[p]
        else:
            seq[i, 0] = default_hold
            
        if p < ENROLLMENT_PASSPHRASE_LENGTH:
            nxt = p + 1
            if p in ups and nxt in downs:
                seq[i, 1] = downs[nxt] - ups[p]
            else:
                seq[i, 1] = default_flight
        else:
            seq[i, 1] = 0.0
            
    return seq


def _train_individual_keystroke_lstm(username: str, device_class: str = "DESKTOP") -> None:
    """
    Fine-tune the generic keystroke LSTM autoencoder on the user's enrollment sequences.
    """
    cache_key = (username, device_class)
    seq_list = _keystroke_sequences_cache.get(cache_key, [])
    if not seq_list:
        return
        
    sequences = np.array(seq_list, dtype=np.float32)
    
    if _ml_metadata and "keystroke_model" in _ml_metadata:
        norm = _ml_metadata["keystroke_model"]["normalization"]
        h_mean, h_std = norm["hold_mean"], norm["hold_std"]
        f_mean, f_std = norm["flight_mean"], norm["flight_std"]
        sequences[:, :, 0] = (sequences[:, :, 0] - h_mean) / h_std
        sequences[:, :, 1] = (sequences[:, :, 1] - f_mean) / f_std
        
    model = LSTMAutoencoder(
        input_size=LSTM_INPUT_SIZE,
        hidden_size=LSTM_HIDDEN_SIZE,
        num_layers=LSTM_NUM_LAYERS,
        latent_dim=LSTM_LATENT_DIM,
        seq_len=LSTM_SEQ_LEN_KEYSTROKE,
    )
    if _generic_keystroke_lstm is not None:
        model.load_state_dict(_generic_keystroke_lstm.state_dict())
        
    # Freeze encoder to prevent overfitting on few samples
    for param in model.encoder_lstm.parameters():
        param.requires_grad = False
    for param in model.encoder_proj.parameters():
        param.requires_grad = False
        
    model.train()
    # Optimize only unfrozen decoder parameters
    optimizer = torch.optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=0.0005)
    criterion = nn.MSELoss()
    
    # Augment training sequences with slight Gaussian noise
    augmented_seqs = []
    for seq in sequences:
        augmented_seqs.append(seq)
        for _ in range(3):
            noise = np.random.normal(0, 0.02, seq.shape)
            augmented_seqs.append(seq + noise)
    augmented = np.array(augmented_seqs, dtype=np.float32)
    
    x_tensor = torch.tensor(augmented, dtype=torch.float32)
    for epoch in range(15):
        optimizer.zero_grad()
        recon, _ = model(x_tensor)
        loss = criterion(recon, x_tensor)
        loss.backward()
        optimizer.step()
        
    model.eval()
    db.save_keystroke_lstm(username, model, device_class)
    log.info(f"Individual keystroke LSTM fine-tuned and saved for {username} ({device_class}).")


def process_enrollment_sample(username: str, key_events: list,
                               field_focus_ts: float = None, device_class: str = "DESKTOP") -> dict:
    """
    Process one passphrase typing attempt during enrollment.
    Returns {"count": int, "complete": bool, "message": str}
    """
    features = extract_keystroke_features(key_events, field_focus_ts)

    if features is None:
        profile = db.get_behavioral_profile(username, device_class)
        return {
            "count":    profile["enrollment_count"] if profile else 0,
            "complete": False,
            "message":  "Could not extract features — please type the full passphrase",
        }

    if not db.user_exists(username):
        db.create_user(username)

    # Store raw sequence for LSTM training
    seq = _extract_keystroke_sequence(key_events)
    if seq is not None:
        cache_key = (username, device_class)
        if cache_key not in _keystroke_sequences_cache:
            _keystroke_sequences_cache[cache_key] = []
        _keystroke_sequences_cache[cache_key].append(seq)

    count = db.add_enrollment_sample(username, features, device_class)

    if count >= ENROLLMENT_REQUIRED_SAMPLES:
        _build_user_keystroke_baseline(username, device_class)
        try:
            _train_individual_keystroke_lstm(username, device_class)
        except Exception as e:
            log.error(f"Failed to train individual keystroke LSTM: {e}")
            
        return {
            "count":    count,
            "complete": True,
            "message":  f"Enrollment complete! Baseline built from {count} samples.",
        }

    remaining = ENROLLMENT_REQUIRED_SAMPLES - count
    return {
        "count":    count,
        "complete": False,
        "message":  f"Sample {count}/{ENROLLMENT_REQUIRED_SAMPLES} recorded. {remaining} more needed.",
    }


def _build_user_keystroke_baseline(username: str, device_class: str = "DESKTOP") -> None:
    """
    Compute per-feature mean and std from all enrollment samples.
    Apply MIN_STD_FLOOR to prevent division-by-zero in Z-Score engine.
    """
    profile = db.get_behavioral_profile(username, device_class)
    if not profile or not profile.get("enrollment_seqs"):
        return

    samples = profile["enrollment_seqs"]
    means, stds = {}, {}

    for feature_name in KEYSTROKE_FEATURES:
        values = [s[feature_name] for s in samples if feature_name in s]
        if not values:
            # Fallback to generic baseline
            means[feature_name] = _generic_keystroke_baseline["means"].get(feature_name, 0.0)
            stds[feature_name]  = _generic_keystroke_baseline["stds"].get(feature_name, 50.0)
            continue

        computed_mean = float(np.mean(values))
        computed_std  = float(np.std(values))

        # Apply MIN_STD_FLOOR — critical safety net
        floor = FEATURES[feature_name]["min_std_floor"]
        safe_std = max(computed_std, floor)

        means[feature_name] = computed_mean
        stds[feature_name]  = safe_std

    db.save_keystroke_baseline(username, means, stds, device_class)
    log.info(f"Baseline built for {username}: "
             f"hold={means.get('mean_hold_time', 0):.1f}ms, "
             f"flight={means.get('mean_flight_time', 0):.1f}ms")

    # --- B1: Persist newly-built baseline to SQLite immediately ---
    import db_sqlite
    db_sqlite.save_keystroke_baseline(username, means, stds, device_class="DESKTOP")


def _extract_mouse_sequences(mouse_samples: list) -> list[np.ndarray]:
    """
    Extract multiple sequences of shape (50, 2) from raw mouse events.
    Returns a list of sequence arrays.
    """
    if not mouse_samples:
        return []
        
    moves = [s for s in mouse_samples if s.get("event") == "move"]
    if len(moves) < 52:
        return []
        
    moves_sorted = sorted(moves, key=lambda s: s["timestamp"])
    xs = np.array([m["x"] for m in moves_sorted], dtype=float)
    ys = np.array([m["y"] for m in moves_sorted], dtype=float)
    ts = np.array([m["timestamp"] for m in moves_sorted], dtype=float)
    
    # Velocities (px/ms)
    dists = np.sqrt(np.diff(xs)**2 + np.diff(ys)**2)
    dts   = np.diff(ts)
    dts   = np.where(dts < 5.0, 5.0, dts)
    vels  = dists / dts
    
    # Accelerations (px/ms^2)
    accels = np.abs(np.diff(vels)) / dts[1:]
    
    # Match lengths to N-2
    vels_matched = vels[:-1]
    
    # Clip outliers
    vels_matched = np.clip(vels_matched, 0.0, 10.0)
    accels       = np.clip(accels, 0.0, 2.0)
    
    features = np.column_stack((vels_matched, accels))
    
    seq_len = 50
    step = 25
    sequences = []
    n_points = len(features)
    for start in range(0, n_points - seq_len + 1, step):
        window = features[start:start+seq_len]
        sequences.append(window)
        
    return sequences


def _train_individual_mouse_lstm(username: str, device_class: str = "DESKTOP") -> None:
    """
    Fine-tune the generic mouse LSTM autoencoder on the user's collected mouse sequences.
    """
    cache_key = (username, device_class)
    seqs_list = _mouse_sequences_cache.get(cache_key, [])
    if not seqs_list:
        return
        
    # Combine all sequences from their session history
    all_seqs = []
    for seq_list in seqs_list:
        all_seqs.extend(seq_list)
        
    if len(all_seqs) < 10:
        return
        
    sequences = np.array(all_seqs, dtype=np.float32)
    
    if _ml_metadata and "mouse_model" in _ml_metadata:
        norm = _ml_metadata["mouse_model"]["normalization"]
        v_mean, v_std = norm["velocity_mean"], norm["velocity_std"]
        a_mean, a_std = norm["acceleration_mean"], norm["acceleration_std"]
        sequences[:, :, 0] = (sequences[:, :, 0] - v_mean) / v_std
        sequences[:, :, 1] = (sequences[:, :, 1] - a_mean) / a_std
        
    model = LSTMAutoencoder(
        input_size=LSTM_INPUT_SIZE,
        hidden_size=LSTM_HIDDEN_SIZE,
        num_layers=LSTM_NUM_LAYERS,
        latent_dim=LSTM_LATENT_DIM,
        seq_len=LSTM_SEQ_LEN_MOUSE,
    )
    if _generic_mouse_lstm is not None:
        model.load_state_dict(_generic_mouse_lstm.state_dict())
        
    # Freeze encoder to prevent overfitting on few samples
    for param in model.encoder_lstm.parameters():
        param.requires_grad = False
    for param in model.encoder_proj.parameters():
        param.requires_grad = False
        
    model.train()
    # Optimize only unfrozen decoder parameters
    optimizer = torch.optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=0.0005)
    criterion = nn.MSELoss()
    
    # Augment training sequences with slight Gaussian noise
    augmented_seqs = []
    for seq in sequences:
        augmented_seqs.append(seq)
        for _ in range(2):
            noise = np.random.normal(0, 0.02, seq.shape)
            augmented_seqs.append(seq + noise)
    augmented = np.array(augmented_seqs, dtype=np.float32)
    
    dataset = TensorDataset(torch.tensor(augmented, dtype=torch.float32))
    loader = DataLoader(dataset, batch_size=32, shuffle=True)
    
    for epoch in range(5):
        for batch_x, in loader:
            optimizer.zero_grad()
            recon, _ = model(batch_x)
            loss = criterion(recon, batch_x)
            loss.backward()
            optimizer.step()
            
    model.eval()
    db.save_mouse_lstm(username, model, device_class)
    log.info(f"Individual mouse LSTM fine-tuned and saved for {username} ({device_class}) on {len(sequences)} sequences.")


def add_mouse_training_sample(username: str, mouse_features: dict, mouse_samples: list = None, device_class: str = "DESKTOP") -> None:
    """
    Add a mouse feature vector to the user's training data.
    Once 10+ samples collected, train individual Isolation Forest.
    """
    if not db.user_exists(username):
        return

    profile = db.get_behavioral_profile(username, device_class)
    if not profile:
        return

    vectors = profile.get("mouse_vectors", []) or []
    if mouse_features:
        vec = _mouse_features_to_vector(mouse_features)
        vectors.append(vec)

        # Also store raw mouse sequences for LSTM training
        if mouse_samples:
            seqs = _extract_mouse_sequences(mouse_samples)
            if seqs:
                cache_key = (username, device_class)
                if cache_key not in _mouse_sequences_cache:
                    _mouse_sequences_cache[cache_key] = []
                _mouse_sequences_cache[cache_key].append(seqs)

        # Save to DB
        db.update_mouse_vectors(username, vectors, device_class)

        # Train individual model once we have enough sessions
        if len(vectors) >= 10:
            _train_individual_mouse_model(username, device_class)
            try:
                _train_individual_mouse_lstm(username, device_class)
            except Exception as e:
                log.error(f"Failed to train individual mouse LSTM: {e}")


def _train_individual_mouse_model(username: str, device_class: str = "DESKTOP") -> None:
    """Fit an Isolation Forest on the user's own mouse sessions."""
    profile = db.get_behavioral_profile(username, device_class)
    vectors = profile.get("mouse_vectors", []) if profile else []

    if len(vectors) < 5:
        return

    X = np.array(vectors)
    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    model.fit(X)
    db.save_mouse_model(username, model, vectors, device_class)
    log.info(f"Individual mouse model trained for {username} ({device_class}) on {len(vectors)} sessions.")


# =============================================================================
# 4. SCORING ENGINES

def _z_to_risk(z: float) -> float:
    """
    Convert absolute Z-score to 0-100 risk contribution.
    Z=0 → 0, Z=1 → 25, Z=2 → 50, Z=3 → 75, Z≥4 → 100
    Linear mapping capped at 4 sigma.
    """
    return min(abs(z) / 4.0 * 100.0, 100.0)


def score_keystrokes(username: str, features: dict, key_events: list = None) -> tuple[float, list]:
    """
    Z-Score and LSTM Autoencoder scorer for keystroke features.
    Compares current session features against user's enrolled baseline/model.

    Returns:
        (category_score: float 0-100,
         breakdown: list of (feature_name, z_score, contribution, label))
    """
    if not features:
        return 50.0, []   # neutral score if no keystroke data

    # Choose model: individual if enrolled/trained, generic otherwise
    lstm_model = db.get_keystroke_lstm(username) or _generic_keystroke_lstm
    seq = _extract_keystroke_sequence(key_events) if key_events else None

    use_lstm = (lstm_model is not None) and (seq is not None) and (_ml_metadata is not None) and ("keystroke_model" in _ml_metadata)

    if use_lstm:
        try:
            # Normalize sequence using training stats
            norm = _ml_metadata["keystroke_model"]["normalization"]
            h_mean, h_std = norm["hold_mean"], norm["hold_std"]
            f_mean, f_std = norm["flight_mean"], norm["flight_std"]

            seq_norm = seq.copy()
            seq_norm[:, 0] = (seq_norm[:, 0] - h_mean) / h_std
            seq_norm[:, 1] = (seq_norm[:, 1] - f_mean) / f_std

            # Predict MSE
            x_tensor = torch.from_numpy(np.array([seq_norm], dtype='float32'))
            with torch.no_grad():
                recon, _ = lstm_model(x_tensor)
                mse = float(((recon - x_tensor) ** 2).mean().item())

            # Map reconstruction error to 0-100 score relative to anomaly threshold
            threshold = _ml_metadata["keystroke_model"]["performance"]["anomaly_threshold"]
            # If MSE = threshold -> score is 50.0. Scale linearly.
            keystroke_score = min(100.0, (mse / max(threshold, 1e-6)) * 50.0)

            # Generate explainability breakdown using z-scores for UI dashboard clarity
            baseline = db.get_keystroke_baseline(username) or _generic_keystroke_baseline
            means = baseline.get("means", {})
            stds  = baseline.get("stds", {})

            breakdown = []
            z_score_based_risk = 0.0
            if means:
                for feat_name in KEYSTROKE_FEATURES:
                    if feat_name not in features:
                        continue
                    mean   = means.get(feat_name, 0.0)
                    std    = stds.get(feat_name,  FEATURES[feat_name]["min_std_floor"])
                    floor  = FEATURES[feat_name]["min_std_floor"]
                    weight = FEATURES[feat_name]["weight"]
                    safe_std = max(std, floor)

                    z = (features[feat_name] - mean) / safe_std
                    # Scale weight contribution according to the overall LSTM score
                    feat_risk = _z_to_risk(z) * weight
                    z_score_based_risk += feat_risk

                    breakdown.append({
                        "feature":      feat_name,
                        "label":        FEATURES[feat_name]["description"],
                        "observed":     round(features[feat_name], 2),
                        "baseline_mean": round(mean, 2),
                        "z_score":      round(z, 2),
                        "contribution": 0.0,  # Recalculated below
                        "unit":         FEATURES[feat_name]["unit"],
                    })

                # Combine LSTM score and Z-score risk score (taking maximum)
                keystroke_score = max(keystroke_score, min(z_score_based_risk, 100.0))

                # Recalculate explainability contributions based on the final combined score
                for item in breakdown:
                    feat_name = item["feature"]
                    mean   = means.get(feat_name, 0.0)
                    std    = stds.get(feat_name,  FEATURES[feat_name]["min_std_floor"])
                    floor  = FEATURES[feat_name]["min_std_floor"]
                    weight = FEATURES[feat_name]["weight"]
                    safe_std = max(std, floor)
                    z = (features[feat_name] - mean) / safe_std
                    feat_risk = _z_to_risk(z) * weight
                    item["contribution"] = round(feat_risk * (keystroke_score / 50.0 if keystroke_score > 0 else 1.0), 2)

                breakdown.sort(key=lambda x: x["contribution"], reverse=True)

            return round(keystroke_score, 1), breakdown

        except Exception as e:
            log.error(f"Error in LSTM keystroke scoring: {e}. Falling back to Z-score.")

    # --- Fallback to Z-Score Profiler ---
    baseline = db.get_keystroke_baseline(username)
    if not baseline:
        baseline = _generic_keystroke_baseline

    means = baseline.get("means", {})
    stds  = baseline.get("stds", {})

    if not means:
        if _generic_keystroke_lstm is not None and key_events:
            try:
                seq = _extract_keystroke_sequence(key_events)
                if seq is not None and _ml_metadata is not None and "keystroke_model" in _ml_metadata:
                    norm = _ml_metadata["keystroke_model"]["normalization"]
                    h_mean, h_std = norm["hold_mean"], norm["hold_std"]
                    f_mean, f_std = norm["flight_mean"], norm["flight_std"]

                    seq_norm = seq.copy()
                    seq_norm[:, 0] = (seq_norm[:, 0] - h_mean) / h_std
                    seq_norm[:, 1] = (seq_norm[:, 1] - f_mean) / f_std

                    x_tensor = torch.from_numpy(np.array([seq_norm], dtype='float32'))
                    with torch.no_grad():
                        recon, _ = _generic_keystroke_lstm(x_tensor)
                        mse = float(((recon - x_tensor) ** 2).mean().item())

                    threshold = _ml_metadata["keystroke_model"]["performance"]["anomaly_threshold"]
                    keystroke_score = min(100.0, (mse / max(threshold, 1e-6)) * 50.0)

                    # For explainability breakdown in cold-start, compare with generic baseline means/stds
                    g_means = _generic_keystroke_baseline.get("means", {})
                    g_stds  = _generic_keystroke_baseline.get("stds", {})

                    breakdown = []
                    z_score_based_risk = 0.0
                    for feat_name in KEYSTROKE_FEATURES:
                        if feat_name not in features:
                            continue
                        mean   = g_means.get(feat_name, 0.0)
                        std    = g_stds.get(feat_name,  FEATURES[feat_name]["min_std_floor"])
                        floor  = FEATURES[feat_name]["min_std_floor"]
                        weight = FEATURES[feat_name]["weight"]
                        safe_std = max(std, floor)

                        z = (features[feat_name] - mean) / safe_std
                        feat_risk = _z_to_risk(z) * weight
                        z_score_based_risk += feat_risk

                        breakdown.append({
                            "feature":      feat_name,
                            "label":        FEATURES[feat_name]["description"],
                            "observed":     round(features[feat_name], 2),
                            "baseline_mean": round(mean, 2),
                            "z_score":      round(z, 2),
                            "contribution": 0.0,
                            "unit":         FEATURES[feat_name]["unit"],
                        })

                    keystroke_score = max(keystroke_score, min(z_score_based_risk, 100.0))

                    for item in breakdown:
                        feat_name = item["feature"]
                        mean   = g_means.get(feat_name, 0.0)
                        std    = g_stds.get(feat_name,  FEATURES[feat_name]["min_std_floor"])
                        floor  = FEATURES[feat_name]["min_std_floor"]
                        weight = FEATURES[feat_name]["weight"]
                        safe_std = max(std, floor)
                        z = (features[feat_name] - mean) / safe_std
                        feat_risk = _z_to_risk(z) * weight
                        item["contribution"] = round(feat_risk * (keystroke_score / 50.0 if keystroke_score > 0 else 1.0), 2)

                    breakdown.sort(key=lambda x: x["contribution"], reverse=True)
                    return round(keystroke_score, 1), breakdown
            except Exception as e:
                log.error(f"Error in generic LSTM fallback: {e}")

        return 50.0, []

    breakdown  = []
    total_risk = 0.0

    for feat_name in KEYSTROKE_FEATURES:
        if feat_name not in features:
            continue

        mean   = means.get(feat_name, 0.0)
        std    = stds.get(feat_name,  FEATURES[feat_name]["min_std_floor"])
        floor  = FEATURES[feat_name]["min_std_floor"]
        weight = FEATURES[feat_name]["weight"]

        # Apply MIN_STD_FLOOR
        safe_std = max(std, floor)

        # Z-Score (how many standard deviations from enrolled mean)
        z = (features[feat_name] - mean) / safe_std

        # Risk contribution for this feature
        risk_contrib = _z_to_risk(z) * weight
        total_risk  += risk_contrib

        breakdown.append({
            "feature":      feat_name,
            "label":        FEATURES[feat_name]["description"],
            "observed":     round(features[feat_name], 2),
            "baseline_mean": round(mean, 2),
            "z_score":      round(z, 2),
            "contribution": round(risk_contrib, 2),
            "unit":         FEATURES[feat_name]["unit"],
        })

    # Sort by contribution (highest first) for SHAP-lite display
    breakdown.sort(key=lambda x: x["contribution"], reverse=True)

    # Normalize to 0-100 (weighted sum already accounts for weights summing to 1)
    keystroke_score = min(total_risk, 100.0)
    return round(keystroke_score, 1), breakdown


def score_mouse(username: str, features: dict, mouse_samples: list = None) -> tuple[float, list]:
    """
    Isolation Forest and LSTM Autoencoder anomaly scorer for mouse features.

    Returns:
        (category_score: float 0-100,
         breakdown: list of dicts with per-feature info)
    """
    if not features:
        return 25.0, []   # neutral-low score if no mouse data

    # Try LSTM scoring if model, samples and metadata are available
    lstm_model = db.get_mouse_lstm(username) or _generic_mouse_lstm
    seqs = _extract_mouse_sequences(mouse_samples) if mouse_samples else []

    use_lstm = (lstm_model is not None) and (len(seqs) > 0) and (_ml_metadata is not None) and ("mouse_model" in _ml_metadata)

    if use_lstm:
        try:
            # Normalize sequences using training stats
            norm = _ml_metadata["mouse_model"]["normalization"]
            v_mean, v_std = norm["velocity_mean"], norm["velocity_std"]
            a_mean, a_std = norm["acceleration_mean"], norm["acceleration_std"]

            normalized_seqs = []
            for s in seqs:
                s_norm = s.copy()
                s_norm[:, 0] = (s_norm[:, 0] - v_mean) / v_std
                s_norm[:, 1] = (s_norm[:, 1] - a_mean) / a_std
                normalized_seqs.append(s_norm)

            # Predict MSE for all sequences
            x_tensor = torch.from_numpy(np.array(normalized_seqs, dtype='float32'))
            with torch.no_grad():
                recon, _ = lstm_model(x_tensor)
                per_sample_mse = ((recon - x_tensor) ** 2).mean(dim=(1, 2))
                mean_mse = float(per_sample_mse.mean().item())

            # Map reconstruction error to 0-100 score relative to anomaly threshold
            threshold = _ml_metadata["mouse_model"]["performance"]["anomaly_threshold"]
            # If MSE = threshold -> score is 50.0. Scale linearly.
            mouse_score = min(100.0, (mean_mse / max(threshold, 1e-6)) * 50.0)

            # Generate explainability breakdown using the feature vectors for UI display
            vec = _mouse_features_to_vector(features)
            mouse_feature_names = list(MOUSE_FEATURES)
            breakdown = []
            for i, feat_name in enumerate(mouse_feature_names):
                if i < len(vec):
                    breakdown.append({
                        "feature":      feat_name,
                        "label":        FEATURES[feat_name]["description"],
                        "observed":     round(vec[i], 4),
                        "contribution": round(FEATURES[feat_name]["weight"] * mouse_score, 2),
                        "unit":         FEATURES[feat_name]["unit"],
                    })
            breakdown.sort(key=lambda x: x["contribution"], reverse=True)

            return round(mouse_score, 1), breakdown

        except Exception as e:
            log.error(f"Error in LSTM mouse scoring: {e}. Falling back to Isolation Forest.")

    # --- Fallback to Isolation Forest ---
    vec = _mouse_features_to_vector(features)

    # Use individual model if available, else generic
    model = db.get_mouse_model(username)
    if model is None:
        model = _generic_mouse_model
    if model is None:
        return 25.0, []

    # score_samples returns more-negative values for anomalies
    # Typical range: [-0.8, -0.2] for trained models
    raw_score = float(model.score_samples([vec])[0])

    # Map to 0-100 risk: -0.2 → 0 risk (normal), -0.8 → 100 risk (anomalous)
    # Linear mapping through the expected range
    mouse_score = max(0.0, min(100.0, (-raw_score - 0.2) / 0.6 * 100.0))

    # Build per-feature breakdown for display
    mouse_feature_names = list(MOUSE_FEATURES)
    breakdown = []
    for i, feat_name in enumerate(mouse_feature_names):
        if i < len(vec):
            breakdown.append({
                "feature":      feat_name,
                "label":        FEATURES[feat_name]["description"],
                "observed":     round(vec[i], 4),
                "contribution": round(FEATURES[feat_name]["weight"] * mouse_score, 2),
                "unit":         FEATURES[feat_name]["unit"],
            })
    breakdown.sort(key=lambda x: x["contribution"], reverse=True)

    return round(mouse_score, 1), breakdown


def score_metadata(username: str, metadata_features: dict) -> tuple[float, list]:
    """
    Rule-based metadata scorer.
    Direct risk point additions for time-of-day, device mismatch, etc.

    Returns:
        (category_score: float 0-100,
         breakdown: list of dicts)
    """
    if not metadata_features:
        return 0.0, []

    breakdown  = []
    total_risk = 0.0

    # --- Time of day (direct risk points) ---
    tod_risk = metadata_features.get("time_of_day_risk", 0.0)
    tod_norm = min(tod_risk / 15.0 * 100.0, 100.0)  # 15 pts = 100% risk
    tod_contrib = tod_norm * FEATURES["time_of_day_risk"]["weight"]
    total_risk += tod_contrib
    breakdown.append({
        "feature":      "time_of_day_risk",
        "label":        FEATURES["time_of_day_risk"]["description"],
        "observed":     tod_risk,
        "contribution": round(tod_contrib, 2),
        "unit":         "risk_points",
    })

    # --- Device fingerprint mismatch ---
    fp_mismatch = metadata_features.get("device_fingerprint_match", 0.0)
    fp_risk_pts = DEVICE_MISMATCH_RISK_POINTS if fp_mismatch > 0 else 0.0
    fp_norm     = min(fp_risk_pts / 18.0 * 100.0, 100.0)  # 18 pts = max
    fp_contrib  = fp_norm * FEATURES["device_fingerprint_match"]["weight"]
    total_risk += fp_contrib
    breakdown.append({
        "feature":      "device_fingerprint_match",
        "label":        FEATURES["device_fingerprint_match"]["description"],
        "observed":     int(fp_mismatch),
        "contribution": round(fp_contrib, 2),
        "unit":         "binary",
    })

    # --- Session action speed (Z-score against user baseline) ---
    action_speed = metadata_features.get("session_action_speed", 0.0)
    baseline = db.get_keystroke_baseline(username)
    # Use generic reference values for metadata — no individual baseline needed
    # Suspiciously fast: >20 actions/min (bot-like); suspiciously slow: < 0.5
    if action_speed > 20.0:
        speed_risk = min((action_speed - 20.0) / 10.0 * 100.0, 100.0)
    elif action_speed < 0.5 and action_speed > 0:
        speed_risk = 20.0  # unusually slow — mild flag
    else:
        speed_risk = 0.0
    speed_contrib = speed_risk * FEATURES["session_action_speed"]["weight"]
    total_risk += speed_contrib
    breakdown.append({
        "feature":      "session_action_speed",
        "label":        FEATURES["session_action_speed"]["description"],
        "observed":     round(action_speed, 2),
        "contribution": round(speed_contrib, 2),
        "unit":         "actions/min",
    })

    # --- Transaction initiation delay ---
    tx_delay = metadata_features.get("transaction_initiation_delay", 30.0)
    # Very fast (<3 seconds) = suspicious; normal is 10-60 seconds
    if tx_delay < 3.0:
        tx_risk = 80.0   # Went straight for transfer — high risk
    elif tx_delay < 8.0:
        tx_risk = 30.0   # Slightly fast
    else:
        tx_risk = 0.0    # Normal browsing before action
    tx_contrib = tx_risk * FEATURES["transaction_initiation_delay"]["weight"]
    total_risk += tx_contrib
    breakdown.append({
        "feature":      "transaction_initiation_delay",
        "label":        FEATURES["transaction_initiation_delay"]["description"],
        "observed":     round(tx_delay, 1),
        "contribution": round(tx_contrib, 2),
        "unit":         "seconds",
    })

    # --- Click dwell time (bot detection proxy) ---
    click_dwell = metadata_features.get("click_dwell_time_mean", 120.0)
    bot_thresh = BOT_SIGNATURES.get("click_dwell_max_ms", 15)
    if click_dwell < bot_thresh:
        dwell_risk = 100.0  # Bot click
    elif click_dwell < 40.0:
        dwell_risk = 50.0   # Suspiciously fast
    else:
        dwell_risk = 0.0
    dwell_contrib = dwell_risk * FEATURES["click_dwell_time_mean"]["weight"]
    total_risk += dwell_contrib
    breakdown.append({
        "feature":      "click_dwell_time_mean",
        "label":        FEATURES["click_dwell_time_mean"]["description"],
        "observed":     round(click_dwell, 1),
        "contribution": round(dwell_contrib, 2),
        "unit":         "ms",
    })

    breakdown.sort(key=lambda x: x["contribution"], reverse=True)
    metadata_score = min(total_risk, 100.0)
    return round(metadata_score, 1), breakdown


def _mouse_features_to_vector(features: dict) -> list:
    """Convert mouse feature dict to ordered list for Isolation Forest input."""
    return [
        features.get("mouse_mean_velocity",        0.0),
        features.get("mouse_std_velocity",         0.0),
        features.get("mouse_mean_acceleration",    0.0),
        features.get("click_frequency",            0.0),
        features.get("click_interval_consistency", 0.0),
        features.get("idle_time_ratio",            0.0),
        features.get("scroll_speed_mean",          0.0),
        features.get("trajectory_straightness",    0.0),
    ]


# =============================================================================
# 5. RISK FUSION
# =============================================================================

def fuse_scores(
    keystroke_score: float,
    mouse_score:     float,
    metadata_score:  float,
    k_breakdown:     list,
    m_breakdown:     list,
    md_breakdown:    list,
    username:        str = None,
    metadata_features: dict = None,
) -> dict:
    """
    Combine three category scores into a single unified risk score (0-100).
    Uses XGBoost fusion classifier if available, else falls back to weighted sum.
    Produces SHAP-lite top-N feature breakdown.
    """
    use_xgb = (_xgb_fusion_model is not None) and (metadata_features is not None)

    # Weighted-sum fallback score (used even when XGBoost is available, for blending)
    weights = CATEGORY_WEIGHTS
    weighted_sum_score = (
        keystroke_score * weights["KEYSTROKE"] +
        mouse_score     * weights["MOUSE"]     +
        metadata_score  * weights["METADATA"]
    )
    weighted_sum_score = min(weighted_sum_score, 100.0)

    if use_xgb:
        try:
            is_enrolled = 1 if (username and db.is_enrolled(username)) else 0

            vector = [keystroke_score, mouse_score, metadata_score, is_enrolled]

            prob_fraud = float(_xgb_fusion_model.predict_proba([vector])[0][1])
            xgb_score  = prob_fraud * 100.0

            # Smart XGBoost boosting:
            # - When XGBoost is low-confidence (≤75%), use weighted sum as-is.
            #   This preserves the natural AMBER zone for moderate deviations.
            # - When XGBoost is highly confident (>75%), add a graduated push
            #   proportional to the model's certainty. At 100% confidence, the
            #   score is pushed towards RED_HIGH/RED_CRITICAL.
            if prob_fraud > 0.75:
                confidence_boost = (prob_fraud - 0.75) / 0.25   # 0→1 as prob goes 0.75→1.0
                # Push up towards max(weighted_sum, 72) + up to 25 extra points
                boosted_ceiling = max(weighted_sum_score, 72.0) + 25.0 * confidence_boost
                final_score = round(min(
                    weighted_sum_score + (boosted_ceiling - weighted_sum_score) * confidence_boost,
                    100.0
                ), 1)
            else:
                # XGBoost uncertain — trust the weighted behavioural sum
                final_score = round(weighted_sum_score, 1)
        except Exception as e:
            log.error(f"Error in XGBoost fusion scoring: {e}. Falling back to weighted sum.")
            use_xgb = False

    if not use_xgb:
        final_score = round(weighted_sum_score, 1)

    band = get_score_band(final_score)

    # Merge all breakdowns for SHAP-lite top-N
    all_contributors = k_breakdown + m_breakdown + md_breakdown
    all_contributors.sort(key=lambda x: x.get("contribution", 0), reverse=True)
    top_contributors = all_contributors[:EXPLAINABILITY_TOP_N]

    return {
        "final_score":      final_score,
        "band":             band,
        "keystroke_score":  round(keystroke_score, 1),
        "mouse_score":      round(mouse_score, 1),
        "metadata_score":   round(metadata_score, 1),
        "top_contributors": top_contributors,
        "all_contributors": all_contributors,
    }


# =============================================================================
# 6. BOT DETECTION
# =============================================================================

def detect_bot(
    key_events:       list,
    mouse_samples:    list,
    metadata:         dict,
) -> tuple[bool, str]:
    """
    Heuristic pre-screening for automated bot activity.
    Called BEFORE ML scoring — bot detection is immediate.
    Returns (is_bot: bool, reason: str)
    """
    sigs = BOT_SIGNATURES

    # 1. WebDriver flag (set by browser automation tools)
    if metadata.get("webdriver_flag", False):
        return True, "WebDriver automation flag detected"

    # 2. Click dwell time < 15ms (inhuman click speed)
    click_dwell = metadata.get("click_dwell_mean", 120.0)
    if click_dwell < sigs["click_dwell_max_ms"] and click_dwell > 0:
        return True, f"Bot click signature: dwell={click_dwell:.1f}ms (threshold: {sigs['click_dwell_max_ms']}ms)"

    # 3. Any flight time < 5ms (programmatic key injection)
    if key_events:
        events_by_pos = {}
        for ev in key_events:
            pos = ev.get("position", 0)
            if pos > 0:
                events_by_pos.setdefault(pos, {})[ev.get("event")] = ev.get("timestamp", 0)

        for pos in sorted(events_by_pos.keys()):
            nxt = pos + 1
            if nxt in events_by_pos:
                curr_up   = events_by_pos[pos].get("up", None)
                next_down = events_by_pos[nxt].get("down", None)
                if curr_up and next_down:
                    flight = next_down - curr_up
                    if 0 < flight < sigs["flight_time_min_ms"]:
                        return True, f"Programmatic keystroke: flight={flight:.1f}ms at pos {pos}->{nxt}"

    # 4. Near-perfect trajectory straightness (mouse moves in straight lines)
    if mouse_samples and len(mouse_samples) >= 5:
        moves = [s for s in mouse_samples if s.get("event") == "move"]
        if len(moves) >= 5:
            xs = [m["x"] for m in moves]
            ys = [m["y"] for m in moves]
            dists = [math.sqrt((xs[i]-xs[i-1])**2 + (ys[i]-ys[i-1])**2)
                     for i in range(1, len(xs))]
            path_len = sum(dists)
            straight = math.sqrt((xs[-1]-xs[0])**2 + (ys[-1]-ys[0])**2)
            straightness = straight / max(path_len, 0.001)
            if straightness > sigs["trajectory_straightness_max"]:
                return True, f"Bot trajectory: straightness={straightness:.3f} (threshold: {sigs['trajectory_straightness_max']})"

    # 5. Zero velocity variance (constant-speed mouse movement)
    if mouse_samples:
        moves = sorted([s for s in mouse_samples if s.get("event") == "move"],
                       key=lambda s: s["timestamp"])
        if len(moves) >= 5:
            xs = [m["x"] for m in moves]
            ys = [m["y"] for m in moves]
            ts = [m["timestamp"] for m in moves]
            dists = np.sqrt(np.diff(xs)**2 + np.diff(np.array(ys))**2)
            dts   = np.diff(ts)
            dts   = np.where(dts == 0, 0.001, dts)
            vels  = dists / dts
            if len(vels) > 2 and float(np.var(vels)) < sigs["velocity_variance_min"]:
                return True, f"Bot velocity: variance={np.var(vels):.6f} (constant speed)"

    return False, ""


# =============================================================================
# 7. VELOCITY CHECK
# =============================================================================

def check_velocity(session_id: str, new_score: float) -> bool:
    """
    Check if the score jumped more than VELOCITY_JUMP_THRESHOLD in one interval.
    Returns True if velocity threshold is exceeded (→ skip to AMBER_HIGH).
    """
    session = db.get_session(session_id)
    if not session or not session["risk_history"]:
        return False

    prev_score = session["current_risk"]
    jump       = new_score - prev_score
    return jump > VELOCITY_JUMP_THRESHOLD


# =============================================================================
# 8. MAIN SCORING ENTRY POINT
# =============================================================================

def score_session(
    session_id:          str,
    key_events:          list = None,
    mouse_samples:       list = None,
    username_key_events: list = None,
) -> dict:
    """
    Main entry point called by app.py on every scoring cycle.
    Scores the session, updates the database, and returns the full result.

    Returns dict with:
        final_score, band, action, breakdown, is_bot, top_contributors
    """
    session = db.get_session(session_id)
    if not session:
        return {"error": "Session not found"}

    username = session["username"]
    now = time.time()
    session_duration_ms = (now - session["created_at"]) * 1000

    # Build metadata dict from session state
    metadata = {
        "webdriver_flag":      session.get("webdriver_flag", False),
        "click_dwell_mean":    session.get("click_dwell_mean", 120.0),
    }

    # ── Step 1: Bot detection (immediate, before ML) ──────────────
    # Combine key_events and username_key_events to check for programmatic keystrokes across BOTH fields!
    combined_keys = (key_events or []) + (username_key_events or [])
    is_bot, bot_reason = detect_bot(combined_keys, mouse_samples or [], metadata)

    if is_bot:
        db.mark_session_as_bot(session_id)
        db.log_event(
            event_type = "BOT_DETECTED",
            session_id = session_id,
            username   = username,
            details    = {"reason": bot_reason},
            risk_score = BOT_SCORE_OVERRIDE,
            risk_band  = "RED_CRITICAL",
        )
        breakdown = {
            "final_score":      BOT_SCORE_OVERRIDE,
            "band":             "RED_CRITICAL",
            "is_bot":           True,
            "bot_reason":       bot_reason,
            "top_contributors": [{"feature": "bot_detection",
                                   "label": bot_reason,
                                   "contribution": 100.0}],
            "all_contributors": [{"feature": "bot_detection",
                                   "label": bot_reason,
                                   "contribution": 100.0}],
            "mouse_samples":    mouse_samples,
        }
        db.update_session_risk(session_id, BOT_SCORE_OVERRIDE, "RED_CRITICAL", breakdown)
        return {
            "final_score":      BOT_SCORE_OVERRIDE,
            "band":             "RED_CRITICAL",
            "action":           "SILENT_BLOCK",
            "is_bot":           True,
            "bot_reason":       bot_reason,
            "top_contributors": [{"feature": "bot_detection",
                                   "label": bot_reason,
                                   "contribution": 100.0}],
        }

    # ── Step 2: Feature extraction ────────────────────────────────
    keystroke_features = (extract_keystroke_features(key_events)
                          if key_events else None)
    mouse_features     = (extract_mouse_features(mouse_samples, session_duration_ms)
                          if mouse_samples else None)
    metadata_features  = extract_metadata_features(
        session,
        db.get_device_fingerprint(username, session.get("device_class", "DESKTOP")),
    )

    # ── Step 3: Category scoring ──────────────────────────────────
    keystroke_score, k_breakdown = score_keystrokes(username, keystroke_features or {}, key_events)
    mouse_score, m_breakdown     = score_mouse(username, mouse_features or {}, mouse_samples)
    metadata_score, md_breakdown = score_metadata(username, metadata_features)

    # ── Step 4: Risk fusion ───────────────────────────────────────
    result = fuse_scores(
        keystroke_score, mouse_score, metadata_score,
        k_breakdown, m_breakdown, md_breakdown,
        username = username,
        metadata_features = metadata_features,
    )

    final_score = result["final_score"]
    band        = result["band"]

    # ── Step 5: Velocity check ────────────────────────────────────
    velocity_exceeded = check_velocity(session_id, final_score)
    if velocity_exceeded and final_score > 40:
        # Fast-rising score — skip AMBER_MID, go straight to AMBER_HIGH
        if band == "AMBER_MID":
            band = "AMBER_HIGH"
            result["band"] = "AMBER_HIGH"
            result["velocity_escalation"] = True

    # ── Step 6: Determine action ──────────────────────────────────
    action = _get_action(band)

    # Update scoring interval based on band
    if band.startswith("RED"):
        new_interval = 5  # Accelerated 5-second interval for active threats/bots
    elif band in ("AMBER_LOW", "AMBER_MID", "AMBER_HIGH"):
        new_interval = 10  # 10s for any amber escalation
    else:
        new_interval = 15  # 15s default (Green)
    db.update_scoring_interval(session_id, new_interval)

    # ── Step 7: Persist to database ───────────────────────────────
    db_result = {**result, "mouse_samples": mouse_samples}
    db.update_session_risk(session_id, final_score, band, db_result)
    if _c.ADVISORY_MODE:
        db.update_session_status(session_id, "active")
    else:
        db.update_session_status(session_id, band.lower())
    db.log_event(
        event_type = "SCORE_UPDATE",
        session_id = session_id,
        username   = username,
        details    = {
            "keystroke_score": result["keystroke_score"],
            "mouse_score":     result["mouse_score"],
            "metadata_score":  result["metadata_score"],
            "action":          action,
            "velocity_flag":   velocity_exceeded,
            "session_count":   db.get_session_count(username),
        },
        risk_score = final_score,
        risk_band  = band,
    )

    # Add mouse features to user's training data
    if mouse_features:
        device_class = session.get("device_class", "DESKTOP")
        add_mouse_training_sample(username, mouse_features, mouse_samples, device_class)

    # ── B1: Progressive Baseline Drift ────────────────────────────
    # After every GREEN session, gently nudge the user's keystroke
    # baseline toward the current session's values.
    device_class = session.get("device_class", "DESKTOP")
    if band == "GREEN" and keystroke_features and _c.BASELINE_DRIFT_WEIGHT > 0:
        import db_sqlite as _db_sql
        _db_sql.update_keystroke_baseline_drift(
            username, device_class, keystroke_features, _c.BASELINE_DRIFT_WEIGHT
        )

    # ── B2: Advisory Mode override ────────────────────────────────
    # If advisory mode is on, never apply friction to the user.
    if _c.ADVISORY_MODE and action not in ("CONTINUE", "MONITOR"):
        action = "MONITOR"   # silent observe only

    return {
        **result,
        "action":            action,
        "is_bot":            False,
        "velocity_exceeded": velocity_exceeded,
        "scoring_interval":  new_interval,
    }


def _get_action(band: str) -> str:
    """Map score band to the action the frontend should take."""
    return {
        "GREEN":        "CONTINUE",
        "AMBER_LOW":    "MONITOR",
        "AMBER_MID":    "SOFT_CHALLENGE",
        "AMBER_HIGH":   "FULL_CHALLENGE",
        "RED_LOW":      "FREEZE_SESSION",
        "RED_HIGH":     "FREEZE_AND_ALERT",
        "RED_CRITICAL": "SILENT_BLOCK",
    }.get(band, "CONTINUE")
