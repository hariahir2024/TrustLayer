# TrustLayer — Continuous AI Behavioral Biometric Authentication

**Team SOLARIS | CBI Hackathon 2026 Phase II | MNNIT Allahabad**

> *TrustLayer adds a continuous behavioral trust verification layer to Indian Public Sector Bank NetBanking portals — silently monitoring who is typing, not just what they type.*

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Key Features](#3-key-features)
4. [Repository Structure](#4-repository-structure)
5. [Environment Requirements](#5-environment-requirements)
6. [Installation & Configuration](#6-installation--configuration)
7. [Build Instructions](#7-build-instructions)
8. [Running the Application](#8-running-the-application)
9. [Deployment Guide](#9-deployment-guide)
10. [Usage & Demo Walkthrough](#10-usage--demo-walkthrough)
11. [Test Credentials](#11-test-credentials)
12. [Model Retraining](#12-model-retraining)
13. [API Reference](#13-api-reference)
14. [AI & Generative AI Disclosure](#14-ai--generative-ai-disclosure)
15. [Third-Party Acknowledgments](#15-third-party-acknowledgments)
16. [Troubleshooting](#16-troubleshooting)
17. [License](#17-license)

---

## 1. Project Overview

Indian Public Sector Banks face an unprecedented surge in Account Takeover (ATO) fraud. RBI data reports **₹29,082 crore** in banking fraud for FY2023-24, with 47% YoY growth in digital channel attacks. The fundamental gap: authentication is **point-in-time** (login + OTP), while fraud happens **mid-session**.

**TrustLayer** solves this by establishing **Continuous Behavioral Authentication**. A lightweight JavaScript SDK (`sdk.js`) silently records keystroke timing patterns and mouse trajectories during natural banking activity. A three-model ML pipeline evaluates these signals in real time and dynamically adjusts the session risk score on a 0–100 scale, triggering proportional responses from silent monitoring to full session freeze.

**No extra steps for legitimate users. No OTP dependency. No server-side credential storage of biometrics.**

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────┐
│              BROWSER (User Device)                  │
│                                                     │
│  ┌─────────────┐    ┌──────────────────────────┐   │
│  │  bank.html  │    │       sdk.js              │   │
│  │  (BSB Portal│───▶│  Biometric Telemetry SDK  │   │
│  │   + UPI)    │    │  • Keystroke timing        │   │
│  └─────────────┘    │  • Mouse trajectory        │   │
│                     │  • Touch events            │   │
│  ┌──────────────┐   │  • Device fingerprint      │   │
│  │dashboard.html│   └────────────┬───────────────┘   │
│  │  (SOC Panel) │                │ REST + WebSocket   │
│  └──────────────┘                │                   │
└─────────────────────────────────┼───────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────┐
│                  FastAPI Backend (app.py)             │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │               ML Engine (ml_engine.py)         │  │
│  │                                                │  │
│  │  ┌──────────────┐  ┌──────────────┐           │  │
│  │  │ LSTM          │  │ LSTM          │           │  │
│  │  │ Autoencoder   │  │ Autoencoder   │           │  │
│  │  │ (Keystroke)   │  │ (Mouse)       │           │  │
│  │  │ CMU-trained   │  │ Balabit-trained│          │  │
│  │  └──────┬───────┘  └──────┬────────┘          │  │
│  │         │                 │                    │  │
│  │         ▼                 ▼                    │  │
│  │  ┌─────────────────────────────────────────┐  │  │
│  │  │        XGBoost Fusion Classifier        │  │  │
│  │  │      (CMU + Balabit Inter-Subject)      │  │  │
│  │  │  Acc: 83.68% | Recall: 77.37%          │  │  │
│  │  └──────────────────┬──────────────────────┘  │  │
│  └─────────────────────┼──────────────────────────┘  │
│                        │                             │
│  ┌─────────────────────▼──────────────────────────┐  │
│  │         7-Band Risk Score (0–100)              │  │
│  │  GREEN → AMBER_LOW → AMBER_MID → AMBER_HIGH    │  │
│  │  → RED_LOW → RED_HIGH → RED_CRITICAL           │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │           SQLite Database (db_sqlite.py)     │    │
│  │  • Behavioral profiles  • Session audit log  │    │
│  │  • Keystroke baselines  • Event timeline     │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

---

## 3. Key Features

| Feature | Description |
|---------|-------------|
| **Silent SDK** | `sdk.js` captures 28 behavioral features invisibly — zero added UI friction |
| **3-Model Pipeline** | LSTM Keystroke + LSTM Mouse + XGBoost Fusion for layered accuracy |
| **7-Band Risk System** | Proportional response — gradual escalation instead of binary block/allow |
| **Bot Heuristics** | Pre-ML detection: WebDriver flag, 0ms dwell, straight-line cursor → instant RED_CRITICAL |
| **Explainable AI** | SHAP-lite feature breakdown in SOC dashboard with plain-English descriptions |
| **Real-Time SOC Dashboard** | WebSocket-powered analyst console with session deep-dive, timeline, and audit trail |
| **UPI & Fund Transfer Gating** | All high-value transactions risk-validated before execution |
| **Step-Up Re-Auth** | AMBER band triggers behavioral re-verification challenge instead of SMS OTP |
| **Admin Overrides** | Force Freeze, False Positive dismissal, Database Audit search |
| **Enrollment Baseline** | 5-sample passphrase typing enrollment builds personal keystroke profile |
| **Profile Confidence** | Cold-start transparency — shows session count (0–15) toward full personalization |

---

## 4. Repository Structure

```
TrustLayer/
│
├── app.py                    ← FastAPI backend — 48 REST & WebSocket endpoints
├── ml_engine.py              ← ML pipeline: LSTM autoencoders + XGBoost fusion
├── db_sqlite.py              ← SQLite database layer — all CRUD operations
├── constants.py              ← Feature weights, thresholds, risk band definitions
├── requirements.txt          ← Python package dependencies (pip-installable)
├── README.md                 ← This file
├── LICENSE                   ← MIT License
├── THIRD_PARTY_ACKNOWLEDGMENTS.md  ← Dataset & library credits
│
├── models/                   ← Pre-trained ML model files (included in repo)
│   ├── lstm_keystroke_pretrained.pt    ← LSTM Autoencoder (CMU DSN-2009 trained)
│   ├── lstm_mouse_pretrained.pt        ← LSTM Autoencoder (Balabit Challenge trained)
│   ├── xgboost_fusion.pkl             ← XGBoost fusion classifier (KMT trained)
│   └── model_metadata.json            ← Live model performance metrics
│
├── scripts/                  ← Utility & retraining scripts
│   ├── retrain_xgb_with_kmt.py        ← Retrain XGBoost on KMT behavioral dataset
│   ├── train_lstm_keystroke.py         ← Train keystroke LSTM autoencoder
│   ├── train_lstm_mouse.py             ← Train mouse LSTM autoencoder
│   ├── seed_demo_data.py              ← Seed database with demo personas
│   └── verify_integration.py          ← End-to-end integration test suite
│
└── static/                   ← Frontend assets (served by FastAPI)
    ├── index.html            ← Project landing page
    ├── bank.html             ← Bharat Suraksha Bank NetBanking simulator
    ├── dashboard.html        ← TrustLayer Security Operations Center (SOC)
    ├── manifest.json         ← PWA manifest
    ├── sw.js                 ← Service worker for PWA support
    ├── css/
    │   └── style.css         ← Global design system & component styles
    └── js/
        ├── sdk.js            ← Biometric telemetry SDK (attaches to any input)
        ├── bank.js           ← Bank portal — auth flow, transactions, UPI, enrollment
        └── dashboard.js      ← SOC dashboard — WebSocket feed, charts, overrides
```

---

## 5. Environment Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| **Operating System** | Windows 10, macOS 12, Ubuntu 20.04 | Windows 11 / Ubuntu 22.04 |
| **Python** | 3.9 | **3.11** (tested & recommended) |
| **RAM** | 4 GB | 8 GB |
| **Disk Space** | 500 MB (excl. datasets) | 1 GB |
| **Browser** | Chrome 90+, Firefox 88+, Edge 90+ | Chrome 120+ |
| **GPU** | Not required | Optional — CUDA 12.1 for faster LSTM retraining |
| **Internet** | Not required at runtime | Required only for CDN assets in dashboard |

> ⚠️ **Python 3.12+ is NOT supported.** XGBoost and PyTorch wheels for 3.12 may cause pickle/model loading errors. Use Python 3.11.

---

## 6. Installation & Configuration

### Step 1: Clone / Extract the Repository

```bash
# If cloning from GitHub (share CBIHack26 account first):
git clone https://github.com/<your-org>/trustlayer.git
cd trustlayer

# Or extract the submitted ZIP:
# Unzip TrustLayer_SourceCode/ and navigate into it
```

### Step 2: Create a Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

> You should see `(venv)` prefixed in your terminal prompt.

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This installs: FastAPI, Uvicorn, scikit-learn, XGBoost, PyTorch (CPU build), NumPy, Pandas, Joblib, and WebSockets.

### Step 4: Configuration (Optional)

The application runs with **zero required configuration** — all defaults are production-ready for local evaluation.

To change the port or database path, edit the bottom of `app.py`:

```python
# app.py — last few lines
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=False)
```

| Config | Default | How to Change |
|--------|---------|--------------|
| **Port** | `8080` | Edit `port=8080` in `app.py` |
| **Database file** | `TRUSTLAYER.db` (auto-created) | Edit `DB_PATH` in `db_sqlite.py` line 1 |
| **Risk thresholds** | See `constants.py` | Edit `GREEN_MAX`, `AMBER_*` variables |
| **Scoring interval** | 30s (Green), 10s (Amber) | Edit `DEFAULT_SCORING_INTERVAL_SEC` in `constants.py` |
| **Enrollment samples** | 5 | Edit `ENROLLMENT_REQUIRED_SAMPLES` in `constants.py` |

---

## 7. Build Instructions

**No build step is required.** The frontend is pure HTML/CSS/JavaScript — no bundler, no compiler. The backend is Python — no compilation needed.

**Optional — Seed demo users into a fresh database:**

```bash
python scripts/seed_demo_data.py
```

This pre-populates `demo_owner` and two intruder personas with enrolled behavioral profiles, so the demo can begin immediately without manual enrollment.

---

## 8. Running the Application

```bash
# Ensure your virtual environment is active
python app.py
```

Expected terminal output:
```
INFO:     TrustLayer ML Engine initialising...
INFO:     Loaded CMU keystroke baseline (51 users)
INFO:     Loaded Balabit mouse model (10 users)
INFO:     Loaded KMT XGBoost fusion model
INFO:     Uvicorn running on http://0.0.0.0:8080
```

Open your browser and navigate to:

| URL | Page |
|-----|------|
| `http://localhost:8080/` | Landing page — project overview |
| `http://localhost:8080/bank` | Bharat Suraksha Bank NetBanking portal |
| `http://localhost:8080/dashboard` | TrustLayer SOC Analyst Dashboard |

---

## 9. Deployment Guide

### Local (Default)
Follow Section 8 above. The application serves itself via FastAPI's built-in static file server.

### LAN / Intranet (Evaluator Demo)
To make the app accessible to other devices on the same network:

```bash
python app.py
# Already binds to 0.0.0.0 — accessible via your machine's IP
# e.g. http://192.168.1.X:8080/
```

### Production / Cloud Deployment
For production-grade deployment (e.g., on an EC2 instance or VPS):

```bash
# Step 1: Install production WSGI server
pip install gunicorn

# Step 2: Run with multiple workers behind a reverse proxy (Nginx recommended)
gunicorn app:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8080

# Step 3: Point Nginx to localhost:8080 and enable HTTPS via Let's Encrypt
```

> **Database**: For production scale, replace SQLite with PostgreSQL by updating `db_sqlite.py` to use `asyncpg`. The rest of the application requires no changes.

> **Environment Variables**: In production, move secrets (e.g., `SECRET_KEY` for session signing) to environment variables rather than hardcoding.

---

## 10. Usage & Demo Walkthrough

Open the **Bank Portal** and **SOC Dashboard** side-by-side in your browser.

### Phase 1 — Enroll a User (First-Time Setup)

1. Go to `http://localhost:8080/bank`
2. Click **Register Here** → fill in details → click **Register**
3. Note your generated **passphrase** (displayed on screen)
4. Click **Proceed** → enter username + password → **Continue**
5. In the **Enrollment Wizard**, type the passphrase naturally **5 times**
6. Trace the **zigzag calibration path** with your mouse
7. Click **Complete Enrollment** — your behavioral baseline is saved

> **Quick demo path**: Use the pre-seeded `demo_owner` account (see Section 11) and click ⚡ **Quick-Fill** in the Demo Controller (bottom-right panel) for instant enrollment.

### Phase 2 — Simulate Threat Personas

Using the **Demo Controller** panel (bottom-right of the bank portal):

| Persona | What Happens | Expected SOC Response |
|---------|-------------|----------------------|
| **Legitimate Owner** | Natural typing cadence matching enrolled baseline | GREEN band (score 0–30), session proceeds |
| **Human Intruder** | Slower/different typing rhythm | AMBER band → Step-up re-auth modal |
| **Automated Bot** | 0ms keystroke dwell, straight cursor | RED_CRITICAL (score 97) → Instant session freeze |

### Phase 3 — SOC Analyst Actions

In `http://localhost:8080/dashboard`:

- **Click a session card** → opens deep-dive workspace with keystroke waveform, mouse trajectory, and SHAP-lite feature breakdown
- **Force Freeze** → manually locks a suspicious session (score → 99)
- **Dismiss / Unfreeze** → marks as false positive, restores access (score → 15)
- **Database Audit tab** → search historical sessions by username, time range, or risk severity
- **Frozen Sessions tab** → grid view of all manually or automatically frozen sessions

---

## 11. Test Credentials

Use these pre-seeded accounts for immediate demonstration without manual registration:

| Role | Username | Password | Notes |
|------|----------|----------|-------|
| **Primary Demo User** | `demo_owner` | `HariAhir@26` | Enrolled — has behavioral baseline |
| **Evaluator Account** | `test_owner` | `TestOwner@26` | Clean account for fresh enrollment |

> The Demo Controller panel (bottom-right) provides **⚡ Quick-Fill** buttons to auto-populate credentials and simulate each persona's typing rhythm.

---

## 12. Model Retraining

All three models can be retrained from scratch using the included scripts.

### Retrain XGBoost Fusion Classifier (Primary — KMT Dataset)

```bash
python scripts/retrain_xgb_with_kmt.py
```

**Current trained model performance** (Inter-Subject GroupKFold Validation on 100% Real Biometrics):

| Metric | Value |
|--------|-------|
| Accuracy | **83.68%** |
| Recall (Intruder Detection) | **77.37%** |
| Precision | 88.54% |
| F1 Score | 82.58% |
| Training Data | 1,275 legitimate + 1,275 impostor real samples (0% synthetic data) |

### Retrain Keystroke LSTM Autoencoder (CMU Dataset)

```bash
python scripts/train_lstm_keystroke.py
```

### Dataset Download Instructions

> ⚠️ **Important — Running the app does NOT require any datasets.**
> Pre-trained models (`models/*.pt`, `models/*.pkl`) are included in the repository.
> Datasets are only needed if you wish to **retrain** the models from scratch.
>
> At startup, the app checks for datasets and logs warnings if not found:
> - `WARNING: CMU dataset not found — Using hardcoded fallback` → app still works ✅
> - `WARNING: BALABIT dataset not found — Using untrained generic mouse model` → app still works ✅

#### Included in this repository (no download needed):

| File | Size | Used by |
|------|------|---------|
| `datasets/cmu_keystroke_benchmark.csv` | 4.45 MB | `train_lstm_keystroke.py` |
| `datasets/SAMPLE_DATA/INB_REQ_LOG.csv` | 318 KB | `scripts/analyze_inb_logs.py` |
| `datasets/SAMPLE_DATA/TXN_HISTORY_UPI_FIN.xlsx` | 63 KB | `scripts/analyze_upi_txn.py` |

#### Must download separately (too large for submission ZIP):

**Balabit Mouse Dynamics Dataset** (195 MB)
```
Download: https://github.com/balabit/Mouse-Dynamics-Challenge
License:  CC BY 4.0
Place at:  datasets/balabit/
           ├── training_files/
           └── test_files/
```

**KMT Behavioral Biometrics Dataset** (~120 MB)
```
Download: https://www.kaggle.com/datasets/
          (search: KMT behavioral biometrics dataset)
License:  CC BY-NC-SA 4.0
Place at:  datasets/behaviour_biometrics_dataset/raw_kmt_dataset/
           raw_kmt_user_0001.json ... raw_kmt_user_0088.json
```

### Run Integration Tests

```bash
python verify_integration.py
```

Launches a background test server on port 8089, simulates all three personas, and verifies scoring correctness.

---

## 13. API Reference

The backend exposes **48 REST and WebSocket endpoints**. Key endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/register` | Create new user account |
| `POST` | `/api/login` | Authenticate and create session |
| `POST` | `/api/enroll` | Submit one keystroke enrollment sample |
| `POST` | `/api/score` | Submit telemetry — returns risk score + band |
| `POST` | `/api/action` | Log a user action event to session audit |
| `POST` | `/api/transfer` | Execute fund transfer (risk-gated) |
| `POST` | `/api/upi` | Execute UPI transfer (risk-gated) |
| `GET` | `/api/session/{id}` | Get current session state |
| `GET` | `/api/dashboard/sessions` | List all active sessions |
| `GET` | `/api/dashboard/session/{id}/logs` | Full audit log for a session |
| `GET` | `/api/dashboard/sessions/frozen` | All frozen sessions |
| `GET` | `/api/dashboard/sessions/search` | Search by username/time/severity |
| `GET` | `/api/admin/model-metadata` | Live XGBoost feature importances |
| `POST` | `/api/admin/freeze/{id}` | Manually freeze a session |
| `POST` | `/api/admin/false-positive/{id}` | Dismiss alert, restore session |
| `WS` | `/ws/dashboard` | Real-time WebSocket event stream |

Full API schema available at `http://localhost:8080/docs` (FastAPI auto-generated Swagger UI).

---

## 14. AI & Generative AI Disclosure

As required by the CBI Hackathon 2026 Phase II guidelines, we disclose all AI and Generative AI usage in this project:

### Machine Learning Models Used

| Model | Framework | Role |
|-------|-----------|------|
| **LSTM Autoencoder** (Keystroke) | PyTorch 2.5 | Reconstruction-error anomaly detection on 10-keystroke sequences |
| **LSTM Autoencoder** (Mouse) | PyTorch 2.5 | Anomaly detection on 50-point mouse trajectory windows |
| **XGBoost Classifier** | XGBoost 3.2 | Fusion of keystroke score, mouse score, metadata score into final risk score |
| **Isolation Forest** | scikit-learn 1.9 | Fallback mouse anomaly scorer for cold-start sessions |
| **Z-Score Engine** | NumPy | Statistical comparison of keystroke features against enrolled baseline |

### Generative AI Usage

- **Antigravity (Google DeepMind)**: Used as an AI pair-programming assistant during development for code suggestions, debugging, and documentation drafting. All generated code was reviewed, tested, and validated by the team.
- **No LLM is used at runtime** — the deployed system uses only the deterministic ML models listed above.

---

## 15. Third-Party Acknowledgments

This project uses the following open datasets and open-source libraries. Full details in `THIRD_PARTY_ACKNOWLEDGMENTS.md`.

### Datasets

| Dataset | Source | Usage |
|---------|--------|-------|
| **CMU Keystroke Dynamics Benchmark** | Carnegie Mellon University (DSN-2009) | Training keystroke LSTM baseline — 51 users, 17,340 sequences |
| **Balabit Mouse Dynamics Challenge** | Balabit Ltd. | Training mouse LSTM baseline — 10 users, 76,543 sessions |
| **KMT Biometric Dataset** | Kaggle / KMT Research | Training XGBoost fusion — 88 users, 1,760 real sessions |

### Key Open-Source Libraries

| Library | License | Usage |
|---------|---------|-------|
| FastAPI | MIT | REST API & WebSocket server |
| PyTorch | BSD-3-Clause | LSTM autoencoder training & inference |
| XGBoost | Apache 2.0 | Fusion risk classifier |
| scikit-learn | BSD-3-Clause | Isolation Forest, preprocessing |
| Uvicorn | BSD-3-Clause | ASGI web server |
| Chart.js | MIT | SOC dashboard visualizations |
| Tabler Icons | MIT | SOC dashboard icon set |

---

## 16. Troubleshooting

### Port Already in Use
```bash
# Windows — find and kill the process on port 8080
netstat -ano | findstr 8080
taskkill /F /PID <PID>

# Or run on a different port
python -m uvicorn app:app --port 8090
```

### `ModuleNotFoundError`
Ensure your virtual environment is active (`(venv)` shows in terminal), then re-run:
```bash
pip install -r requirements.txt
```

### Python Version Error / Pickle Fails
Use Python 3.11. Create a new environment:
```bash
py -3.11 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### WebSocket Disconnected
The dashboard auto-reconnects every 5 seconds. If it persists, ensure only one `app.py` process is running.

### Database Locked
```bash
# Close all Python processes, then:
del TRUSTLAYER.db   # Windows
python app.py       # Fresh DB auto-created on startup
```

### Browser Shows Old Version
Hard refresh: `Ctrl + Shift + R` (Windows/Linux) or `Cmd + Shift + R` (macOS).

---

## 17. License

```
MIT License

Copyright (c) 2026 Team SOLARIS — CBI Hackathon

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

---

*TrustLayer — Team SOLARIS | CBI Hackathon 2026 | MNNIT Allahabad*
