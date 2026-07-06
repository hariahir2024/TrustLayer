# TrustLayer: Continuous Behavioral Biometric Authentication for Digital Banking

**Author:** Technical Architecture & Security Team  
**Document Class:** Technical Reference, Design Justification, and Future Roadmap  
**Target Audience:** Senior Academic & Industry Machine Learning Experts  

---

## Abstract

This paper presents the design, implementation, and empirical justification of **TrustLayer** (internally code-named *BehaviorShield*), an ambient, continuous behavioral biometric authentication system designed to combat Account Takeover (ATO) and digital payment fraud in internet banking. Traditional multi-factor authentication (MFA) mechanisms such as One-Time Passwords (OTPs) and hardware tokens authenticate the *credential* rather than the *person*. TrustLayer addresses this vulnerability by capturing key timing kinetics (keydown/keyup timings) and mouse cursor trajectories silently during a session, building a continuous risk profile. 

The system leverages a multi-modal machine learning pipeline composed of:
1. **LSTM sequence-to-sequence autoencoders** for keystroke dynamics modeling, pre-trained on the CMU Keystroke Dynamics Benchmark.
2. **LSTM sequence-to-sequence autoencoders** for mouse path anomaly detection, trained on the Balabit Mouse Dynamics Challenge dataset.
3. **An XGBoost-based Late Fusion Classifier** integrating behavioral scores, metadata anomalies (atypical hour histograms, device fingerprint shifts calibrated against real banking logs like `INB_REQ_LOG.csv` and `TXN_HISTORY_UPI_FIN.xlsx`), and heuristic bot-detection rules into a unified, calibrated threat score (0–100).

This document details our technical decisions, mathematically justifies our structural choices, presents empirical performance results (86.87% accuracy on real-world datasets), and outlines a future research roadmap targeting Indic keyboard layouts, free-form continuous authentication, and edge-based privacy-preserving biometrics.

---

## 1. Problem Statement & Banking Threat Landscape

Digital banking fraud in India is experiencing a significant rise. According to the Reserve Bank of India (RBI) Annual Report 2024, digital banking frauds accounted for over ₹29,082 crore in losses during FY2023–24. Account Takeover (ATO) fraud, often initiated through spear-phishing, SIM-swapping, credential stuffing, or social engineering (vishing), remains the primary vector. 

Once credentials are compromised, traditional security controls fail:
* **Passwords/Passphrases** are static and easily stolen or replayed.
* **OTPs** are susceptible to SIM-swap redirection, SS7 intercepts, or social engineering coercion.
* **Device Fingerprints** (User-Agent, IP, screen dimensions) are easily spoofed using automated tools like Puppeteer, Selenium, or anti-detect browsers.

The fundamental weakness of these controls is that they are **point-in-time** and authenticate **possession or knowledge**, not the **identity of the actor**. 

TrustLayer solves this by introducing a **continuous, zero-friction behavioral biometrics layer** that runs in the background. By observing *how* a user types and *how* they move their mouse—patterns that are highly stable for an individual and extremely difficult to mimic, even when the passphrase text is known—TrustLayer verifies the user's identity throughout the entire life of the session.

---

## 2. System Architecture & Telemetry Pipeline

TrustLayer is built as a distributed, real-time telemetry pipeline designed to process high-frequency biometric streams with sub-second latency:

