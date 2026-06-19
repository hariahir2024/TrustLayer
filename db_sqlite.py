# =============================================================================
# BehaviorShield — db_sqlite.py
# Team SOLARIS | Cyber Security Hackathon 2026 | MNNIT Allahabad
# =============================================================================
# Persistent SQLite database for all runtime state.
# Replaces database.py and survives server restarts.
# =============================================================================

import os
import uuid
import time
import json
import sqlite3
import hashlib
import pickle
from typing import Optional, List, Dict, Any
from constants import (
    ENROLLMENT_REQUIRED_SAMPLES,
    PROFILE_WARM_SESSIONS,
    DEFAULT_SCORING_INTERVAL_SEC,
    SESSION_TOKEN_LENGTH,
    GENERIC_BASELINE_ACTIVE_UNTIL_SESSIONS,
)

DB_PATH = r"C:\Users\LOQ\Documents\antigravity\behaviorshield.db"
PROFILES_DIR = r"C:\Users\LOQ\Documents\antigravity\profiles"

# Thread-safe in-memory cache for loaded model objects (PyTorch/sklearn)
# Since binary models cannot be cleanly stored in SQLite directly, they are saved as files
# and their instantiated objects are cached here on startup.
_model_cache: Dict[str, Any] = {}

def init_db(db_path: Optional[str] = None):
    """Initialize SQLite database and create all tables if they don't exist."""
    global DB_PATH
    if db_path:
        DB_PATH = db_path
    
    # Ensure directories exist
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    os.makedirs(PROFILES_DIR, exist_ok=True)
    
    conn = _get_conn()
    cursor = conn.cursor()
    
    # 1. Users table (stores credentials, balances, and dynamic passphrase details)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        first_name TEXT DEFAULT '',
        last_name TEXT DEFAULT '',
        city TEXT DEFAULT '',
        mobile TEXT DEFAULT '',
        date_of_birth TEXT DEFAULT '',
        email TEXT DEFAULT '',
        account_number TEXT UNIQUE,
        account_type TEXT DEFAULT 'savings',
        balance REAL DEFAULT 50000.0,
        passphrase TEXT DEFAULT '',
        password_hash TEXT DEFAULT '',
        created_at REAL,
        last_seen_at REAL
    );
    """)
    
    # 2. Behavioral profiles table (Multi-device: composite key username + device_class)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS behavioral_profiles (
        username TEXT,
        device_class TEXT DEFAULT 'DESKTOP',
        enrolled INTEGER DEFAULT 0,
        enrollment_count INTEGER DEFAULT 0,
        session_count INTEGER DEFAULT 0,
        profile_ready INTEGER DEFAULT 0,
        keystroke_means TEXT DEFAULT '{}',
        keystroke_stds TEXT DEFAULT '{}',
        enrollment_seqs TEXT DEFAULT '[]',
        mouse_vectors TEXT DEFAULT '[]',
        device_fps TEXT DEFAULT '[]',
        enrolled_at REAL,
        updated_at REAL,
        PRIMARY KEY (username, device_class)
    );
    """)
    
    # 3. Transactions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        session_id TEXT,
        txn_type TEXT,
        amount REAL,
        description TEXT,
        beneficiary TEXT,
        status TEXT,
        risk_score REAL,
        created_at REAL
    );
    """)
    
    # 4. Security events table (stores global alerts and audit logs)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS security_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT UNIQUE,
        event_type TEXT,
        session_id TEXT,
        username TEXT,
        details TEXT DEFAULT '{}',
        risk_score REAL,
        risk_band TEXT,
        is_intruder INTEGER DEFAULT 0,
        timestamp REAL
    );
    """)
    
    # 5. Payees table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_username TEXT,
        name TEXT,
        account_number TEXT,
        ifsc TEXT,
        bank_name TEXT,
        upi_id TEXT,
        added_at REAL
    );
    """)
    
    # 6. Active sessions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        username TEXT,
        device_class TEXT DEFAULT 'DESKTOP',
        ip_address TEXT,
        user_agent TEXT,
        device_fingerprint TEXT,
        status TEXT DEFAULT 'active',
        current_risk REAL DEFAULT 0.0,
        risk_band TEXT DEFAULT 'GREEN',
        previous_risk REAL DEFAULT 0.0,
        reauth_attempts INTEGER DEFAULT 0,
        scoring_interval INTEGER,
        created_at REAL,
        last_scored_at REAL,
        action_count INTEGER DEFAULT 0,
        first_action_at REAL,
        is_bot INTEGER DEFAULT 0,
        is_intruder INTEGER DEFAULT 0,
        risk_history TEXT DEFAULT '[]',
        last_breakdown TEXT DEFAULT '{}'
    );
    """)
    
    # 7. IP tracker table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ip_tracker (
        ip TEXT PRIMARY KEY,
        bot_detection_count INTEGER DEFAULT 0,
        first_detection REAL,
        rate_limited_until REAL DEFAULT 0,
        blocked_until REAL DEFAULT 0
    );
    """)
    
    # 8. Support tickets table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS support_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id TEXT UNIQUE,
        username TEXT,
        category TEXT,
        description TEXT,
        created_at REAL,
        status TEXT DEFAULT 'Open'
    );
    """)
    
    conn.commit()
    conn.close()

