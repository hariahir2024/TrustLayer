#!/usr/bin/env python3
# =============================================================================
# BehaviorShield — scripts/train_lstm_keystroke.py
# Team SOLARIS | Cyber Security Hackathon 2026 | MNNIT Allahabad
# =============================================================================
# Trains an LSTM Autoencoder on the CMU Keystroke Dynamics Benchmark dataset.
#
# Architecture:
#   Input  : sequence of 11 timesteps × 2 features [hold_ms, flight_ms]
#   Encoder: LSTM(2→128, 2 layers) → Linear(128→16)  [latent bottleneck]
#   Decoder: Linear(16→128) → LSTM(128→128, 2 layers) → Linear(128→2)
#   Output : reconstructed sequence (same shape as input)
#
#   Anomaly score at inference = MSE(input, reconstruction)
#   High MSE → input sequence does not look like training data → suspicious
#
# Run from project root:
#   python scripts/train_lstm_keystroke.py
#
# Output:
#   models/lstm_keystroke_pretrained.pt   ← trained model weights
#   models/model_metadata.json            ← metrics, threshold, normalization params
# =============================================================================

import os
import sys
import json
import time
import datetime
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
    CMU_COLUMNS,
    LSTM_INPUT_SIZE,
    LSTM_HIDDEN_SIZE,
    LSTM_NUM_LAYERS,
    LSTM_LATENT_DIM,
    LSTM_SEQ_LEN_KEYSTROKE,
    LSTM_BATCH_SIZE,
    LSTM_EPOCHS,
    LSTM_LEARNING_RATE,
    LSTM_DROPOUT,
    LSTM_GRAD_CLIP,
    MODEL_KEYSTROKE_PT,
    MODEL_METADATA_JSON,
    MODEL_DIR,
    SYSTEM_VERSION,
    TEAM_NAME,
    HACKATHON,
)

# ── Device ────────────────────────────────────────────────────────────────────
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ── Resolved paths ────────────────────────────────────────────────────────────
DATASET_PATH  = os.path.join(PROJECT_ROOT, DATASET_PATHS["cmu_keystroke"])
MODEL_OUT     = os.path.join(PROJECT_ROOT, MODEL_KEYSTROKE_PT)
METADATA_OUT  = os.path.join(PROJECT_ROOT, MODEL_METADATA_JSON)
MODELS_DIR    = os.path.join(PROJECT_ROOT, MODEL_DIR)

# ── CMU column groups (confirmed from dataset inspection) ─────────────────────
# Password typed in CMU dataset: ".tie5Roanl" + Return (11 keys)
# H.*  = hold time (how long each key was pressed) — in SECONDS
# UD.* = flight time (key-up to next key-down gap) — in SECONDS
HOLD_COLS   = [
    "H.period", "H.t", "H.i", "H.e", "H.five",
    "H.Shift.r", "H.o", "H.a", "H.n", "H.l", "H.Return",
]  # 11 keys
FLIGHT_COLS = [
    "UD.period.t", "UD.t.i", "UD.i.e", "UD.e.five", "UD.five.Shift.r",
    "UD.Shift.r.o", "UD.o.a", "UD.a.n", "UD.n.l", "UD.l.Return",
]  # 10 flights (no flight after last key)

SEQ_LEN    = LSTM_SEQ_LEN_KEYSTROKE   # 11
N_FEATURES = LSTM_INPUT_SIZE           # 2


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

