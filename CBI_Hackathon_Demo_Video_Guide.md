# DEMO VIDEO WALKTHROUGH GUIDE — TRUSTLAYER
**AI-Driven Continuous Behavioral Biometrics Authentication for Indian Banking**

*Team SOLARIS | CBI Hackathon 2026 Phase II Project Submission*

---

## 📹 Video Submission Guidelines (MNNIT Rules)
* **Duration**: 5–8 minutes.
* **Recording requirement**: The demonstration must be recorded **without breaks, cuts, or video editing**. It should show a continuous walkthrough of the working prototype.
* **Aspect Ratio**: 16:9 widescreen.
* **Key components to show**: Problem overview, live demo of the application (registration, calibration, owner, intruder, bot flows), key features (explainability, charts), and impact summary.

---

## ⏱️ Video Timeline & Recording Script

### Scene 1: Introduction & Problem Statement (0:00 - 1:00)
* **Visual on screen**: Open the TRUSTLAYER Launcher Landing Page (`http://localhost:8080/`) showing the Solaris title and architecture diagram. Keep your microphone clear and webcam visible if possible.
* **Action**: Introduce yourself, the team, and the project.
* **Voiceover / Speaking Script**:
  > *"Hello respected judges. I am representing Team SOLARIS, and we are demonstrating TRUSTLAYER, our Proof of Concept for a Continuous AI Behavioral Biometric Authentication system. In this video, we will walk you through a live NetBanking portal and show how our system continuously runs keystroke and mouse trajectory analysis to prevent fraud like Account Takeover (ATO) and automated bot scripts, without disrupting legitimate users. Let's start the demo."*

---

### Scene 2: Account Registration & Biometric Enrollment (1:00 - 2:30)
* **Visual on screen**: Click the link to open the **Bharat Suraksha Bank NetBanking Portal** (`http://localhost:8080/bank`). Click **Register Here** to open the registration form.
* **Action**:
  1. Fill out the registration form (Username: `test_solaris`, Password: `Password@26`, name, DOB, etc.).
  2. Click **Register** to show the Account Created page. Point to the generated account number and copy the unique **passphrase** displayed on the screen.
  3. Click **Proceed to Login**, type the username and password, and click **Continue**.
  4. The screen will redirect to the **Enrollment Calibration Wizard**.
  5. In the **Demo Controller** (bottom-right floating panel), ensure **Legitimate Owner** is selected.
  6. Click **⚡ Quick-Fill Credentials** 5 times. Explain that this represents the owner calibrating their typing speed and rhythms.
  7. Drag your mouse along the curved calibration track from **START** to **END** to record mouse movement metrics.
  8. Click **Complete Enrollment** to redirect to the NetBanking dashboard.
* **Voiceover / Speaking Script**:
  > *"First, we register a new user on our simulated portal, Bharat Suraksha Bank. Upon registration, the system generates a secure 11-character passphrase for biometric calibration. When we log in, we enter the Enrollment Wizard. Here, using our Demo Controller, we simulate the owner typing their credentials five times to register keystroke rhythm baselines. We also trace a curved calibration path to map typical mouse velocities and jerk rates. Once completed, our profile is saved securely."*

---