```
┌─────────────────────────────────────────────────────────────┐
│              Bharat Suraksha Bank Portal (Frontend)          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  bank.html   │  │ dashboard.html│  │    index.html    │  │
│  │  (Banking UI)│  │  (SOC Panel) │  │  (Landing Page)  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────┘  │
│         │                 │                                   │
│  ┌──────▼─────────────────▼─────────────────────────────┐   │
│  │              sdk.js — Silent Telemetry SDK            │   │
│  │  keydown/keyup → hold_time, flight_time, position     │   │
│  │  mousemove    → x, y, velocity, acceleration          │   │
│  │  touchstart   → mobile gesture capture                │   │
│  └──────────────────────────┬────────────────────────────┘   │
└─────────────────────────────┼───────────────────────────────┘
                              │ WebSocket / REST API (FastAPI)
┌─────────────────────────────▼───────────────────────────────┐
│                  FastAPI Backend (app.py)                     │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐ │
│  │  /api/login │  │ /api/score  │  │ /api/admin/*         │ │
│  │  /api/enroll│  │ /api/reauth │  │ /api/transaction     │ │
│  │  /api/register  /api/action  │  │ WebSocket /ws/{id}   │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────────────────┘ │
└─────────┼────────────────┼────────────────────────────────── ┘
           │                │
┌─────────▼────────────────▼────────────────────────────────── ┐
│                    ML Engine (ml_engine.py)                    │
│                                                                │
│  ┌───────────────────┐  ┌───────────────┐  ┌──────────────┐  │
│  │  Keystroke Scorer │  │  Mouse Scorer │  │ Metadata     │  │
│  │  LSTM Autoencoder │  │  LSTM Autoenc │  │ Scorer       │  │
│  │  + Z-Score Profiler  │  Isolation    │  │ (Rule-based) │  │
│  │  CMU Dataset      │  │  Balabit Data │  │              │  │
│  │                   │  │               │  │              │  │
│  └─────────┬─────────┘  └──────┬────────┘  └──────┬───────┘  │
│            │                   │                   │          │
│  ┌─────────▼───────────────────▼───────────────────▼───────┐ │
│  │           XGBoost Fusion Classifier                      │ │
│  │           Trained: KMT Dataset (1,760 real sessions)     │ │
│  │           Output: Fraud probability → Risk Score (0-100) │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────── ┘
           │
┌─────────▼──────────────────────────────┐
│         SQLite Database (db_sqlite.py)  │
│  users, sessions, behavioral_profiles   │
│  keystroke_baselines, security_events   │
└────────────────────────────────────────┘
```

### 2.1 Frontend Telemetry Agent (`sdk.js`)
The client SDK runs in the browser, binding event listeners to keyboard and mouse interactions.
* **Keystroke Capture:** Monitors `keydown` and `keyup` events, recording absolute timestamps (in milliseconds) and key positions (1-indexed index within the password field) instead of character codes.
* **Mouse Capture:** Samples cursor coordinates \((x, y)\) at a standard frequency of 20 Hz (every 50 ms) to balance capture fidelity with network payload sizes.
* **Mobile Support:** Hooks into `touchstart` and `touchend` events to collect touchscreen sweep vectors.

### 2.2 Telemetry Transmission Protocol
Telemetry payload frames are compressed and transmitted via REST POST requests to `/api/score` or streamed through a WebSocket connection. To prevent telemetry interception and replay attacks, each packet contains a cryptographic nonce (`nonce`) and a client-side timestamp. The server verifies that the timestamp is within a 120-second window and matches the nonce against a sliding-window database cache before passing the packet to the ML engine.

---

## 3. Dataset & Empirical Model Training Details

To establish academic credibility, we present the exact datasets, parameters, and baseline metrics used to train and validate our neural models:

### 3.1 Keystroke Dynamics Model
* **Source Dataset:** *CMU Keystroke Dynamics Benchmark (DSN-2009)*.
* **Data Scale:** 17,340 training sequences from 51 unique subjects (400 keystroke trials per subject typing a fixed 10-character password).
* **Normalization Parameters:**
  * Key Hold Mean: 90.09 ms | Key Hold Std Dev: 30.50 ms
  * Inter-key Flight Mean: 144.47 ms | Inter-key Flight Std Dev: 216.27 ms
* **Sequence Modeling Architecture:**
  * **Class:** `LSTMAutoencoder`
  * **Input Shape:** Sequence of \((H_i, F_i)\) pairs (sequence length = 11, input feature dimension = 2).
  * **Model Capacity:** 2 LSTM layers, 128 hidden units per layer, latent bottleneck dimension = 16, dropout = 0.1.
* **Training Run Config:**
  * Optimization: Adam optimizer (learning rate = 0.001), gradient clipping = 1.0.
  * Criterion: Mean Squared Error (`MSELoss`).
  * Training Duration: 50 epochs on CUDA.