def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _connect():
    return _get_conn()


# =============================================================================
# USER OPERATIONS
# =============================================================================

def create_user(username: str, first_name: str = "", last_name: str = "", city: str = "",
                mobile: str = "", dob: str = "", email: str = "", account_type: str = "savings",
                password_hash: str = "", passphrase: str = None, date_of_birth: str = None) -> dict:
    """Initialize a new user profile in SQLite."""
    conn = _get_conn()
    cursor = conn.cursor()
    
    # Generate account details
    account_number = generate_account_number()
    created_now = time.time()
    
    try:
        # Check if already exists
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row:
            return dict(row)
            
        if date_of_birth is not None:
            dob = date_of_birth
            
        if not passphrase:
            from constants import generate_passphrase
            passphrase = generate_passphrase(first_name or username, last_name or username)
        
        cursor.execute("""
        INSERT INTO users (username, first_name, last_name, city, mobile, date_of_birth,
                           email, account_number, account_type, balance, passphrase, password_hash,
                           created_at, last_seen_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 50000.0, ?, ?, ?, ?)
        """, (username, first_name, last_name, city, mobile, dob, email, account_number,
              account_type, passphrase, password_hash, created_now, created_now))
        
        # Create default DESKTOP device profile
        cursor.execute("""
        INSERT OR IGNORE INTO behavioral_profiles (username, device_class, enrolled, enrollment_count,
                                                   session_count, profile_ready, keystroke_means, keystroke_stds,
                                                   enrollment_seqs, mouse_vectors, device_fps, enrolled_at, updated_at)
        VALUES (?, 'DESKTOP', 0, 0, 0, 0, '{}', '{}', '[]', '[]', '[]', NULL, ?)
        """, (username, created_now))
        
        conn.commit()
    except Exception as e:
        print(f"[SQLite] Error creating user: {e}")
    finally:
        conn.close()
        
    return get_user(username)

def get_user(username: str) -> Optional[dict]:
    """Return user profile dictionary or None."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def user_exists(username: str) -> bool:
    """Check if a username is registered."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def hash_password(password: str) -> str:
    """Hash a password using SHA-256."""
    if not password:
        return ""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(username: str, password: str) -> bool:
    """Verify user's password."""
    user = get_user(username)
    if not user:
        return False
    pwd_hash = hash_password(password)
    return user.get("password_hash") == pwd_hash

def update_user_password(username: str, pwd_hash: str) -> None:
    """Update the user's password hash in the database."""
    conn = _get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (pwd_hash, username))
        conn.commit()
    except Exception as e:
        print(f"[SQLite] Error updating password: {e}")
    finally:
        conn.close()


def is_enrolled(username: str, device_class: str = "DESKTOP") -> bool:
    """Return True if user has completed enrollment and has a trained baseline on device_class."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT enrolled FROM behavioral_profiles 
    WHERE username = ? AND device_class = ?
    """, (username, device_class))
    row = cursor.fetchone()
    conn.close()
    return row is not None and bool(row["enrolled"])

def get_behavioral_profile(username: str, device_class: str = "DESKTOP") -> Optional[dict]:
    """Get the behavioral profile details for a specific user and device class."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM behavioral_profiles 
    WHERE username = ? AND device_class = ?
    """, (username, device_class))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["keystroke_means"] = json.loads(d["keystroke_means"])
        d["keystroke_stds"] = json.loads(d["keystroke_stds"])
        d["enrollment_seqs"] = json.loads(d["enrollment_seqs"])
        d["mouse_vectors"] = json.loads(d["mouse_vectors"])
        d["device_fps"] = json.loads(d["device_fps"])
        return d
    return None

def save_behavioral_profile(username: str, device_class: str, means: dict, stds: dict,
                             enrollment_seqs: list, mouse_vectors: list = None, device_fps: list = None) -> None:
    """Save/update the complete behavioral baseline profiles for a user and device class."""
    conn = _get_conn()
    cursor = conn.cursor()
    now = time.time()
    
    # Ensure profile row exists
    cursor.execute("""
    INSERT OR IGNORE INTO behavioral_profiles (username, device_class, enrolled, enrollment_count,
                                               session_count, profile_ready, keystroke_means, keystroke_stds,
                                               enrollment_seqs, mouse_vectors, device_fps, enrolled_at, updated_at)
    VALUES (?, ?, 0, 0, 0, 0, '{}', '{}', '[]', '[]', '[]', NULL, ?)
    """, (username, device_class, now))
    
    cursor.execute("""
    UPDATE behavioral_profiles
    SET enrolled = 1,
        keystroke_means = ?,
        keystroke_stds = ?,
        enrollment_seqs = ?,
        mouse_vectors = COALESCE(?, mouse_vectors),
        device_fps = COALESCE(?, device_fps),
        enrolled_at = COALESCE(enrolled_at, ?),
        updated_at = ?
    WHERE username = ? AND device_class = ?
    """, (json.dumps(means), json.dumps(stds), json.dumps(enrollment_seqs),
          json.dumps(mouse_vectors) if mouse_vectors is not None else None,
          json.dumps(device_fps) if device_fps is not None else None,
          now, now, username, device_class))
    conn.commit()
    conn.close()

