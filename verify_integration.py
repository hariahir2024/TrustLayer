import subprocess
import time
import urllib.request
import json
import sys
import os

# Force UTF-8 output on Windows (prevents cp1252 UnicodeEncodeError)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
        enrollment_timings = [
            {'dwell_ms': 82,  'flight_ms': 105},
            {'dwell_ms': 98,  'flight_ms': 135},
            {'dwell_ms': 88,  'flight_ms': 118},
            {'dwell_ms': 105, 'flight_ms': 128},
            {'dwell_ms': 77,  'flight_ms': 114},
        ]
        
        for attempt in range(1, 6):
            t_config = enrollment_timings[attempt - 1]
            enroll_events = generate_key_events(dwell_ms=t_config['dwell_ms'], flight_ms=t_config['flight_ms'])
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
        
        # Print enrolled user's baseline at the start of the intruder test
        try:
            baseline = get_json(f"/api/admin/baseline/{username}")
            means = baseline.get("means", {})
            stds = baseline.get("stds", {})
            print(f"Enrolled User Baseline:")
            print(f"  hold_time   : mean={means.get('mean_hold_time', 0.0):.1f}ms, std={stds.get('mean_hold_time', 0.0):.1f}ms")
            print(f"  flight_time : mean={means.get('mean_flight_time', 0.0):.1f}ms, std={stds.get('mean_flight_time', 0.0):.1f}ms")
            print(f"  typing_speed: mean={means.get('typing_speed_cps', 0.0):.2f}cps, std={stds.get('typing_speed_cps', 0.0):.2f}cps")
        except Exception as e:
            print("Failed to fetch user baseline:", e)

        # Generate intruder events using updated timings (dwell=130ms, flight=175ms)
        intruder_events = generate_key_events(dwell_ms=130, flight_ms=175)
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
        # Verify it transitions to Amber or Red band (re-auth, challenge, or block actions)
        print(f"Risk Score: {score_res['score']}, Band: {score_res['band']}, Action: {score_res['action']}")
        assert score_res["band"] in ("AMBER_LOW", "AMBER_MID", "AMBER_HIGH", "RED_LOW"), \
            f"Expected intruder to land in AMBER or RED_LOW, got {score_res['band']}"


        # 4b. Simulating Gradual Session Takeover
        print("\n--- 4b. Simulating Gradual Session Takeover ---")
        takeover_user = "takeover_user"
        
        # Enroll takeover_user with varied timings
        print("Enrolling takeover user...")
        for attempt in range(1, 6):
            t_config = enrollment_timings[attempt - 1]
            enroll_events = generate_key_events(dwell_ms=t_config['dwell_ms'], flight_ms=t_config['flight_ms'])
            post_json("/api/enroll", {
                "username": takeover_user,
                "key_events": enroll_events,
                "field_focus_ts": 900.0
            })
            
        # Login takeover_user
        login_res = post_json("/api/login", {
            "username": takeover_user,
            "key_events": generate_key_events(dwell_ms=92, flight_ms=118),
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
        takeover_session_id = login_res["session_id"]
        
        # 3 legitimate calls
        print("Simulating 3 legitimate score calls...")
        legit_events = generate_key_events(dwell_ms=90, flight_ms=120)
        for i in range(1, 4):
            score_res = post_json("/api/score", {
                "session_id": takeover_session_id,
                "key_events": legit_events,
                "mouse_samples": []
            })
            print(f"  Legit Call {i}: Score = {score_res['score']}, Band = {score_res['band']}")
            assert score_res["band"] == "GREEN"
            
        # 3 takeover calls with increasing timings to simulate gradual deviation
        print("Simulating 3 takeover score calls (gradually increasing deviation)...")
        takeover_stages = [
            {"dwell_ms": 105, "flight_ms": 140},
            {"dwell_ms": 120, "flight_ms": 160},
            {"dwell_ms": 130, "flight_ms": 175}
        ]
        
        scores = []
        bands = []
        for i, stage in enumerate(takeover_stages, 1):
            intruder_events = generate_key_events(dwell_ms=stage["dwell_ms"], flight_ms=stage["flight_ms"])
            score_res = post_json("/api/score", {
                "session_id": takeover_session_id,
                "key_events": intruder_events,
                "mouse_samples": [
                    {"timestamp": 2000.0, "x": 100, "y": 100, "event": "move"},
                    {"timestamp": 2100.0, "x": 105, "y": 102, "event": "move"},
                    {"timestamp": 2200.0, "x": 108, "y": 104, "event": "move"},
                    {"timestamp": 2300.0, "x": 110, "y": 105, "event": "move"},
                    {"timestamp": 2400.0, "x": 120, "y": 110, "event": "move"}
                ]
            })
            print(f"  Takeover Call {i} ({stage['dwell_ms']}ms/{stage['flight_ms']}ms): Score = {score_res['score']}, Band = {score_res['band']}, Action = {score_res['action']}")
            scores.append(score_res["score"])
            bands.append(score_res["band"])
            
        # Verify the score strictly rises across all 3 calls
        assert scores[2] > scores[1] > scores[0], f"Expected score to rise monotonically, got {scores}"

        # Call 1 (mildest deviation): should land in amber range — not GREEN, not RED
        assert bands[0] in ("AMBER_LOW", "AMBER_MID", "AMBER_HIGH"), \
            f"Expected Call 1 to be in AMBER range (not GREEN or RED), got {bands[0]}"

        # Call 3 (full intruder timing): must be meaningfully elevated vs Call 1
        assert bands[2] in ("AMBER_MID", "AMBER_HIGH", "RED_LOW", "RED_HIGH"), \
            f"Expected Call 3 to be AMBER_MID or above, got {bands[2]}"

        # The escalation must be real: final score must be at least 15 points above first
        assert scores[2] - scores[0] >= 15, \
            f"Expected meaningful score escalation (>=15 pts), got rise of {scores[2]-scores[0]:.1f}"



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
