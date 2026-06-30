# PRESENTATION DECK OUTLINE — TRUSTLAYER
**AI-Driven Continuous Behavioral Biometrics Authentication for Indian Banking**

*Team SOLARIS | CBI Hackathon 2026 Phase II Project Submission*

---

## Slide 1: Title & Team Introduction
* **Slide Title**: TRUSTLAYER: Continuous AI Behavioral Biometric Authentication for Secure Digital Banking
* **Subtitle**: Protecting Indian Public Sector Banks (PSBs) against Account Takeover and Automated Threat Vectors
* **Team Name**: Team SOLARIS
* **Visuals**: Premium, clean dark-mode slide with a high-contrast glowing shield icon representing biometric protection.
* **Bullet Points**:
  * Continuous verification throughout the session lifecycle.
  * Real-time machine learning telemetry analysis (keystroke rhythm & mouse trajectories).
  * Built specifically for public sector digital banking portals.
* **Speaker Notes**:
  *"Good morning respected judges. We are Team SOLARIS, and today we present TRUSTLAYER. Our solution tackles a critical vulnerability in digital banking: the security gap that exists after a user logs in. Point-in-time checks are no longer enough. We present a system that continuously and silently verifies the user’s identity."*

---

## Slide 2: Problem Statement & NetBanking Vulnerabilities
* **Slide Title**: The Vulnerability of Point-in-Time Security
* **Visuals**: Infographic illustrating a timeline showing a user logging in securely (Green), followed by an Account Takeover event (Red) while the session remains active.
* **Bullet Points**:
  * **Static Authentication**: Passwords and SMS OTPs verify identity only at a single point (login).
  * **Account Takeover (ATO)**: Sessions hijacked via physical access, credential sharing, or session cookies.
  * **Automated Bot Attacks**: Headless scripts performing instant automated funds transfers.
  * **Friction Fatigue**: Over-reliance on OTPs disrupts user experience, leading to transaction drop-offs.
* **Speaker Notes**:
  *"Today, once a user enters an OTP, the door is open. If they step away, an intruder can steal the session. If they share credentials, unauthorized people log in. Furthermore, automated bots can manipulate form fields in milliseconds. Adding more OTPs frustrates customers. We need silent, continuous protection."*

---

## Slide 3: The Proposed Solution
* **Slide Title**: TRUSTLAYER: The Continuous Verification Guard
* **Visuals**: Three-tiered layer diagram showing: Client SDK (Telemetry) -> Backend AI Engine (Scoring) -> Adaptive Friction Action (Escalation/Blocking).
* **Bullet Points**:
  * **Zero Friction**: Captures user behavior silently in the background (no manual checks).
  * **Continuous Verification**: Computes a dynamic risk score (0 to 100) throughout the NetBanking session.
  * **Privacy Preserving**: Records timing and coordinate differentials only—never logs text inputs or passwords.
  * **Adaptive Response**: Real-time mitigation from silent alerts to session termination.
* **Speaker Notes**:
  *"TRUSTLAYER solves this by collecting telemetry data silently as the user types and moves their mouse. It never captures sensitive characters or text. It calculates a dynamic risk index from 0 to 100. If the risk spikes, the system dynamically locks down high-value actions or freezes the session instantly."*

---

## Slide 4: System Architecture
* **Slide Title**: Technical Architecture & Live Telemetry Loop
* **Visuals**: Flow diagram showing user actions -> `sdk.js` -> FastAPI WebSocket -> `ml_engine.py` (Models) -> SQLite Database -> Real-time action overlays and SOC Dashboard notifications.
* **Bullet Points**:
  * **Client Telemetry SDK**: Embedded lightweight JavaScript (`sdk.js`).
  * **FastAPI Server**: High-performance asynchronous backend communicating over WebSockets.
  * **Dynamic Local Database**: SQLite database storing encrypted user profiles and audit logs.
  * **Analyst Dashboard**: Operational dashboard providing live feeds and manual override overrides.