def add_enrollment_sample(username: str, feature_vector: dict, device_class: str = "DESKTOP") -> int:
    """Add enrollment sample, returns current count."""
    conn = _get_conn()
    cursor = conn.cursor()
    now = time.time()
    
    # Ensure profile row exists
    cursor.execute("""
    INSERT OR IGNORE INTO behavioral_profiles (username, device_class, enrolled, enrollment_count,
                                               session_count, profile_ready, keystroke_means, keystroke_stds,
                                               enrollment_seqs, mouse_vectors, device_fps, enrolled_at, updated_at)
    VALUES (?, ?, 0, 0, 0, 0, '{}', '{}', '[]', '[]', '[]', NULL, ?)
    """, (username, device_class, now))
    
    cursor.execute("""
    SELECT enrollment_count, enrollment_seqs FROM behavioral_profiles 
    WHERE username = ? AND device_class = ?
    """, (username, device_class))
    row = cursor.fetchone()
    
    count = 1
    seqs = []
    if row:
        count = row["enrollment_count"] + 1
        seqs = json.loads(row["enrollment_seqs"])
    
    seqs.append(feature_vector)
    
    cursor.execute("""
    UPDATE behavioral_profiles
    SET enrollment_count = ?,
        enrollment_seqs = ?,
        updated_at = ?
    WHERE username = ? AND device_class = ?
    """, (count, json.dumps(seqs), now, username, device_class))
    
    conn.commit()
    conn.close()
    return count

def save_keystroke_baseline(username: str, means: dict, stds: dict, device_class: str = "DESKTOP") -> None:
    """Save computed keystroke baseline."""
    conn = _get_conn()
    cursor = conn.cursor()
    now = time.time()
    
    cursor.execute("""
    UPDATE behavioral_profiles
    SET enrolled = 1,
        keystroke_means = ?,
        keystroke_stds = ?,
        enrolled_at = COALESCE(enrolled_at, ?),
        updated_at = ?
    WHERE username = ? AND device_class = ?
    """, (json.dumps(means), json.dumps(stds), now, now, username, device_class))
    
    # Also update user passphrase record
    from constants import generate_passphrase
    user = get_user(username)
    if user:
        passphrase = generate_passphrase(user["first_name"], user["last_name"])
        cursor.execute("UPDATE users SET passphrase = ? WHERE username = ?", (passphrase, username))
        
    conn.commit()
    conn.close()

def save_mouse_model(username: str, model, training_vectors: list, device_class: str = "DESKTOP") -> None:
    """Save fitted sklearn Isolation Forest model file and cache object."""
    key = f"{username}_{device_class}_mouse_model"
    _model_cache[key] = model
    
    model_path = os.path.join(PROFILES_DIR, f"{key}.pkl")
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
        
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE behavioral_profiles
    SET mouse_vectors = ?
    WHERE username = ? AND device_class = ?
    """, (json.dumps(training_vectors), username, device_class))
    conn.commit()
    conn.close()

def update_mouse_vectors(username: str, vectors: list, device_class: str = "DESKTOP") -> None:
    """Save the mouse training vectors list to the user's profile."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE behavioral_profiles
    SET mouse_vectors = ?
    WHERE username = ? AND device_class = ?
    """, (json.dumps(vectors), username, device_class))
    conn.commit()
    conn.close()

def save_device_fingerprint(username: str, fingerprint_hash: str, device_class: str = "DESKTOP") -> None:
    """Save a verified device fingerprint hash to trusted list."""
    conn = _get_conn()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT device_fps FROM behavioral_profiles 
    WHERE username = ? AND device_class = ?
    """, (username, device_class))
    row = cursor.fetchone()
    
    fps = []
    if row and row["device_fps"]:
        fps = json.loads(row["device_fps"])
        
    if fingerprint_hash not in fps:
        fps.append(fingerprint_hash)
        
    cursor.execute("""
    UPDATE behavioral_profiles
    SET device_fps = ?
    WHERE username = ? AND device_class = ?
    """, (json.dumps(fps), username, device_class))
    
    conn.commit()
    conn.close()

def get_keystroke_baseline(username: str, device_class: str = "DESKTOP") -> Optional[dict]:
    """Get baseline timings."""
    profile = get_behavioral_profile(username, device_class)
    if profile and profile["enrolled"]:
        return {
            "means": profile["keystroke_means"],
            "stds": profile["keystroke_stds"]
        }
    return None

def update_keystroke_baseline_drift(username: str, device_class: str, session_features: dict, drift_weight: float) -> None:
    """Apply progressive timing baseline drift for GREEN sessions."""
    profile = get_behavioral_profile(username, device_class)
    if not profile or not profile.get("enrolled"):
        return
        
    means = profile["keystroke_means"]
    stds = profile["keystroke_stds"]
    
    updated_means = {}
    for k, v in means.items():
        if k in session_features:
            updated_means[k] = (1 - drift_weight) * v + drift_weight * session_features[k]
        else:
            updated_means[k] = v
            
    save_keystroke_baseline(username, updated_means, stds, device_class)

