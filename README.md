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

## Step-by-Step Demo Walkthrough

### 1. Silent Enrollment
1. Open **Bharat Suraksha Bank** (`http://localhost:8080/bank`) and enter a new username (e.g., `solaris_tester`). Click **Continue**.
2. Because the username is unregistered, you will see the **Enrollment Wizard**.
3. Under the floating **Demo Controller** (bottom right), select the **Legitimate Owner** persona.
4. Click **⚡ Quick-Fill Credentials** 5 times. The simulator programmatically types the enrollment passphrase with natural human timing variations.
5. Sweep your mouse pointer along the curved line from **START** to **END** to calibrate your mouse profile.
6. Click **Complete Enrollment**. The account profile is built and stored!

### 2. Live Threat Testing
1. Return to the portal home screen, select a persona in the **Demo Controller**, and click **⚡ Quick-Fill Credentials** on the login page:
   - **Legitimate Owner**: Types with normal fluid speed. Log in succeeds. The SOC dashboard shows a stable, low-risk **Green** status.
   - **Human Intruder**: Types with slow, hesitant rhythms. Log in prompts an **Identity Verification modal** (typing step-up challenge) or an elevated **Amber** risk indicator.
   - **Automated Bot**: Types instantly (0ms timings). Triggers immediate bot heuristic rules, freezing the UI with a **🚨 Session Frozen** red overlay.
2. Open the **SOC Dashboard** (`http://localhost:8080/dashboard`) side-by-side. Click on your active session to view:
   - Live Chart.js bar graph comparing hold/flight times vs enrolled baselines.
   - Mouse trajectory drawing path (Green for normal, Red for bots).
   - Analyst overrides: **Force Freeze** or **False Positive (Unfreeze)**.
