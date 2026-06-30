#!/usr/bin/env python3
# =============================================================================
# TRUSTLAYER — scripts/analyze_upi_txn.py
# Team SOLARIS | Cyber Security Hackathon 2026 — MNNIT Allahabad
# =============================================================================
# Analyzes TXN_HISTORY_UPI_FIN.xlsx to extract amount distributions,
# high-value thresholds, device reuse metrics, and IP diversity.
# Saves results as a JSON summary.
# =============================================================================

import os
import sys
import json
import pandas as pd
import numpy as np

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def main():
    # Setup paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    xlsx_path = os.path.join(project_root, "datasets", "SAMPLE_DATA", "TXN_HISTORY_UPI_FIN.xlsx")
    json_path = os.path.join(project_root, "datasets", "SAMPLE_DATA", "upi_analysis.json")
    
    if not os.path.exists(xlsx_path):
        print(f"Error: Dataset not found at: {xlsx_path}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Loading UPI transaction history from: {xlsx_path}")
    
    # Suppress openpyxl style sheet user warning
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = pd.read_excel(xlsx_path)
        
    print(f"Loaded {len(df)} transactions.")
    
    # 1. AMOUNT column statistics
    amount_col = df["AMOUNT"].dropna()
    count_val = int(amount_col.count())
    mean_val = float(amount_col.mean())
    median_val = float(amount_col.median())
    std_val = float(amount_col.std())
    min_val = float(amount_col.min())
    max_val = float(amount_col.max())
    
    p25 = float(amount_col.quantile(0.25))
    p75 = float(amount_col.quantile(0.75))
    p90 = float(amount_col.quantile(0.90))
    p95 = float(amount_col.quantile(0.95))
    p99 = float(amount_col.quantile(0.99))
    
    # 2. Count transactions above thresholds
    above_5k = int((amount_col > 5000).sum())
    above_10k = int((amount_col > 10000).sum())
    above_20k = int((amount_col > 20000).sum())
    
    # 3. Unique DEVICE_ID count vs total rows
    device_col = df["DEVICE_ID"].dropna()
    total_device_rows = len(df["DEVICE_ID"])
    non_null_device_rows = len(device_col)
    unique_devices = int(device_col.nunique())
    
    # 4. Unique HOST_IP count
    ip_col = df["HOST_IP"].dropna()
    unique_ips = int(ip_col.nunique())
    
    print("\n" + "=" * 55)
    print("  UPI TRANSACTION AMOUNT STATISTICS")
    print("=" * 55)
    print(f"  Count                : {count_val}")
    print(f"  Mean                 : ₹{mean_val:.2f}")
    print(f"  Median (50th %ile)   : ₹{median_val:.2f}")
    print(f"  Standard Deviation   : ₹{std_val:.2f}")
    print(f"  Minimum              : ₹{min_val:.2f}")
    print(f"  Maximum              : ₹{max_val:.2f}")
    print("-" * 40)
    print(f"  25th Percentile      : ₹{p25:.2f}")
    print(f"  75th Percentile      : ₹{p75:.2f}")
    print(f"  90th Percentile      : ₹{p90:.2f}")
    print(f"  95th Percentile      : ₹{p95:.2f}")
    print(f"  99th Percentile      : ₹{p99:.2f}")
    
    print("\n" + "=" * 55)
    print("  HIGH-VALUE TRANSACTION THRESHOLDS")
    print("=" * 55)
    print(f"  Transactions > ₹5,000  : {above_5k} ({above_5k/count_val*100:.1f}%)")
    print(f"  Transactions > ₹10,000 : {above_10k} ({above_10k/count_val*100:.1f}%)")
    print(f"  Transactions > ₹20,000 : {above_20k} ({above_20k/count_val*100:.1f}%)")
    
    print("\n" + "=" * 55)
    print("  DEVICE AND NETWORK DIVERSITY")
    print("=" * 55)
    print(f"  Total Rows           : {len(df)}")
    print(f"  Non-null DEVICE_IDs  : {non_null_device_rows}")
    print(f"  Unique DEVICE_IDs    : {unique_devices}")
    print(f"  Unique HOST_IPs      : {unique_ips}")
    print(f"  Device Fingerprint   : {unique_devices/non_null_device_rows*100:.1f}% unique devices")
    print("=" * 55 + "\n")
    
    # Save to summary dict
    summary = {
        "amount_stats": {
            "count": count_val,
            "mean": mean_val,
            "median": median_val,
            "std": std_val,
            "min": min_val,
            "max": max_val,
            "p25": p25,
            "p75": p75,
            "p90": p90,
            "p95": p95,
            "p99": p99
        },
        "thresholds": {
            "above_5k_count": above_5k,
            "above_5k_pct": above_5k / count_val,
            "above_10k_count": above_10k,
            "above_10k_pct": above_10k / count_val,
            "above_20k_count": above_20k,
            "above_20k_pct": above_20k / count_val
        },
        "device_stats": {
            "total_rows": len(df),
            "non_null_devices": non_null_device_rows,
            "unique_devices": unique_devices,
            "device_reuse_ratio": unique_devices / non_null_device_rows if non_null_device_rows > 0 else 0
        },
        "network_stats": {
            "unique_ips": unique_ips
        }
    }
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4)
        
    print(f"Successfully saved summary analysis to: {json_path}")

if __name__ == "__main__":
    main()
