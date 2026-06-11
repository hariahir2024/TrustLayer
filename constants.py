# =============================================================================
# BehaviorShield — constants.py
# Team SOLARIS | Cyber Security Hackathon 2026 | MNNIT Allahabad
# =============================================================================
# THIS FILE IS WRITTEN FIRST.
# All feature definitions, thresholds, weights, and system parameters live here.
# Every other file imports from this file. Never hardcode values elsewhere.
# =============================================================================


# -----------------------------------------------------------------------------
# ENROLLMENT PASSPHRASE
# Chosen: "SecureAuth@India1" (17 characters)
# Character map by position (1-indexed):
#   1:S  2:e  3:c  4:u  5:r  6:e  7:A  8:u  9:t  10:h
#   11:@ 12:I 13:n 14:d 15:i 16:a 17:1
#
# IMPORTANT: This passphrase is FIXED for the entire demo.
# All team members must practice typing it 30+ times before demo day.
# The behavioral baseline is built from this exact string.
# -----------------------------------------------------------------------------
ENROLLMENT_PASSPHRASE = "SecureAuth@India1"
ENROLLMENT_PASSPHRASE_LENGTH = 17      # number of characters
ENROLLMENT_PASSPHRASE_DISPLAY = "SecureAuth@India1"  # shown to user during enrollment


# -----------------------------------------------------------------------------
# ENROLLMENT & SESSION PARAMETERS
# -----------------------------------------------------------------------------
ENROLLMENT_REQUIRED_SAMPLES   = 5     # number of passphrase entries needed to build baseline
PROFILE_WARM_SESSIONS         = 15    # sessions after which individual profile fully replaces generic baseline
GENERIC_BASELINE_ACTIVE_UNTIL_SESSIONS = 10  # use population baseline until this many sessions
DEFAULT_SCORING_INTERVAL_SEC  = 30    # seconds between passive risk re-scores (Green zone)
AMBER_LOW_SCORING_INTERVAL_SEC = 10   # seconds between scores when in Amber Low zone
SESSION_TOKEN_LENGTH           = 32   # characters in session ID
MAX_ENROLLMENT_AGE_DAYS        = 90   # re-enrollment required after this many days of inactivity


# -----------------------------------------------------------------------------
# FEATURE DEFINITIONS
# 28 named behavioral features, organized by category.
# Each feature entry defines:
#   - description  : human-readable label for dashboard display
#   - category     : KEYSTROKE | MOUSE | METADATA
#   - platform     : WEB | MOBILE_SDK_ONLY | WEB_AND_MOBILE
#   - min_std_floor: minimum standard deviation to prevent division-by-zero
#                    (Z = (x - mean) / max(std, min_std_floor))
#   - weight       : contribution to category score (must sum to 1.0 per category)
#   - unit         : measurement unit for display
# -----------------------------------------------------------------------------

