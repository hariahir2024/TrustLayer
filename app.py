# =============================================================================
# BehaviorShield — app.py
# Team SOLARIS | Cyber Security Hackathon 2026 | MNNIT Allahabad
# =============================================================================
# FastAPI server — all REST API endpoints + WebSocket for live dashboard.
#
# Routes:
#   GET  /                        → Landing page
#   GET  /bank                    → Banking portal
#   GET  /dashboard               → Security ops dashboard
#
#   POST /api/enroll              → Submit enrollment passphrase sample
#   POST /api/login               → Login with behavioral data
#   POST /api/score               → Periodic risk scoring (called by SDK)
#   POST /api/reauth              → Step-up re-authentication (Amber Mid)
#   POST /api/action              → Record a user action (for metadata)
#   POST /api/transaction         → Attempt a banking transaction
#
#   GET  /api/session/{sid}       → Get session state
#   GET  /api/dashboard/stats     → Summary stats for dashboard header
#   GET  /api/dashboard/sessions  → All active sessions list
#   GET  /api/dashboard/logs      → Recent security event log
#
#   POST /api/admin/reset         → Full demo reset
#   POST /api/admin/freeze/{sid}  → Manual session freeze (fraud-ops button)
#   POST /api/admin/false-positive/{sid} → Mark session as false positive
#
#   WS   /ws/dashboard            → WebSocket for real-time dashboard updates
# =============================================================================

import os
import time
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db_sqlite as db          # ← SQLite-backed persistent database (replaces database.py)
import ml_engine as ml
import constants as _const_mod  # for runtime mutation of ADVISORY_MODE
from constants import (
    BANK_NAME, SYSTEM_NAME, SYSTEM_VERSION,
    AMBER_HIGH_ALLOWED_ACTIONS, AMBER_HIGH_BLOCKED_ACTIONS,
    AMBER_HIGH_OTP_REQUIRED_ACTIONS,
    LARGE_TRANSFER_THRESHOLD, BLOCKED_TRANSFER_THRESHOLD,
    REAUTH_MAX_ATTEMPTS, REAUTH_SCORE_PENALTY, STEPUP_REAUTH_THRESHOLD,
    BOT_SCORE_OVERRIDE, ENROLLMENT_REQUIRED_SAMPLES,
    AMBER_LOW_SCORING_INTERVAL_SEC, DEFAULT_SCORING_INTERVAL_SEC,
    ADVISORY_MODE, BASELINE_DRIFT_WEIGHT,
    generate_passphrase, get_score_band,
)

logging.basicConfig(
    level    = logging.INFO,
    format   = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt  = "%H:%M:%S",
)
log = logging.getLogger("app")


# =============================================================================
# WEBSOCKET CONNECTION MANAGER
# =============================================================================

class ConnectionManager:
    """Manages all active WebSocket connections from the dashboard."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)
        log.info(f"Dashboard connected. Total connections: {len(self.active)}")

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)
        log.info(f"Dashboard disconnected. Total connections: {len(self.active)}")

    async def broadcast(self, payload: dict) -> None:
        """Send a JSON message to all connected dashboard clients."""
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# =============================================================================
# APP LIFECYCLE
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise database and load ML baselines at startup."""
    log.info(f"Starting {SYSTEM_NAME} v{SYSTEM_VERSION}")
    db.init_db()                  # create SQLite tables if they don't exist
    ml.load_generic_baselines()   # load CMU/BALABIT population baselines
    ml.restore_all_user_profiles()# reload enrolled user profiles from SQLite
    log.info(f"{BANK_NAME} portal ready.")
    yield
    log.info("Server shutting down.")


app = FastAPI(
    title       = SYSTEM_NAME,
    description = f"{BANK_NAME} — Behavioral Biometric Authentication",
    version     = SYSTEM_VERSION,
    lifespan    = lifespan,
)

# Allow all origins for dev/demo
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# Serve CSS and JS from /static/
app.mount("/static", StaticFiles(directory="static"), name="static")


# =============================================================================
# PAGE ROUTES
# =============================================================================

@app.get("/", include_in_schema=False)
async def index():
    return FileResponse("static/index.html")

@app.get("/bank", include_in_schema=False)
async def bank():
    return FileResponse("static/bank.html")

@app.get("/dashboard", include_in_schema=False)
async def dashboard():
    return FileResponse("static/dashboard.html")


# =============================================================================
# REQUEST MODELS
# =============================================================================

class RegisterRequest(BaseModel):
    username:       str
    first_name:     str
    last_name:      str
    email:          str
    mobile:         str
    city:           str
    date_of_birth:  str
    password:       Optional[str] = ""