### Scene 3: Legitimate Owner Session Flow (2:30 - 3:30)
* **Visual on screen**: Log out of the NetBanking dashboard to return to the login page.
* **Action**:
  1. Select **Legitimate Owner** in the Demo Controller.
  2. Click **⚡ Quick-Fill Credentials** (the simulator will type the passphrase with the registered owner's rhythm).
  3. Click **Continue** to log in successfully.
  4. Show the banking interface (Account details, transfer form, transaction log).
  5. Perform a transaction (e.g. transfer Rs. 5,000 to payee Priya Sharma). Show that the transaction completes silently and immediately.
* **Voiceover / Speaking Script**:
  > *"Now we log in as the legitimate owner. The SDK captures the keystroke hold and flight intervals, verifying that they match our calibrated profile. Since the behavior matches, our risk index remains low. If we perform a transaction, like sending 5,000 Rupees to a payee, the system processes it instantly without prompting for OTPs or blocking access, preserving a friction-free experience."*

---

### Scene 4: Human Intruder Session Flow & Step-Up (3:30 - 4:30)
* **Visual on screen**: Log out and return to the NetBanking login page.
* **Action**:
  1. Select **Human Intruder** in the Demo Controller.
  2. Click **⚡ Quick-Fill Credentials** (the simulator will type the passphrase with a hesitant, slower rhythm).
  3. Click **Continue**.
  4. An **Identity Verification Step-Up Modal** will pop up on the NetBanking screen.
  5. Point to the modal on the screen. Explain that the typing biometric did not align, triggering an adaptive step-up friction challenge.
* **Voiceover / Speaking Script**:
  > *"Next, let's simulate a human intruder attempting a credential-sharing takeover. We select 'Human Intruder' in the Demo Controller and log in. The intruder types the password, but their rhythm is hesitant, causing a Z-score deviation in flight times. The backend immediately detects this mismatch and triggers our adaptive friction: an inline step-up challenge modal. The user cannot access the account unless they verify their identity."*

---

### Scene 5: Automated Bot Attack & Session Freeze (4:30 - 5:30)
* **Visual on screen**: Close/reload the login page.
* **Action**:
  1. Select **Automated Bot** in the Demo Controller.
  2. Click **⚡ Quick-Fill Credentials** (keys are typed instantly in 0ms).
  3. Click **Continue**.
  4. The NetBanking screen instantly freezes with a red overlay showing **🚨 Session Frozen / Blocked**.
  5. Explain that the bot heuristic engine detected a webdriver / programmatic input signature, blocking all client actions immediately.
* **Voiceover / Speaking Script**:
  > *"Let's test an automated bot attack. We select 'Automated Bot' and log in. Bots type characters instantaneously with 0ms intervals. Our client-side SDK and backend heuristics detect this programmatic signature in microseconds. The system immediately terminates the session and locks the screen with a red overlay, blocking the bot from performing any operations."*

---

### Scene 6: SOC Analyst Overview & Triage (5:30 - 7:00)
* **Visual on screen**: Switch browser tabs to the **TRUSTLAYER SOC Dashboard** (`http://localhost:8080/dashboard`).
* **Action**:
  1. Show the header stats: Active sessions count (14), average risk index, and frozen count (2).
  2. Point to the **Active Alerts** list and select our active bot or intruder session.
  3. In the **Deep-Dive Workspace** at the bottom, point to the **SHAP-Lite Explainability** bar chart showing timing deviations.
  4. Point to the **Mouse Trajectory** graph comparing the recorded path (straight red lines for bots) to the owner's calibrated green line.
  5. Demonstrate analyst triage:
     - Select a card and click **Force Freeze** (moves it to the **Frozen Sessions** tab with a score of 99.0).
     - Select another card and click **Dismiss** (marks it green as `✓ Cleared` and hides the buttons).
  6. Click the **Database Audit** tab, type `test_solaris` in the search bar, click **Execute Search**, and show the historical log lookup.
* **Voiceover / Speaking Script**:
  > *"Now we switch to the Security Operations Center Dashboard. Here, security analysts monitor active NetBanking sessions in real time. We see our active sessions listed. If we select the bot alert session, the Deep-Dive Workspace opens. We see real-time SHAP-lite feature contributions explaining the risk. We can also compare mouse trajectories—anomalous robot straight lines are highlighted in red. The analyst can immediately click 'Force Freeze' to lock down the threat permanently, or 'Dismiss' to clear it if it was resolved as a false positive."*

---

### Scene 7: Conclusion & Wrap-Up (7:00 - 8:00)
* **Visual on screen**: Bring the PowerPoint slide outline or the Technical Documentation outline back on screen, showing the F1 metrics.
* **Voiceover / Speaking Script**:
  > *"In summary, TRUSTLAYER provides continuous, friction-free protection for online banking sessions. By using real-world CMU and BALABIT human biometric training data, we achieved a leak-proof F1 classification score of 82.58% and generalized takeover protection. This Proof of Concept demonstrates the practical feasibility, technical robustness, and immediate applicability of our solution. Thank you for your time and evaluation."*