FEATURES = {

    # =========================================================================
    # KEYSTROKE FEATURES (15 features)
    # Captured from: enrollment passphrase field, login passphrase field,
    #                fund transfer amount / recipient fields
    # Privacy: TIMING ONLY. Key identities (which key was pressed) are
    #          NEVER stored or transmitted. Raw events discarded after extraction.
    # =========================================================================

    # --- Aggregate Statistical Features (10) ---

    "mean_hold_time": {
        "description":   "Mean key hold duration",
        "category":      "KEYSTROKE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 8.0,      # ms — human hold time varies ~10-20ms normally
        "weight":        0.14,     # highest weight — most stable behavioral signal
        "unit":          "ms",
    },

    "std_hold_time": {
        "description":   "Consistency of key hold duration",
        "category":      "KEYSTROKE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 5.0,
        "weight":        0.08,
        "unit":          "ms",
    },

    "mean_flight_time": {
        "description":   "Mean gap between consecutive keys",
        "category":      "KEYSTROKE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 8.0,      # ms — inter-key gaps vary ~15-25ms normally
        "weight":        0.14,     # highest weight — inter-key rhythm is core signal
        "unit":          "ms",
    },

    "std_flight_time": {
        "description":   "Consistency of inter-key gaps",
        "category":      "KEYSTROKE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 5.0,
        "weight":        0.08,
        "unit":          "ms",
    },

    "typing_speed_cps": {
        "description":   "Typing speed in characters per second",
        "category":      "KEYSTROKE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 0.3,      # cps — natural day-to-day variation
        "weight":        0.14,     # strong signal — bots type at inhuman or constant speed
        "unit":          "cps",
    },

    "backspace_rate": {
        "description":   "Self-correction frequency (backspace count / total keys)",
        "category":      "KEYSTROKE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 0.02,     # ratio
        "weight":        0.08,
        "unit":          "ratio",
    },

    "rhythm_consistency": {
        "description":   "Coefficient of variation of inter-key intervals",
        "category":      "KEYSTROKE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 0.05,
        "weight":        0.08,
        "unit":          "CV",
    },

    "burst_ratio": {
        "description":   "Ratio of fast key clusters to slow pauses",
        "category":      "KEYSTROKE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 0.05,
        "weight":        0.04,
        "unit":          "ratio",
    },

    "first_key_latency": {
        "description":   "Reaction time from field focus to first keypress",
        "category":      "KEYSTROKE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 20.0,     # ms
        "weight":        0.04,
        "unit":          "ms",
    },

    "completion_time": {
        "description":   "Total time to complete the passphrase field",
        "category":      "KEYSTROKE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 200.0,    # ms — roughly 0.2 seconds
        "weight":        0.08,
        "unit":          "ms",
    },

    # --- Positional Digraph Features (5) ---
    # Digraph = gap between position N and N+1 (timing only, no key identity)
    # Positions chosen from "SecureAuth@India1" for maximum rhythm variation:
    #   Pos 1→2  : S→e  (opening stroke, sets base rhythm)
    #   Pos 6→7  : e→A  (lowercase-to-uppercase shift — natural rhythm break)
    #   Pos 9→10 : t→h  (fast common pair in most typists)
    #   Pos 11→12: @→I  (special character to uppercase — usually a pause point)
    #   Pos 15→16: i→a  (closing quick succession)

    "digraph_pos_1_2": {
        "description":   "Inter-key gap: position 1 → 2 (opening stroke)",
        "category":      "KEYSTROKE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 8.0,      # ms
        "weight":        0.02,     # lower weight — individual digraphs are noisier
        "unit":          "ms",
        "position_pair": (1, 2),
    },

    "digraph_pos_6_7": {
        "description":   "Inter-key gap: position 6 → 7 (case transition point)",
        "category":      "KEYSTROKE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 8.0,
        "weight":        0.02,
        "unit":          "ms",
        "position_pair": (6, 7),
    },

    "digraph_pos_9_10": {
        "description":   "Inter-key gap: position 9 → 10 (fast pair)",
        "category":      "KEYSTROKE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 8.0,
        "weight":        0.02,
        "unit":          "ms",
        "position_pair": (9, 10),
    },

    "digraph_pos_11_12": {
        "description":   "Inter-key gap: position 11 → 12 (special char to uppercase)",
        "category":      "KEYSTROKE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 10.0,     # slightly higher floor — special char transitions vary more
        "weight":        0.02,
        "unit":          "ms",
        "position_pair": (11, 12),
    },

    "digraph_pos_15_16": {
        "description":   "Inter-key gap: position 15 → 16 (closing succession)",
        "category":      "KEYSTROKE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 8.0,
        "weight":        0.02,
        "unit":          "ms",
        "position_pair": (15, 16),
    },

    # =========================================================================
    # MOUSE / POINTER FEATURES (8 features)
    # Captured from: all mouse activity during the session
    # Sampled at: 50ms intervals (20 samples per second)
    # =========================================================================

    "mouse_mean_velocity": {
        "description":   "Average cursor speed across the session",
        "category":      "MOUSE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 0.02,     # px/ms
        "weight":        0.18,
        "unit":          "px/ms",
    },

    "mouse_std_velocity": {
        "description":   "Smoothness of cursor movement (speed consistency)",
        "category":      "MOUSE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 0.01,
        "weight":        0.15,
        "unit":          "px/ms",
    },

    "mouse_mean_acceleration": {
        "description":   "Average rate of change in cursor speed",
        "category":      "MOUSE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 0.005,    # px/ms²
        "weight":        0.12,
        "unit":          "px/ms²",
    },

    "click_frequency": {
        "description":   "Number of clicks per minute during session",
        "category":      "MOUSE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 0.5,      # clicks/min
        "weight":        0.10,
        "unit":          "clicks/min",
    },

    "click_interval_consistency": {
        "description":   "Regularity of time between clicks",
        "category":      "MOUSE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 50.0,     # ms
        "weight":        0.10,
        "unit":          "ms",
    },

    "idle_time_ratio": {
        "description":   "Proportion of session where mouse is stationary",
        "category":      "MOUSE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 0.03,
        "weight":        0.10,
        "unit":          "ratio",
    },

    "scroll_speed_mean": {
        "description":   "Average scroll speed during session",
        "category":      "MOUSE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 0.5,      # px/s
        "weight":        0.10,
        "unit":          "px/s",
    },

    "trajectory_straightness": {
        "description":   "Ratio of actual path length to straight-line distance (1.0 = bot)",
        "category":      "MOUSE",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 0.02,
        "weight":        0.15,
        "unit":          "ratio",
        # NOTE: Higher value = straighter path = more suspicious
        # Bots move in perfectly straight lines → straightness ≈ 1.0
        # Humans curve naturally → straightness typically 1.2–2.5
        "inverted": True,          # flag: low score = anomalous (reversed from other features)
    },

    # =========================================================================
    # SESSION METADATA FEATURES (5 features)
    # Collected once per session at initialization
    # =========================================================================

    "time_of_day_risk": {
        "description":   "Session timing anomaly (late-night flag)",
        "category":      "METADATA",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": None,     # Not a Z-score feature — rule-based
        "weight":        0.20,
        "unit":          "risk_points",
        # Rule: session hour 0–5 AM → +15 risk points added directly
        # Hour 6–22 → 0 additional points
        # Hour 23 → +8 points
        "rule": "TIME_OF_DAY_RULE",
    },

    "device_fingerprint_match": {
        "description":   "Whether session device matches enrolled device profile",
        "category":      "METADATA",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": None,     # Binary — not Z-score
        "weight":        0.30,
        "unit":          "binary",
        # 0 = known device (matches enrolled fingerprint hash)
        # 1 = new/unknown device → adds direct risk points
        # Fingerprint = hash(user_agent + screen_resolution + color_depth + timezone + language)
        "rule": "DEVICE_FINGERPRINT_RULE",
    },

    "session_action_speed": {
        "description":   "Pages or actions completed per minute",
        "category":      "METADATA",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 0.5,      # actions/min
        "weight":        0.20,
        "unit":          "actions/min",
    },

    "transaction_initiation_delay": {
        "description":   "Time from login to first financial action",
        "category":      "METADATA",
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 2.0,      # seconds
        "weight":        0.15,
        "unit":          "seconds",
    },

    "click_dwell_time_mean": {
        "description":   "Mean duration mouse button is held per click",
        "category":      "METADATA",  # grouped with metadata for weighting; captured by SDK
        "platform":      "WEB_AND_MOBILE",
        "min_std_floor": 10.0,     # ms — bots click-release in ~0ms, humans in 80-200ms
        "weight":        0.15,
        "unit":          "ms",
        # Bot signature: click_dwell_time ≈ 0ms (instant programmatic click)
        # Human range: typically 80–250ms
    },
}


