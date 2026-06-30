# TRUSTLAYER — Continuous AI Behavioral Biometric Authentication
**Team SOLARIS | CBI Hackathon 2026 Phase II Submission | MNNIT Allahabad**

TRUSTLAYER is a sovereign, continuous, AI-driven behavioral biometric authentication system designed for Indian Public Sector Banks (PSBs). It silently monitors user keystroke rhythm and mouse trajectories during active NetBanking sessions to identify account takeover (ATO), credential sharing, and automated bot scripts in real time, without adding friction for legitimate customers.

---

## 📖 Project Overview & Core Concept

NetBanking security has historically relied on **point-in-time** checks (e.g., username/password at login and OTPs during transfers). However, once a session is established, it remains vulnerable to:
1. **Account Takeover (ATO)**: Intruders hijacking an active session while the owner is away.
2. **Credential Sharing**: Users sharing access with unauthorized individuals.
3. **Remote Access Trojans (RATs)**: Malicious software controlling the browser.
4. **Automated Bot Attacks**: Headless scripts performing automated fund transfers.

**TRUSTLAYER** solves this by establishing **Continuous Verification**. A lightweight client-side Telemetry SDK (`sdk.js`) silently records keyboard timings and mouse movements during natural usage. These features are evaluated by our backend machine learning engines (Z-Score keystroke comparison, Isolation Forest mouse path analysis, and XGBoost fusion classification) to dynamically adjust a session's risk score.

---

## 🚀 Key Features

1. **Continuous Verification Loop**: Evaluates session risk dynamically (every 10s to 30s) instead of relying on a single login check.
2. **Explainable AI (SHAP-lite)**: Provides real-time, human-readable explanations in the SOC dashboard (e.g., *"+14.0 risk: Flight time between keys 'A' and 'S' deviated from the calibrated baseline"*).
3. **Adaptive Friction Security (Green, Amber, Red)**:
   - **Green (Risk 0–29)**: Session continues silently.
   - **Amber Low/Mid (Risk 30–70)**: Escalates monitoring frequency or triggers a step-up typing rhythm modal.
   - **Amber High (Risk 71–89)**: Locks high-value transactions (such as funds transfers), requiring out-of-band verification (OTP).
   - **Red (Risk 90–100 / Bot)**: Instantly freezes the user interface with an overlay and locks the session, sending immediate alert pushes to the SOC.
4. **Immediate Bot Heuristics**: Catches webdriver footprints, straight-line cursor movements, and 0ms automated typing before machine learning model evaluation.

---

## 📁 Repository Structure

```
<project_root_directory>/ (Submission Package)
├── constants.py              ← System thresholds, weights, and feature limits
├── db_sqlite.py              ← SQLite database handlers for profiles, logs, and events
├── ml_engine.py              ← Feature extraction, Z-Score keystroke model, and Isolation Forest
├── app.py                    ← FastAPI backend server (REST, WebSockets, and Static routing)
├── requirements.txt          ← Python package dependencies
│
├── verify_integration.py     ← Portable automated integration test suite
├── verify_datasets.py        ← Dataset verification test suite
│
├── models/                   ← Pre-trained machine learning classifiers
│   ├── xgboost_fusion_intersubject.pkl ← Retrained inter-subject XGBoost fusion classifier
│   └── model_metadata.json   ← Dynamic model evaluation metrics (F1, precision, accuracy)
│
├── scripts/                  ← Model utility scripts
│   └── train_xgb_intersubject.py ← Retrain XGBoost fusion using real-world CMU/Balabit datasets
│
└── static/                   ← Frontend portal assets
    ├── index.html            ← Project launcher landing page
    ├── bank.html             ← "Bharat Suraksha Bank" NetBanking simulator
    ├── dashboard.html        ← TRUSTLAYER Security Operations Center (SOC) dashboard
    │
    ├── css/
    │   └── style.css         ← UI stylesheet and overlays
    └── js/
        ├── sdk.js            ← Client-side biometric telemetry collector SDK
        ├── bank.js           ← NetBanking transaction and registration handler
        └── dashboard.js      ← SOC dashboard manager (WebSockets, Chart.js, and overrides)
```