* **Speaker Notes**:
  *"Our architecture is lightweight and stateless. The client SDK streams compressed behavioral frames over WebSockets to a FastAPI backend. The backend scores the telemetry against the user's calibrated profile stored in SQLite and updates the dashboard in real-time."*

---

## Slide 5: The AI/ML Biometrics Engine
* **Slide Title**: Multi-Tiered AI/ML Diagnostics
* **Visuals**: Graphics illustrating Keystroke Digraph intervals (Hold/Flight times) and Mouse Trajectory curvature analysis.
* **Bullet Points**:
  * **Keystroke Z-Score Profiling**:
    * Computes deviation ($\sigma$) from baseline Hold Time (key press-down duration) and Flight Time (between-key transitions).
  * **Mouse Isolation Forest**:
    * Analyzes trajectory coordinate streams, velocity ($v$), acceleration ($a$), and Jerk ($j$) to isolate robotic/automated movements.
  * **Explainable AI**:
    * Computes real-time SHAP-lite features to show analysts exactly why the risk score changed.
* **Speaker Notes**:
  *"The ML engine uses two key models: Z-score profiling for keystrokes to detect speed and hesitations, and an Isolation Forest model for mouse dynamics to identify straight lines and robotic movements. We also compute SHAP-lite values to show analysts which behaviors triggered the risk."*

---

## Slide 6: XGBoost Fusion & KMT Dataset Retraining
* **Slide Title**: XGBoost Fusion & Real-World Generalization
* **Visuals**: Performance metric bar chart showing Accuracy, Precision, Recall, and F1-Score.
* **Bullet Points**:
  * **Model Fusion**: XGBoost classifier aggregates keystroke anomalies, mouse path scores, device signatures, and temporal risks.
  * **KMT Dataset Retraining**:
    * Trained on **1,760 sessions** from **88 real-world users** (KMT Keystroke-Mouse-Touch dataset).
    * Simulates same-device human takeover threats to prevent shortcut learning.
  * **Evaluation Metrics**:
    * **Accuracy**: 87.97% | **F1 Score**: 86.55%
    * **Precision**: 80.96% | **Recall**: 92.97%
* **Speaker Notes**:
  *"To move beyond synthetic testing, we retrained our XGBoost fusion classifier on the real-world KMT dataset containing over 1,700 sessions. We simulated same-device takeovers during training, forcing the model to verify identity using behavioral telemetry rather than relying on standard IP or device matches. We achieved an F1 score of 86.55%."*

---

## Slide 7: NetBanking Portal Simulator
* **Slide Title**: Bharat Suraksha Bank Portal Integration
* **Visuals**: Screenshots of the login screen, Enrollment Calibration Wizard (drawing mouse trajectory), and transaction fields.
* **Bullet Points**:
  * **Realistic NetBanking Simulation**: Includes secure registration, credentials generation, login, and payee transfers.
  * **Telemetry Calibration**:
    * Enrollment captures 5 keystroke passphrase repetitions and mouse trajectory swings.
  * **Dynamic Persona Controller**:
    * Legitimate Owner (fluid speed), Human Intruder (hesitant), and Automated Bot (instantaneous).
* **Speaker Notes**:
  *"We built a realistic simulator called Bharat Suraksha Bank. When a new user registers, they generate an 11-character passphrase and complete a quick calibration wizard. We include a Persona Controller to demonstrate how the system handles different actors: owners, intruders, and bots."*

---

## Slide 8: Security Operations Center (SOC) Dashboard
* **Slide Title**: SOC Dashboard: Live Threat Monitoring
* **Visuals**: Screenshot of the dark-mode SOC dashboard displaying the real-time active monitor cards, statistics, and risk charts.
* **Bullet Points**:
  * **Real-Time Active Alert Grid**: Filters and updates cards via WebSockets.
  * **Unified Risk Band Spectrum**: Visual distribution of all active monitored sessions.
  * **Alert Triage Resolutions**: Donut chart tracking Pending alerts, Confirmed Fraud, and False Positives.
  * **Partial Username Search**: Filters active threats instantly.