# Validate feature weights sum correctly per category
# (Used by ml_engine.py at startup to catch misconfiguration early)
KEYSTROKE_FEATURES = [k for k, v in FEATURES.items() if v["category"] == "KEYSTROKE"]
MOUSE_FEATURES     = [k for k, v in FEATURES.items() if v["category"] == "MOUSE"]
METADATA_FEATURES  = [k for k, v in FEATURES.items() if v["category"] == "METADATA"]

KEYSTROKE_WEIGHT_SUM = sum(FEATURES[f]["weight"] for f in KEYSTROKE_FEATURES)   # should be 1.0
MOUSE_WEIGHT_SUM     = sum(FEATURES[f]["weight"] for f in MOUSE_FEATURES)       # should be 1.0
METADATA_WEIGHT_SUM  = sum(FEATURES[f]["weight"] for f in METADATA_FEATURES)    # should be 1.0


# -----------------------------------------------------------------------------
# RISK CATEGORY WEIGHTS
# How much each category contributes to the unified risk score (0–100)
# -----------------------------------------------------------------------------
CATEGORY_WEIGHTS = {
    "KEYSTROKE": 0.40,
    "MOUSE":     0.35,
    "METADATA":  0.25,
}


# -----------------------------------------------------------------------------
# DECISION ENGINE THRESHOLDS — 7-Band System
# -----------------------------------------------------------------------------

