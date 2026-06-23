# BehaviorShield — Continuous AI Behavioral Biometric Authentication

**Team SOLARIS | Cyber Security Hackathon 2026 | MNNIT Allahabad**

BehaviorShield is a sovereign, continuous, AI-driven behavioral biometric authentication system designed for Indian Public Sector Banks. It silently monitors user keystroke rhythm and mouse trajectories during active NetBanking sessions to identify account takeover (ATO), credential sharing, and browser automation bots in real time.

---

## Key Features

1. **Continuous Verification**: Rather than a single login check, BehaviorShield re-evaluates session risk continuously (every 10s to 30s) using a lightweight client-side Telemetry SDK (`sdk.js`).
2. **Explainable AI (SHAP-lite)**: Provides real-time feature contribution breakdowns (e.g., *"+14.0 risk: Mean key hold duration deviated from enrolled baseline"*).
3. **Adaptive Friction Response**: 
   - **Green (Low Risk 0-29)**: Session continues silently.
   - **Amber Low/Mid (Medium Risk 30-70)**: Triggers silent monitoring escalation or a step-up typing rhythm verification modal.
   - **Amber High (Elevated Risk)**: REST API locks down high-value transactions, requiring out-of-band verification (OTP).
   - **Red (High Anomaly/Bot 71-100)**: Instant Matrix-style locked overlay, terminating the session and alert pushes.
4. **Immediate Bot Heuristics**: Captures webdriver driver footprints, 0ms programmatic timings, and straight-line trajectory patterns before model scoring.

---

## Project Structure

```
adventurous-pythagoras/ (Workspace Repository)
├── constants.py            ← All system thresholds, weights, and feature limits
├── database.py             ← In-memory session registry and user profile database
├── ml_engine.py            ← Z-Score keystroke profiler + Isolation Forest mouse engine
├── app.py                  ← FastAPI server (REST APIs + WebSocket + Static Files)
├── requirements.txt        ← Python packages (FastAPI, Scikit-Learn, Numpy, Pandas)
│
├── verify_integration.py   ← Automated end-to-end integration test suite
├── test_ml_engine.py       ← Local test suite for feature extraction and Z-Score logic
│
├── scripts/                ← Utility & model retraining scripts
│   └── retrain_xgb_with_kmt.py ← Retrain XGBoost fusion using real-world KMT dataset
│
└── static/                 ← Frontend Client Assets
    ├── index.html          ← Landing page with technical architecture layouts
    ├── bank.html           ← "Bharat Suraksha Bank" internet banking portal simulator
    ├── dashboard.html      ← BehaviorShield Security Operations Center (SOC) dashboard
    │
    ├── css/
    │   └── style.css       ← Premium dark-mode design system & overlays
    └── js/
        ├── sdk.js          ← Silent biometric telemetry collector SDK
        ├── bank.js         ← Bharat Suraksha Bank controller, form validations, & simulator
        └── dashboard.js    ← WebSocket feed receiver, Chart.js, & analyst controls
```

---

## Installation & Running Locally

1. **Clone the repository and install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the FastAPI Application Server**:
   ```bash
   python app.py
   ```
   *Note: The server will run on port `8080` (configured dynamically to avoid port conflicts).*

3. **Access the Portal**:
   - Open your browser to `http://localhost:8080/` to view the launcher landing page.
   - Click **Bharat Suraksha Bank Simulator** to start a session.
   - Click **Security Operations Center** to open the live analyst monitoring dashboard.

---

## XGBoost Model Retraining (Real KMT Dataset)

BehaviorShield features a multi-tiered XGBoost fusion classifier that fuses keystroke metrics, mouse movements, metadata anomaly scores, device signatures, and temporal risks.

To elevate verification from synthetic calibration to real-world biometrics, the fusion model has been retrained using the **KMT (Keystroke-Mouse-Touch) Behavioral Biometrics Dataset** (containing 1,760 sessions from 88 real-world users, partitioned into 10 legitimate and 10 intruder/takeover sessions per user).

