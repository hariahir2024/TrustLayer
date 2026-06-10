import subprocess
import time
import urllib.request
import json
import sys
import os

# Base URL
PORT = 8089
BASE_URL = f"http://127.0.0.1:{PORT}"

def run_server():
    """Start the FastAPI app in a background subprocess."""
    env = os.environ.copy()
    # Force the app to run on our custom port by overriding the main section run or env
    # But uvicorn in app.py runs on port 8080.
    # To run on PORT 8089, we can temporarily set it or launch uvicorn manually.
    print(f"Launching FastAPI server on port {PORT}...")
    cmd = [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(PORT)]
    p = subprocess.Popen(cmd, cwd="C:\\hackathon\\cbi hackathon", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p

def post_json(endpoint, data):
    """Utility to make a JSON POST request."""
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode("utf-8"))

def get_json(endpoint):
    """Utility to make a GET request."""
    url = f"{BASE_URL}{endpoint}"
    with urllib.request.urlopen(url) as res:
        return json.loads(res.read().decode("utf-8"))

def generate_key_events(dwell_ms, flight_ms):
    """Helper to generate sequential key down/up event lists."""
    events = []
    current_ts = 1000.0
    for i in range(1, 18): # 17 character passphrase
        # Key down
        events.append({
            "timestamp": current_ts,
            "event": "down",
            "position": i
        })
        current_ts += dwell_ms
        # Key up
        events.append({
            "timestamp": current_ts,
            "event": "up",
            "position": i
        })
        current_ts += flight_ms
    return events

def main():
    server_process = None
    try:
        server_process = run_server()
        
        # Wait for server to start
        print("Waiting for server to initialize baselines...")
        max_attempts = 15
        for i in range(max_attempts):
            try:
                urllib.request.urlopen(f"{BASE_URL}/api/health")
                print("Server is up and responding!")
                break
            except Exception:
                time.sleep(1.5)
        else:
            print("Error: Server failed to start in time.")
            sys.exit(1)

        username = "verify_test_user"

        # 1. Reset demo database
        print("\n--- 1. Resetting Database ---")
        reset_res = post_json("/api/admin/reset", {})
        print("Reset response:", reset_res)

        # 2. Perform enrollment (5 attempts)
        print("\n--- 2. Simulating Enrollment (5 Normal attempts) ---")
        enroll_events = generate_key_events(dwell_ms=90, flight_ms=120)
        
        for attempt in range(1, 6):
            enroll_res = post_json("/api/enroll", {
                "username": username,
                "key_events": enroll_events,
                "field_focus_ts": 900.0
            })
            print(f"Attempt {attempt}/5: complete = {enroll_res['complete']}, msg = {enroll_res['message']}")
            assert enroll_res["count"] == attempt

        # 3. Simulate Persona A: Legitimate Owner (Normal rhythm)
        print("\n--- 3. Simulating Persona A: Legitimate Owner Login ---")
        owner_events = generate_key_events(dwell_ms=92, flight_ms=118) # slight variation
        login_res = post_json("/api/login", {
            "username": username,
            "key_events": owner_events,
            "field_focus_ts": 950.0,
            "device_info": {
                "user_agent": "Mozilla/5.0",
                "screen_width": 1920,
                "screen_height": 1080,
                "color_depth": 24,
                "timezone": "Asia/Kolkata",
                "language": "en"
            }
        })
        print("Login response:", login_res)
        session_id = login_res["session_id"]
        assert login_res["enrolled"] == True
        assert login_res["band"] == "GREEN"
        assert login_res["action"] == "CONTINUE"

        # 4. Simulate Persona B: Suspicious Human Intruder (Slow, hesitant rhythm)
        print("\n--- 4. Simulating Persona B: Human Intruder Scoring ---")
        intruder_events = generate_key_events(dwell_ms=250, flight_ms=500) # highly deviated
        score_res = post_json("/api/score", {
            "session_id": session_id,
            "key_events": intruder_events,
            "mouse_samples": [
                {"timestamp": 2000.0, "x": 100, "y": 100, "event": "move"},
                {"timestamp": 2100.0, "x": 105, "y": 102, "event": "move"},
                {"timestamp": 2200.0, "x": 108, "y": 104, "event": "move"},
                {"timestamp": 2300.0, "x": 110, "y": 105, "event": "move"},
                {"timestamp": 2400.0, "x": 120, "y": 110, "event": "move"}
            ]
        })
        print("Intruder Score Response:", score_res)
        # Verify it transitions to Amber band (re-auth or challenge actions)
        print(f"Risk Score: {score_res['score']}, Band: {score_res['band']}, Action: {score_res['action']}")
        assert score_res["band"] in ("AMBER_LOW", "AMBER_MID", "AMBER_HIGH")

        # 5. Simulate Persona C: Automated Bot Script (Inhumanly fast timing)
        print("\n--- 5. Simulating Persona C: Automated Bot Scoring ---")
        # Generate flight times < 5ms (e.g. 1ms)
        bot_events = generate_key_events(dwell_ms=1, flight_ms=1)
        bot_res = post_json("/api/score", {
            "session_id": session_id,
            "key_events": bot_events,
            "mouse_samples": [
                {"timestamp": 3000.0, "x": 100, "y": 100, "event": "move"},
                {"timestamp": 3050.0, "x": 200, "y": 200, "event": "move"},
                {"timestamp": 3100.0, "x": 300, "y": 300, "event": "move"},
                {"timestamp": 3150.0, "x": 400, "y": 400, "event": "move"},
                {"timestamp": 3200.0, "x": 500, "y": 500, "event": "move"}
            ]
        })
        print("Bot Response:", bot_res)
        assert bot_res["is_bot"] == True
        assert bot_res["band"] == "RED_CRITICAL"
        assert bot_res["action"] == "SILENT_BLOCK"

        print("\n=======================================================")
        print("  INTEGRATION TEST VERIFICATION SUCCESSFUL!")
        print("=======================================================")

    except Exception as e:
        print("\n❌ INTEGRATION TEST FAILED:", e)
        # Read stderr/stdout from server
        if server_process:
            print("\n--- Server stderr peek ---")
            try:
                out, err = server_process.communicate(timeout=2)
                print(err.decode())
            except Exception:
                pass
        sys.exit(1)
        
    finally:
        if server_process:
            print("Terminating background server process...")
            server_process.terminate()
            server_process.wait()

if __name__ == "__main__":
    main()
