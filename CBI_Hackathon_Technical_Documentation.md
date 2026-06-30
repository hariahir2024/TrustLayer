# TECHNICAL DOCUMENTATION — TRUSTLAYER
**AI-Driven Continuous Behavioral Biometrics Authentication for Indian Banking**

*Team SOLARIS | CBI Hackathon 2026 Phase II Project Submission*

---

## 1. Problem Statement & Context

In the Indian banking ecosystem, digital transaction volumes have grown exponentially. While this shift has democratized financial services, it has also led to a significant escalation in digital banking fraud. Modern threats have evolved beyond simple credential theft; attackers now deploy sophisticated social engineering, Remote Access Trojans (RATs), browser automation scripts, and session hijacking schemes.

Traditional point-in-time multi-factor authentication (MFA) mechanisms—such as SMS-based OTPs, password challenges, or hardware tokens—suffer from two structural vulnerabilities:
1. **Friction Fatigue**: Frequent OTP prompts degrade user experience, leading to customer dissatisfaction.
2. **Point-of-Entry Security Bias**: Traditional authentication checks occur only once (at login or at transaction approval). Once an attacker bypasses the initial gate (e.g., via SIM-swapping or session capture), they gain unrestricted access to the active NetBanking session.

### Objective
Our solution, **TRUSTLAYER**, establishes a silent, continuous authentication layer that runs throughout the entire lifecycle of a banking session. By analyzing the physiological rhythms of how a user types (keystroke dynamics) and how they navigate (mouse cursor trajectories), TRUSTLAYER continuously validates the user's identity. If an anomaly is detected, the system applies real-time adaptive friction to restrict transaction capability and freeze the session.

---

## 2. Proposed Solution: TRUSTLAYER

TRUSTLAYER is a comprehensive, client-server software suite designed specifically for integration with Public Sector Banks (PSBs). It consists of three primary layers:
1. **Silent Telemetry SDK (`sdk.js`)**: A lightweight client-side script embedded in NetBanking pages. It silently captures timing and spatial telemetry from keypress and mouse events without logging the actual characters typed, preserving user privacy.
2. **FastAPI Biometric Engine (`app.py` & `ml_engine.py`)**: A multi-tiered machine learning back-end that consumes telemetry segments, extracts behavioral vectors, matches them against the user's enrolled profile, and outputs a dynamic risk score (0 to 100).
3. **Adaptive Friction Control & SOC Dashboard (`dashboard.html`)**: An automated mitigation system that implements real-time restrictions (such as stepping up verification or terminating sessions) and feeds live event diagnostics into an interactive Security Operations Center (SOC) dashboard.

```
       +-------------------------------------------------------------+
       |                  Bharat Suraksha Bank Portal                |
       |  +-------------------+              +--------------------+  |
       |  |  User Transaction |              | Client-Side SDK    |  |
       |  |  & Data Forms     |              | (Telemetry events) |  |
       |  +---------+---------+              +---------+----------+  |
       +------------|----------------------------------|-------------+
                    |                                  |
                    | (HTTP POST Transactions)         | (WebSocket Telemetry Feed)
                    v                                  v
       +-------------------------------------------------------------+
       |                     FastAPI Backend Server                  |
       |                                                             |
       |  +-------------------+              +--------------------+  |
       |  | Transaction Guard |              | Biometric Engine   |  |
       |  | (Risk Escalations)|              | (Z-Score & I-Forest|  |
       |  +---------+---------+              +---------+----------+  |
       |            |                                  |             |
       |            |                                  v             |
       |            |                        +--------------------+  |
       |            |                        | XGBoost Fusion     |  |
       |            |                        | Classifier         |  |
       |            |                        +---------+----------+  |
       |            v                                  |             |
       +------------+----------------------------------+-------------+
                    |                                  |
                    | (REST & Event Logs)              | (WebSocket Pushes)
                    v                                  v
       +-------------------------------------------------------------+
       |               Security Operations Center (SOC)              |
       |  +-------------------------------------------------------+  |
       |  | Real-Time Live Feed Monitor & Alert Overlays          |  |
       |  +-------------------------------------------------------+  |
       |  | Deep-Dive Diagnostics (Shapley Explanations, Charts)  |  |
       |  +-------------------------------------------------------+  |
       |  | Override Controls (Force-Freeze / Clear Alert)        |  |
       |  +-------------------------------------------------------+  |
       +-------------------------------------------------------------+
```

---

## 3. Technology Stack