class EnrollRequest(BaseModel):
    username:       str
    key_events:     list
    field_focus_ts: Optional[float] = None
    device_class:   Optional[str] = "DESKTOP"


# =============================================================================
# REGISTRATION ENDPOINT
# =============================================================================

@app.post("/api/register")
async def register(req: RegisterRequest):
    """
    Register a new user account, generate an account number, and return a dynamic passphrase.
    """
    if not req.username or not req.first_name or not req.last_name:
        raise HTTPException(400, "username, first_name, and last_name are required fields")
    
    if db.user_exists(req.username):
        raise HTTPException(400, f"Username '{req.username}' is already registered")
        
    import hashlib
    password_hash = hashlib.sha256(req.password.encode()).hexdigest() if req.password else ""
    
    user = db.create_user(
        username=req.username,
        first_name=req.first_name,
        last_name=req.last_name,
        city=req.city,
        mobile=req.mobile,
        dob=req.date_of_birth,
        email=req.email,
        password_hash=password_hash
    )
    
    if not user:
        raise HTTPException(500, "Failed to create user record")
        
    return {
        "status": "success",
        "username": user["username"],
        "account_number": user["account_number"],
        "passphrase": user["passphrase"],
        "message": "User registered successfully"
    }


class LoginRequest(BaseModel):
    username:         str
    key_events:       list
    field_focus_ts:   Optional[float] = None
    device_info:      Optional[dict]  = {}   # {user_agent, screen_width, screen_height,
                                              #  color_depth, timezone, language}
    password:         Optional[str] = ""

class ScoreRequest(BaseModel):
    session_id:       str
    key_events:       Optional[list]  = []
    mouse_samples:    Optional[list]  = []
    click_dwell_mean: Optional[float] = 120.0
    webdriver_flag:   Optional[bool]  = False

class ReauthRequest(BaseModel):
    session_id:     str
    key_events:     list
    field_focus_ts: Optional[float] = None

class ActionRequest(BaseModel):
    session_id:  str
    action_type: str   # e.g. "view_balance", "transfer", "add_payee"

class TransactionRequest(BaseModel):
    session_id:   str
    action_type:  str
    amount:       Optional[float] = 0.0
    description:  Optional[str]  = ""


# =============================================================================
# ENROLLMENT ENDPOINT
# =============================================================================

@app.post("/api/enroll")
async def enroll(req: EnrollRequest):
    """
    Accept one enrollment passphrase typing sample.
    After ENROLLMENT_REQUIRED_SAMPLES (5) samples, build the user's baseline.
    """
    if not req.username or not req.key_events:
        raise HTTPException(400, "username and key_events are required")

    result = ml.process_enrollment_sample(
        req.username,
        req.key_events,
        req.field_focus_ts,
        device_class=req.device_class or "DESKTOP"
    )

    if result["complete"]:
        # Broadcast enrollment completion to dashboard
        await manager.broadcast({
            "type":     "enrollment_complete",
            "username": req.username,
            "message":  result["message"],
        })

    return result


# =============================================================================
# LOGIN ENDPOINT
# =============================================================================

@app.post("/api/login")
async def login(req: LoginRequest, request: Request):
    """
    Authenticate user and create a behavioral session.
    Scores the login keystroke event immediately as the first behavioral signal.
    """
    if not req.username:
        raise HTTPException(400, "username is required")

    if not db.user_exists(req.username):
        raise HTTPException(400, f"Username '{req.username}' does not exist. Please register.")

    user = db.get_user(req.username)

    if user.get("password_hash") and (req.password or not req.key_events):
        import hashlib
        pwd_hash = hashlib.sha256(req.password.encode()).hexdigest() if req.password else ""
        if user["password_hash"] != pwd_hash:
            raise HTTPException(401, "Invalid password")

    # Compute device fingerprint from browser metadata
    info = req.device_info or {}
    device_class = info.get("device_class", "DESKTOP")
    device_fp = db.generate_device_fingerprint(
        user_agent    = info.get("user_agent", ""),
        screen_width  = info.get("screen_width", 0),
        screen_height = info.get("screen_height", 0),
        color_depth   = info.get("color_depth", 24),
        timezone      = info.get("timezone", ""),
        language      = info.get("language", "en"),
    )

    # Save enrolled device fingerprint on first login for this device class
    known_fp = db.get_device_fingerprint(req.username, device_class)
    if known_fp is None:
        db.save_device_fingerprint(req.username, device_fp, device_class)

    # Real IP extraction (works behind Nginx/Railway reverse proxy)
    ip_address = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.headers.get("X-Real-IP", "")
        or (request.client.host if request.client else "127.0.0.1")
    )

    # Create the session
    session_id = db.create_session(
        username           = req.username,
        ip_address         = ip_address,
        user_agent         = info.get("user_agent", ""),
        device_fingerprint = device_fp,
        device_class       = device_class,
    )

    # Run initial scoring on login keystroke data
    if req.key_events:
        score_result = ml.score_session(session_id, req.key_events, [])
    else:
        score_result = {
            "final_score": 0.0, "band": "GREEN",
            "action": "CONTINUE", "is_bot": False,
            "top_contributors": [],
        }

    db.log_event(
        event_type = "LOGIN_OK",
        session_id = session_id,
        username   = req.username,
        details    = {"device_fp": device_fp},
        risk_score = score_result["final_score"],
        risk_band  = score_result["band"],
    )

    # Broadcast login event to dashboard
    await manager.broadcast({
        "type":       "session_created",
        "session_id": session_id,
        "username":   req.username,
        "score":      score_result["final_score"],
        "band":       score_result["band"],
    })

    # Check if enrolled for this specific device class
    enrolled = db.is_enrolled(req.username, device_class)

    return {
        "session_id":   session_id,
        "username":     req.username,
        "enrolled":     enrolled,
        "passphrase":   user.get("passphrase", ""),
        "score":        score_result["final_score"],
        "band":         score_result["band"],
        "action":       score_result["action"],
        "is_bot":       score_result.get("is_bot", False),
    }


