import logging
import time
logging.basicConfig(level=logging.INFO, format='%(name)s: %(message)s')

print("--- Loading ml_engine ---")
import ml_engine as ml

print("\n--- Loading generic baselines ---")
ml.load_generic_baselines()

print("\n--- Testing feature extraction ---")
base = time.time() * 1000
key_events = []
pos = 1
t = base
for i in range(17):
    t += 350
    key_events.append({"timestamp": t, "event": "down", "position": pos})
    t += 95
    key_events.append({"timestamp": t, "event": "up", "position": pos})
    pos += 1

features = ml.extract_keystroke_features(key_events, base)
print(f"  Keystroke features extracted: {len(features)} features")
print(f"  mean_hold_time  : {features['mean_hold_time']:.1f}ms")
print(f"  mean_flight_time: {features['mean_flight_time']:.1f}ms")
print(f"  typing_speed_cps: {features['typing_speed_cps']:.2f}")

print("\n--- Testing enrollment ---")
import db_sqlite as db
db.init_db()
db.reset_all()
db.create_user("demo_hari")
for i in range(5):
    result = ml.process_enrollment_sample("demo_hari", key_events)
    print(f"  Sample {result['count']}: {result['message'][:60]}")

print("\n--- Testing keystroke scoring ---")
k_score, k_breakdown = ml.score_keystrokes("demo_hari", features)
print(f"  Keystroke score : {k_score}")
print(f"  Top contributor : {k_breakdown[0]['label']} | contrib={k_breakdown[0]['contribution']}")

print("\n--- Testing full session score ---")
sid = db.create_session("demo_hari", "127.0.0.1", "Chrome", "fp_abc123")
result = ml.score_session(sid, key_events, [])
print(f"  Final score : {result['final_score']}")
print(f"  Band        : {result['band']}")
print(f"  Action      : {result['action']}")
print(f"  Is bot      : {result['is_bot']}")
print(f"  Top feature : {result['top_contributors'][0]['label']}")

print("\n--- Testing bot detection ---")
bot_events = []
t = base
for i in range(17):
    t += 2
    bot_events.append({"timestamp": t, "event": "down", "position": i+1})
    bot_events.append({"timestamp": t+1, "event": "up", "position": i+1})
is_bot, reason = ml.detect_bot(bot_events, [], {"webdriver_flag": False, "click_dwell_mean": 5})
print(f"  Bot detected : {is_bot}")
print(f"  Reason       : {reason}")

print("\nALL ml_engine TESTS PASSED")