def get_mouse_model(username: str, device_class: str = "DESKTOP"):
    """Load and return user Isolation Forest mouse model."""
    key = f"{username}_{device_class}_mouse_model"
    if key in _model_cache:
        return _model_cache[key]
        
    model_path = os.path.join(PROFILES_DIR, f"{key}.pkl")
    if os.path.exists(model_path):
        try:
            with open(model_path, "rb") as f:
                model = pickle.load(f)
                _model_cache[key] = model
                return model
        except Exception as e:
            print(f"[SQLite] Error loading mouse model: {e}")
    return None

def get_device_fingerprint(username: str, device_class: str = "DESKTOP") -> Optional[str]:
    """Get primary enrolled device fingerprint (first trusted signature)."""
    profile = get_behavioral_profile(username, device_class)
    if profile and profile["device_fps"]:
        return profile["device_fps"][0]
    return None

def save_keystroke_lstm(username: str, model, device_class: str = "DESKTOP") -> None:
    """Save PyTorch keystroke model and cache it."""
    key = f"{username}_{device_class}_keystroke_lstm"
    _model_cache[key] = model
    
    import torch
    model_path = os.path.join(PROFILES_DIR, f"{key}.pt")
    torch.save({"model_state_dict": model.state_dict()}, model_path)

def get_keystroke_lstm(username: str, device_class: str = "DESKTOP"):
    """Get PyTorch keystroke LSTM model object."""
    key = f"{username}_{device_class}_keystroke_lstm"
    if key in _model_cache:
        return _model_cache[key]
        
    import torch
    from ml_engine import LSTMAutoencoder, LSTM_SEQ_LEN_KEYSTROKE
    model_path = os.path.join(PROFILES_DIR, f"{key}.pt")
    if os.path.exists(model_path):
        try:
            model = LSTMAutoencoder(input_size=2, seq_len=LSTM_SEQ_LEN_KEYSTROKE)
            checkpoint = torch.load(model_path, map_location=torch.device("cpu"), weights_only=True)
            model.load_state_dict(checkpoint["model_state_dict"])
            model.eval()
            _model_cache[key] = model
            return model
        except Exception as e:
            print(f"[SQLite] Error loading keystroke LSTM: {e}")
    return None

def save_mouse_lstm(username: str, model, device_class: str = "DESKTOP") -> None:
    """Save PyTorch mouse model and cache it."""
    key = f"{username}_{device_class}_mouse_lstm"
    _model_cache[key] = model
    
    import torch
    model_path = os.path.join(PROFILES_DIR, f"{key}.pt")
    torch.save({"model_state_dict": model.state_dict()}, model_path)

def get_mouse_lstm(username: str, device_class: str = "DESKTOP"):
    """Get PyTorch mouse LSTM model object."""
    key = f"{username}_{device_class}_mouse_lstm"
    if key in _model_cache:
        return _model_cache[key]
        
    import torch
    from ml_engine import LSTMAutoencoder, LSTM_SEQ_LEN_MOUSE
    model_path = os.path.join(PROFILES_DIR, f"{key}.pt")
    if os.path.exists(model_path):
        try:
            model = LSTMAutoencoder(input_size=2, seq_len=LSTM_SEQ_LEN_MOUSE)
            checkpoint = torch.load(model_path, map_location=torch.device("cpu"), weights_only=True)
            model.load_state_dict(checkpoint["model_state_dict"])
            model.eval()
            _model_cache[key] = model
            return model
        except Exception as e:
            print(f"[SQLite] Error loading mouse LSTM: {e}")
    return None

def increment_user_session_count(username: str, device_class: str = "DESKTOP") -> None:
    """Increment profile usage count and check maturity status."""
    conn = _get_conn()
    cursor = conn.cursor()
    now = time.time()
    
    cursor.execute("UPDATE users SET last_seen_at = ? WHERE username = ?", (now, username))
    
    cursor.execute("""
    SELECT session_count FROM behavioral_profiles 
    WHERE username = ? AND device_class = ?
    """, (username, device_class))
    row = cursor.fetchone()
    
    if row:
        new_count = row["session_count"] + 1
        ready = 1 if new_count >= PROFILE_WARM_SESSIONS else 0
        cursor.execute("""
        UPDATE behavioral_profiles
        SET session_count = ?,
            profile_ready = ?,
            updated_at = ?
        WHERE username = ? AND device_class = ?
        """, (new_count, ready, now, username, device_class))
        
    conn.commit()
    conn.close()