@app.middleware("http")
async def inject_real_ip(request: Request, call_next):
    """Inject real client IP into session on login."""
    response = await call_next(request)
    return response


# =============================================================================
# SCORING ENDPOINT (called periodically by SDK)
# =============================================================================

@app.post("/api/score")
async def score(req: ScoreRequest):
    """
    Periodic risk scoring called by the SDK every N seconds.
    Returns the current risk score and what action the frontend should take.
    """
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    # Check IP block first
    blocked, reason = db.is_ip_blocked(session.get("ip_address", ""))
    if blocked:
        raise HTTPException(429, f"Blocked: {reason}")

    # Update session with click dwell data from this request
    if req.click_dwell_mean:
        session["click_dwell_mean"] = req.click_dwell_mean
    if req.webdriver_flag:
        session["webdriver_flag"] = req.webdriver_flag

    # Run the ML scoring pipeline
    result = ml.score_session(req.session_id, req.key_events, req.mouse_samples)

    # Handle bot detection — register for IP rate limiting
    if result.get("is_bot"):
        ip = session.get("ip_address", "127.0.0.1")
        db.register_bot_detection(ip)

    # Broadcast to dashboard
    await manager.broadcast({
        "type":             "score_update",
        "session_id":       req.session_id,
        "username":         session["username"],
        "score":            result["final_score"],
        "band":             result["band"],
        "action":           result["action"],
        "keystroke_score":  result.get("keystroke_score"),
        "mouse_score":      result.get("mouse_score"),
        "metadata_score":   result.get("metadata_score"),
        "top_contributors": result.get("top_contributors", []),
        "all_contributors": result.get("all_contributors", []),
        "is_bot":           result.get("is_bot", False),
        "velocity_flag":    result.get("velocity_exceeded", False),
        "mouse_samples":    req.mouse_samples,
        "risk_history":     db.get_session_risk_history(req.session_id),
        "timestamp":        time.time(),
        "ip_address":       session.get("ip_address"),
        "user_agent":       session.get("user_agent"),
        "scoring_interval": result.get("scoring_interval", 30),
    })

    # Trigger freeze events on high-risk bands
    if result["band"] in ("RED_LOW", "RED_HIGH") and session["status"] not in ("terminated",):
        db.invalidate_session(req.session_id, reason=f"Risk band: {result['band']}")

        # Simulate SMS/account alert for RED_HIGH
        if result["band"] == "RED_HIGH":
            alert_event = db.log_event(
                event_type = "SIMULATED_SMS_ALERT",
                session_id = req.session_id,
                username   = session["username"],
                details    = {
                    "simulated": True,
                    "message":   "Suspicious session detected. Your session has been ended.",
                    "channel":   "SMS + EMAIL",
                },
                risk_score = result["final_score"],
                risk_band  = result["band"],
            )
            await manager.broadcast({
                "type":    "simulated_alert",
                "alert":   alert_event,
                "username": session["username"],
            })

    return {
        "score":             result["final_score"],
        "band":              result["band"],
        "action":            result["action"],
        "is_bot":            result.get("is_bot", False),
        "top_contributors":  result.get("top_contributors", []),
        "keystroke_score":   result.get("keystroke_score"),
        "mouse_score":       result.get("mouse_score"),
        "metadata_score":    result.get("metadata_score"),
        "velocity_exceeded": result.get("velocity_exceeded", False),
        "scoring_interval":  result.get("scoring_interval", DEFAULT_SCORING_INTERVAL_SEC),
    }