def load_cmu_sequences(path: str) -> tuple[np.ndarray, dict]:
    """
    Load CMU Keystroke dataset and build per-row sequences.

    Each row in CMU represents ONE complete password entry by ONE subject.
    We convert it to a sequence of shape (SEQ_LEN, 2):
        timestep i → [hold_i_ms, flight_i_ms]
    where flight at the last timestep is 0.0 (no next key).

    Negative flight times are KEPT — they indicate key overlap, which is a
    legitimate and discriminative human typing behavior. Clipping them to 0
    would destroy information.

    Returns:
        sequences  : np.ndarray shape (N, SEQ_LEN, 2)  dtype float32
        norm_params: dict with mean/std per channel for z-score normalization
    """
    print(f"\n{'='*60}")
    print(f"  Loading CMU Keystroke dataset...")
    print(f"  Path: {path}")

    df = pd.read_csv(path)
    print(f"  Rows: {len(df):,}  |  Subjects: {df['subject'].nunique()}  |  Columns: {df.shape[1]}")

    # Validate expected columns exist
    missing_hold   = [c for c in HOLD_COLS   if c not in df.columns]
    missing_flight = [c for c in FLIGHT_COLS if c not in df.columns]
    if missing_hold or missing_flight:
        raise ValueError(
            f"Missing columns — Hold: {missing_hold}, Flight: {missing_flight}\n"
            f"Available: {list(df.columns)}"
        )

    # Convert seconds → milliseconds
    holds_ms   = df[HOLD_COLS].values   * 1000.0   # shape (N, 11)
    flights_ms = df[FLIGHT_COLS].values * 1000.0   # shape (N, 10)

    # Remove rows with any NaN (corrupted entries)
    valid_mask = ~(np.isnan(holds_ms).any(axis=1) | np.isnan(flights_ms).any(axis=1))
    holds_ms   = holds_ms[valid_mask]
    flights_ms = flights_ms[valid_mask]
    n_dropped  = (~valid_mask).sum()
    if n_dropped:
        print(f"  Dropped {n_dropped:,} rows with NaN values.")

    N = len(holds_ms)
    print(f"  Valid samples: {N:,}")

    # Build sequence tensor: shape (N, SEQ_LEN=11, 2)
    # At each timestep i: [hold_i, flight_i]
    # Timestep 10 (last key H.Return): flight = 0.0
    sequences = np.zeros((N, SEQ_LEN, N_FEATURES), dtype=np.float32)
    for i in range(SEQ_LEN):
        sequences[:, i, 0] = holds_ms[:, i]               # hold at position i
        if i < len(FLIGHT_COLS):
            sequences[:, i, 1] = flights_ms[:, i]         # flight after position i
        # else: flight = 0.0 already (last key)

    print(f"\n  Sequence stats (ms):")
    print(f"    Hold   — mean: {holds_ms.mean():.1f}  std: {holds_ms.std():.1f}  "
          f"min: {holds_ms.min():.1f}  max: {holds_ms.max():.1f}")
    print(f"    Flight — mean: {flights_ms.mean():.1f}  std: {flights_ms.std():.1f}  "
          f"min: {flights_ms.min():.1f}  max: {flights_ms.max():.1f}")
    print(f"    Negative flights: {(flights_ms < 0).sum():,} "
          f"({100*(flights_ms < 0).mean():.1f}% — kept: valid overlap behavior)")

    # Z-score normalization per feature channel across all timesteps and samples
    # Fit on training data only → save params so inference can use same scale
    all_holds   = sequences[:, :, 0].flatten()
    all_flights = sequences[:, :, 1].flatten()

    hold_mean, hold_std     = float(all_holds.mean()),   max(float(all_holds.std()), 1e-6)
    flight_mean, flight_std = float(all_flights.mean()), max(float(all_flights.std()), 1e-6)

    sequences[:, :, 0] = (sequences[:, :, 0] - hold_mean)   / hold_std
    sequences[:, :, 1] = (sequences[:, :, 1] - flight_mean) / flight_std

    norm_params = {
        "hold_mean":   hold_mean,
        "hold_std":    hold_std,
        "flight_mean": flight_mean,
        "flight_std":  flight_std,
    }

    print(f"\n  Normalization (z-score):")
    print(f"    Hold:   mean={hold_mean:.2f}ms  std={hold_std:.2f}ms")
    print(f"    Flight: mean={flight_mean:.2f}ms  std={flight_std:.2f}ms")
    print(f"{'='*60}\n")

    return sequences, norm_params


# =============================================================================
# 3. LSTM AUTOENCODER MODEL
# =============================================================================