def get_all_users() -> dict:
    """Get all enrolled users."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()
    conn.close()
    
    res = {}
    for r in rows:
        username = r["username"]
        res[username] = dict(r)
        res[username]["enrolled"] = is_enrolled(username)
    return res

def load_all_profiles() -> dict:
    """Warm up cached models and profiles into RAM at server boot and return them."""
    print("[SQLite] Loading pre-trained PyTorch and sklearn profiles from disk...")
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM behavioral_profiles")
    rows = cursor.fetchall()
    conn.close()
    
    profiles = {}
    for r in rows:
        username = r["username"]
        dev_class = r["device_class"]
        d = dict(r)
        try:
            d["keystroke_means"] = json.loads(d["keystroke_means"])
            d["keystroke_stds"] = json.loads(d["keystroke_stds"])
            d["enrollment_seqs"] = json.loads(d["enrollment_seqs"])
            d["mouse_vectors"] = json.loads(d["mouse_vectors"])
            d["device_fps"] = json.loads(d["device_fps"])
        except Exception as e:
            print(f"[SQLite] JSON parse error on profile load: {e}")
            
        profiles[(username, dev_class)] = d
        
        # Warm up caches for enrolled profiles
        if d.get("enrolled"):
            get_keystroke_lstm(username, dev_class)
            get_mouse_lstm(username, dev_class)
            get_mouse_model(username, dev_class)
            
    return profiles

# =============================================================================
# SESSION OPERATIONS
# =============================================================================

def create_session(
    username: str,
    ip_address: str,
    user_agent: str,
    device_fingerprint: str,
    device_class: str = "DESKTOP"
) -> str:
    """Insert a new session into SQLite database."""
    session_id = str(uuid.uuid4()).replace("-", "")[:SESSION_TOKEN_LENGTH]
    conn = _get_conn()
    cursor = conn.cursor()
    now = time.time()
    
    cursor.execute("""
    INSERT INTO sessions (session_id, username, device_class, ip_address, user_agent,
                           device_fingerprint, status, current_risk, risk_band, previous_risk,
                           reauth_attempts, scoring_interval, created_at, last_scored_at,
                           action_count, first_action_at, is_bot, is_intruder, risk_history, last_breakdown)
    VALUES (?, ?, ?, ?, ?, ?, 'active', 0.0, 'GREEN', 0.0, 0, ?, ?, NULL, 0, NULL, 0, 0, '[]', '{}')
    """, (session_id, username, device_class, ip_address, user_agent, device_fingerprint,
          DEFAULT_SCORING_INTERVAL_SEC, now))
    
    conn.commit()
    conn.close()
    
    # Increment profile session stats
    increment_user_session_count(username, device_class)
    return session_id

def get_session(session_id: str) -> Optional[dict]:
    """Get active session details."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["risk_history"] = json.loads(d["risk_history"])
        d["last_breakdown"] = json.loads(d["last_breakdown"])
        d["is_bot"] = bool(d["is_bot"])
        d["is_intruder"] = bool(d["is_intruder"])
        return d
    return None

def session_exists(session_id: str) -> bool:
    """Check if session is active."""
    return get_session(session_id) is not None

def update_session_risk(
    session_id: str,
    score: float,
    band: str,
    breakdown: dict,
) -> None:
    """Update risk levels and SHAP analysis logs."""
    conn = _get_conn()
    cursor = conn.cursor()
    
    session = get_session(session_id)
    if not session:
        conn.close()
        return
        
    history = session["risk_history"]
    history.append({
        "timestamp": time.time(),
        "score": round(score, 1),
        "band": band
    })
    
    # Bound history length
    if len(history) > 60:
        history = history[-60:]
        
    cursor.execute("""
    UPDATE sessions
    SET previous_risk = current_risk,
        current_risk = ?,
        risk_band = ?,
        last_scored_at = ?,
        risk_history = ?,
        last_breakdown = ?
    WHERE session_id = ?
    """, (round(score, 1), band, time.time(), json.dumps(history), json.dumps(breakdown), session_id))
    
    conn.commit()
    conn.close()

def update_session_status(session_id: str, status: str) -> None:
    """Set status (active, terminated, frozen etc.)"""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE sessions SET status = ? WHERE session_id = ?", (status, session_id))
    conn.commit()
    conn.close()

def update_scoring_interval(session_id: str, interval_sec: int) -> None:
    """Modify client refresh rate."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE sessions SET scoring_interval = ? WHERE session_id = ?", (interval_sec, session_id))
    conn.commit()
    conn.close()

def increment_reauth_attempts(session_id: str) -> int:
    """Increment re-auth fail counts."""
    conn = _get_conn()
    cursor = conn.cursor()
    session = get_session(session_id)
    count = 0
    if session:
        count = session["reauth_attempts"] + 1
        cursor.execute("UPDATE sessions SET reauth_attempts = ? WHERE session_id = ?", (count, session_id))
        conn.commit()
    conn.close()
    return count

def get_reauth_attempts(session_id: str) -> int:
    """Return count of verification checks."""
    session = get_session(session_id)
    return session["reauth_attempts"] if session else 0

def record_session_action(session_id: str) -> None:
    """Log click action for velocity feature tracking."""
    conn = _get_conn()
    cursor = conn.cursor()
    session = get_session(session_id)
    if session:
        count = session["action_count"] + 1
        first_action = session["first_action_at"] or time.time()
        cursor.execute("""
        UPDATE sessions 
        SET action_count = ?, first_action_at = ? 
        WHERE session_id = ?
        """, (count, first_action, session_id))
        conn.commit()
    conn.close()

def mark_session_as_bot(session_id: str) -> None:
    """Mark session as a confirmed automated attack."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE sessions SET is_bot = 1, status = 'red_critical' WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