# =============================================================================
# STEP-UP RE-AUTHENTICATION (Amber Mid)
# =============================================================================

@app.post("/api/reauth")
async def reauth(req: ReauthRequest):
    """
    Handle the Amber Mid soft re-authentication challenge.
    User re-types the enrollment passphrase — we score it behaviorally.
    If score exceeds STEPUP_REAUTH_THRESHOLD → mismatch → penalty added.
    """
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    username = session["username"]

    # Extract and score the re-auth keystroke sample
    features = ml.extract_keystroke_features(req.key_events, req.field_focus_ts)
    if not features:
        return {"success": False, "message": "Could not extract features from typing sample"}

    reauth_score, breakdown = ml.score_keystrokes(username, features)

    attempts = db.get_reauth_attempts(req.session_id)

    if reauth_score <= STEPUP_REAUTH_THRESHOLD:
        # Behavioral match — reset session risk
        session["current_risk"] = max(session["current_risk"] - 25.0, 10.0)
        new_score = round(session["current_risk"], 1)
        db.update_session_risk(req.session_id, new_score, get_score_band(new_score), {})
        db.update_session_status(req.session_id, "active")
        db.log_event(
            event_type = "REAUTH_SUCCESS",
            session_id = req.session_id,
            username   = username,
            details    = {"reauth_score": reauth_score, "reset_to": new_score},
            risk_score = new_score,
        )
        await manager.broadcast({
            "type":       "reauth_success",
            "session_id": req.session_id,
            "username":   username,
            "new_score":  new_score,
        })
        return {"success": True, "new_score": new_score, "message": "Identity verified"}

    else:
        # Behavioral mismatch
        new_attempts = db.increment_reauth_attempts(req.session_id)
        penalty_score = min(session["current_risk"] + REAUTH_SCORE_PENALTY, 100.0)
        new_band = get_score_band(penalty_score)
        db.update_session_risk(req.session_id, penalty_score, new_band, {})
        db.log_event(
            event_type = "REAUTH_FAIL",
            session_id = req.session_id,
            username   = username,
            details    = {"reauth_score": reauth_score, "attempt": new_attempts},
            risk_score = penalty_score,
            risk_band  = new_band,
        )
        await manager.broadcast({
            "type":       "reauth_fail",
            "session_id": req.session_id,
            "username":   username,
            "new_score":  penalty_score,
            "band":       new_band,
        })

        if new_attempts >= REAUTH_MAX_ATTEMPTS:
            db.update_session_status(req.session_id, "amber_high")
            return {
                "success":   False,
                "escalate":  True,
                "new_score": penalty_score,
                "band":      new_band,
                "message":   "Verification failed. Enhanced security applied.",
            }

        return {
            "success":           False,
            "escalate":          False,
            "attempts_remaining": REAUTH_MAX_ATTEMPTS - new_attempts,
            "new_score":         penalty_score,
            "message":           f"Verification failed. {REAUTH_MAX_ATTEMPTS - new_attempts} attempt(s) remaining.",
        }


# =============================================================================
# ACTION RECORDING
# =============================================================================

@app.post("/api/action")
async def record_action(req: ActionRequest):
    """Record that the user performed an action (page visit, button click, etc.)."""
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    db.record_session_action(req.session_id)
    return {"recorded": True}


# =============================================================================
# TRANSACTION ENDPOINT (with Amber High restrictions)
# =============================================================================

@app.post("/api/transaction")
async def transaction(req: TransactionRequest):
    """
    Handle a banking transaction request.
    Applies Amber High restrictions based on current session risk band.
    """
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    band   = session.get("risk_band", "GREEN")
    amount = req.amount or 0.0
    action = req.action_type

    db.record_session_action(req.session_id)

    # Apply restrictions at AMBER_HIGH
    if band == "AMBER_HIGH":
        if action in AMBER_HIGH_BLOCKED_ACTIONS:
            return {
                "allowed":  False,
                "reason":   "service_unavailable",
                "message":  "Service temporarily unavailable. Please try again later.",
                "otp_required": False,
            }
        if action in AMBER_HIGH_OTP_REQUIRED_ACTIONS:
            return {
                "allowed":      True,
                "otp_required": True,
                "message":      "Additional verification required.",
            }
        if action == "transfer" and amount >= LARGE_TRANSFER_THRESHOLD:
            return {
                "allowed":  False,
                "reason":   "service_unavailable",
                "message":  "Service temporarily unavailable. Please try again later.",
                "otp_required": False,
            }

    # Block all transactions for frozen sessions
    if band in ("RED_LOW", "RED_HIGH", "RED_CRITICAL") or session["status"] == "terminated":
        return {
            "allowed":  False,
            "reason":   "session_suspended",
            "message":  "Your session has been suspended. Please log in again.",
        }

    db.log_event(
        event_type = "TRANSACTION_ALLOWED",
        session_id = req.session_id,
        username   = session["username"],
        details    = {"action": action, "amount": amount},
        risk_score = session["current_risk"],
        risk_band  = band,
    )

    return {
        "allowed":      True,
        "otp_required": False,
        "message":      "Transaction processed successfully.",
    }


