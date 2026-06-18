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

class LoginRequest(BaseModel):
    username:         str
    key_events:       list
    field_focus_ts:   Optional[float] = None
    device_info:      Optional[dict]  = {}   # {user_agent, screen_width...}
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
    action_type: str

class TransactionRequest(BaseModel):
    session_id:   str
    action_type:  str
    amount:       Optional[float] = 0.0
    description:  Optional[str]  = ""


# =============================================================================
# AUTHENTICATION & ENROLLMENT ENDPOINTS
# =============================================================================

@app.post("/api/register")
async def register(req: RegisterRequest):
    """Register a new user account and generate dynamic passphrase."""
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


@app.post("/api/enroll")
async def enroll(req: EnrollRequest):
    """Accept one enrollment passphrase typing sample."""
    if not req.username or not req.key_events:
        raise HTTPException(400, "username and key_events are required")

    result = ml.process_enrollment_sample(req.username, req.key_events, req.field_focus_ts)

    if result.get("complete"):
        await manager.broadcast({
            "type": "enrollment_complete",
            "username": req.username,
            "message": result.get("message", "Enrollment completed")
        })
    return result


@app.post("/api/login")
async def login(req: LoginRequest):
    """Authenticate credentials and initialize behavioral tracking session."""
    if not req.username:
        raise HTTPException(400, "username is required")

    if not db.user_exists(req.username):
        raise HTTPException(404, "User does not exist")

    info = req.device_info or {}
    device_fp = db.generate_device_fingerprint(
        user_agent=info.get("user_agent", ""),
        screen_width=info.get("screen_width", 0),
        screen_height=info.get("screen_height", 0),
        color_depth=info.get("color_depth", 0),
        timezone=info.get("timezone", ""),
        language=info.get("language", "")
    )

    await manager.broadcast({
        "type": "login_attempt",
        "username": req.username,
        "device_fp": device_fp
    })

    return {"status": "success", "username": req.username, "device_fingerprint": device_fp}


# =============================================================================