def invalidate_session(session_id: str, reason: str = "security") -> None:
    """Terminate the session."""
    conn = _get_conn()
    cursor = conn.cursor()
    session = get_session(session_id)
    if session:
        cursor.execute("UPDATE sessions SET status = 'terminated' WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()
        log_event(
            event_type = "SESSION_INVALIDATED",
            session_id = session_id,
            username   = session["username"],
            details    = {"reason": reason},
        )
    else:
        conn.close()

def get_all_sessions() -> dict:
    """Get active sessions as a map (key=session_id)."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions")
    rows = cursor.fetchall()
    conn.close()
    
    res = {}
    for r in rows:
        d = dict(r)
        d["risk_history"] = json.loads(d["risk_history"])
        d["last_breakdown"] = json.loads(d["last_breakdown"])
        d["is_bot"] = bool(d["is_bot"])
        d["is_intruder"] = bool(d["is_intruder"])
        res[r["session_id"]] = d
    return res

def get_active_sessions() -> list:
    """Get sessions currently monitored in dashboard list."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions WHERE status != 'terminated'")
    rows = cursor.fetchall()
    conn.close()
    
    res = []
    for r in rows:
        d = dict(r)
        d["risk_history"] = json.loads(d["risk_history"])
        d["last_breakdown"] = json.loads(d["last_breakdown"])
        d["is_bot"] = bool(d["is_bot"])
        d["is_intruder"] = bool(d["is_intruder"])
        res.append(d)
    return res

def get_session_risk_history(session_id: str) -> list:
    """Get timeline chart risk list."""
    session = get_session(session_id)
    return session["risk_history"] if session else []

# =============================================================================
# TRANSACTION DATA
# =============================================================================

def add_transaction(username: str, session_id: str, txn_type: str, amount: float,
                    description: str, beneficiary: str, status: str = "success", risk_score: float = 0.0) -> None:
    """Log a transaction record in the ledger."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO transactions (username, session_id, txn_type, amount, description, beneficiary, status, risk_score, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (username, session_id, txn_type, amount, description, beneficiary, status, risk_score, time.time()))
    
    # Deduct balance if successful debit
    if status == "success" and txn_type in ("debit", "transfer", "bill", "upi"):
        cursor.execute("UPDATE users SET balance = balance - ? WHERE username = ?", (amount, username))
        
    conn.commit()
    conn.close()

def get_transactions(username: str, limit: int = 20) -> list:
    """Fetch user's transaction ledger history."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM transactions WHERE username = ? 
    ORDER BY created_at DESC LIMIT ?
    """, (username, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# =============================================================================
# PAYEE OPERATIONS
# =============================================================================

def add_payee(owner_username: str, name: str, account_number: str = "", ifsc: str = "",
              bank_name: str = "", upi_id: str = "") -> None:
    """Register a new payee."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO payees (owner_username, name, account_number, ifsc, bank_name, upi_id, added_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (owner_username, name, account_number, ifsc, bank_name, upi_id, time.time()))
    conn.commit()
    conn.close()

def get_payees(owner_username: str) -> list:
    """Return all registered payees."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payees WHERE owner_username = ?", (owner_username,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_payee(payee_id: int, owner_username: str = None) -> bool:
    """Remove a payee from list. Returns True if deleted."""
    conn = _get_conn()
    cursor = conn.cursor()
    if owner_username:
        cursor.execute("DELETE FROM payees WHERE id = ? AND owner_username = ?", (payee_id, owner_username))
    else:
        cursor.execute("DELETE FROM payees WHERE id = ?", (payee_id,))
    rows_deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_deleted > 0

def add_support_ticket(username: str, category: str, description: str) -> dict:
    """Create a support ticket in SQLite."""
    conn = _get_conn()
    cursor = conn.cursor()
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    created_now = time.time()
    cursor.execute("""
    INSERT INTO support_tickets (ticket_id, username, category, description, created_at, status)
    VALUES (?, ?, ?, ?, ?, 'Open')
    """, (ticket_id, username, category, description, created_now))
    conn.commit()
    
    cursor.execute("SELECT * FROM support_tickets WHERE ticket_id = ?", (ticket_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row)

def get_support_tickets(username: str) -> list:
    """Fetch support tickets for a user."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM support_tickets WHERE username = ? ORDER BY created_at DESC", (username,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# =============================================================================
# SECURITY EVENT LOG
# =============================================================================

def log_event(
    event_type: str,
    session_id: str,
    username: str,
    details: dict = None,
    risk_score: float = None,
    risk_band: str = None,
) -> dict:
    """Log an audit event to global logs and persist it."""
    event_id = str(uuid.uuid4())[:8]
    now = time.time()
    details_str = json.dumps(details or {})
    
    conn = _get_conn()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
        INSERT INTO security_events (event_id, event_type, session_id, username, details, risk_score, risk_band, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (event_id, event_type, session_id, username, details_str, risk_score, risk_band, now))
        conn.commit()
    except Exception as e:
        print(f"[SQLite] Event log insertion error: {e}")
    finally:
        conn.close()
        
    return {
        "event_id": event_id,
        "timestamp": now,
        "event_type": event_type,
        "session_id": session_id,
        "username": username,
        "risk_score": risk_score,
        "risk_band": risk_band,
        "details": details or {}
    }

def get_fraud_logs(limit: int = 50) -> list:
    """Get log feed feed rows (newest first)."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM security_events ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    res = []
    for r in rows:
        d = dict(r)
        d["details"] = json.loads(d["details"])
        d["is_intruder"] = bool(d["is_intruder"])
        res.append(d)
    return res

def get_session_events(session_id: str) -> list:
    """Get log list specific to a single session."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM security_events WHERE session_id = ? ORDER BY timestamp ASC", (session_id,))
    rows = cursor.fetchall()
    conn.close()
    
    res = []
    for r in rows:
        d = dict(r)
        d["details"] = json.loads(d["details"])
        d["is_intruder"] = bool(d["is_intruder"])
        res.append(d)
    return res

