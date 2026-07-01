import pytest
import time
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import ml_engine as ml
import db_sqlite as db

def setup_module(module):
    """Initialize test database."""
    db.init_db()
    db.reset_all()
    ml.load_generic_baselines()

def generate_keystroke_events(hold_time=90.0, flight_time=120.0, positions_count=17):
    """Utility to generate mock timing events."""
    events = []
    base_ts = time.time() * 1000
    current_ts = base_ts
    
    for i in range(positions_count):
        current_ts += flight_time
        events.append({"timestamp": current_ts, "event": "down", "position": i + 1})
        current_ts += hold_time
        events.append({"timestamp": current_ts, "event": "up", "position": i + 1})
        
    return events, base_ts

def test_user_registration_and_salted_passwords():
    """Verify registration encodes passwords with secure PBKDF2-SHA256 salts."""
    username = "test_salted_user"
    password = "MySecurePassword123"
    
    # Registration hash
    hashed = db.hash_password(password)
    assert hashed.startswith("pbkdf2_sha256$100000$")
    
    # Create user in db
    db.create_user(username=username, password_hash=hashed)
    assert db.user_exists(username) is True
    
    # Successful password verify
    assert db.verify_password(username, password) is True
    
    # Failed password verify
    assert db.verify_password(username, "WrongPassword") is False
    
    # Verify legacy compatibility
    legacy_user = "test_legacy_user"
    import hashlib
    legacy_hash = hashlib.sha256(password.encode()).hexdigest()
    db.create_user(username=legacy_user, password_hash=legacy_hash)
    
    # Verify legacy password still checks out successfully
    assert db.verify_password(legacy_user, password) is True

def test_identical_enrollment_gives_green():
    """Verify that consistent owner typing yields a GREEN profile risk band."""
    username = "test_owner_user"
    db.create_user(username)
    
    # Generate 5 identical calibration samples
    for _ in range(5):
        events, base_ts = generate_keystroke_events(hold_time=90.0, flight_time=120.0)
        result = ml.process_enrollment_sample(username, events, device_class="DESKTOP")
        
    # Calibration should be complete
    assert result["complete"] is True
    
    # Register device fingerprint (as production flow does on login)
    db.save_device_fingerprint(username, "fingerprint_xyz", device_class="DESKTOP")
    
    # Score a matching live session
    session_id = db.create_session(username, "127.0.0.1", "Chrome", "fingerprint_xyz")
    events, base_ts = generate_keystroke_events(hold_time=92.0, flight_time=122.0) # slight natural variation
    
    score_result = ml.score_session(session_id, events, [])
    assert score_result["final_score"] < 30.0
    assert score_result["band"] == "GREEN"

def test_different_user_gives_elevated_score():
    """Verify that mismatched typing timing (e.g. human intruder) escalates risk."""
    owner_username = "test_owner_profile"
    db.create_user(owner_username)
    
    # Enroll owner with fast, consistent timings
    for _ in range(5):
        events, base_ts = generate_keystroke_events(hold_time=70.0, flight_time=90.0)
        ml.process_enrollment_sample(owner_username, events, device_class="DESKTOP")
        
    # Register device fingerprint (simulating legit owner device)
    db.save_device_fingerprint(owner_username, "fingerprint_xyz", device_class="DESKTOP")
    
    # Simulate intruder logging in with slow, hesitant typing timings on a new device (takeover attempt)
    session_id = db.create_session(owner_username, "127.0.0.1", "Chrome", "fingerprint_attacker")
    intruder_events, base_ts = generate_keystroke_events(hold_time=180.0, flight_time=350.0)
    
    score_result = ml.score_session(session_id, intruder_events, [])
    # Risk should escalate to Amber or Red bands
    assert score_result["final_score"] > 40.0
    assert score_result["band"] in ("AMBER_MID", "AMBER_HIGH", "RED_LOW", "RED_HIGH", "RED_CRITICAL")

def test_bot_detection_catches_programmatic_input():
    """Verify that programmatic inputs with sub-5ms delays trigger the bot heuristic engine."""
    events = []
    base_ts = time.time() * 1000
    current_ts = base_ts
    
    # Generate keys with 1ms flight time and 1ms hold time
    for i in range(17):
        current_ts += 1
        events.append({"timestamp": current_ts, "event": "down", "position": i + 1})
        current_ts += 1
        events.append({"timestamp": current_ts, "event": "up", "position": i + 1})
        
    is_bot, reason = ml.detect_bot(events, [], {"webdriver_flag": False, "click_dwell_mean": 20})
    assert is_bot is True
    assert "Flight time" in reason or "0ms" in reason

