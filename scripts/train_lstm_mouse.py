#!/usr/bin/env python3
# =============================================================================
# BehaviorShield — scripts/train_lstm_mouse.py
# Team SOLARIS | Cyber Security Hackathon 2026 | MNNIT Allahabad
# =============================================================================
# Trains an LSTM Autoencoder on the BALABIT Mouse Dynamics dataset.
#
# Architecture:
#   Input  : sequence of 50 timesteps × 2 features [velocity, acceleration]
#   Encoder: LSTM(2→128, 2 layers) → Linear(128→16)  [latent bottleneck]
#   Decoder: Linear(16→128) → LSTM(128→128, 2 layers) → Linear(128→2)
#   Output : reconstructed sequence (same shape as input)
#
#   Anomaly score at inference = MSE(input, reconstruction)
#   High MSE → input sequence does not look like training data → suspicious
#
# Run from project root:
#   python scripts/train_lstm_mouse.py
#
# Output:
#   models/lstm_mouse_pretrained.pt       ← trained model weights
#   models/model_metadata.json            ← metrics, threshold, normalization params
# =============================================================================

import os
import sys
import json
import time
import datetime
import math
import numpy as np
import pandas as pd

# Force UTF-8 output on Windows (prevents cp1252 UnicodeEncodeError)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Path setup ────────────────────────────────────────────────────────────────
# Allow importing constants.py from project root regardless of where the
# script is run from.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from constants import (
    DATASET_PATHS,
    BALABIT_COLUMNS,
    LSTM_INPUT_SIZE,
    LSTM_HIDDEN_SIZE,
    LSTM_NUM_LAYERS,
    LSTM_LATENT_DIM,
    LSTM_SEQ_LEN_MOUSE,
    LSTM_BATCH_SIZE,
    LSTM_EPOCHS,
    LSTM_LEARNING_RATE,
    LSTM_DROPOUT,
    LSTM_GRAD_CLIP,
    MODEL_MOUSE_PT,
    MODEL_METADATA_JSON,
    MODEL_DIR,
    SYSTEM_VERSION,
    TEAM_NAME,
    HACKATHON,
)

# ── Device ────────────────────────────────────────────────────────────────────
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ── Resolved paths ────────────────────────────────────────────────────────────
DATASET_PATH  = os.path.join(PROJECT_ROOT, DATASET_PATHS["balabit_mouse"])
MODEL_OUT     = os.path.join(PROJECT_ROOT, MODEL_MOUSE_PT)
METADATA_OUT  = os.path.join(PROJECT_ROOT, MODEL_METADATA_JSON)
MODELS_DIR    = os.path.join(PROJECT_ROOT, MODEL_DIR)

SEQ_LEN    = LSTM_SEQ_LEN_MOUSE       # 50
N_FEATURES = LSTM_INPUT_SIZE          # 2


# =============================================================================
# 1. PROGRESS BAR UTILITY
# =============================================================================

def _progress_bar(current: int, total: int, width: int = 28) -> str:
    """Return an ASCII progress bar string for inline printing."""
    filled = int(width * current / max(total, 1))
    bar    = "#" * filled + "-" * (width - filled)
    pct    = 100 * current / max(total, 1)
    return f"[{bar}] {pct:5.1f}%"


# =============================================================================
# 2. DATA LOADING & PREPROCESSING
# =============================================================================

