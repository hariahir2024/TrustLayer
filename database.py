# =============================================================================
# BehaviorShield — database.py
# Team SOLARIS | Cyber Security Hackathon 2026 | MNNIT Allahabad
# =============================================================================
# In-memory database for all runtime state.
# No external database required — pure Python dicts.
# Stores: user profiles, sessions, security event log, IP tracker.
# =============================================================================

import uuid
import time
import hashlib
from typing import Optional
from constants import (
    ENROLLMENT_REQUIRED_SAMPLES,
    PROFILE_WARM_SESSIONS,
    DEFAULT_SCORING_INTERVAL_SEC,
    SESSION_TOKEN_LENGTH,
    GENERIC_BASELINE_ACTIVE_UNTIL_SESSIONS,
)


# =============================================================================
# IN-MEMORY STORES
# =============================================================================

# User registry — enrolled users and their behavioral baselines
_users: dict = {}

# Active sessions — currently running banking sessions
_sessions: dict = {}

# Global security event log — ordered list of all security events
_fraud_log: list = []

# IP rate-limit tracker — for bot detection and blocking
_ip_tracker: dict = {}


# =============================================================================
# USER OPERATIONS
# =============================================================================

def create_user(username: str) -> dict:
    """
    Initialize a new user profile.
    Called when a user starts the enrollment process for the first time.
    """
    if username in _users:
        return _users[username]

    _users[username] = {
        # Enrollment state
        "username":               username,
        "enrolled":               False,           # True once baseline is built
        "enrollment_count":       0,               # number of passphrase samples collected
        "enrollment_samples":     [],              # raw keystroke feature dicts (one per attempt)
        "enrollment_sequences":   [],              # raw keystroke sequences (N, 11, 2)
        "mouse_training_sequences": [],            # raw mouse sequences lists

        # Keystroke behavioral baseline (built after ENROLLMENT_REQUIRED_SAMPLES)
        "keystroke_baseline": {
            "means": {},                           # {feature_name: float}
            "stds":  {},                           # {feature_name: float}
        },

        # Mouse model (fitted Isolation Forest — stored as sklearn object)
        "mouse_model":            None,
        "mouse_training_vectors": [],              # raw mouse feature dicts for training
        "keystroke_lstm":         None,            # fitted keystroke LSTM autoencoder module
        "mouse_lstm":             None,            # fitted mouse LSTM autoencoder module

        # Device profile
        "device_fingerprint":     None,            # hash of enrolled device signature

        # Session history
        "session_count":          0,
        "enrolled_at":            None,            # unix timestamp
        "last_seen_at":           None,

        # Profile maturity flag
        # False = still using generic population baseline
        # True  = individual profile is active (session_count >= PROFILE_WARM_SESSIONS)
        "profile_ready":          False,
    }

    return _users[username]


def get_user(username: str) -> Optional[dict]:
    """Return user profile or None if not found."""
    return _users.get(username)


def user_exists(username: str) -> bool:
    """Check if a username is registered."""
    return username in _users


def is_enrolled(username: str) -> bool:
    """Return True if user has completed enrollment and has a trained baseline."""
    user = _users.get(username)
    return user is not None and user["enrolled"]


def add_enrollment_sample(username: str, feature_vector: dict) -> int:
    """
    Add one keystroke feature vector from an enrollment passphrase attempt.
    Returns the current enrollment count after adding.
    """
    if username not in _users:
        create_user(username)

    _users[username]["enrollment_samples"].append(feature_vector)
    _users[username]["enrollment_count"] += 1

    return _users[username]["enrollment_count"]


def save_keystroke_baseline(username: str, means: dict, stds: dict) -> None:
    """
    Save the computed keystroke baseline (means + stds per feature).
    Called by ml_engine after processing all enrollment samples.
    """
    _users[username]["keystroke_baseline"]["means"] = means
    _users[username]["keystroke_baseline"]["stds"]  = stds
    _users[username]["enrolled"]    = True
    _users[username]["enrolled_at"] = time.time()


def save_mouse_model(username: str, model, training_vectors: list) -> None:
    """
    Save the fitted Isolation Forest mouse model for a user.
    Called by ml_engine after training on enrollment mouse data.
    """
    _users[username]["mouse_model"]            = model
    _users[username]["mouse_training_vectors"] = training_vectors


