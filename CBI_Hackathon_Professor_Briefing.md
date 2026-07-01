# PROJECT BRIEFING & EVALUATOR PROPOSAL — TRUSTLAYER
**Continuous AI Behavioral Biometric Authentication for Sovereign Digital Banking**

*Prepared for Hackathon Evaluation Committees & Academic Advisors*  
*Team SOLARIS | CBI Hackathon 2026*

---

## 1. Executive Summary

Digital banking security is at an architectural crossroads. Traditional security measures—such as usernames, passwords, and multi-factor authentication (MFA) via SMS OTPs—are **point-in-time checks** that verify identity only at a single instance (the moment of login or transaction submission). Once a session is established, it remains fully vulnerable to session hijacking, Remote Access Trojans (RATs), credential sharing, and automated bot scripts.

**TRUSTLAYER** addresses this point-of-entry security bias by introducing **Continuous AI Behavioral Biometric Authentication**. Operating silently in the background, our solution captures millisecond-level keystroke rhythm metrics and sub-pixel mouse trajectory dynamics. Using a multi-tiered anomaly detection framework (Z-Score profiling, Isolation Forest classifiers, and XGBoost fusion models), TRUSTLAYER continuously scores session risk (0-100) and implements real-time adaptive friction (Green, Amber, Red). 