* **Performance Metrics:**
  * Final Training Loss (MSE): 0.0665
  * Best Validation Loss (MSE): 0.0465
  * Anomaly Threshold: 0.1647 (calibrated at the 95th percentile of validation reconstruction error).

### 3.2 Mouse Dynamics Model
* **Source Dataset:** *BALABIT Mouse Dynamics Challenge*.
* **Data Scale:** 76,543 mouse coordinate streams representing continuous movement trajectories.
* **Normalization Parameters:**
  * Velocity Mean: 0.57 px/ms | Velocity Std Dev: 1.34 px/ms
  * Acceleration Mean: 0.05 px/ms² | Acceleration Std Dev: 0.22 px/ms²
* **Sequence Modeling Architecture:**
  * **Class:** `LSTMAutoencoder`
  * **Input Shape:** Sequence of \((v_t, a_t)\) coordinate derivatives (sequence length = 50, input feature dimension = 2).
  * **Model Capacity:** 2 LSTM layers, 128 hidden units per layer, latent bottleneck dimension = 16, dropout = 0.1 (totaling 468,370 parameters).
* **Performance Metrics:**
  * Final Training Loss (MSE): 0.2442
  * Best Validation Loss (MSE): 0.2567
  * Anomaly Threshold: 1.0739 (calibrated at the 95th percentile of validation reconstruction error).

### 3.3 XGBoost Late Fusion Model (Production Classifier)
* **Dataset Composition:** 
  * *Original model:* Blends KMT Real Behavioral Biometrics Dataset (1,760 sessions from 88 real human subjects) with 5,000 synthetic sessions.
  * *Inter-subject (v2) model:* Trained using **100% real data** (CMU keystrokes, BALABIT mouse trajectories, and real transaction data distributions drawn from CBI Hackathon bank datasets `INB_REQ_LOG.csv` and `TXN_HISTORY_UPI_FIN.xlsx`).
* **Validation Methodology:** 5-fold cross-validation grouped by `subject_id` to prevent user leakage between training and validation splits.
* **Feature Importances:**
  1. Keystroke Score: **45.36%**
  2. Metadata Score (IP/Time anomaly): **24.98%**
  3. Mouse Anomaly Score: **20.85%**
  4. User Enrollment Status: **8.81%**
* **Empirical Classification Metrics:**
  * Cross-validated Accuracy: **86.87%**
  * Recall (Fraud Catching Rate): **92.40%**
  * Precision: **79.41%**
  * F1-Score: **85.41%**
  * Inter-subject Cross-Val Accuracy (v2): **83.68%** | F1-Score: **82.58%**

---

## 4. Feature Engineering & Kinematics

TrustLayer extracts **28 distinct features** across three modalities:

### 4.1 Keystroke Dynamics (15 Features)
Keystroke biometrics analyze the timing patterns of typing. Crucially, **the identity of keys pressed is never stored or transmitted** to comply with privacy regulations. We analyze purely the timing between transitions:

1. **Hold Time (Dwell Time - \(H_i\)):** The duration a key is held down.
   \[H_i = t_{\text{up}}(i) - t_{\text{down}}(i)\]
2. **Flight Time (Inter-key Gap - \(F_i\)):** The interval between releasing a key and pressing the next.
   \[F_i = t_{\text{down}}(i+1) - t_{\text{up}}(i)\]
3. **Typing Speed (Characters Per Second - CPS):** Total length of sequence divided by total duration.
4. **Statistical Aggregates:** Mean and standard deviation of hold/flight times across the session (\(\mu_H, \sigma_H, \mu_F, \sigma_F\)).
5. **Backspace Rate:** The ratio of correction keystrokes to total inputs (indicating self-correction behavior).
6. **Digraph Latencies:** Specific key-to-key transitions (e.g., transition from lowercase characters to the `@` symbol, or transitions between name components).

### 4.2 Mouse Dynamics (8 Features)
Mouse movements are captured continuously. We extract mathematical features from cursor paths:
1. **Mean and Std of Velocity:** Calculated as Euclidean distance divided by time difference between coordinates:
   \[v_t = \frac{\sqrt{(x_t - x_{t-1})^2 + (y_t - y_{t-1})^2}}{\Delta t}\]