# =============================================================================
# SESSION STATE
# =============================================================================

@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Return current session state for the banking portal to query."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    return {
        "session_id":    session_id,
        "username":      session["username"],
        "status":        session["status"],
        "risk_score":    session["current_risk"],
        "band":          session["risk_band"],
        "risk_history":  session["risk_history"][-20:],  # last 20 points
        "action_count":  session["action_count"],
        "scoring_interval": session["scoring_interval"],
        "reauth_attempts":  session["reauth_attempts"],
        "created_at":    session["created_at"],
    }


# =============================================================================
# DASHBOARD API
# =============================================================================

@app.get("/api/dashboard/stats")
async def dashboard_stats():
    """Summary statistics for the dashboard header cards."""
    return db.get_stats()


@app.get("/api/dashboard/sessions")
async def dashboard_sessions():
    """All sessions with their current risk state for the sessions table."""
    sessions = db.get_active_sessions()
    return [
        {
            "session_id":   s["session_id"],
            "username":     s["username"],
            "status":       s["status"],
            "risk_score":   s["current_risk"],
            "band":         s["risk_band"],
            "is_bot":       s["is_bot"],
            "duration_sec": round(time.time() - s["created_at"], 0),
            "action_count": s["action_count"],
            "last_breakdown": s.get("last_breakdown"),
            "ip_address":   s.get("ip_address"),
            "user_agent":   s.get("user_agent"),
            "scoring_interval": s.get("scoring_interval"),
        }
        for s in sessions
    ]


@app.get("/api/dashboard/logs")
async def dashboard_logs(limit: int = 50):
    """Recent security event log for the fraud-ops feed."""
    logs = db.get_fraud_logs(limit)
    return [
        {
            "event_id":   e["event_id"],
            "timestamp":  e["timestamp"],
            "event_type": e["event_type"],
            "session_id": e.get("session_id"),
            "username":   e["username"],
            "risk_score": e["risk_score"],
            "risk_band":  e["risk_band"],
            "details":    e["details"],
        }
        for e in logs
    ]


@app.get("/api/dashboard/session/{session_id}/history")
async def session_history(session_id: str):
    """Full risk history for the session heartbeat timeline chart."""
    history = db.get_session_risk_history(session_id)
    return {"session_id": session_id, "history": history}


# =============================================================================
# ADMIN / FRAUD-OPS ENDPOINTS
# =============================================================================

@app.post("/api/admin/freeze/{session_id}")
async def admin_freeze(session_id: str):
    """Manual session freeze by fraud-ops analyst."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    db.invalidate_session(session_id, reason="Manual freeze by fraud-ops")
    db.log_event(
        event_type = "ADMIN_FREEZE",
        session_id = session_id,
        username   = session["username"],
        details    = {"action": "manual_freeze"},
    )
    await manager.broadcast({
        "type":       "session_frozen",
        "session_id": session_id,
        "username":   session["username"],
        "reason":     "Manual freeze by fraud-ops",
    })
    return {"frozen": True}


@app.post("/api/admin/false-positive/{session_id}")
async def admin_false_positive(session_id: str):
    """Mark a frozen session as a false positive and restore it."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    db.update_session_status(session_id, "active")
    db.update_session_risk(session_id, 15.0, "GREEN", {})
    db.log_event(
        event_type = "ADMIN_FALSE_POSITIVE",
        session_id = session_id,
        username   = session["username"],
        details    = {"action": "marked_false_positive"},
    )
    await manager.broadcast({
        "type":       "false_positive",
        "session_id": session_id,
        "username":   session["username"],
    })
    return {"restored": True, "new_score": 15.0}


@app.post("/api/admin/reset")
async def admin_reset():
    """
    Full demo reset — clears all sessions, events, and user profiles.
    Use between demo runs to start fresh.
    """
    db.reset_all()
    await manager.broadcast({"type": "demo_reset"})
    log.info("Demo reset performed.")
    return {"reset": True, "message": "All sessions and profiles cleared."}


@app.post("/api/admin/soft-reset")
async def admin_soft_reset():
    """
    Soft reset — clears in-memory sessions and logs but keeps enrolled user profiles in SQLite.
    Useful for showing a new attack scenario without re-enrolling.
    """
    db.reset_all()   # clears in-memory sessions, ip_tracker, model_cache only
    await manager.broadcast({"type": "soft_reset"})
    return {"reset": True, "message": "Sessions cleared. Enrolled profiles retained in database."}


