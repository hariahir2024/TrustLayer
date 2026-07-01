# Third-Party Acknowledgments

**TrustLayer — Team SOLARIS | CBI Hackathon 2026**

This document provides full acknowledgment for all third-party datasets, libraries, frameworks, and APIs used in this project, as required by the CBI Hackathon 2026 Phase II submission guidelines.

---

## Open Datasets

### 1. CMU Keystroke Dynamics Benchmark Dataset
- **Source**: Carnegie Mellon University, School of Computer Science
- **Citation**: Killourhy, K., & Maxion, R. (2009). *Comparing Anomaly-Detection Algorithms for Keystroke Dynamics*. IEEE/IFIP International Conference on Dependable Systems & Networks (DSN-2009).
- **URL**: https://www.cs.cmu.edu/~keystroke/
- **License**: Research use — free for academic and research purposes with attribution
- **Usage in TrustLayer**: Training the keystroke LSTM autoencoder generic baseline model (`lstm_keystroke_pretrained.pt`). The dataset contains 51 subjects each typing a password 400 times, providing 17,340 labeled keystroke sequences used to establish population-level typing rhythm norms.

### 2. Balabit Mouse Dynamics Challenge Dataset
- **Source**: Balabit Ltd., released as part of the User Behavior Analytics Challenge
- **Citation**: Balabit (2016). *Balabit Mouse Dynamics Challenge*. Kaggle / Balabit Research.
- **URL**: https://github.com/balabit/Mouse-Dynamics-Challenge
- **License**: CC BY 4.0 (Creative Commons Attribution 4.0 International)
- **Usage in TrustLayer**: Training the mouse trajectory LSTM autoencoder generic baseline model (`lstm_mouse_pretrained.pt`). The dataset contains mouse movement logs from 10 users over 76,543 sessions in a real corporate network environment.

### 3. KMT Behavioral Biometrics Dataset (Real Session Data)
- **Source**: KMT Research / Kaggle
- **License**: CC BY-NC-SA 4.0 (research use)
- **Usage in TrustLayer**: Retraining the XGBoost fusion classifier (`xgboost_fusion.pkl`) on real-world web interaction sessions. The dataset contains 88 users across 1,760 real behavioral sessions, used for inter-subject classification training (genuine user vs. impostor).

---

## Open-Source Libraries & Frameworks

### Backend

| Library | Version | License | Purpose |
|---------|---------|---------|---------|
| **FastAPI** | 0.136.3 | MIT | REST API server, WebSocket endpoints, static file serving |
| **Uvicorn** | 0.49.0 | BSD-3-Clause | ASGI server for FastAPI |
| **PyTorch** | 2.5.1 | BSD-3-Clause | LSTM autoencoder training and inference |
| **XGBoost** | 3.2.0 | Apache 2.0 | Fusion risk classifier (gradient boosting) |
| **scikit-learn** | 1.9.0 | BSD-3-Clause | Isolation Forest, StandardScaler, model utilities |
| **NumPy** | 2.4.4 | BSD-3-Clause | Numerical computation, Z-score calculations |
| **Pandas** | 3.0.3 | BSD-3-Clause | Dataset loading and preprocessing |
| **Joblib** | 1.5.3 | BSD-3-Clause | Model serialization and parallel processing |
| **Websockets** | 16.0 | BSD-3-Clause | WebSocket protocol support |
| **Python standard library** | 3.11 | PSF | `sqlite3`, `json`, `logging`, `os`, `time`, `hashlib`, `uuid` |

### Frontend

| Library | Version | License | Purpose |
|---------|---------|---------|---------|
| **Chart.js** | Latest (CDN) | MIT | SOC dashboard: risk score charts, feature importance bars, heartbeat graphs |
| **Tabler Icons** | Latest (CDN) | MIT | SOC dashboard icon system |
| **Google Fonts — Inter** | Latest (CDN) | Open Font License | Typography across all pages |

### Development Tools (Not included in submission)

| Tool | License | Purpose |
|------|---------|---------|
| **Antigravity (Google DeepMind)** | Commercial | AI pair-programming assistant — code suggestions reviewed and validated by team |

---

## Research Papers Referenced

The design and architecture of TrustLayer draws on the following published academic research:

1. **Continuous Authentication Using Mouse Dynamics** — Shen, C., et al. (2012). *IEEE Transactions on Human-Machine Systems*.

2. **Keystroke Dynamics for User Authentication** — Killourhy, K. & Maxion, R. (2009). *DSN-2009*.

3. **MBBFAuth: Multimodal Behavioral Biometrics Fusion for Continuous Authentication** — Referenced from provided literature.

4. **DABBiT: A Drift-Adaptive Behavioral Biometrics Framework** — Referenced from provided literature (Tanzanian Internet Banking study).

5. **SHAP (SHapley Additive exPlanations)** — Lundberg, S. M., & Lee, S. I. (2017). *A Unified Approach to Interpreting Model Predictions*. NeurIPS 2017.

---

## RBI Regulatory References

- Reserve Bank of India, *Master Direction on IT Framework for the NBFC Sector* (2017)
- RBI Annual Report 2023–24: Banking Fraud Statistics
- RBI Circular on *Guidelines on Digital Payment Security Controls* (RBI/2020-21/66)

---

*All third-party components are used in compliance with their respective licenses. Where licenses require attribution, it has been provided above.*

*TrustLayer — Team SOLARIS | CBI Hackathon 2026 | MNNIT Allahabad*
