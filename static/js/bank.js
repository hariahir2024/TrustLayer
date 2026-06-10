/**
 * BehaviorShield — bank.js
 * Team SOLARIS | Cyber Security Hackathon 2026 | MNNIT Allahabad
 * 
 * Redesigned client-side portal logic for Vishwa Bank NetBanking.
 * Integrates with BehaviorShield Telemetry SDK (sdk.js) to monitor sessions.
 * Manages multi-tab routing, persistent local storage databases,
 * payee registration, transfers, statement searches, and timing presets.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Auth UI View elements
    const authContainer = document.getElementById('auth-container');
    const views = {
        username: document.getElementById('username-view'),
        enroll: document.getElementById('enroll-view'),
        login: document.getElementById('login-view'),
        portal: document.getElementById('portal-view')
    };

    // Dashboard Tabs
    const tabs = {
        dashboard: document.getElementById('page-dashboard'),
        transfer: document.getElementById('page-transfer'),
        payees: document.getElementById('page-payees'),
        statements: document.getElementById('page-statements')
    };

    // Inputs
    const inputs = {
        username: document.getElementById('start-username'),
        enroll: document.getElementById('enroll-input'),
        loginPass: document.getElementById('login-password'),
        challenge: document.getElementById('challenge-input'),
        otp: document.getElementById('otp-input'),
        
        // Redesigned Transfer
        txMethod: document.getElementById('tx-method'),
        txPayeeSelect: document.getElementById('tx-payee-select'),
        txAmount: document.getElementById('tx-amount'),
        txDesc: document.getElementById('tx-desc'),
        
        // Payee Registry
        payeeName: document.getElementById('new-payee-name'),
        payeeAccount: document.getElementById('new-payee-account'),
        payeeIfsc: document.getElementById('new-payee-ifsc'),
        payeeLimit: document.getElementById('new-payee-limit'),

        // Statements
        stmtSearch: document.getElementById('stmt-search'),
        stmtFilter: document.getElementById('stmt-filter')
    };

    // Buttons
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
        freezeReset: document.getElementById('btn-freeze-reset'),
        addPayee: document.getElementById('btn-add-payee'),
        stmtDownload: document.getElementById('stmt-download')
    };

    // Displays
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

    // Overlay modls
    const overlays = {
        freeze: document.getElementById('freeze-overlay'),
        challenge: document.getElementById('challenge-backdrop'),
        otp: document.getElementById('otp-backdrop')
    };

    // State
    let currentUsername = "";
    let sessionId = null;
    let enrollmentSamplesCollected = 0;
    let isMouseCalibrated = false;
    let selectedPersona = "owner"; 
    let currentTransactionPayload = null;
    let currentFocusFieldTs = null;

    // Local DB variables loaded per user
    let userPayees = [];
    let userTransactions = [];
    let userSavingsBalance = 423891.50;

    // Monitor input elements with SDK
    BehaviorShield.monitorInput(inputs.enroll);
    BehaviorShield.monitorInput(inputs.loginPass);
    BehaviorShield.monitorInput(inputs.challenge);
    BehaviorShield.monitorInput(inputs.txAmount);
    BehaviorShield.monitorInput(inputs.txDesc);
    BehaviorShield.monitorInput(inputs.payeeName);
    BehaviorShield.monitorInput(inputs.payeeAccount);
    BehaviorShield.monitorInput(inputs.payeeIfsc);
    BehaviorShield.monitorInput(inputs.payeeLimit);

    // Timing helper focus hooks
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

        if (viewName === 'portal') {
            authContainer.classList.add('hidden');
            buttons.logout.style.display = 'inline-flex';
            switchBankTab('dashboard'); // default to dashboard tab
        } else {
            authContainer.classList.remove('hidden');
            buttons.logout.style.display = 'none';
        }
    }

    // Tab Switching inside Portal
    window.switchBankTab = function(tabName) {
        Object.keys(tabs).forEach(key => {
            if (key === tabName) {
                tabs[key].classList.remove('hidden');
                document.getElementById(`tab-nav-${key}`).classList.add('active');
            } else {
                tabs[key].classList.add('hidden');
                document.getElementById(`tab-nav-${key}`).classList.remove('active');
            }
        });
    };

    // Register click events to nav sidebar items
    Object.keys(tabs).forEach(key => {
        document.getElementById(`tab-nav-${key}`).addEventListener('click', () => switchBankTab(key));
    });

    // ==========================================
    // LOCAL STORAGE DATABASE MANAGEMENT
    // ==========================================
    function loadUserDatabase() {
        const prefix = `vb_${currentUsername}_`;
        
        // Load Balance
        const savedBalance = localStorage.getItem(`${prefix}balance`);
        userSavingsBalance = savedBalance ? parseFloat(savedBalance) : 423891.50;
        updateBalanceDisplays();

        // Load Payees
        const savedPayees = localStorage.getItem(`${prefix}payees`);
        if (savedPayees) {
            userPayees = JSON.parse(savedPayees);
        } else {
            // Default initial payees
            userPayees = [
                { name: "Ramesh Kumar", account: "5010023912903", ifsc: "SBIN0001802", limit: 100000 },
                { name: "Asha Sharma", account: "1009023841029", ifsc: "HDFC0000104", limit: 50000 }
            ];
            savePayees();
        }
        renderPayees();

        // Load Transactions
        const savedTx = localStorage.getItem(`${prefix}transactions`);
        if (savedTx) {
            userTransactions = JSON.parse(savedTx);
        } else {
            // Default transactions
            userTransactions = [
                { date: "10 Jun", ref: "TXN098412908", desc: "Electricity Bill Payment", type: "DEBIT", debit: 4200.00, credit: 0, status: "Paid" },
                { date: "08 Jun", ref: "TXN092489104", desc: "Salary Credited", type: "CREDIT", debit: 0, credit: 95000.00, status: "Success" },
                { date: "05 Jun", ref: "TXN084129841", desc: "Transfer to Asha Sharma", type: "DEBIT", debit: 12500.00, credit: 0, status: "Success" }
            ];
            saveTransactions();
        }
        renderTransactions();
    }

    function savePayees() {
        localStorage.setItem(`vb_${currentUsername}_payees`, JSON.stringify(userPayees));
    }

    function saveTransactions() {
        localStorage.setItem(`vb_${currentUsername}_transactions`, JSON.stringify(userTransactions));
    }

    function saveBalance() {
        localStorage.setItem(`vb_${currentUsername}_balance`, userSavingsBalance.toString());
    }

    function updateBalanceDisplays() {
        const amtStr = `₹ ${userSavingsBalance.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        document.querySelectorAll('.balance-amount').forEach(el => el.textContent = amtStr);
    }

    // ==========================================
    // RENDER LAYOUTS
    // ==========================================
    function renderPayees() {
        const container = document.getElementById('payee-list-container');
        const select = inputs.txPayeeSelect;
        
        container.innerHTML = '';
        select.innerHTML = '<option value="">-- Choose Beneficiary --</option>';

        if (userPayees.length === 0) {
            container.innerHTML = '<p class="text-muted text-xs p-4">No registered beneficiaries found.</p>';
            return;
        }

        userPayees.forEach((p, idx) => {
            // Append select dropdown option
            const opt = document.createElement('option');
            opt.value = idx;
            opt.textContent = `${p.name} (A/C: ...${p.account.slice(-4)})`;
            select.appendChild(opt);

            // Append payee grid card
            const card = document.createElement('div');
            card.className = 'payee-card';
            card.innerHTML = `
                <div class="payee-card-header">
                    <div class="flex items-center gap-2">
                        <div class="payee-avatar">${p.name[0]}</div>
                        <strong>${p.name}</strong>
                    </div>
                    <button class="btn btn-ghost btn-sm text-xs" style="color: var(--red); border-color: rgba(239, 68, 68, 0.2);" onclick="removePayee(${idx})">Remove</button>
                </div>
                <div class="text-xs text-secondary mt-1">A/C: <span class="text-mono">${p.account}</span></div>
                <div class="text-xs text-secondary">IFSC: <span class="text-mono">${p.ifsc}</span></div>
                <div class="text-xs text-secondary" style="border-top: 1px solid var(--border); padding-top: 0.4rem; margin-top: 0.2rem;">
                  Limit: <strong class="text-mono">₹${p.limit.toLocaleString('en-IN')}</strong>
                </div>
            `;
            container.appendChild(card);
        });
    }

    window.removePayee = function(index) {
        if (confirm("Are you sure you want to remove this payee?")) {
            userPayees.splice(index, 1);
            savePayees();
            renderPayees();
        }
    };

    function renderTransactions() {
        const dashboardTbody = document.getElementById('transaction-rows');
        const statementsTbody = document.getElementById('statements-table-body');
        
        dashboardTbody.innerHTML = '';
        statementsTbody.innerHTML = '';

        if (userTransactions.length === 0) {
            dashboardTbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No recent activities.</td></tr>';
            statementsTbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No entries match criteria.</td></tr>';
            return;
        }

        // Apply filters for statements view
        const searchVal = inputs.stmtSearch.value.trim().toLowerCase();
        const filterVal = inputs.stmtFilter.value;

        // Render dashboard (last 5, unfiltered)
        userTransactions.slice(0, 5).forEach(tx => {
            const tr = document.createElement('tr');
            const amtClass = tx.type === 'DEBIT' ? 'text-brand' : '';
            const amtSign = tx.type === 'DEBIT' ? '-' : '+';
            const amtVal = tx.type === 'DEBIT' ? tx.debit : tx.credit;

            tr.innerHTML = `
                <td class="text-mono text-xs">${tx.date}</td>
                <td>${tx.desc}</td>
                <td class="text-mono fw-600 ${amtClass}" style="${tx.type === 'CREDIT' ? 'color: var(--green);' : ''}">${amtSign} ₹ ${amtVal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                <td><span class="badge ${tx.status === 'Success' || tx.status === 'Paid' ? 'badge-green' : 'badge-amber'}">${tx.status}</span></td>
            `;
            dashboardTbody.appendChild(tr);
        });

        // Render statements with filter constraints
        userTransactions.forEach(tx => {
            // Filter search
            if (searchVal && !tx.desc.toLowerCase().includes(searchVal)) return;

            // Filter type
            if (filterVal === 'DEBIT' && tx.type !== 'DEBIT') return;
            if (filterVal === 'CREDIT' && tx.type !== 'CREDIT') return;

            const tr = document.createElement('tr');
            
            const debText = tx.type === 'DEBIT' ? `₹ ${tx.debit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '-';
            const credText = tx.type === 'CREDIT' ? `₹ ${tx.credit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '-';
            const debStyle = tx.type === 'DEBIT' ? 'color: var(--brand); font-weight: 600;' : '';
            const credStyle = tx.type === 'CREDIT' ? 'color: var(--green); font-weight: 600;' : '';

            tr.innerHTML = `
                <td class="text-mono text-xs">${tx.date}</td>
                <td class="text-mono text-xs">${tx.ref}</td>
                <td>${tx.desc}</td>
                <td class="text-mono" style="${debStyle}">${debText}</td>
                <td class="text-mono" style="${credStyle}">${credText}</td>
                <td><span class="badge ${tx.status === 'Success' || tx.status === 'Paid' ? 'badge-green' : 'badge-amber'}">${tx.status}</span></td>
            `;
            statementsTbody.appendChild(tr);
        });

        if (statementsTbody.children.length === 0) {
            statementsTbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No entries match criteria.</td></tr>';
        }
    }

    // Attach filter event listeners
    inputs.stmtSearch.addEventListener('input', renderTransactions);
    inputs.stmtFilter.addEventListener('change', renderTransactions);

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
            BehaviorShield.destroy();

            if (data.enrolled) {
                document.getElementById('login-username-readonly').value = currentUsername;
                displays.loginMessage.textContent = "Enter your NetBanking passphrase.";
                showView('login');
            } else {
                showView('enroll');
                resetEnrollmentProgress();
            }
        } catch (err) {
            console.error("Error checking user:", err);
            alert("Connection error. Is app.py running?");
        }
    });

    // ==========================================
    // ENROLLMENT PROGRESS & MOUSE CALIBRATION
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
                BehaviorShield.extractKeyEvents(); 
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

    function initializeMouseCalibration() {
        const area = document.getElementById('mouse-path-area');
        let inProgress = false;

        area.addEventListener('mouseenter', function() { inProgress = true; });
        area.addEventListener('mouseleave', function() { inProgress = false; });

        area.addEventListener('mousemove', function(e) {
            if (!inProgress || isMouseCalibrated) return;
            const rect = area.getBoundingClientRect();
            const x = e.clientX - rect.left;
            
            if (x > 480) {
                isMouseCalibrated = true;
                displays.calibrationSuccess.classList.remove('hidden');
                buttons.enrollComplete.disabled = false;
                console.log("[Vishwa Bank] Mouse calibration complete.");
            }
        });
    }

    buttons.enrollComplete.addEventListener('click', function() {
        alert("Enrollment baseline registered successfully!");
        showView('username');
    });

    // ==========================================
    // LOGIN & LAUNCH PORTAL
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

        if (pass !== "SecureAuth@India1") {
            alert("Invalid credentials. Enter the enrolled passphrase.");
            inputs.loginPass.value = "";
            BehaviorShield.extractKeyEvents(); 
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
            
            if (data.is_bot || data.action === 'FREEZE_SESSION' || data.action === 'FREEZE_AND_ALERT' || data.action === 'SILENT_BLOCK') {
                showFreezeOverlay();
                return;
            }

            // Authenticated successfully! Load database and init SDK
            sessionId = data.session_id;
            inputs.loginPass.value = "";
            document.getElementById('hello-user').textContent = currentUsername;

            loadUserDatabase();
            
            BehaviorShield.init(sessionId, currentUsername);
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
    // ADD NEW PAYEE LOGIC
    // ==========================================
    buttons.addPayee.addEventListener('click', async function() {
        const name = inputs.payeeName.value.trim();
        const acc = inputs.payeeAccount.value.trim();
        const ifsc = inputs.payeeIfsc.value.trim();
        const limStr = inputs.payeeLimit.value.trim();

        if (!name || !acc || !ifsc || !limStr) {
            alert("Please fill all payee parameters.");
            return;
        }

        // IFSC Validation (Standard Indian Banking format: 4 letters, 0, 6 digits/chars)
        if (!/^[A-Z]{4}0[A-Z0-9]{6}$/.test(ifsc)) {
            alert("Invalid IFSC format. Example: SBIN0001802");
            return;
        }

        const limit = parseFloat(limStr);

        // Submit action request to backend scoring
        await fetch('/api/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, action_type: 'add_payee' })
        });

        // Trigger manual telemetry scoring check
        await BehaviorShield.forceSubmitScore();

        // Check if session got frozen
        const sessionCheckRes = await fetch(`/api/session/${sessionId}`);
        const sessionCheck = await sessionCheckRes.json();
        if (sessionCheck.status === 'terminated' || sessionCheck.band.startsWith('RED')) {
            showFreezeOverlay();
            return;
        }

        // Add payee locally
        userPayees.push({ name, account: acc, ifsc, limit });
        savePayees();
        renderPayees();
        alert(`Beneficiary ${name} registered successfully!`);

        // Clear fields
        inputs.payeeName.value = "";
        inputs.payeeAccount.value = "";
        inputs.payeeIfsc.value = "";
        inputs.payeeLimit.value = "";
    });

    // ==========================================
    // SCORING LISTENERS (FROM SDK)
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
    // MODAL HANDLERS
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
            BehaviorShield.extractKeyEvents(); 
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
    // AUTHORIZED TRANSFER (AMBER HIGH / OTP)
    // ==========================================
    buttons.txSubmit.addEventListener('click', async function() {
        const payeeIdx = inputs.txPayeeSelect.value;
        const amountStr = inputs.txAmount.value.trim();
        const desc = inputs.txDesc.value.trim() || "Fund Transfer";

        if (payeeIdx === "" || !amountStr) {
            alert("Please select a payee beneficiary and enter an amount.");
            return;
        }

        const payeeObj = userPayees[parseInt(payeeIdx)];
        const amount = parseFloat(amountStr);

        if (amount > userSavingsBalance) {
            alert("Insufficient balance in savings account.");
            return;
        }

        if (amount > payeeObj.limit) {
            alert(`Transfer amount exceeds registered payee transfer limit of ₹${payeeObj.limit.toLocaleString()}`);
            return;
        }

        currentTransactionPayload = {
            session_id: sessionId,
            action_type: 'transfer',
            amount: amount,
            description: `${inputs.txMethod.value} to ${payeeObj.name}`
        };

        // Track action
        await fetch('/api/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, action_type: 'transfer' })
        });

        // Trigger manual telemetry submit
        await BehaviorShield.forceSubmitScore();

        // Proceed to transfer API check
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
                    showOtpModal();
                } else {
                    processSuccessfulTransaction();
                }
            } else {
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
        
        const payeeObj = userPayees[parseInt(inputs.txPayeeSelect.value)];
        const amount = parseFloat(inputs.txAmount.value);
        const method = inputs.txMethod.value;
        const desc = inputs.txDesc.value.trim() || "Fund Transfer";

        // Create transaction row
        const newTx = {
            date: "Today",
            ref: `TXN${Math.floor(100000000 + Math.random() * 900000000)}`,
            desc: `${method} transfer to ${payeeObj.name}: ${desc}`,
            type: "DEBIT",
            debit: amount,
            credit: 0,
            status: "Success"
        };

        userTransactions.unshift(newTx);
        saveTransactions();
        
        userSavingsBalance -= amount;
        saveBalance();

        updateBalanceDisplays();
        renderTransactions();
        switchBankTab('dashboard');

        // Clear fields
        inputs.txPayeeSelect.value = "";
        inputs.txAmount.value = "";
        inputs.txDesc.value = "";
    }

    // ==========================================
    // DOWNLOAD STATEMENT SIMULATOR
    // ==========================================
    buttons.stmtDownload.addEventListener('click', function() {
        alert("Statement Generated!\nMock PDF Statement file download initiated: Vishwa_Statement_2026.pdf");
    });

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

    const simButtons = document.querySelectorAll('.sim-mode-btn');
    simButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            simButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedPersona = btn.getAttribute('data-persona');
            console.log(`[Simulator] Active Persona: ${selectedPersona}`);
        });
    });

    buttons.quickFill.addEventListener('click', function() {
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

    function simulateTyping(inputElement, text, persona) {
        inputElement.value = "";
        inputElement.focus();
        currentFocusFieldTs = Date.now();

        BehaviorShield.extractKeyEvents();

        let index = 0;

        function typeNextChar() {
            if (index >= text.length) {
                setTimeout(() => {
                    const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter' });
                    inputElement.dispatchEvent(enterEvent);
                }, 200);
                return;
            }

            const char = text[index];
            const code = `Key${char.toUpperCase()}`;

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

            setTimeout(function() {
                const downEvent = new KeyboardEvent('keydown', { key: char, code: code });
                inputElement.dispatchEvent(downEvent);

                setTimeout(function() {
                    inputElement.value += char;
                    const upEvent = new KeyboardEvent('keyup', { key: char, code: code });
                    inputElement.dispatchEvent(upEvent);

                    index++;
                    typeNextChar();
                }, dwellTime);

            }, flightTime);
        }

        typeNextChar();
    }
});