# Score bands (upper bounds, inclusive)
GREEN_MAX       = 30   # 0–30   : Silent pass
AMBER_LOW_MAX   = 45   # 31–45  : Passive monitoring intensified (invisible to user)
AMBER_MID_MAX   = 60   # 46–60  : Soft re-auth using enrollment passphrase
AMBER_HIGH_MAX  = 70   # 61–70  : Transaction restrictions + full re-auth modal
RED_LOW_MAX     = 82   # 71–82  : Session frozen overlay
RED_HIGH_MAX    = 95   # 83–95  : Session frozen + simulated SMS alert webhook
                        # 96–100 : Red Critical — silent block, bot detected

# Score band labels (for dashboard display and logging)
SCORE_BANDS = {
    (0,  GREEN_MAX):     "GREEN",
    (GREEN_MAX+1,    AMBER_LOW_MAX):  "AMBER_LOW",
    (AMBER_LOW_MAX+1, AMBER_MID_MAX): "AMBER_MID",
    (AMBER_MID_MAX+1, AMBER_HIGH_MAX):"AMBER_HIGH",
    (AMBER_HIGH_MAX+1, RED_LOW_MAX):  "RED_LOW",
    (RED_LOW_MAX+1,  RED_HIGH_MAX):   "RED_HIGH",
    (RED_HIGH_MAX+1, 100):            "RED_CRITICAL",
}

def get_score_band(score: float) -> str:
    """Return the band label for a given risk score."""
    score = int(round(score))
    if score <= GREEN_MAX:       return "GREEN"
    if score <= AMBER_LOW_MAX:   return "AMBER_LOW"
    if score <= AMBER_MID_MAX:   return "AMBER_MID"
    if score <= AMBER_HIGH_MAX:  return "AMBER_HIGH"
    if score <= RED_LOW_MAX:     return "RED_LOW"
    if score <= RED_HIGH_MAX:    return "RED_HIGH"
    return "RED_CRITICAL"


# -----------------------------------------------------------------------------
# SCORE VELOCITY RULE
# If score jumps more than this many points in a single scoring interval,
# skip Amber Mid and escalate directly to Amber High.
# -----------------------------------------------------------------------------
VELOCITY_JUMP_THRESHOLD = 20   # points — single-interval jump threshold


# -----------------------------------------------------------------------------
# STEP-UP RE-AUTHENTICATION PARAMETERS (Amber Mid)
# -----------------------------------------------------------------------------
STEPUP_REAUTH_THRESHOLD   = 45    # If re-auth keystroke score > this, treat as mismatch
REAUTH_SCORE_PENALTY      = 20    # Points added to session score on re-auth failure
REAUTH_MAX_ATTEMPTS       = 2     # Attempts before escalation to Amber High


# -----------------------------------------------------------------------------
# TRANSACTION RESTRICTIONS (Amber High — score 61–70)
# -----------------------------------------------------------------------------
AMBER_HIGH_ALLOWED_ACTIONS = [
    "view_balance",
    "view_statements",
    "view_profile",
]
AMBER_HIGH_OTP_REQUIRED_ACTIONS = [
    "transfer_under_1000",     # ₹0 – ₹999
    "upi_payment",
]
AMBER_HIGH_BLOCKED_ACTIONS = [
    "transfer_over_1000",      # ₹1,000 and above
    "change_password",
    "change_mobile",
    "add_payee",
    "transfer_over_10000",
]
LARGE_TRANSFER_THRESHOLD = 1000    # ₹ — transfers above this require OTP at Amber High
BLOCKED_TRANSFER_THRESHOLD = 10000 # ₹ — transfers above this are blocked at Amber High


