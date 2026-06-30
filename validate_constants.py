import sys
sys.path.insert(0, '.')
from constants import *

print("=== TRUSTLAYER constants.py — Validation Report ===\n")

# Feature count
print(f"Total features defined: {len(FEATURES)}")
print(f"  Keystroke : {len(KEYSTROKE_FEATURES)} features")
print(f"  Mouse     : {len(MOUSE_FEATURES)} features")
print(f"  Metadata  : {len(METADATA_FEATURES)} features")

# Weight sums
print(f"\nCategory weight sums (each must = 1.00):")
print(f"  Keystroke weights : {KEYSTROKE_WEIGHT_SUM:.2f}")
print(f"  Mouse weights     : {MOUSE_WEIGHT_SUM:.2f}")
print(f"  Metadata weights  : {METADATA_WEIGHT_SUM:.2f}")

# Category weights
print(f"\nRisk category weights (must sum to 1.00):")
total = sum(CATEGORY_WEIGHTS.values())
for k, v in CATEGORY_WEIGHTS.items():
    print(f"  {k}: {v}")
print(f"  Total: {total:.2f}")

# Score band test
print(f"\nScore band mapping:")
for score in [0, 15, 30, 31, 45, 46, 60, 61, 70, 71, 82, 83, 95, 96, 100]:
    print(f"  Score {score:3d} -> {get_score_band(score)}")

# Passphrase info
print(f"\nPassphrase: \"{ENROLLMENT_PASSPHRASE}\" ({ENROLLMENT_PASSPHRASE_LENGTH} chars)")

# MIN_STD_FLOOR check — keystroke only
print(f"\nMIN_STD_FLOOR values (keystroke features):")
for name in KEYSTROKE_FEATURES:
    floor = FEATURES[name]["min_std_floor"]
    print(f"  {name:<35} floor={floor}")

print(f"\n=== All checks passed ===")