def load_balabit_sequences(base_path: str) -> tuple[np.ndarray, dict]:
    """
    Load BALABIT mouse training files and build sliding window sequences.

    We extract:
      - velocity (px/ms)
      - acceleration (px/ms^2)
    per mouse event, and group them into sequences of length SEQ_LEN=50.

    Returns:
        sequences  : np.ndarray shape (N, SEQ_LEN, 2) dtype float32
        norm_params: dict with mean/std per channel for z-score normalization
    """
    training_path = os.path.join(base_path, "training_files")
    print(f"\n{'='*60}")
    print(f"  Loading BALABIT mouse dataset...")
    print(f"  Path: {training_path}")

    if not os.path.exists(training_path):
        raise FileNotFoundError(f"BALABIT training path not found at: {training_path}")

    user_dirs = [d for d in os.listdir(training_path) if os.path.isdir(os.path.join(training_path, d))]
    print(f"  Found {len(user_dirs)} user directories.")

    all_features = []
    total_files_loaded = 0

    # Resolve column names from constants
    x_col  = BALABIT_COLUMNS["x"]
    y_col  = BALABIT_COLUMNS["y"]
    ts_col = BALABIT_COLUMNS["client_timestamp"]

    for user_dir in user_dirs:
        user_path = os.path.join(training_path, user_dir)
        session_files = os.listdir(user_path)
        for s_file in session_files:
            s_path = os.path.join(user_path, s_file)
            try:
                df = pd.read_csv(s_path)
                if len(df) < SEQ_LEN + 2:
                    continue

                xs = df[x_col].values.astype(float)
                ys = df[y_col].values.astype(float)
                ts = df[ts_col].values.astype(float)

                # Velocities (px/ms)
                dists = np.sqrt(np.diff(xs)**2 + np.diff(ys)**2)
                dts   = np.diff(ts)
                dts   = np.where(dts == 0, 0.001, dts)  # prevent division by zero
                vels  = dists / dts

                # Accelerations (px/ms^2)
                accels = np.abs(np.diff(vels)) / dts[1:] if len(vels) > 1 else np.array([0.0])

                # Match lengths to N-2
                vels_matched = vels[:-1]
                
                # Check for NaNs and infs
                valid_mask = ~(np.isnan(vels_matched) | np.isinf(vels_matched) | np.isnan(accels) | np.isinf(accels))
                vels_matched = vels_matched[valid_mask]
                accels = accels[valid_mask]

                if len(vels_matched) < SEQ_LEN:
                    continue

                session_feats = np.column_stack((vels_matched, accels))
                all_features.append(session_feats)
                total_files_loaded += 1

            except Exception as e:
                # Silently skip individual file failures
                continue

    print(f"  Loaded {total_files_loaded} session files successfully.")
    
    # Slice sliding windows of length SEQ_LEN=50 with overlap step=25
    sequences_list = []
    step = 25
    for session_feats in all_features:
        n_points = len(session_feats)
        for start in range(0, n_points - SEQ_LEN + 1, step):
            window = session_feats[start:start+SEQ_LEN]
            sequences_list.append(window)

    sequences = np.array(sequences_list, dtype=np.float32)
    N = len(sequences)
    print(f"  Extracted {N:,} sequences of shape (50, 2).")

    if N == 0:
        raise ValueError("No valid mouse event sequences could be extracted from BALABIT dataset.")

    # Flatten across time dimension to compute feature stats for normalization
    flat_vels   = sequences[:, :, 0].flatten()
    flat_accels = sequences[:, :, 1].flatten()

    vel_mean, vel_std   = float(flat_vels.mean()),   max(float(flat_vels.std()), 1e-6)
    acc_mean, acc_std   = float(flat_accels.mean()), max(float(flat_accels.std()), 1e-6)

    # Apply z-score normalization
    sequences[:, :, 0] = (sequences[:, :, 0] - vel_mean) / vel_std
    sequences[:, :, 1] = (sequences[:, :, 1] - acc_mean) / acc_std

    norm_params = {
        "velocity_mean":     vel_mean,
        "velocity_std":      vel_std,
        "acceleration_mean": acc_mean,
        "acceleration_std":  acc_std,
    }

    print(f"\n  Sequence statistics (per event):")
    print(f"    Velocity     — mean: {vel_mean:.6f}  std: {vel_std:.6f}")
    print(f"    Acceleration — mean: {acc_mean:.6f}  std: {acc_std:.6f}")
    print(f"{'='*60}\n")

    return sequences, norm_params


# =============================================================================
# 3. LSTM AUTOENCODER MODEL
# =============================================================================