2. **Path Straightness (Curvature Index):** The ratio of the actual mouse path length to the straight-line distance between the start and end coordinates:
   \[S = \frac{\sum \Delta d_i}{\sqrt{(x_{\text{end}} - x_{\text{start}})^2 + (y_{\text{end}} - y_{\text{start}})^2}}\]
   *Automated bots move in mathematically perfect straight lines (\(S = 1.0\)), whereas humans exhibit jitter and curved trajectories (\(S > 1.15\)).*
3. **Jitter & Acceleration:** Rates of velocity change, helping identify mechanical/robotic movements.
4. **Scroll & Click Frequency:** Cadence of page interactions.

### 4.3 Contextual Metadata (5 Features)
1. **Device Fingerprint Matching:** Cryptographic hash of browser properties. Mismatches increase risk scores.
2. **Per-User Time-Of-Day Histogram:** Tracks the user's historical login hours. If a user habitually logs in during standard working hours, a login attempt at 3:00 AM triggers an anomaly.
3. **Session Action Speed:** Navigation velocity between pages.
4. **Transaction Initiation Delay:** The time delta between successful login and transaction request. Short delays (e.g., < 2 seconds) suggest scripted automated takeovers.

---

## 5. Machine Learning Modality Models

### 5.1 Keystroke Modeling: LSTM Autoencoder
To model typing sequences dynamically, we use an **LSTM Autoencoder**. 

* **Why an Autoencoder?** Supervised binary classification (Legitimate vs. Fraud) is impractical for per-user biometrics because **we cannot collect data from all potential future intruders** during a user's enrollment. Therefore, the task is framed as **unsupervised anomaly detection (one-class learning)**. We train the network to reconstruct the legitimate user's sequence. When an intruder types, the reconstruction error will spike.
* **Architecture:** 
  * **Encoder:** 2-layer LSTM with 128 hidden units. It takes the sequence of \((H_i, F_i)\) pairs (sequence length = 11) and compresses it into a latent vector \(\mathbf{z}\).
  * **Decoder:** 2-layer LSTM that expands \(\mathbf{z}\) back to the original sequence shape.
  * **Loss Function:** Mean Squared Error (MSE) reconstruction loss:
    \[L = \frac{1}{N}\sum_{i=1}^{N} ||\mathbf{X}_i - \mathbf{\hat{X}}_i||^2\]
* **Calibration & Z-Score Fallback:** During the "cold-start" phase (when a user has logged in fewer than 15 times), the system supplements the LSTM reconstruction score with a per-feature Z-score deviation model:
  \[Z_f = \frac{|x_f - \mu_f|}{\max(\sigma_f, \text{floor})}\]

### 5.2 Mouse Modeling: Isolation Forest
For mouse trajectory analysis, we leverage an **Isolation Forest** (unsupervised anomaly detection based on decision tree partitioning).
* **Rationale:** Mouse movements are highly irregular and feature-rich. Isolation Forests isolate anomalies by randomly selecting a feature and split value. Because anomalies require fewer splits to isolate, they appear closer to the root of the trees.
* **Input:** Vector of extracted statistical path features (velocity mean/std, curvature, idle ratios).

### 5.3 Late Fusion: XGBoost Classifier
To merge these different scoring outputs (Keystroke, Mouse, Metadata), we implement a **Late Fusion Classifier** using an **XGBoost (Extreme Gradient Boosting)** ensemble model.

* **Why Late Fusion?** Early fusion (concatenating raw coordinate streams and keystroke timings) is fragile due to alignment issues (e.g., a user might type without moving the mouse, or vice versa). Late fusion allows each model to evaluate its modality independently.
* **XGBoost Rationale:** XGBoost is highly efficient, robust to missing values (e.g., if no mouse data is collected during a keystroke-only action), and models complex, non-linear relationships between risk factors (such as an unknown device combined with atypical hours).
* **Calibrated Confidence Blending:** To prevent model polarization (XGBoost outputs clustering too heavily around 0% or 100%), we blend the XGBoost classification probability with a weighted linear sum of the raw feature scores:
  \[\text{Risk Score} = w \cdot P_{\text{XGBoost}} + (1 - w) \cdot \left( \sum w_c \cdot S_c \right)\]

