#!/usr/bin/env python3
# =============================================================================
# BehaviorShield — scripts/analyze_inb_logs.py
# Team SOLARIS | Cyber Security Hackathon 2026 — MNNIT Allahabad
# =============================================================================
# Analyzes INB_REQ_LOG.csv to extract request transition times (deltas)
# per session and find the most common service request sequences.
# =============================================================================

import os
import sys
import pandas as pd
import numpy as np

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def main():
    # Determine the directory paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    csv_path = os.path.join(project_root, "datasets", "SAMPLE_DATA", "INB_REQ_LOG.csv")
    
    if not os.path.exists(csv_path):
        print(f"Error: Dataset not found at: {csv_path}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Loading log data from: {csv_path}")
    df = pd.read_csv(csv_path)
    
    # Step 1: Preprocessing session logs
    initial_len = len(df)
    df = df.dropna(subset=["INB_SESSION_ID"])
    dropped = initial_len - len(df)
    if dropped > 0:
        print(f"Note: Dropped {dropped} rows with missing INB_SESSION_ID.")
        
    # Step 2: Parse request dates (Format: YYYY-MM-DD-HH.MM.SS.ffffff)
    try:
        df["parsed_date"] = pd.to_datetime(df["INB_REQUEST_DATE"], format="%Y-%m-%d-%H.%M.%S.%f")
    except Exception as e:
        print("Warning: Standard date format parsing failed. Trying default parser...", file=sys.stderr)
        df["parsed_date"] = pd.to_datetime(df["INB_REQUEST_DATE"])

    # Step 3: Sort by session and then request timestamp
    df = df.sort_values(by=["INB_SESSION_ID", "parsed_date"])
    
    # Step 4: Calculate time delta between consecutive requests per session
    df["time_delta"] = df.groupby("INB_SESSION_ID")["parsed_date"].diff().dt.total_seconds()
    
    # Extract all valid transition deltas
    deltas = df["time_delta"].dropna()
    
    print("\n" + "=" * 55)
    print("  SESSION REQUEST TRANSITION TIME METRICS")
    print("=" * 55)
    if len(deltas) > 0:
        mean_sec = deltas.mean()
        median_sec = deltas.median()
        p95_sec = np.percentile(deltas, 95)
        
        print(f"  Total Transitions  : {len(deltas)}")
        print(f"  Mean Delta Time    : {mean_sec:.3f} seconds")
        print(f"  Median Delta Time  : {median_sec:.3f} seconds")
        print(f"  95th Percentile    : {p95_sec:.3f} seconds")
    else:
        print("  No transitions found. All sessions contain a single request.")
        
    # Step 5: Group and aggregate request sequence per session
    # We aggregate session requests sorted chronologically into a sequence tuple
    sequences = df.groupby("INB_SESSION_ID")["INB_SERVICE_ID"].apply(lambda x: tuple(x.dropna()))
    
    # Count frequency of each sequence
    seq_counts = sequences.value_counts()
    
    print("\n" + "=" * 55)
    print("  MOST COMMON SERVICE REQUEST SEQUENCES")
    print("=" * 55)
    if not seq_counts.empty:
        most_common_seq = seq_counts.index[0]
        most_common_freq = seq_counts.iloc[0]
        
        print(f"  Most Common Sequence (Freq: {most_common_freq} sessions):")
        print(f"  ⇒ " + " -> ".join(most_common_seq))
        
        print("\n  Top 5 Navigation Sequences:")
        for rank, (seq, freq) in enumerate(seq_counts.head(5).items(), 1):
            seq_path = " -> ".join(seq)
            print(f"    {rank}. [{freq}x] {seq_path}")
    else:
        print("  No sequences could be extracted.")
    print("=" * 55 + "\n")

if __name__ == "__main__":
    main()