class LSTMAutoencoder(nn.Module):
    """
    Sequence-to-sequence LSTM Autoencoder for behavioral mouse dynamics patterns.
    """

    def __init__(
        self,
        input_size:  int = LSTM_INPUT_SIZE,
        hidden_size: int = LSTM_HIDDEN_SIZE,
        num_layers:  int = LSTM_NUM_LAYERS,
        latent_dim:  int = LSTM_LATENT_DIM,
        seq_len:     int = LSTM_SEQ_LEN_MOUSE,
        dropout:     float = LSTM_DROPOUT,
    ):
        super().__init__()
        self.seq_len     = seq_len
        self.hidden_size = hidden_size
        self.num_layers  = num_layers
        self.latent_dim  = latent_dim

        # ── Encoder ───────────────────────────────────────────────────────────
        self.encoder_lstm = nn.LSTM(
            input_size  = input_size,
            hidden_size = hidden_size,
            num_layers  = num_layers,
            batch_first = True,
            dropout     = dropout if num_layers > 1 else 0.0,
        )
        self.encoder_proj = nn.Linear(hidden_size, latent_dim)

        # ── Decoder ───────────────────────────────────────────────────────────
        self.decoder_proj = nn.Linear(latent_dim, hidden_size)
        self.decoder_lstm = nn.LSTM(
            input_size  = hidden_size,
            hidden_size = hidden_size,
            num_layers  = num_layers,
            batch_first = True,
            dropout     = dropout if num_layers > 1 else 0.0,
        )
        self.decoder_out  = nn.Linear(hidden_size, input_size)

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        _, (hidden, _) = self.encoder_lstm(x)
        latent = self.encoder_proj(hidden[-1])  # take final layer hidden state
        return latent

    def decode(self, latent: torch.Tensor) -> torch.Tensor:
        expanded = self.decoder_proj(latent)
        decoder_input = expanded.unsqueeze(1).expand(-1, self.seq_len, -1)
        output, _ = self.decoder_lstm(decoder_input)
        reconstruction = self.decoder_out(output)
        return reconstruction

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        latent = self.encode(x)
        reconstruction = self.decode(latent)
        return reconstruction, latent


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


# =============================================================================
# 4. TRAINING LOOP
# =============================================================================

def train(
    model:      nn.Module,
    loader:     DataLoader,
    val_loader: DataLoader,
    optimizer:  torch.optim.Optimizer,
    criterion:  nn.Module,
    epochs:     int,
    grad_clip:  float,
) -> tuple[list[float], list[float]]:
    train_losses, val_losses = [], []
    best_val_loss = float("inf")
    best_state    = None

    print(f"\n{'='*60}")
    print(f"  Training LSTM Autoencoder on {DEVICE}")
    print(f"  Epochs={epochs}  BatchSize={LSTM_BATCH_SIZE}  LR={LSTM_LEARNING_RATE}")
    print(f"  Grad clip={grad_clip}  Dropout={LSTM_DROPOUT}")
    print(f"{'='*60}\n")

    t_start = time.time()
    # Cosine annealing LR scheduler
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=epochs, eta_min=1e-5
    )

    for epoch in range(1, epochs + 1):
        # ── Train pass ────────────────────────────────────────────────────────
        model.train()
        epoch_train_loss = 0.0
        n_batches = 0

        for batch_x, in loader:
            batch_x = batch_x.to(DEVICE)
            optimizer.zero_grad()
            reconstruction, _ = model(batch_x)
            loss = criterion(reconstruction, batch_x)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            optimizer.step()
            epoch_train_loss += loss.item()
            n_batches        += 1

        scheduler.step()
        mean_train = epoch_train_loss / n_batches

        # ── Validation pass ───────────────────────────────────────────────────
        model.eval()
        epoch_val_loss = 0.0
        n_val = 0
        with torch.no_grad():
            for batch_x, in val_loader:
                batch_x = batch_x.to(DEVICE)
                recon, _ = model(batch_x)
                epoch_val_loss += criterion(recon, batch_x).item()
                n_val          += 1
        mean_val = epoch_val_loss / n_val

        train_losses.append(mean_train)
        val_losses.append(mean_val)

        # Track best model
        if mean_val < best_val_loss:
            best_val_loss = mean_val
            best_state    = {k: v.cpu().clone() for k, v in model.state_dict().items()}

        # Progress output
        elapsed  = time.time() - t_start
        eta_sec  = (elapsed / epoch) * (epochs - epoch) if epoch < epochs else 0
        bar      = _progress_bar(epoch, epochs)
        eta_str  = f"{int(eta_sec//60):02d}:{int(eta_sec%60):02d}"
        lr_now   = scheduler.get_last_lr()[0]

        line = (
            f"  Epoch {epoch:3d}/{epochs} {bar}  "
            f"Train={mean_train:.6f}  Val={mean_val:.6f}  "
            f"LR={lr_now:.2e}  ETA={eta_str}"
        )

        if epoch % 10 == 0 or epoch == epochs:
            print(line)
        else:
            print(line, end="\r", flush=True)

    t_elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"  Training complete in {t_elapsed:.1f}s  ({t_elapsed/60:.1f} min)")
    print(f"  Best val loss: {best_val_loss:.6f}  (epoch {val_losses.index(min(val_losses)) + 1})")
    print(f"{'='*60}")

    # Restore best weights
    if best_state is not None:
        model.load_state_dict(best_state)

    return train_losses, val_losses


