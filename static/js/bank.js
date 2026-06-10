/**
 * BehaviorShield — bank.js
 * Team SOLARIS | Cyber Security Hackathon 2026 | MNNIT Allahabad
 * 
 * Client-side logic for Vishwa Bank Simulator.
 * Integrates with BehaviorShield Telemetry SDK (sdk.js) to sendtiming details.
 * Implements interactive enrollment, login, fund transfer, re-authentication,
 * and a floating developer panel for persona simulations.
 */

document.addEventListener('DOMContentLoaded', function() {
    // UI Elements
    const views = {
        username: document.getElementById('username-view'),
        enroll: document.getElementById('enroll-view'),
        login: document.getElementById('login-view'),
        portal: document.getElementById('portal-view')
    };

    const inputs = {
        username: document.getElementById('start-username'),
        enroll: document.getElementById('enroll-input'),
        loginPass: document.getElementById('login-password'),
        challenge: document.getElementById('challenge-input'),
        otp: document.getElementById('otp-input'),
        txPayee: document.getElementById('tx-payee'),
        txAccount: document.getElementById('tx-account'),
        txAmount: document.getElementById('tx-amount')
    };

    const buttons = {
        nextStep: document.getElementById('btn-next-step'),
        enrollCancel: document.getElementById('enroll-cancel'),
        enrollComplete: document.getElementById('enroll-complete-btn'),
        loginBack: document.getElementById('login-back'),
        loginSubmit: document.getElementById('login-submit'),
        logout: document.getElementById('logout-btn'),
        txSubmit: document.getElementById('tx-submit'),
        challengeSubmit: document.getElementById('challenge-submit-btn'),
        otpSubmit: document.getElementById('otp-submit-btn'),
        otpCancel: document.getElementById('otp-cancel-btn'),
        quickFill: document.getElementById('btn-quick-fill'),
        freezeReset: document.getElementById('btn-freeze-reset')
    };

    const displays = {
        enrollProgressText: document.getElementById('enroll-progress-text'),
        enrollProgressBar: document.getElementById('enroll-progress-bar'),
        liveRiskScore: document.getElementById('live-risk-score'),
        liveRiskBadge: document.getElementById('live-risk-badge'),
        liveRiskBar: document.getElementById('live-risk-bar'),
        liveInterval: document.getElementById('live-interval-text'),
        challengeAttempts: document.getElementById('challenge-attempts'),
        challengeError: document.getElementById('challenge-error'),
        otpError: document.getElementById('otp-error'),
        loginMessage: document.getElementById('login-message'),
        calibrationSuccess: document.getElementById('calibration-success')
    };

    const overlays = {
        freeze: document.getElementById('freeze-overlay'),
        challenge: document.getElementById('challenge-backdrop'),
        otp: document.getElementById('otp-backdrop')
    };

    // State Variables
    let currentUsername = "";
    let sessionId = null;
    let enrollmentSamplesCollected = 0;
    let isMouseCalibrated = false;
    let selectedPersona = "owner"; // 'owner' | 'intruder' | 'bot'
    let currentTransactionPayload = null;
    let currentFocusFieldTs = null;

    // Monitor input fields in dashboard
    BehaviorShield.monitorInput(inputs.enroll);
    BehaviorShield.monitorInput(inputs.loginPass);
    BehaviorShield.monitorInput(inputs.challenge);
    BehaviorShield.monitorInput(inputs.txPayee);
    BehaviorShield.monitorInput(inputs.txAccount);
    BehaviorShield.monitorInput(inputs.txAmount);

    // Track focus timestamps manually for the custom SDK timing
    inputs.enroll.addEventListener('focus', () => currentFocusFieldTs = Date.now());
    inputs.loginPass.addEventListener('focus', () => currentFocusFieldTs = Date.now());
    inputs.challenge.addEventListener('focus', () => currentFocusFieldTs = Date.now());

    // ==========================================
    // VIEW TRANSITIONS
    // ==========================================
    function showView(viewName) {
        Object.keys(views).forEach(key => {
            if (key === viewName) {
                views[key].classList.remove('hidden');
            } else {
                views[key].classList.add('hidden');
            }
        });

        // Toggle logout button visibility
        if (viewName === 'portal') {
            buttons.logout.style.display = 'inline-flex';
        } else {
            buttons.logout.style.display = 'none';
        }
    }

    // ==========================================
    // USERNAME GATE / VERIFY ENROLLMENT
    // ==========================================
    buttons.nextStep.addEventListener('click', async function() {
        const username = inputs.username.value.trim();
        if (!username) {
            alert("Please enter a username.");
            return;
        }

        currentUsername = username;
        
        // Attempt a login call with empty key_events to check if username is enrolled
        try {
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: currentUsername,
                    key_events: [],
                    device_info: BehaviorShield.getDeviceFingerprint()
                })
            });

            if (!response.ok) {
                alert("Server error checking user status.");
                return;
            }

            const data = await response.json();
            
            // Clean up old session first if exists
            BehaviorShield.destroy();

            if (data.enrolled) {
                // User is already enrolled. Go to Login view.
                document.getElementById('login-username-readonly').value = currentUsername;
                displays.loginMessage.textContent = "Welcome back! Enter your NetBanking passphrase.";
                showView('login');
            } else {
                // User needs enrollment. Go to Enrollment view.
                showView('enroll');
                resetEnrollmentProgress();
            }
        } catch (err) {
            console.error("Error checking user:", err);
            alert("Connection error. Is app.py running?");
        }
    });

    // ==========================================
    // ENROLLMENT LOGIC
    // ==========================================
    function resetEnrollmentProgress() {
        enrollmentSamplesCollected = 0;
        isMouseCalibrated = false;
        displays.enrollProgressText.textContent = "Sample 0/5";
        displays.enrollProgressBar.style.width = "0%";
        inputs.enroll.value = "";
        inputs.enroll.disabled = false;
        document.getElementById('enroll-mouse-step').classList.add('hidden');
        displays.calibrationSuccess.classList.add('hidden');
        buttons.enrollComplete.disabled = true;
    }

    inputs.enroll.addEventListener('keydown', async function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            const text = inputs.enroll.value.trim();
            if (text !== "SecureAuth@India1") {
                alert("Passphrase does not match exactly! Please type: SecureAuth@India1");
                inputs.enroll.value = "";
                BehaviorShield.extractKeyEvents(); // clear timing buffer
                return;
            }

            const keyEvents = BehaviorShield.extractKeyEvents();

            try {
                const response = await fetch('/api/enroll', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: currentUsername,
                        key_events: keyEvents,
                        field_focus_ts: currentFocusFieldTs
                    })
                });

                const data = await response.json();
                enrollmentSamplesCollected = data.count;

                displays.enrollProgressText.textContent = `Sample ${enrollmentSamplesCollected}/5`;
                displays.enrollProgressBar.style.width = `${(enrollmentSamplesCollected / 5) * 100}%`;
                inputs.enroll.value = "";
                currentFocusFieldTs = Date.now();

                if (data.complete) {
                    inputs.enroll.disabled = true;
                    // Show Step 2: Mouse calibration
                    document.getElementById('enroll-mouse-step').classList.remove('hidden');
                    initializeMouseCalibration();
                }
            } catch (err) {
                console.error("Enrollment failed:", err);
                alert("Failed to submit sample.");
            }
        }
    });

    buttons.enrollCancel.addEventListener('click', () => showView('username'));

    // Interactive mouse tracing calibration
    function initializeMouseCalibration() {
        const area = document.getElementById('mouse-path-area');
        let inProgress = false;

        area.addEventListener('mouseenter', function() {
            inProgress = true;
        });

        area.addEventListener('mouseleave', function() {
            inProgress = false;
        });

        // When the user moves the mouse inside the canvas, if they sweep left-to-right, we mark it done
        area.addEventListener('mousemove', function(e) {
            if (!inProgress || isMouseCalibrated) return;
            const rect = area.getBoundingClientRect();
            const x = e.clientX - rect.left;
            
            // If mouse reaches near the end circle (width ~ 520px)
            if (x > 480) {
                isMouseCalibrated = true;
                displays.calibrationSuccess.classList.remove('hidden');
                buttons.enrollComplete.disabled = false;
                console.log("[Vishwa Bank] Mouse calibration complete.");
            }
        });
    }

    buttons.enrollComplete.addEventListener('click', function() {
        // Enrollment completed, proceed back to username gate which will now route to login
        alert("Enrollment baseline registered successfully!");
        showView('username');
    });

    // ==========================================
    // LOGIN LOGIC
    // ==========================================
    buttons.loginBack.addEventListener('click', () => showView('username'));

    buttons.loginSubmit.addEventListener('click', handleLogin);
    inputs.loginPass.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            handleLogin();
        }
    });

    async function handleLogin() {
        const pass = inputs.loginPass.value.trim();
        if (!pass) {
            alert("Please enter your password.");
            return;
        }

        // Verify username/passphrase for PoC
        if (pass !== "SecureAuth@India1") {
            alert("Invalid credentials. Enter the enrolled passphrase.");
            inputs.loginPass.value = "";
            BehaviorShield.extractKeyEvents(); // clear timing buffer
            return;
        }

        const keyEvents = BehaviorShield.extractKeyEvents();
        const deviceFingerprint = BehaviorShield.getDeviceFingerprint();

        try {
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: currentUsername,
                    key_events: keyEvents,
                    field_focus_ts: currentFocusFieldTs,
                    device_info: deviceFingerprint
                })
            });

            if (!response.ok) {
                alert("Login failed.");
                return;
            }

            const data = await response.json();
            
            if (data.is_bot) {
                showFreezeOverlay();
                return;
            }

            if (data.action === 'FREEZE_SESSION' || data.action === 'FREEZE_AND_ALERT' || data.action === 'SILENT_BLOCK') {
                showFreezeOverlay();
                return;
            }

            // Successfully logged in!
            sessionId = data.session_id;
            inputs.loginPass.value = "";
            
            // Initialize Behavioral Telemetry SDK
            BehaviorShield.init(sessionId, currentUsername);
            
            // Update Dashboard Risk displays initially
            updateRiskMetrics(data.score, data.band, 30);
            
            showView('portal');
            console.log("[Vishwa Bank] Logged in successfully. Session:", sessionId);
            
        } catch (err) {
            console.error("Login Error:", err);
            alert("Error logging in.");
        }
    }

    buttons.logout.addEventListener('click', function() {
        BehaviorShield.destroy();
        sessionId = null;
        currentUsername = "";
        inputs.username.value = "";
        showView('username');
    });

    // ==========================================
    // HEARTBEAT / SCORING UPDATES
    // ==========================================
    window.addEventListener('behaviorshield_update', function(e) {
        const data = e.detail;
        console.log("[Vishwa Bank] Score updated:", data);
        updateRiskMetrics(data.score, data.band, data.scoring_interval);
    });

    window.addEventListener('behaviorshield_freeze', function(e) {
        console.warn("[Vishwa Bank] Session Frozen event received!");
        showFreezeOverlay();
    });

    window.addEventListener('behaviorshield_challenge', function(e) {
        console.warn("[Vishwa Bank] Step-up challenge requested!");
        showChallengeModal();
    });

    function updateRiskMetrics(score, band, interval) {
        displays.liveRiskScore.textContent = score.toFixed(1);
        displays.liveInterval.textContent = interval;

        // Set colors and classes based on band
        displays.liveRiskScore.className = "score-number";
        displays.liveRiskBar.className = "score-bar-fill";
        displays.liveRiskBadge.className = "badge";

        displays.liveRiskBar.style.width = `${score}%`;

        if (band === 'GREEN') {
            displays.liveRiskScore.classList.add('green');
            displays.liveRiskBar.classList.add('green');
            displays.liveRiskBadge.classList.add('badge-green');
            displays.liveRiskBadge.textContent = "Low Risk (Silent)";
        } else if (band === 'AMBER_LOW' || band === 'AMBER_MID') {
            displays.liveRiskScore.classList.add('amber');
            displays.liveRiskBar.classList.add('amber');
            displays.liveRiskBadge.classList.add('badge-amber');
            displays.liveRiskBadge.textContent = band === 'AMBER_LOW' ? "Elevated (Monitor)" : "Medium Anomaly (Challenge)";
        } else if (band === 'AMBER_HIGH') {
            displays.liveRiskScore.classList.add('orange');
            displays.liveRiskBar.classList.add('orange');
            displays.liveRiskBadge.classList.add('badge-orange');
            displays.liveRiskBadge.textContent = "High Anomaly (OTP Required)";
        } else {
            displays.liveRiskScore.classList.add('red');
            displays.liveRiskBar.classList.add('red');
            displays.liveRiskBadge.classList.add('badge-red');
            displays.liveRiskBadge.textContent = "Critical (Session Lock)";
        }
    }

    // ==========================================
    // SESSION FREEZE
    // ==========================================
    function showFreezeOverlay() {
        overlays.freeze.classList.remove('hidden');
        BehaviorShield.destroy();
    }

    buttons.freezeReset.addEventListener('click', function() {
        overlays.freeze.classList.add('hidden');
        sessionId = null;
        currentUsername = "";
        inputs.username.value = "";
        showView('username');
    });

    // ==========================================
    // STEP-UP PASSPHRASE CHALLENGE (AMBER MID)
    // ==========================================
    function showChallengeModal() {
        overlays.challenge.classList.remove('hidden');
        inputs.challenge.value = "";
        displays.challengeError.classList.add('hidden');
        inputs.challenge.focus();
        currentFocusFieldTs = Date.now();
    }

    buttons.challengeSubmit.addEventListener('click', submitChallenge);
    inputs.challenge.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            submitChallenge();
        }
    });

    async function submitChallenge() {
        const text = inputs.challenge.value.trim();
        if (text !== "SecureAuth@India1") {
            displays.challengeError.textContent = "Passphrase does not match exactly!";
            displays.challengeError.classList.remove('hidden');
            inputs.challenge.value = "";
            BehaviorShield.extractKeyEvents(); // clear
            return;
        }

        const keyEvents = BehaviorShield.extractKeyEvents();

        try {
            const response = await fetch('/api/reauth', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    key_events: keyEvents,
                    field_focus_ts: currentFocusFieldTs
                })
            });

            const data = await response.json();
            if (data.success) {
                overlays.challenge.classList.add('hidden');
                updateRiskMetrics(data.new_score, 'GREEN', 30);
                alert("Identity verified! Risk score has been reset.");
            } else {
                if (data.escalate) {
                    overlays.challenge.classList.add('hidden');
                    alert("Max challenge attempts exceeded! Restrictions applied.");
                    updateRiskMetrics(data.new_score, data.band, 30);
                } else {
                    displays.challengeAttempts.textContent = `Attempts remaining: ${data.attempts_remaining}`;
                    displays.challengeError.textContent = data.message;
                    displays.challengeError.classList.remove('hidden');
                    inputs.challenge.value = "";
                    currentFocusFieldTs = Date.now();
                }
            }
        } catch (err) {
            console.error("Challenge submit failed:", err);
            alert("Error submitting challenge.");
        }
    }

    // ==========================================
    // FUND TRANSFER LOGIC (AMBER HIGH / OTP)
    // ==========================================
    buttons.txSubmit.addEventListener('click', async function() {
        const payee = inputs.txPayee.value.trim();
        const account = inputs.txAccount.value.trim();
        const amountStr = inputs.txAmount.value.trim();

        if (!payee || !account || !amountStr) {
            alert("Please fill all fund transfer fields.");
            return;
        }

        const amount = parseFloat(amountStr);

        currentTransactionPayload = {
            session_id: sessionId,
            action_type: 'transfer',
            amount: amount,
            description: `Transfer to ${payee}`
        };

        // Notify session action before transaction
        await fetch('/api/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, action_type: 'transfer' })
        });

        // Trigger manual SDK telemetry flush before submit
        await BehaviorShield.forceSubmitScore();

        // Send transaction
        sendTransactionRequest();
    });

    async function sendTransactionRequest() {
        try {
            const response = await fetch('/api/transaction', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(currentTransactionPayload)
            });

            const data = await response.json();

            if (data.allowed) {
                if (data.otp_required) {
                    // Show OTP Verification
                    showOtpModal();
                } else {
                    // Allowed directly!
                    processSuccessfulTransaction();
                }
            } else {
                // Denied
                alert(`Transaction Blocked: ${data.message}`);
            }
        } catch (err) {
            console.error("Transaction Error:", err);
            alert("Error processing transaction.");
        }
    }

    function showOtpModal() {
        overlays.otp.classList.remove('hidden');
        inputs.otp.value = "";
        displays.otpError.classList.add('hidden');
        inputs.otp.focus();
    }

    buttons.otpCancel.addEventListener('click', () => overlays.otp.classList.add('hidden'));

    buttons.otpSubmit.addEventListener('click', submitOtp);
    inputs.otp.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            submitOtp();
        }
    });

    function submitOtp() {
        const code = inputs.otp.value.trim();
        // PoC accepts any 6-digit OTP (e.g., 123456)
        if (code.length === 6 && /^\d+$/.test(code)) {
            overlays.otp.classList.add('hidden');
            processSuccessfulTransaction();
        } else {
            displays.otpError.classList.remove('hidden');
            inputs.otp.value = "";
        }
    }

    function processSuccessfulTransaction() {
        alert("Transaction processed successfully!");
        
        // Add row to transactions table
        const tbody = document.getElementById('transaction-rows');
        const newRow = document.createElement('tr');
        newRow.innerHTML = `
            <td class="text-mono text-xs">Today</td>
            <td>Transfer to ${inputs.txPayee.value}</td>
            <td class="text-mono text-brand fw-600">- ₹ ${parseFloat(inputs.txAmount.value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
            <td><span class="badge badge-green">Success</span></td>
        `;
        tbody.insertBefore(newRow, tbody.firstChild);

        // Deduct balance
        const balanceEl = document.querySelector('.balance-amount');
        let currentBalance = parseFloat(balanceEl.textContent.replace('₹', '').replace(/,/g, '').trim());
        currentBalance -= parseFloat(inputs.txAmount.value);
        balanceEl.textContent = `₹ ${currentBalance.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

        // Clear fields
        inputs.txPayee.value = "";
        inputs.txAccount.value = "";
        inputs.txAmount.value = "";
    }

    // ==========================================
    // FLOATING DEVELOPER SIMULATOR PANEL
    // ==========================================
    const toggle = document.getElementById('demo-widget-toggle');
    const widget = document.getElementById('demo-widget');

    toggle.addEventListener('click', function() {
        widget.classList.toggle('collapsed');
        const icon = document.getElementById('demo-toggle-icon');
        icon.textContent = widget.classList.contains('collapsed') ? '▲' : '▼';
    });

    // Handle Persona selections
    const simButtons = document.querySelectorAll('.sim-mode-btn');
    simButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            simButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedPersona = btn.getAttribute('data-persona');
            console.log(`[Simulator] Active Persona: ${selectedPersona}`);
        });
    });

    // Auto fill credentials and trigger typing telemetry simulation
    buttons.quickFill.addEventListener('click', function() {
        // Determine which screen is active
        const isLoginActive = !views.login.classList.contains('hidden');
        const isEnrollActive = !views.enroll.classList.contains('hidden');
        const isChallengeActive = !overlays.challenge.classList.contains('hidden');

        let targetInput = null;
        if (isEnrollActive) targetInput = inputs.enroll;
        else if (isLoginActive) targetInput = inputs.loginPass;
        else if (isChallengeActive) targetInput = inputs.challenge;

        if (!targetInput) {
            alert("Quick-Fill is only active on Enrollment, Login, or step-up inputs.");
            return;
        }

        const text = "SecureAuth@India1";
        simulateTyping(targetInput, text, selectedPersona);
    });

    /**
     * Programmatic typing rhythm injector
     */
    function simulateTyping(inputElement, text, persona) {
        inputElement.value = "";
        inputElement.focus();
        currentFocusFieldTs = Date.now();

        // Clear SDK key buffers
        BehaviorShield.extractKeyEvents();

        let index = 0;
        let runningTimeOffset = 0;

        function typeNextChar() {
            if (index >= text.length) {
                // If it's enrollment or login, press Enter automatically!
                setTimeout(() => {
                    const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter' });
                    inputElement.dispatchEvent(enterEvent);
                }, 200);
                return;
            }

            const char = text[index];
            const code = `Key${char.toUpperCase()}`; // approximation for SDK maps

            // Define timing parameters based on persona
            let dwellTime = 90;
            let flightTime = 120;

            if (persona === 'owner') {
                dwellTime = 70 + Math.random() * 40;
                flightTime = 80 + Math.random() * 60;
            } else if (persona === 'intruder') {
                dwellTime = 150 + Math.random() * 80;
                flightTime = 220 + Math.random() * 150;
            } else if (persona === 'bot') {
                dwellTime = 1;
                flightTime = 1;
            }

            // Simulate keydown
            setTimeout(function() {
                // Trigger real keydown
                const downEvent = new KeyboardEvent('keydown', { key: char, code: code });
                inputElement.dispatchEvent(downEvent);

                // Simulate keyup after dwellTime
                setTimeout(function() {
                    inputElement.value += char;
                    const upEvent = new KeyboardEvent('keyup', { key: char, code: code });
                    inputElement.dispatchEvent(upEvent);

                    index++;
                    typeNextChar();
                }, dwellTime);

            }, flightTime);
        }

        // Start typing
        typeNextChar();
    }
});