@app.get("/api/admin/baseline/{username}")
async def admin_get_baseline(username: str, device_class: str = "DESKTOP"):
    """Get the user's keystroke baseline for verification."""
    baseline = db.get_keystroke_baseline(username, device_class)
    if not baseline:
        raise HTTPException(404, "Baseline not found")
    return baseline



# =============================================================================
# USER PROFILE ENDPOINTS
# =============================================================================

@app.get("/api/profile/{username}")
async def get_profile(username: str):
    """Return full user profile (for the Profile tab)."""
    user = db.get_user(username)
    if not user:
        raise HTTPException(404, "User not found")
    # Never return the password hash
    user.pop("password_hash", None)
    return user


@app.get("/api/passphrase/{username}")
async def get_passphrase(username: str):
    """Return the user's enrollment passphrase (shown during enrollment screen)."""
    user = db.get_user(username)
    if not user:
        raise HTTPException(404, "User not found")
    return {"passphrase": user["passphrase"]}


class ChangePasswordRequest(BaseModel):
    username:     str
    old_password: str
    new_password: str


@app.post("/api/change-password")
async def change_password(req: ChangePasswordRequest):
    """Update user password after verifying old password."""
    if not db.verify_password(req.username, req.old_password):
        raise HTTPException(401, "Current password is incorrect")
    if len(req.new_password) < 8:
        raise HTTPException(400, "New password must be at least 8 characters")
    db.update_user_password(req.username, db.hash_password(req.new_password))
    return {"success": True, "message": "Password updated successfully"}


@app.post("/api/reset-enrollment/{username}")
async def reset_enrollment(username: str, device_class: str = "DESKTOP"):
    """
    Clear behavioral profile for (username, device_class).
    Forces re-enrollment on next login from that device class.
    """
    import sqlite3
    conn = db._connect()
    try:
        conn.execute("""
            UPDATE behavioral_profiles
            SET enrolled=0, enrollment_count=0, keystroke_means='{}',
                keystroke_stds='{}', enrollment_seqs='[]', device_fps='[]'
            WHERE username=? AND device_class=?
        """, (username, device_class))
        conn.commit()
    finally:
        conn.close()
    log.info(f"Enrollment reset: {username}/{device_class}")
    return {"success": True, "message": f"Biometric profile cleared for {username} on {device_class}"}


@app.get("/api/security-events/{username}")
async def get_security_events(username: str, limit: int = 10):
    """Return recent login events for the Security Centre (Profile tab)."""
    events = db.get_user_security_events(username, limit=limit)
    return {"events": events}


@app.get("/api/session-history/{username}")
async def get_session_history(username: str, limit: int = 10):
    """Return persistent session history for a user."""
    history = db.get_session_history(username, limit=limit)
    return {"sessions": history}


# =============================================================================
# TRANSACTION ENDPOINTS
# =============================================================================

@app.get("/api/transactions/{username}")
async def get_transactions(username: str, limit: int = 50, txn_type: str = None):
    """Return transaction history for a user."""
    if not db.user_exists(username):
        raise HTTPException(404, "User not found")
    txns = db.get_transactions(username, limit=limit, txn_type=txn_type)
    return {"transactions": txns, "count": len(txns)}


class BillPaymentRequest(BaseModel):
    session_id:  str
    biller_type: str      # 'electricity', 'mobile', 'dth', 'insurance', 'water'
    consumer_id: str
    amount:      float
    description: str = ""


@app.post("/api/bill-payment")
async def bill_payment(req: BillPaymentRequest):
    """Process a bill payment transaction."""
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session["status"] == "terminated":
        raise HTTPException(403, "Session is frozen")

    username = session["username"]
    user     = db.get_user(username)
    if not user or user["balance"] < req.amount:
        raise HTTPException(400, "Insufficient balance")

    txn = db.add_transaction(
        username    = username,
        session_id  = req.session_id,
        txn_type    = f"bill_{req.biller_type}",
        amount      = req.amount,
        description = req.description or f"{req.biller_type.title()} payment — {req.consumer_id}",
        beneficiary = req.consumer_id,
        status      = "success",
        risk_score  = session["current_risk"],
    )
    db.record_session_action(req.session_id)
    return {"success": True, "transaction": txn, "new_balance": user["balance"] - req.amount}


class UPIRequest(BaseModel):
    session_id: str
    upi_id:     str
    amount:     float
    note:       str = ""