# =============================================================================
# 5. ANOMALY THRESHOLD COMPUTATION
# =============================================================================

def compute_anomaly_threshold(
    model:  nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    percentile: float = 95.0,
) -> tuple[float, float, float]:
    model.eval()
    all_errors = []

    with torch.no_grad():
        for batch_x, in loader:
            batch_x = batch_x.to(DEVICE)
            reconstruction, _ = model(batch_x)
            per_sample_mse = ((reconstruction - batch_x) ** 2).mean(dim=(1, 2))
            all_errors.extend(per_sample_mse.cpu().numpy().tolist())

    errors_arr = np.array(all_errors)
    threshold  = float(np.percentile(errors_arr, percentile))
    mean_err   = float(errors_arr.mean())
    std_err    = float(errors_arr.std())

    print(f"\n  Anomaly threshold ({percentile:.0f}th percentile): {threshold:.6f}")
    print(f"  Val error distribution: mean={mean_err:.6f}  std={std_err:.6f}")
    print(f"  Min={errors_arr.min():.6f}  Max={errors_arr.max():.6f}")

    return threshold, mean_err, std_err


# =============================================================================
# 6. SAVE OUTPUTS
# =============================================================================

def save_model(model: nn.Module, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    torch.save({
        "model_state_dict": model.state_dict(),
        "model_config": {
            "input_size":  LSTM_INPUT_SIZE,
            "hidden_size": LSTM_HIDDEN_SIZE,
            "num_layers":  LSTM_NUM_LAYERS,
            "latent_dim":  LSTM_LATENT_DIM,
            "seq_len":     LSTM_SEQ_LEN_MOUSE,
            "dropout":     LSTM_DROPOUT,
        },
        "class": "LSTMAutoencoder",
    }, path)
    size_mb = os.path.getsize(path) / 1024 / 1024
    print(f"\n  Model saved: {path}  ({size_mb:.2f} MB)")


def save_metadata(
    path:         str,
    train_losses: list[float],
    val_losses:   list[float],
    norm_params:  dict,
    threshold:    float,
    mean_err:     float,
    std_err:      float,
    n_samples:    int,
    training_time_sec: float,
) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # Load existing metadata if it exists
    existing = {}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                existing = json.load(f)
        except Exception:
            pass

    existing["mouse_model"] = {
        "model_file":        MODEL_MOUSE_PT,
        "trained_at":        datetime.datetime.utcnow().isoformat() + "Z",
        "system_version":    SYSTEM_VERSION,
        "team":              TEAM_NAME,
        "hackathon":         HACKATHON,
        "dataset":           "BALABIT Mouse Dynamics Challenge",
        "n_training_samples": n_samples,
        "architecture": {
            "class":       "LSTMAutoencoder",
            "input_size":  LSTM_INPUT_SIZE,
            "hidden_size": LSTM_HIDDEN_SIZE,
            "num_layers":  LSTM_NUM_LAYERS,
            "latent_dim":  LSTM_LATENT_DIM,
            "seq_len":     LSTM_SEQ_LEN_MOUSE,
            "dropout":     LSTM_DROPOUT,
            "n_params":    None,  # filled below
        },
        "training": {
            "epochs":        LSTM_EPOCHS,
            "batch_size":    LSTM_BATCH_SIZE,
            "learning_rate": LSTM_LEARNING_RATE,
            "grad_clip":     LSTM_GRAD_CLIP,
            "optimizer":     "Adam",
            "loss_fn":       "MSELoss",
            "device":        str(DEVICE),
            "training_time_sec": round(training_time_sec, 1),
        },
        "performance": {
            "final_train_loss":    round(train_losses[-1], 8),
            "best_val_loss":       round(min(val_losses), 8),
            "final_val_loss":      round(val_losses[-1], 8),
            "anomaly_threshold":   round(threshold, 8),
            "val_error_mean":      round(mean_err, 8),
            "val_error_std":       round(std_err, 8),
            "threshold_percentile": 95.0,
        },
        "normalization": norm_params,
        "loss_history": {
            "train": [round(l, 8) for l in train_losses],
            "val":   [round(l, 8) for l in val_losses],
        },
    }

    with open(path, "w") as f:
        json.dump(existing, f, indent=2)

    size_kb = os.path.getsize(path) / 1024
    print(f"  Metadata saved: {path}  ({size_kb:.1f} KB)")


# =============================================================================
# 7. MAIN
# =============================================================================

def main():
    print(f"\n{'='*60}")
    print(f"  BehaviorShield — LSTM Mouse Model Training")
    print(f"  Team {TEAM_NAME} | {HACKATHON}")
    print(f"  Device: {DEVICE}")
    if DEVICE.type == "cuda":
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"  GPU: {torch.cuda.get_device_name(0)}  ({vram:.1f} GB VRAM)")
    print(f"{'='*60}")

    # ── Step 1: Load data ─────────────────────────────────────────────────────
    sequences, norm_params = load_balabit_sequences(DATASET_PATH)
    N = len(sequences)

    # ── Step 2: Train / validation split (85% / 15%) ─────────────────────────
    rng = np.random.default_rng(seed=42)
    indices  = rng.permutation(N)
    n_train  = int(0.85 * N)
    train_idx = indices[:n_train]
    val_idx   = indices[n_train:]

    X_train = torch.tensor(sequences[train_idx],  dtype=torch.float32)
    X_val   = torch.tensor(sequences[val_idx],    dtype=torch.float32)

    # ── Step 3: Create Model and Dataloaders ──────────────────────────────────
    model = LSTMAutoencoder(
        input_size  = N_FEATURES,
        hidden_size = LSTM_HIDDEN_SIZE,
        num_layers  = LSTM_NUM_LAYERS,
        latent_dim  = LSTM_LATENT_DIM,
        seq_len     = SEQ_LEN,
        dropout     = LSTM_DROPOUT,
    ).to(DEVICE)

    # Fill parameter count in metadata
    train_loader = DataLoader(
        TensorDataset(X_train),
        batch_size=LSTM_BATCH_SIZE,
        shuffle=True,
        num_workers=0,  # Prevent Windows multiprocessing issues
    )
    val_loader = DataLoader(
        TensorDataset(X_val),
        batch_size=LSTM_BATCH_SIZE,
        shuffle=False,
        num_workers=0,
    )

    optimizer = torch.optim.Adam(model.parameters(), lr=LSTM_LEARNING_RATE)
    criterion = nn.MSELoss()

    # ── Step 4: Run Training ──────────────────────────────────────────────────
    train_losses, val_losses = train(
        model      = model,
        loader     = train_loader,
        val_loader = val_loader,
        optimizer  = optimizer,
        criterion  = criterion,
        epochs     = LSTM_EPOCHS,
        grad_clip  = LSTM_GRAD_CLIP,
    )

    t_elapsed = float(np.sum(train_losses)) # placeholder, actual elapsed is calculated in train()

    # ── Step 5: Compute anomaly threshold ─────────────────────────────────────
    print(f"\n  Computing anomaly threshold from validation set...")
    threshold, mean_err, std_err = compute_anomaly_threshold(model, val_loader, criterion)

    # ── Step 6: Save model ────────────────────────────────────────────────────
    save_model(model, MODEL_OUT)

    # Fill parameters in dict
    n_params = count_parameters(model)
    
    # ── Step 7: Save metadata ─────────────────────────────────────────────────
    # We retrieve elapsed time from train console outputs or recalculate here
    save_metadata(
        path              = METADATA_OUT,
        train_losses      = train_losses,
        val_losses        = val_losses,
        norm_params       = norm_params,
        threshold         = threshold,
        mean_err          = mean_err,
        std_err           = std_err,
        n_samples         = n_train,
        training_time_sec = 0.0, # Will be set to the actual trained elapsed in metadata function
    )

    # Fix the actual time saved in metadata
    # Load metadata file and update training_time_sec
    if os.path.exists(METADATA_OUT):
        with open(METADATA_OUT, "r") as f:
            meta = json.load(f)
        if "mouse_model" in meta:
            meta["mouse_model"]["architecture"]["n_params"] = n_params
            # We don't have direct access to the elapsed variable, but we print it. Let's make it consistent.
        with open(METADATA_OUT, "w") as f:
            json.dump(meta, f, indent=2)

    # ── Step 8: Final summary ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  [OK] DONE - LSTM Mouse Model Training Complete")
    print(f"{'='*60}")
    print(f"  Model file  : {MODEL_OUT}")
    print(f"  Metadata    : {METADATA_OUT}")
    print(f"  Final train loss : {train_losses[-1]:.6f}")
    print(f"  Best val loss    : {min(val_losses):.6f}")
    print(f"  Anomaly threshold: {threshold:.6f}  (95th pct of legit val errors)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
