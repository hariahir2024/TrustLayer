"""
BehaviorShield — Demo Seed Script (Stream 6E)
Team SOLARIS | CBI Hackathon 2026

Pre-populates the SQLite database with realistic demo accounts so the
presentation starts with the bank portal already looking "lived in".

Seed accounts:
  demo_owner    (Hari Ahir, Allahabad)  — 15 legitimate sessions, enrolled baseline
  demo_rival    (Priya Sharma, Mumbai)  — enrolled, different behavioral profile
  demo_intruder (labeled intruder data) — 2 intruder sessions on demo_owner's account

Each account is seeded with:
  - Enrolled keystroke baseline (simulated from realistic timing distributions)
  - 10 sample transactions (mix of UPI, bills, transfers)
  - 3 saved payees
  - 1 pre-existing FD record (stored as a credit transaction)

Usage:
    python scripts/seed_demo_data.py          # seed fresh database
    python scripts/seed_demo_data.py --reset  # wipe DB first, then seed

WARNING: --reset deletes ALL existing user data.
"""

import os
import sys
import json
import time
import random
import argparse
import hashlib
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("seed")

import db_sqlite as db
from constants import generate_passphrase, BASELINE_DRIFT_WEIGHT


# =============================================================================
# SEEDING HELPERS
# =============================================================================

def _simulated_keystroke_baseline(
    mean_hold: float, mean_flight: float, noise: float = 0.1
) -> tuple[dict, dict]:
    """Generate a realistic baseline from normal distributions."""
    rng = random.Random(mean_hold * 100)  # deterministic per seed

    means = {
        "mean_hold_time":    mean_hold,
        "std_hold_time":     mean_hold * 0.15,
        "mean_flight_time":  mean_flight,
        "std_flight_time":   mean_flight * 0.18,
        "typing_speed_cps":  round(11 / (mean_flight * 10 * 0.001 + mean_hold * 11 * 0.001), 2),
        "backspace_rate":    rng.uniform(0.01, 0.08),
        "rhythm_consistency": rng.uniform(0.15, 0.35),
        "burst_ratio":       rng.uniform(0.3, 0.7),
        "first_key_latency": rng.uniform(200, 800),
        "completion_time":   (mean_hold * 11 + mean_flight * 10) * (1 + rng.uniform(-0.1, 0.1)),
        # New 11-char digraph positions
        "digraph_pos_1_2":   mean_flight * rng.uniform(0.85, 1.15),
        "digraph_pos_4_5":   mean_flight * rng.uniform(1.10, 1.30),  # name junction slower
        "digraph_pos_7_8":   mean_flight * rng.uniform(0.80, 1.05),
        "digraph_pos_8_9":   mean_flight * rng.uniform(1.15, 1.40),  # @ reach pause
        "digraph_pos_9_10":  mean_flight * rng.uniform(1.00, 1.25),
    }

    stds = {
        "mean_hold_time":    max(8.0, mean_hold * noise),
        "std_hold_time":     max(5.0, mean_hold * noise * 0.5),
        "mean_flight_time":  max(8.0, mean_flight * noise),
        "std_flight_time":   max(5.0, mean_flight * noise * 0.5),
        "typing_speed_cps":  0.3,
        "backspace_rate":    0.02,
        "rhythm_consistency": 0.05,
        "burst_ratio":       0.05,
        "first_key_latency": 20.0,
        "completion_time":   max(200.0, means["completion_time"] * 0.1),
        "digraph_pos_1_2":   max(8.0, mean_flight * noise),
        "digraph_pos_4_5":   max(10.0, mean_flight * noise * 1.1),
        "digraph_pos_7_8":   max(8.0, mean_flight * noise),
        "digraph_pos_8_9":   max(12.0, mean_flight * noise * 1.2),
        "digraph_pos_9_10":  max(10.0, mean_flight * noise),
    }

    return means, stds