def save_device_fingerprint(username: str, fingerprint_hash: str) -> None:
    """Store the enrolled device fingerprint hash."""
    _users[username]["device_fingerprint"] = fingerprint_hash


def get_keystroke_baseline(username: str) -> Optional[dict]:
    """Return the user's keystroke baseline dict, or None if not enrolled."""
    user = _users.get(username)
    if user and user["enrolled"]:
        return user["keystroke_baseline"]
    return None


def get_mouse_model(username: str):
    """Return the user's fitted Isolation Forest model, or None."""
    user = _users.get(username)
    return user["mouse_model"] if user else None


def get_device_fingerprint(username: str) -> Optional[str]:
    """Return the enrolled device fingerprint hash."""
    user = _users.get(username)
    return user["device_fingerprint"] if user else None


def save_keystroke_lstm(username: str, model) -> None:
    """Save the fitted keystroke LSTM autoencoder for a user."""
    if username in _users:
        _users[username]["keystroke_lstm"] = model


def get_keystroke_lstm(username: str):
    """Return the user's fitted keystroke LSTM autoencoder, or None."""
    user = _users.get(username)
    return user["keystroke_lstm"] if user else None


def save_mouse_lstm(username: str, model) -> None:
    """Save the fitted mouse LSTM autoencoder for a user."""
    if username in _users:
        _users[username]["mouse_lstm"] = model


def get_mouse_lstm(username: str):
    """Return the user's fitted mouse LSTM autoencoder, or None."""
    user = _users.get(username)
    return user["mouse_lstm"] if user else None


def increment_user_session_count(username: str) -> None:
    """Increment session count and update profile_ready flag."""
    if username in _users:
        _users[username]["session_count"] += 1
        _users[username]["last_seen_at"]   = time.time()

        # Mark profile as ready once threshold is reached
        if _users[username]["session_count"] >= PROFILE_WARM_SESSIONS:
            _users[username]["profile_ready"] = True


def get_all_users() -> dict:
    """Return the full user registry (for admin/debug use)."""
    return _users


# =============================================================================
# SESSION OPERATIONS
# =============================================================================

def create_session(
    username:       str,
    ip_address:     str,
    user_agent:     str,
    device_fingerprint: str,
) -> str:
    """
    Create a new banking session and return its session_id.
    Called when a user successfully logs in.
    """
    session_id = str(uuid.uuid4()).replace("-", "")[:SESSION_TOKEN_LENGTH]

    _sessions[session_id] = {
        "session_id":       session_id,
        "username":         username,
        "ip_address":       ip_address,
        "user_agent":       user_agent,
        "device_fingerprint": device_fingerprint,

        # Risk state
        "status":           "active",       # active | amber_low | amber_mid | amber_high | red_low | red_high | red_critical
        "current_risk":     0.0,            # 0-100
        "risk_band":        "GREEN",
        "previous_risk":    0.0,            # used for velocity calculation

        # Risk history for session heartbeat timeline chart
        "risk_history": [],                 # [{"timestamp": float, "score": float, "band": str}]

        # Step-up re-auth tracking (Amber Mid)
        "reauth_attempts":  0,

        # Scoring frequency
        "scoring_interval": DEFAULT_SCORING_INTERVAL_SEC,

        # Timing
        "created_at":       time.time(),
        "last_scored_at":   None,

        # Action tracking (for session_action_speed + transaction_initiation_delay features)
        "action_count":     0,
        "first_action_at":  None,

        # Bot detection flag
        "is_bot":           False,

        # Per-session event log (subset of global fraud_log)
        "events":           [],

        # Explainability — last decision breakdown
        "last_breakdown":   None,
    }

    # Update user's session count
    increment_user_session_count(username)

    return session_id


def get_session(session_id: str) -> Optional[dict]:
    """Return session dict or None if not found."""
    return _sessions.get(session_id)


def session_exists(session_id: str) -> bool:
    """Check if a session ID is active."""
    return session_id in _sessions