---

## 🛠️ Installation & Environment Setup

Follow these steps to set up the local environment and launch the prototype.

### Prerequisites
* Python 3.9, 3.10, or 3.11 installed.
* Standard modern web browser (Google Chrome, Microsoft Edge, or Mozilla Firefox).

### Step 1: Create a Virtual Environment
It is highly recommended to use a virtual environment to prevent dependency conflicts with other Python installations:
```bash
# Navigate to the project root directory
cd <project_root_directory>

# Create the virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### Step 2: Install Dependencies
Install all required libraries, including FastAPI, scikit-learn, numpy, pandas, and uvicorn:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Run the FastAPI Server
Launch the server process. It will run on port `8080` by default:
```bash
python app.py
```
*Note: Once started, you will see a log line in the terminal indicating uvicorn is running: `INFO: Uvicorn running on http://127.0.0.1:8080`.*

---

## 🧪 Testing & Model Retraining

We provide both automated verification test suites and retraining pipelines using real-world biometric datasets.

### 1. Run Automated Integration Tests
Verify that the server, database, WebSocket broadcasts, and machine learning models are functioning correctly under different scenarios (legitimate owner, human intruder, bot script):
```bash
python verify_integration.py
```
*This script launches a temporary background server instance on port 8089, simulates telemetry data for the three personas, verifies that the system blocks threats, and prints a success report.*

### 2. Model Retraining (Real CMU + BALABIT Datasets)
The fusion classifier has been retrained using 100% real human biometrics: the **CMU Keystroke Dynamics Benchmark** (51 subjects) and the **BALABIT Mouse Dynamics Dataset**:
```bash
python scripts/train_xgb_intersubject.py
```
*Running this script profiles keystroke/mouse parameters, trains the model (`models/xgboost_fusion_intersubject.pkl`), and outputs model statistics. The model achieves:*
* **GroupKFold Accuracy**: 83.68%
* **GroupKFold Precision**: 88.54%
* **GroupKFold Recall**: 77.37%
* **GroupKFold F1 Score**: 0.8258 (82.58%)

---

## 🖥️ Live Demo Walkthrough Guide

Open your browser to `http://localhost:8080/` to access the launcher page, then follow this flow:

### Phase 1: Registration & Calibration
1. Click **Bharat Suraksha Bank Simulator** (`http://localhost:8080/bank`).
2. Click **Register Here** and create a new account (e.g., username: `solaris_user`, password: `Password@26`).
3. Click **Register**. The system will generate an account number and a unique **11-character passphrase** (e.g., `SolaTest@26`). Copy this passphrase.
4. Click **Proceed to Login**, enter your username and password, and click **Continue**.
5. You will enter the **Enrollment Wizard** (new device calibration).
6. Under the **Demo Controller** (floating in the bottom right), select the **Legitimate Owner** persona.
7. Click **⚡ Quick-Fill Credentials** 5 times to type the passphrase with natural human variations.
8. Drag your mouse along the curved calibration line from **START** to **END** to record mouse dynamics.
9. Click **Complete Enrollment**. Your biometric profile is now securely generated and stored!

### Phase 2: Simulating Threat Personas
Open the **Security Operations Center (SOC) Dashboard** (`http://localhost:8080/dashboard`) in a side-by-side browser window.
1. **Legitimate Owner**: Log in using the `Legitimate Owner` persona. The session completes successfully. The SOC dashboard registers a stable, low-risk **Green** status.
2. **Human Intruder**: Select the `Human Intruder` persona in the Demo Controller and click log in. The keystroke rhythm will be slow/hesitant. An **Identity Verification Modal** (step-up challenge) will appear on the banking screen.
3. **Automated Bot**: Select the `Automated Bot` persona and click log in. The bot types instantly (0ms keys). The system instantly blocks the session, showing a **🚨 Session Frozen** lock overlay on the banking screen, and logs the threat in the SOC.