@app.post("/api/upi")
async def upi_payment(req: UPIRequest):
    """Process a UPI payment."""
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session["status"] == "terminated":
        raise HTTPException(403, "Session is frozen")

    username = session["username"]
    user     = db.get_user(username)
    if not user or user["balance"] < req.amount:
        raise HTTPException(400, "Insufficient balance")

    txn = db.add_transaction(
        username    = username,
        session_id  = req.session_id,
        txn_type    = "upi",
        amount      = req.amount,
        description = req.note or f"UPI to {req.upi_id}",
        beneficiary = req.upi_id,
        status      = "success",
        risk_score  = session["current_risk"],
    )
    db.record_session_action(req.session_id)
    return {"success": True, "transaction": txn, "new_balance": user["balance"] - req.amount}


# =============================================================================
# PAYEE ENDPOINTS
# =============================================================================

@app.get("/api/payees/{username}")
async def get_payees(username: str):
    """Return saved payees for a user."""
    return {"payees": db.get_payees(username)}


class AddPayeeRequest(BaseModel):
    session_id:     str
    name:           str
    account_number: str = ""
    ifsc:           str = ""
    bank_name:      str = ""
    upi_id:         str = ""


@app.post("/api/payees")
async def add_payee(req: AddPayeeRequest):
    """Add a new saved payee."""
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    # Block adding payees at AMBER HIGH
    if session["risk_band"] in ("AMBER_HIGH", "RED_LOW", "RED_HIGH", "RED_CRITICAL"):
        raise HTTPException(403, "Adding payees is restricted at your current security level")

    payee = db.add_payee(
        owner_username = session["username"],
        name           = req.name,
        account_number = req.account_number,
        ifsc           = req.ifsc,
        bank_name      = req.bank_name,
        upi_id         = req.upi_id,
    )
    db.record_session_action(req.session_id)
    return {"success": True, "payee": payee}


@app.delete("/api/payees/{payee_id}")
async def delete_payee(payee_id: int, session_id: str):
    """Remove a saved payee."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    deleted = db.delete_payee(payee_id, session["username"])
    if not deleted:
        raise HTTPException(404, "Payee not found or not owned by this user")
    return {"success": True}


# =============================================================================
# FIXED DEPOSIT ENDPOINT
# =============================================================================

class FDRequest(BaseModel):
    session_id: str
    amount:     float
    tenure:     int

@app.post("/api/fd")
async def book_fd(req: FDRequest):
    """Book a new Fixed Deposit."""
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session["status"] == "terminated":
        raise HTTPException(403, "Session is frozen")
        
    username = session["username"]
    user = db.get_user(username)
    if not user or user["balance"] < req.amount:
        raise HTTPException(400, "Insufficient balance")
        
    rates = {1: 6.8, 3: 7.2, 5: 7.5}
    rate = rates.get(req.tenure, 6.8)
    
    # Record transaction
    db.add_transaction(
        username=username,
        session_id=req.session_id,
        txn_type="deposit",
        amount=req.amount,
        description=f"FD Booking — {req.tenure} Yr @ {rate}% p.a.",
        beneficiary="Fixed Deposit Account",
        status="success",
        risk_score=session["current_risk"]
    )
    
    # Manually deduct balance for 'deposit' type
    conn = db._get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance - ? WHERE username = ?", (req.amount, username))
    conn.commit()
    conn.close()
    
    db.record_session_action(req.session_id)
    
    updated_user = db.get_user(username)
    return {
        "success": True,
        "new_balance": updated_user["balance"],
        "maturity_amount": req.amount * (1 + (rate / 100) * req.tenure),
        "interest_earned": req.amount * (rate / 100) * req.tenure
    }


# =============================================================================
# PASSWORD MANAGEMENT ENDPOINT
# =============================================================================

class ChangePasswordRequest(BaseModel):
    session_id:   str
    old_password: str
    new_password: str

@app.post("/api/profile/change-password")
async def change_password(req: ChangePasswordRequest):
    """Change user's NetBanking password."""
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session["status"] == "terminated":
        raise HTTPException(403, "Session is frozen")
        
    username = session["username"]
    user = db.get_user(username)
    if not user:
        raise HTTPException(404, "User not found")
        
    import hashlib
    old_hash = hashlib.sha256(req.old_password.encode()).hexdigest()
    if user["password_hash"] and user["password_hash"] != old_hash:
        raise HTTPException(400, "Incorrect current password")
        
    new_hash = hashlib.sha256(req.new_password.encode()).hexdigest()
    
    conn = db._get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (new_hash, username))
    conn.commit()
    conn.close()
    
    db.record_session_action(req.session_id)
    return {"success": True, "message": "Password changed successfully"}


# =============================================================================
# SUPPORT TICKETS ENDPOINTS
# =============================================================================

class SupportTicketRequest(BaseModel):
    session_id:  str
    category:    str
    description: str