def update_session_risk(
    session_id: str,
    score:      float,
    band:       str,
    breakdown:  dict,
) -> None:
    """
    Update the session's current risk score, band, and explainability breakdown.
    Appends to risk_history for the heartbeat timeline chart.
    """
    if session_id not in _sessions:
        return

    session = _sessions[session_id]
    session["previous_risk"]  = session["current_risk"]
    session["current_risk"]   = round(score, 1)
    session["risk_band"]      = band
    session["last_scored_at"] = time.time()
    session["last_breakdown"] = breakdown

    # Append to heartbeat timeline
    session["risk_history"].append({
        "timestamp": time.time(),
        "score":     round(score, 1),
        "band":      band,
    })

    # Keep only last 60 data points (matches SESSION_TIMELINE_MAX_POINTS)
    if len(session["risk_history"]) > 60:
        session["risk_history"] = session["risk_history"][-60:]


def update_session_status(session_id: str, status: str) -> None:
    """
    Update the session state.
    Valid statuses: active, amber_low, amber_mid, amber_high,
                    red_low, red_high, red_critical
    """
    if session_id in _sessions:
        _sessions[session_id]["status"] = status


def update_scoring_interval(session_id: str, interval_sec: int) -> None:
    """Change the scoring frequency for a session (Green=30s, Amber Low=10s)."""
    if session_id in _sessions:
        _sessions[session_id]["scoring_interval"] = interval_sec


def increment_reauth_attempts(session_id: str) -> int:
    """
    Increment the step-up re-auth attempt counter.
    Returns the new attempt count.
    """
    if session_id in _sessions:
        _sessions[session_id]["reauth_attempts"] += 1
        return _sessions[session_id]["reauth_attempts"]
    return 0


def get_reauth_attempts(session_id: str) -> int:
    """Return current re-auth attempt count for a session."""
    session = _sessions.get(session_id)
    return session["reauth_attempts"] if session else 0


def record_session_action(session_id: str) -> None:
    """
    Record that the user performed an action in this session.
    Used to compute session_action_speed and transaction_initiation_delay.
    """
    if session_id not in _sessions:
        return

    session = _sessions[session_id]
    session["action_count"] += 1

    if session["first_action_at"] is None:
        session["first_action_at"] = time.time()


def mark_session_as_bot(session_id: str) -> None:
    """Flag a session as a confirmed bot/scripted attack."""
    if session_id in _sessions:
        _sessions[session_id]["is_bot"]   = True
        _sessions[session_id]["status"]   = "red_critical"


def invalidate_session(session_id: str, reason: str = "security") -> None:
    """
    Invalidate (freeze) a session token.
    The session record is kept for the fraud log but marked as terminated.
    """
    if session_id in _sessions:
        _sessions[session_id]["status"] = "terminated"
        log_event(
            event_type = "SESSION_INVALIDATED",
            session_id = session_id,
            username   = _sessions[session_id]["username"],
            details    = {"reason": reason},
        )


def get_all_sessions() -> dict:
    """Return all sessions (for dashboard display)."""
    return _sessions


def get_active_sessions() -> list:
    """Return only sessions with status not in (terminated, red_critical)."""
    return [
        s for s in _sessions.values()
        if s["status"] not in ("terminated",)
    ]


def get_session_risk_history(session_id: str) -> list:
    """Return the risk score timeline for the heartbeat chart."""
    session = _sessions.get(session_id)
    return session["risk_history"] if session else []


# =============================================================================
# SECURITY EVENT LOG
# =============================================================================

def log_event(
    event_type: str,
    session_id: str,
    username:   str,
    details:    dict = None,
    risk_score: float = None,
    risk_band:  str = None,
) -> dict:
    """
    Append a security event to the global fraud log and to the session's event list.

    event_type examples:
        LOGIN_OK, LOGIN_FAILED, SCORE_UPDATE, AMBER_LOW, AMBER_MID_CHALLENGE,
        AMBER_HIGH_RESTRICTION, REAUTH_SUCCESS, REAUTH_FAIL,
        SESSION_FROZEN, BOT_DETECTED, SESSION_INVALIDATED,
        ADMIN_UNFREEZE, ADMIN_FORCE_STEPUP, SIMULATED_SMS_ALERT
    """
    event = {
        "event_id":   str(uuid.uuid4())[:8],
        "timestamp":  time.time(),
        "event_type": event_type,
        "session_id": session_id,
        "username":   username,
        "risk_score": risk_score,
        "risk_band":  risk_band,
        "details":    details or {},
    }

    # Append to global log
    _fraud_log.append(event)

    # Append to session-level log
    if session_id in _sessions:
        _sessions[session_id]["events"].append(event)

    return event