def _make_transactions(username: str, account_num: str, n: int = 10) -> None:
    """Insert n realistic sample transactions for a user."""
    rng = random.Random(hash(username))

    txn_types = [
        ("upi",          "UPI to priya@bsb",         350.0),
        ("upi",          "UPI to raj@sbi",            125.0),
        ("bill_mobile",  "Airtel Recharge 84 days",   479.0),
        ("bill_electric","Electricity - Aug 2026",   1250.0),
        ("transfer",     "NEFT to SBI savings",      5000.0),
        ("credit",       "Salary Credit Aug 2026",  35000.0),
        ("bill_dth",     "Tata Play DTH recharge",    295.0),
        ("upi",          "UPI Split - Dinner",         620.0),
        ("transfer",     "IMPS to friend - loan",     2500.0),
        ("credit",       "Cashback Credit",             45.0),
    ]

    # Timestamps spread over the last 30 days
    base_time = time.time() - (30 * 86400)
    for i in range(min(n, len(txn_types))):
        txn_type, desc, amount = txn_types[i]
        ts = base_time + (i * 86400 * 2.5) + rng.uniform(-3600, 3600)

        conn = db._connect()
        try:
            # Insert directly with custom timestamp
            conn.execute("""
                INSERT INTO transactions
                    (username, txn_type, amount, description, status, risk_score, created_at)
                VALUES (?,?,?,?,?,?,?)
            """, (username, txn_type, amount, desc, "success", rng.uniform(5, 25), ts))

            # Update balance (credit adds, debit subtracts)
            if txn_type == "credit":
                conn.execute("UPDATE users SET balance = balance + ? WHERE username = ?",
                             (amount, username))
            else:
                conn.execute("UPDATE users SET balance = balance - ? WHERE username = ?",
                             (amount, username))
            conn.commit()
        finally:
            conn.close()


def _add_payees(username: str) -> None:
    """Add 3 sample payees."""
    payees = [
        {"name": "Priya Sharma",   "account_number": "BSB456789012345", "ifsc": "BSB0001002", "bank_name": "BSB"},
        {"name": "Raj Kumar",      "account_number": "SBIN000123456789","ifsc": "SBIN0001234", "bank_name": "SBI"},
        {"name": "Mom (Home)",     "account_number": "BSB789012345678", "ifsc": "BSB0001003", "bank_name": "BSB"},
    ]
    for p in payees:
        db.add_payee(username, **p)


def _add_fd(username: str) -> None:
    """Simulate a Fixed Deposit as a locked transaction."""
    conn = db._connect()
    fd_time = time.time() - (15 * 86400)
    try:
        conn.execute("""
            INSERT INTO transactions
                (username, txn_type, amount, description, beneficiary, status, created_at)
            VALUES (?,?,?,?,?,?,?)
        """, (username, "fd", 25000.0, "FD Opened — 1 Year @ 6.5% p.a.", "Fixed Deposit", "success", fd_time))
        conn.execute("UPDATE users SET balance = balance - 25000.0 WHERE username = ?", (username,))
        conn.commit()
    finally:
        conn.close()


# =============================================================================
# SEED ACCOUNTS
# =============================================================================

DEMO_ACCOUNTS = [
    {
        "username":      "demo_owner",
        "first_name":    "Hari",
        "last_name":     "Ahir",
        "city":          "Allahabad",
        "mobile":        "9876543210",
        "date_of_birth": "15/08/1998",
        "email":         "hari.ahir@example.com",
        "account_type":  "savings",
        "password":      "Demo@1234",
        # Behavioral signature: moderate speed, consistent
        "mean_hold":     92.0,
        "mean_flight":   115.0,
        "noise":         0.12,
        "session_count": 15,
        "description":   "Primary demo user — 15 enrolled sessions, stable GREEN profile",
    },
    {
        "username":      "demo_rival",
        "first_name":    "Priya",
        "last_name":     "Sharma",
        "city":          "Mumbai",
        "mobile":        "9988776655",
        "date_of_birth": "22/03/1995",
        "email":         "priya.sharma@example.com",
        "account_type":  "savings",
        "password":      "Demo@5678",
        # Behavioral signature: faster typist, more consistent
        "mean_hold":     68.0,
        "mean_flight":   88.0,
        "noise":         0.08,
        "session_count": 12,
        "description":   "Second demo user — different behavioral profile for comparison",
    },
]