class LSTMAutoencoder(nn.Module):
    """
    Sequence-to-sequence LSTM Autoencoder for behavioral keystroke patterns.

    The encoder compresses a typing sequence into a 16-dim latent vector.
    The decoder reconstructs the full sequence from the latent vector.
    Anomaly score = MSE(original_sequence, reconstructed_sequence).

    A legitimate user's sequences are reconstructed accurately (low MSE).
    A different person's sequences are reconstructed poorly (high MSE).

    Args:
        input_size  : features per timestep (2: hold + flight)
        hidden_size : LSTM hidden units (128)
        num_layers  : LSTM depth (2)
        latent_dim  : bottleneck dimension (16)
        seq_len     : sequence length (11 for CMU)
        dropout     : dropout between layers (0.1)
    """

    def __init__(
        self,
        input_size:  int = LSTM_INPUT_SIZE,
        hidden_size: int = LSTM_HIDDEN_SIZE,
        num_layers:  int = LSTM_NUM_LAYERS,
        latent_dim:  int = LSTM_LATENT_DIM,
        seq_len:     int = LSTM_SEQ_LEN_KEYSTROKE,
        dropout:     float = LSTM_DROPOUT,
    ):
        super().__init__()
        self.seq_len     = seq_len
        self.hidden_size = hidden_size
        self.num_layers  = num_layers
        self.latent_dim  = latent_dim

        # ── Encoder ───────────────────────────────────────────────────────────
        # Processes the input sequence and compresses to a latent vector.
        # We take the hidden state at the FINAL timestep of the last layer.
        self.encoder_lstm = nn.LSTM(
            input_size  = input_size,
            hidden_size = hidden_size,
            num_layers  = num_layers,
            batch_first = True,
            dropout     = dropout if num_layers > 1 else 0.0,
        )
        self.encoder_proj = nn.Linear(hidden_size, latent_dim)  # compress

        # ── Decoder ───────────────────────────────────────────────────────────
        # Expands the latent vector back to a full sequence.
        # Strategy: project latent → repeat seq_len times → feed to LSTM
        self.decoder_proj = nn.Linear(latent_dim, hidden_size)  # expand
        self.decoder_lstm = nn.LSTM(
            input_size  = hidden_size,
            hidden_size = hidden_size,
            num_layers  = num_layers,
            batch_first = True,
            dropout     = dropout if num_layers > 1 else 0.0,
        )
        self.decoder_out  = nn.Linear(hidden_size, input_size)  # reconstruct features

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        """
        Encode input sequence to latent vector.
        x: (batch, seq_len, input_size)
        returns: (batch, latent_dim)
        """
        _, (hidden, _) = self.encoder_lstm(x)
        # hidden: (num_layers, batch, hidden_size) — take final layer
        latent = self.encoder_proj(hidden[-1])   # (batch, latent_dim)
        return latent

    def decode(self, latent: torch.Tensor) -> torch.Tensor:
        """
        Decode latent vector back to sequence.
        latent: (batch, latent_dim)
        returns: (batch, seq_len, input_size)
        """
        # Expand latent → repeat across time dimension
        expanded = self.decoder_proj(latent)                      # (batch, hidden_size)
        decoder_input = expanded.unsqueeze(1).expand(
            -1, self.seq_len, -1
        )                                                          # (batch, seq_len, hidden_size)

        output, _ = self.decoder_lstm(decoder_input)              # (batch, seq_len, hidden_size)
        reconstruction = self.decoder_out(output)                  # (batch, seq_len, input_size)
        return reconstruction

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Full forward pass.
        Returns: (reconstruction, latent)
        """
        latent = self.encode(x)
        reconstruction = self.decode(latent)
        return reconstruction, latent


def count_parameters(model: nn.Module) -> int:
    """Return total number of trainable parameters."""
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
    """
    Train the LSTM Autoencoder.

    Each forward pass reconstructs the input sequence. Loss = MSE between
    original and reconstructed sequence. No labels needed — unsupervised.

    Returns:
        train_losses : list of per-epoch mean train loss
        val_losses   : list of per-epoch mean validation loss
    """
    train_losses, val_losses = [], []
    best_val_loss = float("inf")
    best_state    = None

    print(f"\n{'='*60}")
    print(f"  Training LSTM Autoencoder on {DEVICE}")
    print(f"  Epochs={epochs}  BatchSize={LSTM_BATCH_SIZE}  LR={LSTM_LEARNING_RATE}")
    print(f"  Grad clip={grad_clip}  Dropout={LSTM_DROPOUT}")
    print(f"{'='*60}\n")

    total_start = time.time()

    for epoch in range(1, epochs + 1):
        # ── Train ────────────────────────────────────────────────────────────
        model.train()
        epoch_train_loss = 0.0
        n_batches = 0

        for batch_x, in loader:
            batch_x = batch_x.to(DEVICE)

            optimizer.zero_grad()
            reconstruction, _ = model(batch_x)
            loss = criterion(reconstruction, batch_x)
            loss.backward()

            # Gradient clipping — prevents exploding gradients in deep LSTMs
            nn.utils.clip_grad_norm_(model.parameters(), grad_clip)

            optimizer.step()

            epoch_train_loss += loss.item()
            n_batches        += 1

        mean_train_loss = epoch_train_loss / n_batches

        # ── Validate ─────────────────────────────────────────────────────────
        model.eval()
        epoch_val_loss = 0.0
        n_val_batches  = 0

        with torch.no_grad():
            for batch_x, in val_loader:
                batch_x = batch_x.to(DEVICE)
                reconstruction, _ = model(batch_x)
                val_loss = criterion(reconstruction, batch_x)
                epoch_val_loss += val_loss.item()
                n_val_batches  += 1

        mean_val_loss = epoch_val_loss / n_val_batches

        train_losses.append(mean_train_loss)
        val_losses.append(mean_val_loss)

        # Save best model (early-stopping checkpoint)
        if mean_val_loss < best_val_loss:
            best_val_loss = mean_val_loss
            best_state    = {k: v.cpu().clone() for k, v in model.state_dict().items()}

        # ── Progress bar ──────────────────────────────────────────────────────
        bar = _progress_bar(epoch, epochs)
        elapsed = time.time() - total_start
        eta_sec = (elapsed / epoch) * (epochs - epoch)
        eta_str = f"{int(eta_sec // 60):02d}:{int(eta_sec % 60):02d}"

        status = (
            f"  Epoch {epoch:3d}/{epochs} {bar}  "
            f"Train: {mean_train_loss:.6f}  "
            f"Val: {mean_val_loss:.6f}  "
            f"ETA: {eta_str}"
        )

        if epoch < epochs:
            print(status, end="\r", flush=True)
        else:
            print(status)   # final line — keep it

        # Milestone prints every 10 epochs (don't get overwritten)
        if epoch % 10 == 0:
            print(f"  ── Epoch {epoch:3d}: train={mean_train_loss:.6f}  val={mean_val_loss:.6f}  "
                  f"best_val={best_val_loss:.6f}")

    total_time = time.time() - total_start
    print(f"\n  Training complete in {total_time:.1f}s")
    print(f"  Best validation loss: {best_val_loss:.6f}")

    # Restore best weights before returning
    if best_state is not None:
        model.load_state_dict(best_state)
        print(f"  Best weights restored.")

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
    """
    Compute the anomaly detection threshold from reconstruction errors on
    the validation set (legitimate sessions only).

    Strategy: 95th percentile of reconstruction error on legitimate data.
    Any score above this → flag as anomaly.

    Returns: (threshold, mean_error, std_error)
    """
    model.eval()
    all_errors = []

    with torch.no_grad():
        for batch_x, in loader:
            batch_x = batch_x.to(DEVICE)
            reconstruction, _ = model(batch_x)
            # Per-sample MSE (not batch mean)
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
    """Save model weights, architecture config, and class name."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    torch.save({
        "model_state_dict": model.state_dict(),
        "model_config": {
            "input_size":  LSTM_INPUT_SIZE,
            "hidden_size": LSTM_HIDDEN_SIZE,
            "num_layers":  LSTM_NUM_LAYERS,
            "latent_dim":  LSTM_LATENT_DIM,
            "seq_len":     LSTM_SEQ_LEN_KEYSTROKE,
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
    """
    Save training metrics and normalization params to model_metadata.json.

    This file is the single source of truth for:
    - When the model was trained and on what data
    - Normalization parameters (needed at inference time)
    - Anomaly threshold (used by ml_engine.py to score sessions)
    - Training loss history (for plotting and auditing)
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # Load existing metadata if it exists (avoid overwriting mouse model data)
    existing = {}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                existing = json.load(f)
        except Exception:
            pass

    existing["keystroke_model"] = {
        "model_file":        MODEL_KEYSTROKE_PT,
        "trained_at":        datetime.datetime.utcnow().isoformat() + "Z",
        "system_version":    SYSTEM_VERSION,
        "team":              TEAM_NAME,
        "hackathon":         HACKATHON,
        "dataset":           "CMU Keystroke Dynamics Benchmark (DSN-2009)",
        "dataset_url":       "https://www.cs.cmu.edu/~keystroke/",
        "n_training_samples": n_samples,
        "architecture": {
            "class":       "LSTMAutoencoder",
            "input_size":  LSTM_INPUT_SIZE,
            "hidden_size": LSTM_HIDDEN_SIZE,
            "num_layers":  LSTM_NUM_LAYERS,
            "latent_dim":  LSTM_LATENT_DIM,
            "seq_len":     LSTM_SEQ_LEN_KEYSTROKE,
            "dropout":     LSTM_DROPOUT,
            "n_params":    None,   # filled below
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
    print(f"  BehaviorShield — LSTM Keystroke Model Training")
    print(f"  Team {TEAM_NAME} | {HACKATHON}")
    print(f"  Device: {DEVICE}")
    if DEVICE.type == "cuda":
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"  GPU: {torch.cuda.get_device_name(0)}  ({vram:.1f} GB VRAM)")
    print(f"{'='*60}")

    # ── Step 1: Load data ─────────────────────────────────────────────────────
    sequences, norm_params = load_cmu_sequences(DATASET_PATH)
    N = len(sequences)

    # ── Step 2: Train / validation split (85% / 15%) ─────────────────────────
    # We shuffle before splitting to ensure all subjects appear in both sets
    rng = np.random.default_rng(seed=42)
    indices  = rng.permutation(N)
    n_train  = int(0.85 * N)
    train_idx = indices[:n_train]
    val_idx   = indices[n_train:]

    X_train = torch.tensor(sequences[train_idx],  dtype=torch.float32)
    X_val   = torch.tensor(sequences[val_idx],    dtype=torch.float32)

    print(f"  Train set: {len(X_train):,} sequences")
    print(f"  Val   set: {len(X_val):,} sequences")

    train_dataset = TensorDataset(X_train)
    val_dataset   = TensorDataset(X_val)

    train_loader = DataLoader(
        train_dataset,
        batch_size = LSTM_BATCH_SIZE,
        shuffle    = True,
        pin_memory = (DEVICE.type == "cuda"),
        num_workers= 0,     # 0 = safer on Windows (avoids multiprocessing issues)
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size = LSTM_BATCH_SIZE,
        shuffle    = False,
        pin_memory = (DEVICE.type == "cuda"),
        num_workers= 0,
    )

    # ── Step 3: Build model ───────────────────────────────────────────────────
    model = LSTMAutoencoder(
        input_size  = LSTM_INPUT_SIZE,
        hidden_size = LSTM_HIDDEN_SIZE,
        num_layers  = LSTM_NUM_LAYERS,
        latent_dim  = LSTM_LATENT_DIM,
        seq_len     = LSTM_SEQ_LEN_KEYSTROKE,
        dropout     = LSTM_DROPOUT,
    ).to(DEVICE)

    n_params = count_parameters(model)
    print(f"\n  Model parameters: {n_params:,}")
    print(f"  Architecture summary:")
    print(f"    Encoder: LSTM({LSTM_INPUT_SIZE}->{LSTM_HIDDEN_SIZE}, layers={LSTM_NUM_LAYERS}) -> Linear({LSTM_HIDDEN_SIZE}->{LSTM_LATENT_DIM})")
    print(f"    Decoder: Linear({LSTM_LATENT_DIM}->{LSTM_HIDDEN_SIZE}) -> LSTM({LSTM_HIDDEN_SIZE}->{LSTM_HIDDEN_SIZE}, layers={LSTM_NUM_LAYERS}) -> Linear({LSTM_HIDDEN_SIZE}->{LSTM_INPUT_SIZE})")

    # ── Step 4: Optimizer + loss ──────────────────────────────────────────────
    optimizer = torch.optim.Adam(model.parameters(), lr=LSTM_LEARNING_RATE)
    criterion = nn.MSELoss()

    # Optional: cosine annealing LR scheduler for smoother convergence
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=LSTM_EPOCHS, eta_min=1e-5
    )

    # ── Step 5: Train ─────────────────────────────────────────────────────────
    t_start = time.time()

    train_losses, val_losses = [], []
    best_val_loss = float("inf")
    best_state    = None

    print(f"\n{'='*60}")
    print(f"  Training LSTM Autoencoder on {DEVICE}")
    print(f"  Epochs={LSTM_EPOCHS}  BatchSize={LSTM_BATCH_SIZE}  LR={LSTM_LEARNING_RATE}")
    print(f"  Grad clip={LSTM_GRAD_CLIP}  Dropout={LSTM_DROPOUT}")
    print(f"{'='*60}\n")

    for epoch in range(1, LSTM_EPOCHS + 1):
        # Train pass
        model.train()
        epoch_train_loss, n_batches = 0.0, 0
        for batch_x, in train_loader:
            batch_x = batch_x.to(DEVICE)
            optimizer.zero_grad()
            reconstruction, _ = model(batch_x)
            loss = criterion(reconstruction, batch_x)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), LSTM_GRAD_CLIP)
            optimizer.step()
            epoch_train_loss += loss.item()
            n_batches        += 1

        scheduler.step()
        mean_train = epoch_train_loss / n_batches

        # Validation pass
        model.eval()
        epoch_val_loss, n_val = 0.0, 0
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
        eta_sec  = (elapsed / epoch) * (LSTM_EPOCHS - epoch) if epoch < LSTM_EPOCHS else 0
        bar      = _progress_bar(epoch, LSTM_EPOCHS)
        eta_str  = f"{int(eta_sec//60):02d}:{int(eta_sec%60):02d}"
        lr_now   = scheduler.get_last_lr()[0]

        line = (
            f"  Epoch {epoch:3d}/{LSTM_EPOCHS} {bar}  "
            f"Train={mean_train:.6f}  Val={mean_val:.6f}  "
            f"LR={lr_now:.2e}  ETA={eta_str}"
        )

        if epoch % 10 == 0 or epoch == LSTM_EPOCHS:
            print(line)    # milestone — always shown, not overwritten
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

    # ── Step 6: Compute anomaly threshold ─────────────────────────────────────
    print(f"\n  Computing anomaly threshold from validation set...")
    threshold, mean_err, std_err = compute_anomaly_threshold(model, val_loader, criterion)

    # ── Step 7: Save model ────────────────────────────────────────────────────
    save_model(model, MODEL_OUT)

    # ── Step 8: Save metadata ─────────────────────────────────────────────────
    save_metadata(
        path              = METADATA_OUT,
        train_losses      = train_losses,
        val_losses        = val_losses,
        norm_params       = norm_params,
        threshold         = threshold,
        mean_err          = mean_err,
        std_err           = std_err,
        n_samples         = n_train,
        training_time_sec = t_elapsed,
    )

    # ── Step 9: Final summary ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  [OK] DONE - LSTM Keystroke Model Training Complete")
    print(f"{'='*60}")
    print(f"  Model file  : {MODEL_OUT}")
    print(f"  Metadata    : {METADATA_OUT}")
    print(f"  Final train loss : {train_losses[-1]:.6f}")
    print(f"  Best val loss    : {best_val_loss:.6f}")
    print(f"  Anomaly threshold: {threshold:.6f}  (95th pct of legit val errors)")
    print(f"  Training time    : {t_elapsed:.1f}s")
    print(f"\n  Next step: run  python scripts/train_lstm_mouse.py")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