### Phase 3: SOC Analyst Overrides
In the **SOC Dashboard**:
1. Click on the active session card in the sidebar to open the **Session Deep-Dive Workspace** at the bottom.
2. Look at the live graphs showing key flight times, SHAP-lite features, and mouse paths.
3. If an alert is active, click **Force Freeze** to manually suspend the session (moving it to the **Frozen Sessions** tab with a score of 99.0).
4. If an alert was a false positive, click **Dismiss** (or **Unfreeze** on a frozen card) to restore user access (resetting the score back to `15.0` with a green `✓ Cleared` badge).

---

## 🔍 Troubleshooting Guide

Here are common issues you might experience during setup or evaluation, along with how to resolve them:

### 1. `Uvicorn: [WinError 10048] Only one usage of each socket address is normally permitted`
* **Cause**: Another application is already using port `8080` (e.g., another server or a ghost python process).
* **Fix**:
  * You can find and kill the process using port 8080:
    * **Windows (cmd)**:
      ```cmd
      netstat -ano | findstr 8080
      taskkill /F /PID <PID_NUMBER>
      ```
  * Alternatively, run the app on a different port by editing `app.py` or launching uvicorn manually:
    ```bash
    python -m uvicorn app:app --port 8090
    ```

### 2. Browser console shows `WebSocket connection to ws://... failed`
* **Cause**: The browser is blocking the WebSocket or the server port was changed, causing a mismatch.
* **Fix**: Ensure your dashboard is hitting the exact port python is running on. Reload the page. The dashboard has auto-reconnection logic and should hook back up in 5 seconds.

### 3. Country flag emojis show up as letters (e.g. `IN` or `US`) on Windows
* **Cause**: Windows OS does not natively support flag emojis in default system fonts.
* **Resolution**: We have integrated **FlagCDN** graphic support in `dashboard.js`. If you see letter codes, perform a **Hard Refresh** (`Ctrl + F5`) to force the browser to load the latest flag image rendering script.

### 4. Database Lock Error (`sqlite3.OperationalError: database is locked`)
* **Cause**: Two processes are trying to write to `TRUSTLAYER.db` simultaneously.
* **Fix**: Close any duplicate terminal windows running python scripts. Ensure only one `app.py` server process is active.

### 5. `ModuleNotFoundError: No module named '...'`
* **Cause**: Python is running outside the virtual environment where dependencies were installed.
* **Fix**: Ensure you have activated your virtual environment (you should see `(venv)` prefixed in your terminal prompt) before running scripts.

### 6. Python Version Mismatch & Library Installation Issues
* **Cause**: The evaluator's PC is running an unsupported Python version (such as Python 3.12+), which causes dependency installation failures (due to missing pre-compiled binary wheels) or model loading crashes (`pickle.UnpicklingError`).
* **Fix (Step-by-Step)**:
  1. Check which Python version your virtual environment is using:
     ```powershell
     # In PowerShell / CMD
     venv\Scripts\python --version
     ```
     *If it says Python 3.12.x or 3.13.x, that is the root cause.*
  2. Install a supported Python version globally:
     * Download and install **Python 3.11** (or 3.10) from the official [python.org](https://www.python.org/downloads/) website.
     * **IMPORTANT**: Make sure to check the box **"Add Python to PATH"** during the installation setup.
  3. Recreate your virtual environment using Python 3.11:
     ```powershell
     # Deactivate and remove the old environment
     deactivate
     rmdir venv /s /q

     # Create a new virtual environment bound to Python 3.11
     py -3.11 -m venv venv
     
     # Activate the new environment
     venv\Scripts\activate
     ```
  4. Upgrade pip and re-install all project dependencies:
     ```powershell
     python -m pip install --upgrade pip
     python -m pip install -r requirements.txt
     ```
  5. Run the application:
     ```powershell
     python app.py
     ```