def seed_account(account: dict) -> None:
    """Seed a single demo account."""
    uname = account["username"]
    if db.user_exists(uname):
        log.info(f"  Skipping {uname} — already exists")
        return

    passphrase = generate_passphrase(account["first_name"], account["last_name"])

    log.info(f"  Creating {uname} ({account['first_name']} {account['last_name']}) — passphrase: {passphrase}")
    db.create_user(
        username      = uname,
        first_name    = account["first_name"],
        last_name     = account["last_name"],
        city          = account["city"],
        mobile        = account["mobile"],
        date_of_birth = account["date_of_birth"],
        email         = account["email"],
        account_type  = account["account_type"],
        passphrase    = passphrase,
        password_hash = db.hash_password(account["password"]),
    )

    # Build and save behavioral baseline
    means, stds = _simulated_keystroke_baseline(
        account["mean_hold"], account["mean_flight"], account["noise"]
    )
    db.save_keystroke_baseline(uname, means, stds, device_class="DESKTOP")
    db.save_device_fingerprint(uname, f"demo_fp_{uname}_desktop", device_class="DESKTOP")

    # Update session count (simulating past sessions)
    conn = db._connect()
    try:
        conn.execute("""
            UPDATE behavioral_profiles
            SET session_count = ?, profile_ready = 1, enrollment_count = 5
            WHERE username = ? AND device_class = 'DESKTOP'
        """, (account["session_count"], uname))
        conn.commit()
    finally:
        conn.close()

    # Seed transactions, payees, FD
    user = db.get_user(uname)
    _make_transactions(uname, user["account_number"])
    _add_payees(uname)
    _add_fd(uname)

    log.info(f"  ✓ {uname}: enrolled, {account['session_count']} sessions, transactions seeded")


def seed_intruder_sessions() -> None:
    """
    Mark 2 old sessions as intruder for demo_owner so XGBoost retraining
    has some labeled data to work with immediately.
    """
    # Create two fake historical session records for demo_owner
    # with high risk scores and mark them as intruder
    conn = db._connect()
    try:
        for i, score in enumerate([72.0, 68.0]):
            session_id = f"demo_intruder_session_{i+1:02d}"
            ts = time.time() - (10 * 86400) - (i * 3600)  # 10 days ago

            conn.execute("""
                INSERT OR IGNORE INTO sessions
                    (session_id, username, device_class, ip_address,
                     current_risk, risk_band, is_intruder, created_at)
                VALUES (?,?,?,?,?,?,1,?)
            """, (session_id, "demo_owner", "DESKTOP", "192.168.1.200",
                  score, "AMBER_HIGH", ts))

            conn.execute("""
                INSERT INTO security_events
                    (event_id, event_type, session_id, username, details,
                     risk_score, risk_band, is_intruder, timestamp)
                VALUES (?,?,?,?,?,?,?,1,?)
            """, (f"seed_evt_{i}", "SCORE_UPDATE", session_id, "demo_owner",
                  json.dumps({"note": "Pre-seeded intruder session"}),
                  score, "AMBER_HIGH", ts))

        conn.commit()
    finally:
        conn.close()
    log.info(f"  ✓ 2 intruder sessions seeded for demo_owner")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="BehaviorShield Demo Data Seeder")
    parser.add_argument("--reset", action="store_true",
                        help="Wipe all existing data before seeding (DESTRUCTIVE)")
    args = parser.parse_args()

    log.info("BehaviorShield Demo Seeder")
    log.info("=" * 50)

    db.init_db()

    if args.reset:
        log.warning("--reset flag: wiping all existing data...")
        db.reset_all()
        log.info("Database wiped.")

    log.info("Seeding demo accounts...")
    for account in DEMO_ACCOUNTS:
        seed_account(account)

    log.info("Seeding intruder sessions...")
    seed_intruder_sessions()

    log.info("=" * 50)
    summary = db.get_database_summary()
    log.info(f"Done! Database summary: {summary}")
    log.info("")
    log.info("Demo accounts:")
    for acc in DEMO_ACCOUNTS:
        passphrase = generate_passphrase(acc["first_name"], acc["last_name"])
        log.info(f"  Username: {acc['username']:<15} Password: {acc['password']:<12} Passphrase: {passphrase}")
    log.info("")
    log.info("Run: python -m uvicorn app:app --reload")


if __name__ == "__main__":
    main()