* **Programming Language**: Python 3.9+ (Server), JavaScript ECMAScript 6 (Client).
* **Backend Framework**: FastAPI (Asynchronous ASGI server for handling WebSockets and high-throughput REST APIs).
* **Machine Learning Stack**: 
  * `scikit-learn` (Isolation Forest implementation for mouse dynamics).
  * `xgboost` (Gradient boosted decision trees for multi-feature classification fusion).
  * `numpy` & `pandas` (Matrix operations, vector processing, and dataset structures).
* **Database**: SQLite3 (Transactional data storage, event logging, and user behavioral profile store).
* **Frontend Visualization**: Vanilla HTML5/CSS3 (Dark-mode CSS UI), `Chart.js` (Real-time biometric feature graphs).

---

## 4. System Workflow & Data Flow

### Step 1: Calibration & Profile Enrollment
When a customer registers a new NetBanking account:
1. They complete an enrollment wizard where they type a designated **11-character passphrase** 5 times.
2. The SDK extracts key **Hold Times** (keypress to keyrelease duration) and **Flight Times** (keyrelease to next keypress duration) for all digraphs.
3. The user draws a designated curved path with their cursor. The SDK samples coordinates, velocities, accelerations, and curvature.
4. The server computes the mean ($\mu$) and standard deviation ($\sigma$) of the timing vectors, writing this baseline profile into the `behavioral_profiles` database table.

### Step 2: Continuous Verification Loop
Once logged in, the Telemetry SDK begins a silent collection loop:
1. Keyboard timings are collected during form entries.
2. Mouse cursor coordinates and timings are sampled at a rate of 100 Hz.
3. Every 30 seconds (or after 50 keypresses/mouse events), the SDK packages this telemetry into a JSON payload and transmits it over an active WebSocket connection.
4. The backend extracts behavioral features from the payload and evaluates them through the ML engines.
5. The resulting risk score is stored in the active session record and pushed live to the SOC dashboard.

### Step 3: Adaptive Action & Friction Scale
* **GREEN (Risk Score < 30)**: Normal transaction parameters. Access remains seamless.
* **AMBER LOW/MID (Risk Score 30 - 70)**: High-frequency telemetry polling is triggered. If the user initiates a funds transfer, they are presented with a silent typing-verification step-up modal (challenging them to type their passphrase to verify biometric alignment).
* **AMBER HIGH (Risk Score 71 - 89)**: High-value transaction operations (e.g. adding a payee or transferring funds) are immediately locked. An OTP challenge is forced.
* **RED / BOT (Risk Score 90 - 100 or Bot Trigger)**: The session status changes to locked. An immediate `SESSION_FROZEN` packet is pushed over WebSockets, causing the client browser to freeze with a red overlay, blocking all interaction.

---

## 5. Database Design

We utilize SQLite3 to maintain user, profile, transaction, and audit logs. The tables are structured as follows:

### 5.1. `users` Table
Stores standard identity, account balances, and credentials:
* `username` (TEXT, Primary Key)
* `first_name` / `last_name` (TEXT)
* `account_number` (TEXT, Unique)
* `balance` (REAL)
* `password_hash` (TEXT)
* `passphrase` (TEXT) - Hashed/Salted reference for stepping challenges.

### 5.2. `behavioral_profiles` Table
Stores calibrated biometric means ($\mu$) and standard deviations ($\sigma$):
* `username` (TEXT, Composite Primary Key)
* `device_class` (TEXT, Composite Primary Key - e.g., 'desktop', 'mobile')
* `keystroke_profile` (TEXT - JSON serialized digraph hold/flight statistics)
* `mouse_profile` (TEXT - JSON serialized coordinate/velocity baselines)
* `created_at` (REAL)

### 5.3. `sessions` Table
Tracks live telemetry risk states and triage metadata:
* `session_id` (TEXT, Primary Key)
* `username` (TEXT)
* `status` (TEXT - `'active'`, `'terminated'`, `'red_high'` (Frozen), `'red_critical'` (Bot))
* `current_risk` (REAL)
* `risk_band` (TEXT - `'GREEN'`, `'AMBER_LOW'`, `'AMBER_MID'`, `'AMBER_HIGH'`, `'RED_LOW'`, `'RED_HIGH'`, `'RED_CRITICAL'`)
* `is_bot` / `is_intruder` (INTEGER - Boolean flags)
* `risk_history` / `last_breakdown` (TEXT - JSON strings storing SHAP-lite risk vectors and timelines)
* `ip_address` / `user_agent` (TEXT)
* `action_count` (INTEGER)