# -----------------------------------------------------------------------------
# BOT DETECTION SIGNATURES (Red Critical — score 96–100)
# Any session matching these heuristics gets immediate Red Critical classification
# regardless of the computed score.
# -----------------------------------------------------------------------------
BOT_SIGNATURES = {
    "webdriver_flag":         True,   # navigator.webdriver === true
    "click_dwell_max_ms":     15,     # click dwell time < 15ms = bot click
    "flight_time_min_ms":     5,      # any flight time < 5ms = programmatic injection
    "trajectory_straightness_max": 1.05,  # near-perfect straight line = bot
    "velocity_variance_min":  0.001,  # zero velocity variance = constant speed = bot
}
BOT_SCORE_OVERRIDE = 97   # Score assigned when bot signatures are detected


# -----------------------------------------------------------------------------
# IP RATE LIMITING (Red Critical sessions)
# -----------------------------------------------------------------------------
IP_RATE_LIMIT_COOLDOWN_SEC = 600    # 10 minutes — first bot detection
IP_BLOCK_DURATION_SEC      = 86400  # 24 hours — after 3 bot detections
IP_BLOCK_TRIGGER_COUNT     = 3      # detections before 24-hour block


# -----------------------------------------------------------------------------
# TIME-OF-DAY RISK RULE
# Direct risk point additions based on session hour (24h format)
# -----------------------------------------------------------------------------
TIME_OF_DAY_RISK_POINTS = {
    0:  15,   # 12:00 AM — high risk
    1:  15,   # 1:00 AM
    2:  15,   # 2:00 AM
    3:  15,   # 3:00 AM
    4:  15,   # 4:00 AM
    5:  10,   # 5:00 AM
    6:   5,   # 6:00 AM — early but possible
    23:  8,   # 11:00 PM
    # All other hours: 0 additional points
}

def get_time_of_day_risk(hour: int) -> int:
    """Return direct risk points for a given session hour (0-23)."""
    return TIME_OF_DAY_RISK_POINTS.get(hour, 0)


# -----------------------------------------------------------------------------
# DEVICE FINGERPRINT RISK RULE
# -----------------------------------------------------------------------------
DEVICE_MISMATCH_RISK_POINTS = 18   # Points added when device fingerprint doesn't match enrolled


# -----------------------------------------------------------------------------
# EXPLAINABILITY (SHAP-lite)
# Number of top contributing features to report in the risk breakdown
# -----------------------------------------------------------------------------
EXPLAINABILITY_TOP_N = 4   # Show top 4 contributors in dashboard + fraud-ops alert


# -----------------------------------------------------------------------------
# DASHBOARD & VISUALIZATION
# -----------------------------------------------------------------------------
SESSION_TIMELINE_MAX_POINTS  = 60   # Maximum data points on the heartbeat chart
MOUSE_CANVAS_SAMPLE_RATE_MS  = 50   # Milliseconds between mouse coordinate samples
DASHBOARD_WS_HEARTBEAT_SEC   = 15   # WebSocket keepalive interval


# -----------------------------------------------------------------------------
# DEMO MODE SETTINGS
# Used when DEMO_MODE = True to load pre-baked personas
# Set to False in production
# -----------------------------------------------------------------------------
DEMO_MODE = True

DEMO_PERSONAS = {
    "legitimate": {
        "label":       "Legitimate Owner",
        "description": "Natural typing and mouse movement matching enrolled baseline",
        "expected_score_range": (5, 25),
        "expected_band": "GREEN",
    },
    "sophisticated_mimic": {
        "label":       "Sophisticated Mimic",
        "description": "Careful, deliberate typing attempting to match victim rhythm",
        "expected_score_range": (45, 65),
        "expected_band": "AMBER_MID",
    },
    "casual_intruder": {
        "label":       "Casual Intruder",
        "description": "Different rhythm, hesitant, unfamiliar with passphrase",
        "expected_score_range": (55, 75),
        "expected_band": "AMBER_HIGH",
    },
    "automated_bot": {
        "label":       "Automated Bot",
        "description": "Programmatic injection — 0ms dwell, straight-line mouse, webdriver flag",
        "expected_score_range": (95, 100),
        "expected_band": "RED_CRITICAL",
    },
}