def label_session_intruder(session_id: str, label_all_recent: bool = False) -> None:
    """Label session (and optionally recent user sessions) as intruder."""
    conn = _get_conn()
    cursor = conn.cursor()
    
    session = get_session(session_id)
    if not session:
        conn.close()
        return
        
    username = session["username"]
    
    if label_all_recent:
        # Label all sessions for this user created in the last 30 minutes
        cutoff = time.time() - 1800
        cursor.execute("""
        UPDATE sessions SET is_intruder = 1 
        WHERE username = ? AND created_at >= ?
        """, (username, cutoff))
        cursor.execute("""
        UPDATE security_events SET is_intruder = 1 
        WHERE username = ? AND timestamp >= ?
        """, (username, cutoff))
    else:
        cursor.execute("UPDATE sessions SET is_intruder = 1 WHERE session_id = ?", (session_id,))
        cursor.execute("UPDATE security_events SET is_intruder = 1 WHERE session_id = ?", (session_id,))
        
    conn.commit()
    conn.close()

def get_labeled_data() -> list:
    """Return all session details that have been labeled (is_intruder=1 or is_intruder=0) for XGBoost retraining."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions WHERE status == 'terminated' OR status == 'frozen' OR is_intruder = 1")
    rows = cursor.fetchall()
    conn.close()
    
    res = []
    for r in rows:
        d = dict(r)
        d["last_breakdown"] = json.loads(d["last_breakdown"])
        res.append(d)
    return res

def get_data_collection_summary() -> dict:
    """Calculate the status metrics of data collection campaigns."""
    conn = _get_conn()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as total_users FROM users")
    total_users = cursor.fetchone()["total_users"]
    
    cursor.execute("SELECT COUNT(*) as total_sessions FROM sessions")
    total_sessions = cursor.fetchone()["total_sessions"]
    
    cursor.execute("SELECT COUNT(*) as total_intruder FROM sessions WHERE is_intruder = 1")
    total_intruder = cursor.fetchone()["total_intruder"]
    
    cursor.execute("""
    SELECT username, device_class, session_count, enrolled 
    FROM behavioral_profiles
    """)
    profiles_rows = cursor.fetchall()
    conn.close()
    
    users_list = []
    for pr in profiles_rows:
        users_list.append({
            "username": pr["username"],
            "device_class": pr["device_class"],
            "session_count": pr["session_count"],
            "enrolled": bool(pr["enrolled"]),
            "intruder_count": total_intruder # simplified mapping
        })
        
    return {
        "users": users_list,
        "totals": {
            "total_users": total_users,
            "total_sessions": total_sessions,
            "total_intruder_sessions": total_intruder,
            "ready_for_retraining": total_intruder >= 20,
            "legitimate_count": total_sessions - total_intruder,
            "intruder_count": total_intruder
        }
    }

def get_stats() -> dict:
    """Return header stats counters."""
    conn = _get_conn()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE status = 'active'")
    active_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE status IN ('red_low', 'red_high')")
    frozen_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE is_bot = 1")
    bot_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM security_events")
    events_count = cursor.fetchone()[0]
    
    # Threats are events of specific severity
    cursor.execute("""
    SELECT COUNT(*) FROM security_events 
    WHERE event_type IN ('SESSION_FROZEN', 'BOT_DETECTED', 'REAUTH_FAIL', 'AMBER_HIGH_RESTRICTION')
    """)
    threats_count = cursor.fetchone()[0]
    
    conn.close()
    return {
        "active_sessions": active_count,
        "frozen_sessions": frozen_count,
        "bot_sessions": bot_count,
        "threats_today": threats_count,
        "total_users": users_count,
        "total_events": events_count,
    }

# =============================================================================
# IP RATE LIMITING
# =============================================================================

def is_ip_blocked(ip: str) -> tuple[bool, str]:
    """Check IP blocked status."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ip_tracker WHERE ip = ?", (ip,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return False, ""
        
    now = time.time()
    # Check block timer
    if row["blocked_until"] > now:
        remaining = int(row["blocked_until"] - now)
        return True, f"IP blocked for {remaining // 60} more minutes"
        
    # Check rate limit cooldown
    if row["rate_limited_until"] > now:
        remaining = int(row["rate_limited_until"] - now)
        return True, f"Rate limited for {remaining} more seconds"
        
    return False, ""

def register_bot_detection(ip: str) -> dict:
    """Log a bot IP trigger event and update rate limits."""
    from constants import (
        IP_RATE_LIMIT_COOLDOWN_SEC,
        IP_BLOCK_DURATION_SEC,
        IP_BLOCK_TRIGGER_COUNT,
    )
    
    conn = _get_conn()
    cursor = conn.cursor()
    now = time.time()
    
    cursor.execute("SELECT * FROM ip_tracker WHERE ip = ?", (ip,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute("""
        INSERT INTO ip_tracker (ip, bot_detection_count, first_detection, rate_limited_until, blocked_until)
        VALUES (?, 1, ?, 0, 0)
        """, (ip, now))
        count = 1
    else:
        count = row["bot_detection_count"] + 1
        cursor.execute("UPDATE ip_tracker SET bot_detection_count = ? WHERE ip = ?", (count, ip))
        
    rate_limited = 0
    blocked = 0
    if count >= IP_BLOCK_TRIGGER_COUNT:
        blocked = now + IP_BLOCK_DURATION_SEC
    else:
        rate_limited = now + IP_RATE_LIMIT_COOLDOWN_SEC
        
    cursor.execute("""
    UPDATE ip_tracker
    SET rate_limited_until = ?, blocked_until = ?
    WHERE ip = ?
    """, (rate_limited, blocked, ip))
    
    conn.commit()
    
    cursor.execute("SELECT * FROM ip_tracker WHERE ip = ?", (ip,))
    updated = dict(cursor.fetchone())
    conn.close()
    return updated

def get_ip_tracker() -> dict:
    """Retrieve full block tracker map."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ip_tracker")
    rows = cursor.fetchall()
    conn.close()
    return {r["ip"]: dict(r) for r in rows}

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def generate_device_fingerprint(
    user_agent: str,
    screen_width: int,
    screen_height: int,
    color_depth: int,
    timezone: str,
    language: str,
) -> str:
    """Generate fingerprint signature."""
    raw = f"{user_agent}|{screen_width}x{screen_height}|{color_depth}|{timezone}|{language}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def get_security_events_for_user(username: str, limit: int = 5) -> list:
    """Fetch security audit events for a user."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT se.timestamp, s.device_class, s.ip_address, se.risk_score, se.event_type as status
    FROM security_events se
    LEFT JOIN sessions s ON se.session_id = s.session_id
    WHERE se.username = ?
    ORDER BY se.timestamp DESC LIMIT ?
    """, (username, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def generate_account_number() -> str:
    """Generate a unique BSB prefix account number."""
    import random
    digits = "".join([str(random.randint(0, 9)) for _ in range(12)])
    return f"BSB{digits}"

def reset_all() -> None:
    """Clear database tables completely (demo database reset)."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users")
    cursor.execute("DELETE FROM behavioral_profiles")
    cursor.execute("DELETE FROM transactions")
    cursor.execute("DELETE FROM security_events")
    cursor.execute("DELETE FROM payees")
    cursor.execute("DELETE FROM sessions")
    cursor.execute("DELETE FROM ip_tracker")
    conn.commit()
    conn.close()
    
    # Clear model files on disk
    if os.path.exists(PROFILES_DIR):
        for f in os.listdir(PROFILES_DIR):
            try:
                os.remove(os.path.join(PROFILES_DIR, f))
            except Exception:
                pass
    _model_cache.clear()
    print("[SQLite] Reset complete. Database and cached model profiles cleared.")

def get_database_summary() -> dict:
    """Return statistics of database storage."""
    conn = _get_conn()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    u = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM sessions")
    s = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM security_events")
    e = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM ip_tracker")
    i = cursor.fetchone()[0]
    
    conn.close()
    return {
        "users": u,
        "sessions": s,
        "events": e,
        "ips": i
    }


# =============================================================================
# ALIASES — standardised names expected by app.py (Stream 1/B3)
# =============================================================================

def get_user_security_events(username: str, limit: int = 10) -> list:
    """
    Return recent security/login events for a user.
    Alias for get_security_events_for_user with a consistent name.
    Used by: GET /api/security-events/{username}
    """
    return get_security_events_for_user(username, limit=limit)


def get_session_history(username: str, limit: int = 10) -> list:
    """
    Return the persistent session history rows for a user from session_history table.
    Each row contains: session_id, device_class, ip_address, final_score, final_band,
    is_intruder, created_at.
    Used by: GET /api/session-history/{username}
    """
    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT session_id, device_class, ip_address, final_score, final_band,
                   is_intruder, created_at
            FROM session_history
            WHERE username = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (username, limit))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def reset_all_including_db() -> None:
    """
    Hard wipe: deletes all rows from every table AND clears model files.
    Used by: scripts/seed_demo_data.py --reset
    """
    reset_all()   # clears tables and model cache (existing function)
    print("[SQLite] Hard wipe complete.")