* **Speaker Notes**:
  *"For bank security teams, we created a dark-mode SOC Dashboard. It displays live active session cards, risk index band distributions, threat resolutions, and provides instant partial username search to help analysts manage threats."*

---

## Slide 9: Session Deep-Dive & Incident Resolution
* **Slide Title**: In-Depth Diagnostics & Triage Controls
* **Visuals**: Screenshot of the Deep-Dive Workspace showing the SHAP feature breakdown graph, mouse trajectory paths, and override controls.
* **Bullet Points**:
  * **SHAP-Lite Contribution Graph**: Displays positive and negative risk contributors.
  * **Interactive Mouse Path Comparison**: Compares the user's live trajectory with their enrolled path.
  * **Incident Resolution Actions**:
    * **Force Freeze**: Suspend the session and block access immediately.
    * **Dismiss (False Positive)**: Clear the alert and restore access.
* **Speaker Notes**:
  *"When an analyst selects a session, the Deep-Dive Workspace opens. The analyst can view SHAP feature breakdowns, compare mouse trajectories, and immediately execute triage controls: either Force-Freezing the session to block access or Dismissing the alert if it was a false positive."*

---

## Slide 10: Adaptive Friction Escalation Flow
* **Slide Title**: Adaptive Friction Security Policy
* **Visuals**: Flowchart illustrating the security response for Green, Amber Low/Mid, Amber High, and Red bands.
* **Bullet Points**:
  * **Green (Risk < 30)**: Continues silently.
  * **Amber Low/Mid (Risk 30-70)**: Triggers step-up typing rhythm verification modal.
  * **Amber High (Risk 71-89)**: Blocks fund transfers and forces out-of-band SMS OTP step-up.
  * **Red / Bot (Risk >= 90)**: Triggers client overlay freeze, terminates active session, and logs event in the SOC.
* **Speaker Notes**:
  *"Rather than using a blunt lock policy, the system applies adaptive friction. Low risk is silent. Medium risk triggers a typing challenge modal. High risk blocks financial transfers and requires an OTP. Critical risks or bot detections lock the browser immediately."*

---

## Slide 11: Security, Privacy, & Compliance
* **Slide Title**: Privacy-First Design & GDPR Compliance
* **Visuals**: Icon graphic showing Hashed Identifiers, Encrypted Timings, and GDPR Compliance seal.
* **Bullet Points**:
  * **GDPR-Compliant Pseudonymization**:
    * Displays masked Subject IDs (e.g., `SUB-HAR-262F`) in the SOC dashboard to protect customer PII.
  * **Zero Character Ingestion**:
    * Only timing differentials are captured; no keyboard characters or password keys are transmitted.
  * **Local In-Memory SQLite Store**:
    * Secure, localized data management with clean data cleaning policies.
* **Speaker Notes**:
  *"Security software must respect customer privacy. TRUSTLAYER only measures timing differentials in milliseconds; it never logs actual keys or passwords. Furthermore, user names are pseudonymized as Subject IDs in the dashboard. This ensures gdpr compliance."*

---

## Slide 12: Business Impact & Future Scope
* **Slide Title**: Scalability, Future Scope, & Business Value
* **Visuals**: Summary graphic illustrating fraud savings, client-side execution, and mobile sensors.
* **Bullet Points**:
  * **Fraud Cost Reduction**: Stops active ATOs, credential sharing, and bot scripts before transactions are approved.
  * **Client-Side Edge Inference**:
    * Future plans to compile models to ONNX/WebAssembly for zero-latency client-side scoring.
  * **Mobile Sensor Fusion**:
    * Expanding telemetry to mobile gestures (swipes, tap area size, gyroscope, accelerometer).
  * **PSB Integration**: Modular API ready for integration with existing NetBanking portals.
* **Speaker Notes**:
  *"To conclude, TRUSTLAYER delivers massive business value by stopping takeovers and bots before they execute transactions. In the future, we plan to shift ML scoring to the client's browser using WebAssembly and expand support to mobile sensor dynamics. Thank you, and we welcome any questions."*