---

## 6. Security Decision Engine & Hardening

### 6.1 Seven-Band Risk Corridor
The resulting risk score (0–100) is mapped to seven distinct risk bands, triggering automated security controls:

| Band | Score Range | System Action | User Friction |
|------|-------------|---------------|---------------|
| **GREEN** | 0–30 | Continue session, default telemetry rate (15s) | None |
| **AMBER_LOW** | 31–45 | Accelerate telemetry interval to 10s | None |
| **AMBER_MID** | 46–60 | Trigger Step-Up Re-Authentication | User must retype passphrase |
| **AMBER_HIGH** | 61–70 | Require Transaction OTP + Limit transactions to ₹10,000 | Soft friction |
| **RED_LOW** | 71–82 | Freeze session (temporary UI lock) | UI overlay locked |
| **RED_HIGH** | 83–95 | Terminate session + SMS/ntfy.sh notification | Account logged out |
| **RED_CRITICAL** | 96–100 | Silent block + IP rate limit ban | IP blacklisted |

### 6.2 Hardening Mechanisms
1. **Persistent Account-Level Lockout:** Failed password entries and behavioral mismatches (RED bands) are logged in a persistent SQLite `login_failures` table. After 5 consecutive failures, the username account is locked for 15 minutes. This state persists across server reboots to prevent bypasses.
2. **Score Velocity Guard:** If a session's risk score increases by more than 20 points within a single scoring interval, the system skips intermediate bands and immediately escalates the session to **AMBER_HIGH**, preventing rapid takeover attacks.
3. **Sandbox Loopback Bypass:** The IP ban mechanism excludes loopback addresses (`127.0.0.1`, `::1`) from active bans, ensuring presenters do not lock themselves out during live demonstrations while still logging the simulated attack behavior.

---

## 7. Project Decisions & Rationales

A strict academic reviewer will evaluate the engineering compromises made during the design phase. Below are the key decisions and their justifications:

### Decision 1: Ambient Telemetry (Zero Added UI Fields)
* **Design:** Telemetry is captured purely from standard inputs (login fields, transfer forms) and ambient navigation. No dedicated biometric captcha or phrase typing is requested.
* **Justification:** Adding security friction (such as requiring a user to type a long text block) degrades user experience and increases transaction abandonment. Furthermore, active challenges alert attackers that they are being monitored, allowing them to adjust their pace or switch to manual control. Ambient capture keeps the security layer invisible and resilient to social engineering.

### Decision 2: 11-Character Passphrase Length Formula
* **Design:** Passphrase is generated dynamically as: `First4(first_name) + First4(last_name) + @ + YY` (e.g., `HariAhir@26`).
* **Justification:** Recurrent neural networks (LSTMs) require a minimum sequence length to extract stable temporal patterns (short sequences like 4-digit PINs lack sufficient degrees of freedom). However, overly long phrases increase user typographical errors. An 11-character sequence strikes a balance, providing 10 flight-time intervals and 11 hold-time data points, which is sufficient for LSTM convergence, while remaining memorable and containing hand-alternating digraph transitions.

### Decision 3: Unsupervised Autoencoder over Supervised Classifier for Biometrics
* **Design:** Keystroke dynamics are evaluated using an LSTM Autoencoder trained solely on the legitimate owner's samples.
* **Justification:** A supervised classifier trained to separate User A from User B requires negative training samples (intruders) at training time. In production, we cannot predict *who* will attempt to compromise the account. An autoencoder models the reconstruction boundary of the legitimate owner. It measures: *"How much does this interaction deviate from this specific user's typing baseline?"* This approach is more robust to unknown intruder profiles.

### Decision 4: Late Fusion via XGBoost over Simple Averaging
* **Design:** We pass modality scores (keystroke, mouse, metadata) to an XGBoost classifier to compute the final score, rather than using a static weighted average.
* **Justification:** Behavioral signals are highly correlated and non-linear. For example, a metadata anomaly (atypical hour) is benign if the keystroke and mouse biometrics match perfectly. However, if combined with a slight keystroke deviation, the overall risk is much higher than the sum of its parts. XGBoost captures these cross-feature interactions automatically.