### Retraining Goals & Takeover Detection
To prevent shortcut learning where the classifier relies solely on metadata or device match flags to decide legitimacy (e.g., ignoring biometrics when a device signature matches), we implemented:
1. **Takeover Simulation**: 50% of the training intruder samples are mapped as same-device takeovers (matching device and low metadata score), forcing the model to rely primarily on behavioral telemetry.
2. **Stratified Synthetic Augmentation**: Combined KMT real sessions with 5,000 synthetic samples spanning five distinct risk tiers (including Amber overlap zones and Bots).

### Running Retraining
Execute the retraining pipeline locally to rebuild the model and generate a metrics report:
```bash
python scripts/retrain_xgb_with_kmt.py
```
This script runs the baseline profiling, extracts features, performs the fit, and saves the new classifier to `models/xgboost_fusion.pkl`.

### Retraining Results
The model achieves high generalization across real biometric sessions:
- **Accuracy**: 87.97%
- **Precision**: 80.96%
- **Recall**: 92.97%
- **F1 Score**: 86.55%

### Verification
Run the automated end-to-end integration test suite to verify that the FastAPI backend successfully uses the retrained model to block same-session, same-device human intruders and automated bots:
```bash
python verify_integration.py
```

---

## Step-by-Step Demo Walkthrough

### 1. Account Registration & Biometric Enrollment
1. Open **Bharat Suraksha Bank** (`http://localhost:8080/bank`).
2. Click **Register Here** under the Secure NetBanking Login card.
3. Fill in the registration form details (e.g., choose a username like `solaris_tester`, enter a password, fill in your details, and set a Date of Birth).
4. Click **Register**. The **Account Created** screen will appear, displaying a generated account number and a unique **11-character passphrase** (e.g., `SolaTest@26`).
5. Click **Proceed to Login**. The username will be pre-filled. Enter the password you chose during registration and click **Continue**.
6. Since this is a new account/device with no existing biometric profile, you will be redirected to the **Enrollment Wizard**.
7. Under the floating **Demo Controller** (bottom right), select the **Legitimate Owner** persona.
8. Click **⚡ Quick-Fill Credentials** 5 times. The simulator will type the generated passphrase with natural human variations.
9. Sweep your mouse pointer or finger along the curved line from **START** to **END** to calibrate your touch/mouse baselines.
10. Click **Complete Enrollment**. The secure biometric profile is now stored in the SQLite database!

### 2. Live Threat Testing
1. Return to the login page (`http://localhost:8080/bank`), enter your registered username and password, select a persona in the **Demo Controller**, and click **⚡ Quick-Fill Credentials**:
   - **Legitimate Owner**: Types with normal fluid speed. Log in succeeds. The SOC dashboard shows a stable, low-risk **Green** status.
   - **Human Intruder**: Types with slow, hesitant rhythms. Log in prompts an **Identity Verification modal** (typing step-up challenge) or an elevated **Amber** risk indicator.
   - **Automated Bot**: Types instantly (0ms timings). Triggers immediate bot heuristic rules, freezing the UI with a **🚨 Session Frozen** red overlay.
2. Open the **SOC Dashboard** (`http://localhost:8080/dashboard`) side-by-side. Click on your active session to view:
   - Live Chart.js bar graph comparing hold/flight times vs enrolled baselines.
   - Mouse trajectory drawing path (Green for normal, Red for bots).
   - Analyst overrides: **Force Freeze** or **False Positive (Unfreeze)**.

> [!TIP]
> **Using Pre-Seeded Accounts**: You can bypass registration and test directly using the pre-seeded account **`demo_owner`** (Password: `HariAhir@26`). Enter `demo_owner` and the password on the login screen, select a persona from the Demo Controller, and use **⚡ Quick-Fill Credentials** to test owner, intruder, or bot scenarios.
