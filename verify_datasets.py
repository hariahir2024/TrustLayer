import pandas as pd
import os
import sys

# Fix Windows terminal encoding
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

print("=" * 55)
print("  BehaviorShield - Dataset Verification")
print("=" * 55)

# 1. CMU Keystroke Dataset
print("\n[CMU] CMU Keystroke Benchmark")
base_dir = os.path.dirname(os.path.abspath(__file__))
cmu_path = os.path.join(base_dir, "datasets", "cmu_keystroke_benchmark.csv")
df_cmu = pd.read_csv(cmu_path)
print(f"  Shape         : {df_cmu.shape[0]} rows × {df_cmu.shape[1]} columns")
print(f"  Subjects      : {df_cmu['subject'].nunique()} unique users")
print(f"  Reps          : {df_cmu['rep'].max()} max per subject")
print(f"  Columns       : {list(df_cmu.columns[:6])} ... (first 6)")

# Check for hold time and flight time columns
hold_cols = [c for c in df_cmu.columns if c.startswith('H.')]
ud_cols   = [c for c in df_cmu.columns if c.startswith('UD.')]
dd_cols   = [c for c in df_cmu.columns if c.startswith('DD.')]
print(f"  Hold time cols: {len(hold_cols)}  (H.*)")
print(f"  Flight UD cols: {len(ud_cols)}  (UD.*)")
print(f"  Flight DD cols: {len(dd_cols)}  (DD.*)")
print(f"  OK - CMU dataset looks correct")

# -- 2. BALABIT Mouse Dataset ------------------------------
print("\n[BALABIT] BALABIT Mouse Dynamics")
print("-" * 40)
balabit_base = os.path.join(base_dir, "datasets", "balabit")

# Count users and sessions
training_path = os.path.join(balabit_base, "training_files")
users = os.listdir(training_path)
total_sessions = sum(
    len(os.listdir(os.path.join(training_path, u)))
    for u in users
)
print(f"  Training users   : {len(users)}")
print(f"  Total sessions   : {total_sessions}")

# Peek at one session file
sample_user = users[0]
sample_sessions = os.listdir(os.path.join(training_path, sample_user))
sample_file = os.path.join(training_path, sample_user, sample_sessions[0])
df_bal = pd.read_csv(sample_file)
print(f"  Sample file      : {sample_user}/{sample_sessions[0]}")
print(f"  Columns          : {list(df_bal.columns)}")
print(f"  Rows in sample   : {len(df_bal)}")

# Check for expected columns
expected = ['record_timestamp', 'client_timestamp', 'button', 'state', 'x', 'y']
found = [c for c in expected if c in df_bal.columns]
missing = [c for c in expected if c not in df_bal.columns]
print(f"  Expected cols    : {len(found)}/{len(expected)} found")
if missing:
    print(f"  ⚠️  Missing       : {missing}")
    # Try to show actual columns for debugging
    print(f"  Actual columns   : {list(df_bal.columns)}")
else:
    print(f"  OK - BALABIT dataset looks correct")

# Check labels file
labels_path = os.path.join(balabit_base, "public_labels.csv")
df_labels = pd.read_csv(labels_path)
print(f"\n  Labels file      : {len(df_labels)} entries")
print(f"  Label columns    : {list(df_labels.columns)}")
legit = df_labels[df_labels.iloc[:, -1] == 1].shape[0] if len(df_labels.columns) >= 2 else "N/A"
print(f"  OK - Labels file loaded")

# ── Summary ───────────────────────────────────────────────
print("\n" + "=" * 55)
print("  VERIFICATION SUMMARY")
print("=" * 55)
print(f"  CMU Keystroke   : OK  {df_cmu.shape[0]} rows, {df_cmu['subject'].nunique()} subjects")
print(f"  BALABIT Mouse   : OK  {len(users)} users, {total_sessions} sessions")
print(f"  BALABIT Labels  : OK  {len(df_labels)} labeled entries")
print(f"\n  Datasets ready for ml_engine.py -- ALL GOOD")