def get_fraud_logs(limit: int = 50) -> list:
    """Return the most recent security events (newest first)."""
    return list(reversed(_fraud_log[-limit:]))


def get_session_events(session_id: str) -> list:
    """Return all events for a specific session."""
    session = _sessions.get(session_id)
    return session["events"] if session else []


def get_stats() -> dict:
    """Return dashboard summary stats."""
    active  = [s for s in _sessions.values() if s["status"] == "active"]
    frozen  = [s for s in _sessions.values() if s["status"] in ("red_low", "red_high")]
    bots    = [s for s in _sessions.values() if s["is_bot"]]
    threats = [e for e in _fraud_log if e["event_type"] in (
        "SESSION_FROZEN", "BOT_DETECTED", "REAUTH_FAIL", "AMBER_HIGH_RESTRICTION"
    )]

    return {
        "active_sessions":  len(active),
        "frozen_sessions":  len(frozen),
        "bot_sessions":     len(bots),
        "threats_today":    len(threats),
        "total_users":      len(_users),
        "total_events":     len(_fraud_log),
    }


# =============================================================================
# IP RATE LIMITING
# =============================================================================

def is_ip_blocked(ip: str) -> tuple[bool, str]:
    """
    Check if an IP address is currently rate-limited or blocked.
    Returns (is_blocked: bool, reason: str)
    """
    if ip not in _ip_tracker:
        return False, ""

    tracker = _ip_tracker[ip]
    now = time.time()

    # Check 24-hour hard block
    if tracker.get("blocked_until", 0) > now:
        remaining = int(tracker["blocked_until"] - now)
        return True, f"IP blocked for {remaining // 60} more minutes"

    # Check 10-minute rate limit cooldown
    if tracker.get("rate_limited_until", 0) > now:
        remaining = int(tracker["rate_limited_until"] - now)
        return True, f"Rate limited for {remaining} more seconds"

    return False, ""


def register_bot_detection(ip: str) -> dict:
    """
    Register a bot detection event for an IP.
    Applies rate limit on first detection, 24-hour block after threshold.
    Returns the updated tracker entry.
    """
    from constants import (
        IP_RATE_LIMIT_COOLDOWN_SEC,
        IP_BLOCK_DURATION_SEC,
        IP_BLOCK_TRIGGER_COUNT,
    )

    now = time.time()

    if ip not in _ip_tracker:
        _ip_tracker[ip] = {
            "bot_detection_count": 0,
            "first_detection":     now,
            "rate_limited_until":  0,
            "blocked_until":       0,
        }

    tracker = _ip_tracker[ip]
    tracker["bot_detection_count"] += 1

    if tracker["bot_detection_count"] >= IP_BLOCK_TRIGGER_COUNT:
        # Hard 24-hour block
        tracker["blocked_until"] = now + IP_BLOCK_DURATION_SEC
    else:
        # 10-minute rate limit cooldown
        tracker["rate_limited_until"] = now + IP_RATE_LIMIT_COOLDOWN_SEC

    return tracker


def get_ip_tracker() -> dict:
    """Return the full IP tracker (for admin/debug)."""
    return _ip_tracker


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def generate_device_fingerprint(
    user_agent:    str,
    screen_width:  int,
    screen_height: int,
    color_depth:   int,
    timezone:      str,
    language:      str,
) -> str:
    """
    Generate a device fingerprint hash from browser metadata.
    Hash(UA + resolution + color_depth + timezone + language)
    Only the hash is stored — never the raw values.
    """
    raw = f"{user_agent}|{screen_width}x{screen_height}|{color_depth}|{timezone}|{language}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def reset_all() -> None:
    """
    Hard reset all in-memory stores.
    Used for testing or demo reset between runs.
    """
    global _users, _sessions, _fraud_log, _ip_tracker
    _users      = {}
    _sessions   = {}
    _fraud_log  = []
    _ip_tracker = {}


def get_database_summary() -> dict:
    """Return a summary of current database state (for health checks)."""
    return {
        "users":    len(_users),
        "sessions": len(_sessions),
        "events":   len(_fraud_log),
        "ips":      len(_ip_tracker),
    }
