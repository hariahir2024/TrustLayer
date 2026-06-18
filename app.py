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

import time
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import database as db
import ml_engine as ml
from constants import (
    BANK_NAME, SYSTEM_NAME, SYSTEM_VERSION,
    AMBER_HIGH_ALLOWED_ACTIONS, AMBER_HIGH_BLOCKED_ACTIONS,
    AMBER_HIGH_OTP_REQUIRED_ACTIONS,
    LARGE_TRANSFER_THRESHOLD, BLOCKED_TRANSFER_THRESHOLD,
    REAUTH_MAX_ATTEMPTS, REAUTH_SCORE_PENALTY, STEPUP_REAUTH_THRESHOLD,
    BOT_SCORE_OVERRIDE, ENROLLMENT_REQUIRED_SAMPLES,
    AMBER_LOW_SCORING_INTERVAL_SEC, DEFAULT_SCORING_INTERVAL_SEC,
    get_score_band,
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
    """Load ML baselines at startup."""
    log.info(f"Starting {SYSTEM_NAME} v{SYSTEM_VERSION}")
    ml.load_generic_baselines()
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

class EnrollRequest(BaseModel):
    username:       str
    key_events:     list
    field_focus_ts: Optional[float] = None

class LoginRequest(BaseModel):
    username:         str
    key_events:       list
    field_focus_ts:   Optional[float] = None
    device_info:      Optional[dict]  = {}   # {user_agent, screen_width, screen_height,
                                              #  color_depth, timezone, language}

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
async def login(req: LoginRequest):
    """
    Authenticate user and create a behavioral session.
    Scores the login keystroke event immediately as the first behavioral signal.
    """
    if not req.username:
        raise HTTPException(400, "username is required")

    # Create user if first visit
    if not db.user_exists(req.username):
        db.create_user(req.username)

    user = db.get_user(req.username)

    # Compute device fingerprint from browser metadata
    info = req.device_info or {}
    device_fp = db.generate_device_fingerprint(
        user_agent    = info.get("user_agent", ""),
        screen_width  = info.get("screen_width", 0),
        screen_height = info.get("screen_height", 0),
        color_depth   = info.get("color_depth", 24),
        timezone      = info.get("timezone", ""),
        language      = info.get("language", "en"),
    )

    # Save enrolled device fingerprint on first login
    if user["device_fingerprint"] is None:
        db.save_device_fingerprint(req.username, device_fp)

    # Create the session
    session_id = db.create_session(
        username           = req.username,
        ip_address         = "127.0.0.1",
        user_agent         = info.get("user_agent", ""),
        device_fingerprint = device_fp,
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

    return {
        "session_id":   session_id,
        "username":     req.username,
        "enrolled":     user["enrolled"],
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
        "scoring_interval": new_interval,
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
    Soft reset — clears sessions and logs but keeps enrolled user profiles.
    Useful for showing a new attack scenario without re-enrolling.
    """
    # Only clear sessions and logs, keep _users
    from database import _sessions, _fraud_log, _ip_tracker
    _sessions.clear()
    _fraud_log.clear()
    _ip_tracker.clear()
    await manager.broadcast({"type": "soft_reset"})
    return {"reset": True, "message": "Sessions cleared. Enrolled profiles retained."}


@app.get("/api/admin/baseline/{username}")
async def admin_get_baseline(username: str):
    """Get the user's keystroke baseline for verification."""
    baseline = db.get_keystroke_baseline(username)
    if not baseline:
        raise HTTPException(404, "Baseline not found")
    return baseline



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
        # Send initial state snapshot on connect
        await ws.send_json({
            "type":     "connected",
            "stats":    db.get_stats(),
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
    return {
        "status":   "ok",
        "system":   SYSTEM_NAME,
        "version":  SYSTEM_VERSION,
        "bank":     BANK_NAME,
        "database": db.get_database_summary(),
    }


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)