---

## 8. Future Research Roadmap

For phase 3 and production scaling, the following initiatives are planned:

### 8.1 Indic Keyboard layouts & Bilingual Typing Priors
* **The Challenge:** Keyboard layouts, punctuation speeds, and shorthand vary across regions. Base LSTM models trained on Western benchmarks (CMU/Balabit) exhibit high false positive rates when applied to Indian users typing in regional layouts or bilingual (English + Hindi/transliterated Hinglish) contexts.
* **Roadmap:** Deploy TrustLayer in "Advisory Mode" (passive monitoring) across a pilot user base to collect opt-in baseline samples of regional typing styles. We will train regional typing priors to adapt Z-score limits and LSTM weights dynamically based on the user's localized keyboard locale.

### 8.2 Free-Form Continuous Authentication
* **The Challenge:** Passphrase dynamics only protect the login gateway. If an attacker hijacks an active browser session (session hijacking/XSS), the login gateway is bypassed.
* **Roadmap:** We will integrate the **GREYC-Keystroke Dataset** (free-text typing data from 133 users) to transition the system to continuous authentication. Instead of scoring fixed text, the SDK will run a background sliding window (e.g., every 50 characters typed in search fields, chat boxes, or payment descriptions), comparing free-form digraphs against a running baseline.

### 8.3 Privacy-Preserving On-Device Biometrics (Edge ML)
* **The Challenge:** Storing or transmitting raw timing events and cursor coordinates creates a privacy risk and requires compliance with data residency laws.
* **Roadmap:** Port the LSTM autoencoder models to **TensorFlow.js** to execute inference locally inside the user's browser. The frontend SDK will process coordinates and keystrokes on the client device, transmitting only the final compressed anomaly scores to the server, ensuring raw biometric data never leaves the user's device.

### 8.4 Graph-Based Navigation Path Auditing
* **The Challenge:** Advanced bots can mimic human timing characteristics on individual elements, bypassing simple velocity checks.
* **Roadmap:** Model user navigation paths as a directed graph where nodes represent pages (e.g., Account Inquiry, Add Payee, RTGS Transfer) and edges represent transitions. Using Graph Neural Networks (GNNs), we will analyze session traversal paths to identify bot-like traversal patterns that deviate from typical human navigation flows.

---

## 9. Appendix: Database Portability & Environment Initialization

To facilitate peer review and ease of deployment, the repository omits local SQLite binary database files (`TRUSTLAYER.db`, `behaviorshield.db`, etc.) from git tracking. Analysts should note the following configuration:

1. **Auto-Initialization (Cold Start):** The SQLite database schema (tables for `users`, `sessions`, `login_failures`, `behavioral_profiles`, and `security_events`) is constructed dynamically at runtime when the FastAPI server is first booted. The application will automatically seed standard configurations.
2. **Model Training & Pre-trained Weights:**
   * The deep neural sequence networks (LSTM Autoencoders for keystroke and mouse telemetry) are **fully pre-trained** on the CMU and Balabit benchmarks. Their optimized tensors are bundled directly in the `/models/` directory (`lstm_keystroke_pretrained.pt` and `lstm_mouse_pretrained.pt`). No local GPU training is required for basic execution.
   * The active XGBoost late fusion model (`xgboost_fusion.pkl`) is similarly pre-trained on KMT human biometrics (1,760 sessions) and cached metadata.
3. **Local Retraining Pipeline:** To demonstrate incremental learning or verify training pipelines locally, developers can run:
   ```bash
   python scripts/retrain_xgb_augmented.py
   ```
   This script reads locally recorded session histories and recalculates classification weights. To prevent execution failures, the script requires a small set of labeled intruder samples (or can be forced using the `--force` flag for staging).
4. **Integration Validation:** Run the self-contained test suite to boot a temporary instance, perform enrollment, run simulations, and verify the model's response:
   ```bash
   python verify_integration.py
   ```