### 5.4. `security_events` Table
Audit logs for SOC charts:
* `event_id` (INTEGER, Primary key auto-increment)
* `session_id` (TEXT)
* `event_type` (TEXT - `'LOGIN_OK'`, `'SCORE_UPDATE'`, `'SESSION_FROZEN'`, `'BOT_DETECTED'`, `'REAUTH_FAIL'`, `'ADMIN_FALSE_POSITIVE'`)
* `username` (TEXT)
* `details` (TEXT - JSON logs)
* `timestamp` (REAL)

---

## 6. AI/ML Models & Analytics Architecture

TRUSTLAYER combines statistical anomaly detection with ensemble machine learning classifiers to establish robust biometric verification.

### 6.1. Keystroke Rhythm Model (Z-Score Profiling)
For every key hold duration ($H$) and flight duration ($F$) in digraph transitions, the model calculates the distance from the calibrated user profile baseline:
$$Z = \frac{|x - \mu|}{\sigma}$$
Where $x$ is the live sample timing, $\mu$ is the enrolled user average, and $\sigma$ is the enrolled user standard deviation. Digraphs with $Z > 3$ represent significant deviation. The aggregated ratio of anomalous digraphs acts as the baseline keystroke anomaly score.

### 6.2. Mouse Dynamics Model (Isolation Forest)
We train an Isolation Forest model locally on the user's calibrated mouse gestures. The model isolates trajectory samples based on four features:
* **Velocity ($v$)**: Distance traveled over time.
* **Acceleration ($a$)**: Delta velocity over time.
* **Jerk ($j$)**: Rate of change of acceleration (indicator of automated automation scripts).
* **Path Curvature**: Angular deviation from direct lines.
The model returns an anomaly score representing cursor path naturalness.

### 6.3. XGBoost Fusion Classifier
To combine keystroke scores, mouse scores, device signatures, network parameters (IP changes), and session activity history, we train a gradient-boosted decision tree ensemble (**XGBoost**). 
To make the model production-ready, we retrained the fusion pipeline using the **KMT (Keystroke-Mouse-Touch) Behavioral Biometrics Dataset** (containing 1,760 sessions from 88 real-world users).
* **Same-Device Takeover Training**: We simulated same-device takeovers (matching user agents and IP blocks but displaying mismatched typing rhythm) in 50% of the threat training samples. This forced the classifier to rely on biometric telemetry instead of solely relying on hardware signature matches.
* **Generalization Metrics**:
  * **Accuracy**: 87.97%
  * **Precision**: 80.96%
  * **Recall**: 92.97%
  * **F1 Score**: 86.55%

---

## 7. Security, Privacy & Compliance Measures

Sovereign banking software must treat security and privacy as first-class citizens. TRUSTLAYER implements key features to meet banking standard requirements:

1. **GDPR-Compliant Pseudonymization**:
   * Analysts in the SOC dashboard triage alerts under secure, hashed identifiers (e.g. `SUB-HAR-262F` instead of displaying raw customer names). This prevents exposing personally identifiable information (PII) to operational personnel.
2. **Client-Side Telemetry Scrubbing**:
   * The SDK collects event timestamps (key press up and down transitions) in milliseconds. It does **not** collect character keys or text input. Passwords and transactional data are never captured, preventing keylogger-style data exposure.
3. **Out-of-Band Step-Up Enforcement**:
   * If a session risk index hits Amber High ($> 70$), the transaction pipeline restricts fund transfers. The server locks the active session state locally, requiring multi-factor SMS OTP verification before unlocking.

---

## 8. Scalability, Limitations & Future Enhancements

### 8.1. Scalability Considerations
* **Telemetry Compression**: Real-time cursor coordinates are packed using delta-compression, reducing telemetry payloads to under 2KB per transmission.
* **Stateless Scoring Endpoint**: The ML inference engine runs statelessly. Telemetry packages can be distributed across multi-node FastAPI worker clusters behind a standard load balancer.

### 8.2. Assumptions & Limitations
* **Hardware Variables**: Keyboards with high input latency (low polling rates) or differing mouse DPI sensitivities can cause minor biometric drifts.
* **Physical Impairments**: Temporary physical injuries (such as a bandaged finger) will cause Z-score deviations, requiring manual analyst clearance or temporary OTP bypass step-ups.

### 8.3. Future Enhancements
* **Edge Inference Deployment**: Compile models to ONNX/WebAssembly format, shifting biometric scoring from the FastAPI backend to the user's browser (client-side edge execution), significantly reducing backend computing overhead.
* **Mobile Sensor Fusion**: Extend telemetry collection to mobile devices by incorporating touchscreen touch area size, gyroscope rotation rates, and accelerometer tilt angles.