def test_cors_configuration_in_app():
    """Verify CORS middleware allows specified local origins and headers."""
    from app import app
    from fastapi.middleware.cors import CORSMiddleware
    
    cors_middleware = None
    for middleware in app.user_middleware:
        if middleware.cls == CORSMiddleware:
            cors_middleware = middleware
            break
            
    assert cors_middleware is not None
    # Verify allowed origins contains localhost (ports 8080 and 8089)
    origins = cors_middleware.kwargs.get("allow_origins", [])
    assert "http://localhost:8080" in origins
    assert "http://127.0.0.1:8080" in origins
    assert "http://localhost:8089" in origins

def test_replay_attack_nonce_protection():
    """Verify that sending the same score request twice with the same nonce yields HTTP 400 Replay detected."""
    import asyncio
    from app import score, ScoreRequest
    from fastapi import HTTPException
    
    username = "test_replay_user"
    db.create_user(username)
    session_id = db.create_session(username, "127.0.0.1", "Chrome", "fingerprint_xyz")
    
    events, base_ts = generate_keystroke_events()
    ts = time.time() * 1000
    nonce = "unique_nonce_12345"
    
    req = ScoreRequest(
        session_id=session_id,
        key_events=events,
        mouse_samples=[],
        timestamp=ts,
        nonce=nonce
    )
    
    # Run async function using standard library asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    res1 = loop.run_until_complete(score(req))
    assert res1 is not None
    
    # Second call with identical nonce - should fail with 400
    with pytest.raises(HTTPException) as exc_info:
        loop.run_until_complete(score(req))
        
    assert exc_info.value.status_code == 400
    assert "Replay detected" in exc_info.value.detail

def test_upi_blocked_under_high_risk():
    """Verify that a session under RED_HIGH risk blocks UPI transfers and returns 403."""
    import asyncio
    from app import upi_payment, UPIRequest
    from fastapi import HTTPException
    
    username = "test_upi_user"
    db.create_user(username)
    session_id = db.create_session(username, "127.0.0.1", "Chrome", "fingerprint_xyz")
    
    # Artificially elevate the session's risk band to RED_HIGH
    db.update_session_risk(session_id, score=85.0, band="RED_HIGH", breakdown={})
    
    req = UPIRequest(
        session_id=session_id,
        upi_id="receiver@okbank",
        amount=10000.0,
        note="Test UPI"
    )
    
    # Run the async endpoint function directly using asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    with pytest.raises(HTTPException) as exc_info:
        loop.run_until_complete(upi_payment(req))
        
    assert exc_info.value.status_code == 403
    assert "Transaction blocked" in exc_info.value.detail

def test_session_history_endpoint():
    """Verify that updating a session inserts records into session_history and get_session_history endpoint returns them."""
    import asyncio
    from app import get_session_history
    
    username = "history_test_user"
    db.create_user(username)
    session_id = db.create_session(username, "127.0.0.1", "Firefox", "fingerprint_abc")
    
    # Update risk to trigger insertion into session_history
    db.update_session_risk(session_id, score=15.0, band="GREEN", breakdown={})
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    res = loop.run_until_complete(get_session_history(username))
    assert res is not None
    assert "sessions" in res
    assert len(res["sessions"]) > 0
    assert res["sessions"][0]["session_id"] == session_id
    assert res["sessions"][0]["device_class"] == "DESKTOP"
    assert res["sessions"][0]["ip_address"] == "127.0.0.1"
    assert res["sessions"][0]["final_score"] == 15.0
    assert res["sessions"][0]["final_band"] == "GREEN"

def test_get_transactions_with_txn_type():
    """Verify that get_transactions correctly supports and filters by txn_type."""
    username = "txn_test_user"
    db.create_user(username)
    session_id = "test_session_id_1"
    
    # Add a upi transaction (should return the dict payload)
    t1 = db.add_transaction(username, session_id, "upi", 150.0, "UPI payment", "payee@upi")
    assert t1["txn_type"] == "upi"
    assert t1["amount"] == 150.0
    
    # Add a bill payment transaction
    t2 = db.add_transaction(username, session_id, "bill_electricity", 1200.0, "Electricity bill", "electricity_board")
    assert t2["txn_type"] == "bill_electricity"
    assert t2["amount"] == 1200.0
    
    # Query all
    all_txns = db.get_transactions(username)
    assert len(all_txns) == 2
    
    # Query upi only
    upi_txns = db.get_transactions(username, txn_type="upi")
    assert len(upi_txns) == 1
    assert upi_txns[0]["txn_type"] == "upi"
    
    # Query bill only (wildcard startswith match)
    bill_txns = db.get_transactions(username, txn_type="bill")
    assert len(bill_txns) == 1
    assert bill_txns[0]["txn_type"] == "bill_electricity"