@app.post("/api/support/tickets")
async def log_support_ticket(req: SupportTicketRequest):
    """Submit a support ticket."""
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session["status"] == "terminated":
        raise HTTPException(403, "Session is frozen")
        
    username = session["username"]
    ticket = db.add_support_ticket(username, req.category, req.description)
    db.record_session_action(req.session_id)
    return {"success": True, "ticket": ticket}

@app.get("/api/support/tickets/{username}")
async def get_support_tickets(username: str):
    """Return all support tickets for a user."""
    tickets = db.get_support_tickets(username)
    return {"tickets": tickets, "count": len(tickets)}


# =============================================================================
# USER PROFILE & SECURITY AUDIT ENDPOINTS
# =============================================================================

@app.get("/api/user/{username}")
async def get_user_profile(username: str):
    """Get profile details for a user."""
    user = db.get_user(username)
    if not user:
        raise HTTPException(404, "User not found")
    return {
        "username":       user["username"],
        "first_name":     user["first_name"],
        "last_name":      user["last_name"],
        "email":          user["email"],
        "mobile":         user["mobile"],
        "city":           user["city"],
        "date_of_birth":  user["date_of_birth"],
        "account_number": user["account_number"],
        "balance":        user["balance"],
        "passphrase":     user["passphrase"]
    }

@app.get("/api/user/{username}/security-log")
async def get_security_log(username: str, limit: int = 5):
    """Fetch security audit events for a user."""
    log_entries = db.get_security_events_for_user(username, limit=limit)
    return {"events": log_entries, "count": len(log_entries)}


# =============================================================================
# DATA COLLECTION CAMPAIGN ENDPOINTS (Stream 6)
# =============================================================================

class LabelIntruderRequest(BaseModel):
    session_id:       str
    label_all_recent: bool = False


@app.post("/api/admin/label-intruder")
async def label_intruder(req: LabelIntruderRequest):
    """
    Mark session(s) as intruder for XGBoost retraining dataset.
    Used after a friend/family member completes test sessions on the account.
    """
    count = db.label_session_intruder(req.session_id, req.label_all_recent)
    log.info(f"Intruder label applied: session={req.session_id}, rows_updated={count}")
    return {"success": True, "sessions_labeled": count}


@app.get("/api/admin/data-collection-summary")
async def data_collection_summary():
    """Return per-user per-device session counts for the SOC dashboard."""
    return db.get_data_collection_summary()


# =============================================================================
# ADVISORY MODE TOGGLE (Bonus B2)
# =============================================================================

class SetModeRequest(BaseModel):
    mode: str   # 'active' or 'advisory'


@app.post("/api/admin/set-mode")
async def set_mode(req: SetModeRequest):
    """
    Toggle between Active Mode (challenges users) and Advisory Mode (silent scoring).
    Change takes effect immediately for all subsequent scoring events.
    """
    if req.mode not in ("active", "advisory"):
        raise HTTPException(400, "mode must be 'active' or 'advisory'")

    _const_mod.ADVISORY_MODE = (req.mode == "advisory")
    log.info(f"System mode changed to: {req.mode.upper()}")

    await manager.broadcast({
        "type": "mode_changed",
        "mode": req.mode,
        "message": f"System switched to {req.mode.upper()} mode",
    })
    return {"success": True, "mode": req.mode}


@app.get("/api/admin/mode")
async def get_mode():
    """Return the current system operating mode."""
    import constants
    return {"mode": "advisory" if constants.ADVISORY_MODE else "active"}


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================

@app.websocket("/ws/dashboard")
async def websocket_dashboard(ws: WebSocket):
    """
    WebSocket connection for the real-time fraud-ops dashboard.
    Sends live score updates, session events, and alerts.
    """
    await manager.connect(ws)
    try:
        import constants
        # Send initial state snapshot on connect
        await ws.send_json({
            "type":     "connected",
            "stats":    db.get_stats(),
            "mode":     "advisory" if constants.ADVISORY_MODE else "active",
            "sessions": [
                {
                    "session_id": s["session_id"][:8] + "...",
                    "username":   s["username"],
                    "score":      s["current_risk"],
                    "band":       s["risk_band"],
                }
                for s in db.get_active_sessions()
            ],
        })

        # Keep connection alive — client sends periodic pings
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")

    except WebSocketDisconnect:
        manager.disconnect(ws)


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.get("/api/health")
async def health():
    import constants
    return {
        "status":   "ok",
        "system":   SYSTEM_NAME,
        "version":  SYSTEM_VERSION,
        "bank":     BANK_NAME,
        "mode":     "advisory" if constants.ADVISORY_MODE else "active",
        "database": db.get_database_summary(),
    }


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)