Beyond state-of-the-art machine learning models, the TRUSTLAYER prototype is hardened to production standards, implementing:
* **Cryptographic Hardening**: Saluted **PBKDF2-SHA256 password hashing** (100,000 iterations) to secure stored credentials.
* **Anti-Replay Protection**: Enforced client-side cryptographic nonces (UUIDs) and timestamp freshness checks at the API layer.
* **Unified Risk-Gating**: Dynamic transaction restrictions (₹5,000 soft limit requiring step-up/OTP, ₹10,000 hard block) for both standard transfers and instant **UPI payment channels** (securing India's #1 banking fraud vector).
* **Network & IP Defense**: Sliding window login rate-limiting (5 requests/min per IP) and progressive bot IP blocking.

This document provides a detailed overview of the system's capabilities, research justification, and a structured engineering roadmap of features under active development for the final hackathon showcase.

---

## 2. Research Context & Academic Novelty

Behavioral biometrics represents the next frontier in cognitive authentication. Unlike physiological biometrics (fingerprint, face ID) which require active user consent and hardware support, behavioral biometrics measure *how* a user interacts with the system, relying on muscle memory and cognitive motor patterns.

### 2.1. Feature Extraction Mechanics
* **Keystroke Dynamics**:
  * *Hold Time (HT)*: The millisecond duration a key is held down ($t_{\text{release}} - t_{\text{press}}$).
  * *Flight Time (FT)*: The transition duration between keys ($t_{\text{press}(n+1)} - t_{\text{release}(n)}$).
  * *Digraphs/Trigraphs*: Timing relationships of key pairings (e.g., transition rhythms for common pairs like `TH`, `ER`, `IN`).
* **Mouse Dynamics**:
  * Spatial coordinates ($x, y$), velocity vectors ($v$), acceleration profiles ($a$), and Jerk ($j$ - the rate of change of acceleration).
  * Trajectory curvature (deviation from the direct line path).

### 2.2. The Multi-Tiered ML Pipeline
1. **Keystroke Profiler (Z-Score)**: Evaluates digraph timings against the user's enrolled profile baseline:
   $$Z = \frac{|x - \mu|}{\sigma}$$
   Where $x$ is the live sample timing, $\mu$ is the enrolled average, and $\sigma$ is the standard deviation. This acts as a fast-response classifier.
2. **Mouse Profiler (Isolation Forest)**: An unsupervised algorithm trained on the user's trajectory baselines. It isolates coordinate streams, mapping straight lines or algorithmic curvatures (indicative of bots) as high anomalies.
3. **XGBoost Fusion Classifier**: Fuses keystroke deviations, mouse anomaly indices, device signatures, network parameters, and session history into a single probability score.

---

## 3. Generalization & Real-World Robustness (Inter-Subject Pipeline)

A common failure point of behavioral biometric systems is "overfitting to synthetic calibration" (where the model works only under perfect lab conditions). To ensure production robustness, we retrained the fusion classifier using 100% real human biometrics: the **CMU Keystroke Dynamics Benchmark** (51 subjects, 400 sessions each) and the **BALABIT Mouse Dynamics Dataset** (legitimate trajectories vs. coordinate-shuffled impostor movements).

* **Leak-Proof Cross-Validation**: We evaluated the model using a **Subject GroupKFold (5 Folds)** protocol grouped by Subject ID. This guarantees that no subject's timing signature leaks between training and validation splits.
* **Intruder Simulation**: We simulated same-device takeovers (matching local IP address and browser fingerprints but presenting anomalous keystroke/mouse dynamics) to force the classifier to rely strictly on biometric behavior.
* **Unified Fusion Classifier Metrics**:
  * **Classification Accuracy**: 83.68%
  * **F1-Score**: 0.8258 (82.58%)
  * **Precision**: 88.54% (high precision minimizes false positives for bank customers)
  * **Recall**: 77.37%

---

## 4. Final Hackathon Implementation Roadmap

For the final evaluation showcase, Team SOLARIS is actively developing four advanced extensions to elevate TRUSTLAYER from a functional Proof of Concept to a production-ready enterprise security platform:

```
               +-------------------------------------------------+
               |             TRUSTLAYER Future Roadmap           |
               +-----------------------+-------------------------+
                                       |
        +------------------------------+------------------------------+
        |                                                             |
        v                                                             v
+-------+-----------------------+                             +-------+-----------------------+
|  1. Client-Side Edge          |                             |  2. Multimodal Mobile         |
|     Inference (WebAssembly)   |                             |     Sensor Fusion             |
|                               |                             |                               |
|  - Compiles models to ONNX    |                             |  - Touch contact area size    |
|  - Zero-latency client checks |                             |  - Gyroscope rotation rates   |
|  - Offline threat blocking    |                             |  - Accelerometer tilt angles  |
+-------+-----------------------+                             +-------+-----------------------+
        |                                                             |
        +------------------------------+------------------------------+
                                       |
        +------------------------------+------------------------------+
        |                                                             |
        v                                                             v
+-------+-----------------------+                             +-------+-----------------------+
|  3. Distributed Threat        |                             |  4. Privacy-Preserving        |
|     Graph Analytics           |                             |     Federated Learning        |
|                               |                             |                               |
|  - Connects compromised IPs   |                             |  - Retrains model on-device   |
|  - Tracks botnet coordinates  |                             |  - Aggregates model weights   |
|  - Exposes coordinated rings  |                             |  - Zero PII leaves client     |
+-------------------------------+                             +-------------------------------+
```

### Roadmap Item 1: Client-Side Edge Inference (ONNX & WebAssembly)
* **Objective**: Shift machine learning scoring from the FastAPI backend directly to the user's browser.
* **Mechanism**: We compile the Z-Score and Isolation Forest models into the **ONNX format** and execute them client-side using **ONNX Runtime Web** (WebAssembly).
* **Impact**:
  * Reduces backend CPU consumption to zero.
  * Guarantees instantaneous (under 200ms) session locking upon intrusion, before malicious data reaches the bank server.

### Roadmap Item 2: Multimodal Mobile Sensor Fusion
* **Objective**: Extend continuous biometric protection to mobile NetBanking applications.
* **Mechanism**: Capture mobile touch interactions:
  * **Touch Contact Area**: The surface area size of touch events (indicates thumb size vs. automated robotic touch inputs).
  * **Swipe Velocity**: Flick trajectory profiles.
  * **Sensor Fusion**: Correlate touch events with high-frequency accelerometer and gyroscope data (capturing the physical hand-tremor and device tilt angles unique to the user).
* **Impact**: Restricts banking fraud on mobile platforms, capturing credential sharing and mobile-based overlay malware.

### Roadmap Item 3: Threat Vector Graph Analytics
* **Objective**: Connect multiple compromised user accounts to identify distributed botnets.
* **Mechanism**: Deploy a graph database layer that correlates session anomalies across different bank accounts.
  * Connects sessions sharing similar IP ranges, browser signatures, and biometric anomalies (e.g. identifying if the same physical human intruder is attempting takeovers across 5 distinct bank accounts).
* **Impact**: Exposes organized cybercrime rings and botnets targeting the banking infrastructure.

### Roadmap Item 4: Privacy-Preserving Federated Learning
* **Objective**: Retrain biometric models continuously without exposing sensitive user telemetry.
* **Mechanism**: Implement Federated Learning:
  * User profiles are retrained locally on-device during active banking usage.
  * Only anonymized mathematical weight updates are sent back to the bank’s central server for global model optimization.
* **Impact**: Complete compliance with global data privacy regulations. Biometric data never leaves the customer's personal device.