# -----------------------------------------------------------------------------
# DATASET REFERENCES
# Public datasets used for cold-start generic baseline
# Download and place in /datasets/ before running ml_engine.py
# -----------------------------------------------------------------------------
DATASET_PATHS = {
    "cmu_keystroke": "datasets/cmu_keystroke_benchmark.csv",
    "balabit_mouse": "datasets/balabit/",
}

# Verified column names (from verify_datasets.py run)
CMU_COLUMNS = {
    "subject":      "subject",        # user ID (e.g. s002)
    "session":      "sessionIndex",   # session number
    "rep":          "rep",            # repetition number (1-50)
    # Hold time columns (key press duration) — H.period, H.t, H.i, etc.
    "hold_prefix":  "H.",
    # Flight time cols (key-up to next key-down) — UD.period.t, UD.t.i, etc.
    "flight_prefix": "UD.",
}

BALABIT_COLUMNS = {
    # NOTE: BALABIT uses spaces not underscores in column names
    "record_timestamp":  "record timestamp",
    "client_timestamp":  "client timestamp",
    "button":            "button",
    "state":             "state",
    "x":                 "x",
    "y":                 "y",
    # Label column in public_labels.csv
    "label_col":         "is_illegal",   # 0 = legitimate, 1 = intruder
    "filename_col":      "filename",
}


# -----------------------------------------------------------------------------
# SYSTEM INFO
# -----------------------------------------------------------------------------
SYSTEM_NAME    = "BehaviorShield"
SYSTEM_VERSION = "1.0.0-poc"
BANK_NAME      = "Bharat Suraksha Bank"
TEAM_NAME      = "SOLARIS"
HACKATHON      = "Cyber Security Hackathon 2026 — MNNIT Allahabad"


# -----------------------------------------------------------------------------
# LSTM AUTOENCODER — Training Hyperparameters
# Used by: scripts/train_lstm_keystroke.py, scripts/train_lstm_mouse.py
#          ml_engine.py (inference)
# Tuned for RTX 3050 6GB VRAM — safe to increase if you have more headroom.
# -----------------------------------------------------------------------------

# Architecture
LSTM_INPUT_SIZE  = 2     # features per timestep: [hold_time_ms, flight_time_ms]
LSTM_HIDDEN_SIZE = 128   # hidden units per LSTM layer (64 = safe 4GB, 128 = safe 6GB)
LSTM_NUM_LAYERS  = 2     # encoder and decoder depth
LSTM_LATENT_DIM  = 16    # bottleneck latent vector dimension

# Sequence dimensions
LSTM_SEQ_LEN_KEYSTROKE = 11   # CMU dataset: 11 keystrokes per password rep
LSTM_SEQ_LEN_MOUSE     = 50   # BALABIT: 50 consecutive mouse move events per window

# Training
LSTM_BATCH_SIZE     = 64      # samples per gradient step
LSTM_EPOCHS         = 50      # training epochs
LSTM_LEARNING_RATE  = 0.001   # Adam optimizer initial learning rate
LSTM_DROPOUT        = 0.1     # dropout between LSTM layers (regularization)
LSTM_GRAD_CLIP      = 1.0     # gradient clipping max norm (prevents exploding gradients)

# Anomaly threshold (set after training from validation reconstruction error)
# If MSE > this threshold → flag as anomaly
# Will be overridden by the value computed and saved in model_metadata.json
LSTM_ANOMALY_THRESHOLD_DEFAULT = 0.05   # placeholder — real value computed at train time

# Model file paths (relative to project root)
MODEL_DIR              = "models"
MODEL_KEYSTROKE_PT     = "models/lstm_keystroke_pretrained.pt"
MODEL_MOUSE_PT         = "models/lstm_mouse_pretrained.pt"
MODEL_XGBOOST_PKL      = "models/xgboost_fusion.pkl"
MODEL_METADATA_JSON    = "models/model_metadata.json"

