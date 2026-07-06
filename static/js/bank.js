/**
 * TRUSTLAYER — bank.js
 * Team SOLARIS | Cyber Security Hackathon 2026 | MNNIT Allahabad
 * 
 * Redesigned client-side portal logic for Bharat Suraksha Bank NetBanking.
 * Integrates with TRUSTLAYER Telemetry SDK (sdk.js) to monitor sessions.
 * Manages multi-tab routing, persistent local storage databases,
 * payee registration, transfers, statement searches, and timing presets.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Register Service Worker for PWA (Stream 5)
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/sw.js')
            .then(reg => console.log('[PWA] Service Worker registered!', reg))
            .catch(err => console.error('[PWA] Service Worker registration failed:', err));
    }

    // Auth UI View elements
    const authContainer = document.getElementById('auth-container');
    const views = {
        username: document.getElementById('username-view'),
        register: document.getElementById('register-view'),
        created: document.getElementById('created-view'),
        enroll: document.getElementById('enroll-view'),
        login: document.getElementById('login-view'),
        portal: document.getElementById('portal-view')
    };

    // Dashboard Tabs
    const tabs = {
        dashboard: document.getElementById('page-dashboard'),
        transfer: document.getElementById('page-transfer'),
        bills: document.getElementById('page-bills'),
        upi: document.getElementById('page-upi'),
        payees: document.getElementById('page-payees'),
        statements: document.getElementById('page-statements'),
        fd: document.getElementById('page-fd'),
        profile: document.getElementById('page-profile'),
        support: document.getElementById('page-support')
    };

    // Inputs
    const inputs = {
        username: document.getElementById('start-username'),
        startPass: document.getElementById('start-password'),
        regUser: document.getElementById('reg-username'),
        regPass: document.getElementById('reg-password'),
        regFirst: document.getElementById('reg-first-name'),
        regLast: document.getElementById('reg-last-name'),
        regEmail: document.getElementById('reg-email'),
        regMobile: document.getElementById('reg-mobile'),
        regCity: document.getElementById('reg-city'),
        regDob: document.getElementById('reg-dob'),
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
        stmtFilter: document.getElementById('stmt-filter'),
        
        // Bills
        billCategory: document.getElementById('bill-category'),
        billConsumer: document.getElementById('bill-consumer-id'),
        billAmount: document.getElementById('bill-amount'),
        
        // UPI
        upiVpa: document.getElementById('upi-vpa'),
        upiAmount: document.getElementById('upi-amount'),
        
        // FD
        fdAmount: document.getElementById('fd-amount'),
        fdTenure: document.getElementById('fd-tenure'),
        
        // Profile
        profOldPass: document.getElementById('prof-old-pass'),
        profNewPass: document.getElementById('prof-new-pass'),
        
        // Support
        supportCategory: document.getElementById('support-category'),
        supportMessage: document.getElementById('support-message')
    };

    // Buttons
    const buttons = {
        nextStep: document.getElementById('btn-next-step'),
        showRegister: document.getElementById('link-show-register'),
        regBack: document.getElementById('reg-back-login'),
        regSubmit: document.getElementById('reg-submit-btn'),
        createdProceed: document.getElementById('created-proceed-btn'),
        enrollCancel: document.getElementById('enroll-cancel'),
        enrollComplete: document.getElementById('enroll-complete-btn'),
        loginBack: document.getElementById('login-back'),
        loginSubmit: document.getElementById('login-submit'),
        logout: document.getElementById('logout-btn'),
        txSubmit: document.getElementById('tx-submit'),
        billSubmit: document.getElementById('bill-submit-btn'),
        upiSubmit: document.getElementById('upi-submit-btn'),
        fdSubmit: document.getElementById('fd-submit-btn'),
        profPassBtn: document.getElementById('prof-pass-btn'),
        supportSubmit: document.getElementById('support-submit-btn'),
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
        createdAccount: document.getElementById('created-account-number'),
        createdPassphrase: document.getElementById('created-passphrase'),
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
    let userPassphrase = "";   // fetched from server after login/registration
    let sessionId = null;
    let enrollmentSamplesCollected = 0;
    let isMouseCalibrated = false;
    let traceCoords = [];
    let selectedPersona = "owner"; 
    let currentTransactionPayload = null;
    let currentFocusFieldTs = null;

    // Local DB variables loaded per user
    let userPayees = [];
    let userTransactions = [];
    let userSavingsBalance = 423891.50;

    // Monitor input elements with SDK
    TRUSTLAYER.monitorInput(inputs.enroll);
    TRUSTLAYER.monitorInput(inputs.loginPass);
    TRUSTLAYER.monitorInput(inputs.username);
    TRUSTLAYER.monitorInput(inputs.challenge);
    TRUSTLAYER.monitorInput(inputs.txAmount);
    TRUSTLAYER.monitorInput(inputs.txDesc);
    TRUSTLAYER.monitorInput(inputs.payeeName);
    TRUSTLAYER.monitorInput(inputs.payeeAccount);
    TRUSTLAYER.monitorInput(inputs.payeeIfsc);
    TRUSTLAYER.monitorInput(inputs.payeeLimit);
    TRUSTLAYER.monitorInput(inputs.upiVpa);
    TRUSTLAYER.monitorInput(inputs.upiAmount);
    TRUSTLAYER.monitorInput(inputs.billConsumer);
    TRUSTLAYER.monitorInput(inputs.billAmount);
    TRUSTLAYER.monitorInput(inputs.fdAmount);

    // Timing helper focus hooks
    inputs.enroll.addEventListener('focus', () => currentFocusFieldTs = Date.now());
    inputs.loginPass.addEventListener('focus', () => currentFocusFieldTs = Date.now());
    inputs.challenge.addEventListener('focus', () => currentFocusFieldTs = Date.now());

    // Mobile menu toggle handlers
    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            const sidebar = document.querySelector('.sidebar');
            if (sidebar) {
                sidebar.classList.toggle('open');
            }
        });
    }

    // Close sidebar if clicking outside it on mobile
    document.addEventListener('click', function(e) {
        const sidebar = document.querySelector('.sidebar');
        if (sidebar && sidebar.classList.contains('open')) {
            const mobileMenuBtn = document.getElementById('mobile-menu-btn');
            const isClickInside = sidebar.contains(e.target) || (mobileMenuBtn && mobileMenuBtn.contains(e.target));
            if (!isClickInside) {
                sidebar.classList.remove('open');
            }
        }
    });

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

        if (viewName === 'username') {
            inputs.username.value = "";
            inputs.startPass.value = "";
            inputs.loginPass.value = "";
            const readonlyUser = document.getElementById('login-username-readonly');
            if (readonlyUser) readonlyUser.value = "";
        }

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

        if (tabName === 'profile') {
            loadUserProfile();
            loadUserAuditLog();
        } else if (tabName === 'support') {
            loadSupportTickets();
        } else if (tabName === 'upi') {
            document.getElementById('upi-my-vpa').textContent = `${currentUsername}@bsb`;
        } else if (tabName === 'fd') {
            updateFdCalculation();
        }

        // Close mobile navigation sidebar when selecting a tab
        const sidebar = document.querySelector('.sidebar');
        if (sidebar) {
            sidebar.classList.remove('open');
        }
    };

    // Register click events to nav sidebar items
    Object.keys(tabs).forEach(key => {
        document.getElementById(`tab-nav-${key}`).addEventListener('click', () => switchBankTab(key));
    });

    // ==========================================
    // LOCAL STORAGE DATABASE MANAGEMENT
    // ==========================================
    async function loadUserDatabase() {
        const prefix = `vb_${currentUsername}_`;
        
        // Load Profile & Balance from server
        try {
            const res = await fetch(`/api/profile/${currentUsername}`);
            if (res.ok) {
                const user = await res.json();
                userSavingsBalance = user.balance;
                updateBalanceDisplays();
            } else {
                const savedBalance = localStorage.getItem(`${prefix}balance`);
                userSavingsBalance = savedBalance ? parseFloat(savedBalance) : 423891.50;
                updateBalanceDisplays();
            }
        } catch (e) {
            console.error("Error loading balance from server:", e);
            const savedBalance = localStorage.getItem(`${prefix}balance`);
            userSavingsBalance = savedBalance ? parseFloat(savedBalance) : 423891.50;
            updateBalanceDisplays();
        }

        // Load Payees from server
        try {
            const res = await fetch(`/api/payees/${currentUsername}`);
            if (res.ok) {
                const data = await res.json();
                userPayees = data.payees || [];
            } else {
                userPayees = [];
            }
        } catch (e) {
            console.error("Error loading payees from server:", e);
            userPayees = [];
        }
        renderPayees();

        // Load Transactions from server
        await fetchTransactionsFromServer();
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
    const usernameForm = document.getElementById('username-form');
    if (usernameForm) {
        usernameForm.addEventListener('submit', function(e) {
            e.preventDefault();
            handleUsernameSubmit();
        });
    }

    async function handleUsernameSubmit() {
        const username = inputs.username.value.trim();
        const password = inputs.startPass.value;
        if (!username || !password) {
            alert("Please enter both username and password.");
            return;
        }

        currentUsername = username;
        
        const usernameKeys = TRUSTLAYER.extractKeyEvents();

        try {
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: currentUsername,
                    password: password,
                    key_events: [],
                    username_key_events: usernameKeys,
                    device_info: TRUSTLAYER.getDeviceFingerprint()
                })
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                if (response.status === 423) {
                    alert(errData.detail || "Account temporarily locked due to too many failed attempts.");
                } else {
                    alert(errData.detail || "Invalid username or password.");
                }
                return;
            }

            const data = await response.json();
            TRUSTLAYER.destroy();

            userPassphrase = data.passphrase;

            if (data.enrolled) {
                document.getElementById('login-username-readonly').value = currentUsername;
                displays.loginMessage.textContent = "Enter your NetBanking passphrase.";
                showView('login');
            } else {
                document.getElementById('enroll-passphrase-display').textContent = userPassphrase;
                showView('enroll');
                resetEnrollmentProgress();
            }
        } catch (err) {
            console.error("Error logging in:", err);
            alert("Connection error. Is app.py running?");
        }
    }

    // Registration UI Navigation
    buttons.showRegister.addEventListener('click', function(e) {
        e.preventDefault();
        showView('register');
    });

    buttons.regBack.addEventListener('click', function() {
        showView('username');
    });

    buttons.createdProceed.addEventListener('click', function() {
        showView('username');
        inputs.username.value = currentUsername;
        inputs.startPass.value = '';
        inputs.startPass.focus();
    });

    // Registration Submit
    buttons.regSubmit.addEventListener('click', async function() {
        const username = inputs.regUser.value.trim();
        const password = inputs.regPass.value;
        const firstName = inputs.regFirst.value.trim();
        const lastName = inputs.regLast.value.trim();
        const email = inputs.regEmail.value.trim();
        const mobile = inputs.regMobile.value.trim();
        const city = inputs.regCity.value.trim();
        const dob = inputs.regDob.value;

        if (!username || !password || !firstName || !lastName || !email || !mobile || !city || !dob) {
            alert("Please fill in all fields to register.");
            return;
        }

        try {
            const response = await fetch('/api/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: username,
                    password: password,
                    first_name: firstName,
                    last_name: lastName,
                    email: email,
                    mobile: mobile,
                    city: city,
                    date_of_birth: dob,
                    account_type: (document.getElementById('reg-account-type') || {}).value || 'savings',
                })
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                alert(errData.detail || "Registration failed.");
                return;
            }

            const data = await response.json();
            currentUsername = data.username;
            // Set the per-user passphrase from the registration response
            if (data.passphrase) userPassphrase = data.passphrase;

            // Display account created card details
            displays.createdAccount.textContent = data.account_number;
            displays.createdPassphrase.textContent = data.passphrase || '-';
            showView('created');

            // Clear registration inputs
            inputs.regUser.value = "";
            inputs.regPass.value = "";
            inputs.regFirst.value = "";
            inputs.regLast.value = "";
            inputs.regEmail.value = "";
            inputs.regMobile.value = "";
            inputs.regCity.value = "";
            inputs.regDob.value = "";
        } catch (err) {
            console.error("Error registering:", err);
            alert("Connection error during registration.");
        }
    });

    // Form submission is handled natively via form submit event

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

        const label = document.getElementById('path-instruction-label');
        if (label) label.textContent = "Trace curve left to right";
        const ball = document.getElementById('calibration-ball');
        if (ball) {
            ball.setAttribute('cx', '40');
            ball.setAttribute('cy', '75');
            ball.setAttribute('fill', 'var(--cyan)');
            ball.setAttribute('r', '10');
        }
        const tracePath = document.getElementById('dynamic-trace-path');
        if (tracePath) tracePath.setAttribute('d', '');
    }

    async function submitEnrollmentSample() {
        const text = inputs.enroll.value.trim();
        const targetPass = document.getElementById('enroll-passphrase-display').textContent.trim();
        if (text !== targetPass) {
            alert(`Passphrase does not match exactly! Please type: ${targetPass}`);
            inputs.enroll.value = "";
            TRUSTLAYER.extractKeyEvents(); 
            return;
        }

        const keyEvents = TRUSTLAYER.extractKeyEvents();
        if (!keyEvents || keyEvents.length === 0) {
            alert("No typing dynamics recorded. Please type the passphrase character-by-character.");
            return;
        }

        try {
            const response = await fetch('/api/enroll', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: currentUsername,
                    key_events: keyEvents,
                    field_focus_ts: currentFocusFieldTs,
                    device_class: TRUSTLAYER.getDeviceFingerprint().device_class
                })
            });

            const data = await response.json();
            if (!response.ok) {
                alert(data.detail || "Failed to submit sample. Please re-type it naturally.");
                inputs.enroll.value = "";
                return;
            }

            enrollmentSamplesCollected = data.count;

            displays.enrollProgressText.textContent = `Sample ${enrollmentSamplesCollected}/5`;
            displays.enrollProgressBar.style.width = `${(enrollmentSamplesCollected / 5) * 100}%`;
            inputs.enroll.value = "";
            currentFocusFieldTs = Date.now();

            if (data.complete) {
                inputs.enroll.disabled = true;
                const enrollSubmitBtn = document.getElementById('enroll-submit-btn');
                if (enrollSubmitBtn) enrollSubmitBtn.disabled = true;
                document.getElementById('enroll-mouse-step').classList.remove('hidden');
                initializeMouseCalibration();
            }
        } catch (err) {
            console.error("Enrollment failed:", err);
            alert("Failed to submit sample.");
        }
    }

    const enrollForm = document.getElementById('enroll-form');
    if (enrollForm) {
        enrollForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            await submitEnrollmentSample();
        });
    }

    buttons.enrollCancel.addEventListener('click', () => {
        if (sessionId) {
            fetch(`/api/session/terminate/${sessionId}`, { method: 'POST' }).catch(() => {});
            sessionId = null;
        }
        showView('username');
    });

    function initializeMouseCalibration() {
        const area = document.getElementById('mouse-path-area');
        const path = document.getElementById('calibration-svg-path');
        const ball = document.getElementById('calibration-ball');
        const label = document.getElementById('path-instruction-label');
        const tracePath = document.getElementById('dynamic-trace-path');
        
        let isTracing = false;
        traceCoords = [];
        const pathLength = path.getTotalLength();

        function getZigzagY(x) {
            if (x <= 40) return 75;
            if (x >= 520) return 75;
            if (x >= 40 && x < 120) {
                return 75 - 0.625 * (x - 40);
            } else if (x >= 120 && x < 200) {
                return 25 + 1.25 * (x - 120);
            } else if (x >= 200 && x < 280) {
                return 125 - 1.25 * (x - 200);
            } else if (x >= 280 && x < 360) {
                return 25 + 1.25 * (x - 280);
            } else if (x >= 360 && x < 440) {
                return 125 - 1.25 * (x - 360);
            } else if (x >= 440 && x <= 520) {
                return 25 + 0.625 * (x - 440);
            }
            return 75;
        }

        // Ensure start state is visual
        ball.setAttribute('cx', '40');
        ball.setAttribute('cy', '75');
        ball.setAttribute('fill', 'var(--cyan)');
        ball.setAttribute('r', '10');
        label.textContent = "Move cursor to START to begin tracing";
        if (tracePath) tracePath.setAttribute('d', '');

        function handleInteraction(clientX, clientY) {
            if (isMouseCalibrated) return;
            
            const rect = area.getBoundingClientRect();
            const mouseX = clientX - rect.left;
            const mouseY = clientY - rect.top;
            
            // Map coordinates to SVG viewBox (0 0 560 150)
            const svgX = (mouseX / rect.width) * 560;
            const svgY = (mouseY / rect.height) * 150;

            if (!isTracing) {
                // Check if user is near the START coordinates (40, 75)
                const distToStart = Math.sqrt((svgX - 40) ** 2 + (svgY - 75) ** 2);
                if (distToStart < 25) {
                    isTracing = true;
                    traceCoords = [{x: 40, y: 75}];
                    if (tracePath) tracePath.setAttribute('d', 'M 40 75');
                    ball.setAttribute('fill', 'var(--cyan)');
                    ball.setAttribute('r', '12'); // grow to show active
                    label.textContent = "Trace along the dashed line to END";
                    console.log("[BSB] Tracing started");
                }
            } else {
                // Project cursor onto the zigzag path mathematically
                // Path goes horizontally from X=40 to X=520
                const clampedX = Math.max(40, Math.min(520, svgX));
                const targetY = getZigzagY(clampedX);
                
                // Move the ball along the path
                ball.setAttribute('cx', clampedX.toFixed(1));
                ball.setAttribute('cy', targetY.toFixed(1));

                // Add trail coordinates
                traceCoords.push({x: svgX, y: svgY});
                const dStr = traceCoords.map((pt, i) => `${i === 0 ? 'M' : 'L'} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`).join(' ');
                if (tracePath) tracePath.setAttribute('d', dStr);

                // Optional security check: if cursor goes way too far from the ball (e.g. > 70px), we reset
                const distToBall = Math.sqrt((svgX - clampedX) ** 2 + (svgY - targetY) ** 2);
                if (distToBall > 70) {
                    isTracing = false;
                    traceCoords = [];
                    if (tracePath) tracePath.setAttribute('d', '');
                    ball.setAttribute('cx', '40');
                    ball.setAttribute('cy', '75');
                    ball.setAttribute('fill', 'var(--cyan)');
                    ball.setAttribute('r', '10');
                    label.textContent = "Trace deviated too much! Return to START";
                    console.log("[BSB] Tracing reset due to deviation");
                    return;
                }

                // Check for completion (clampedX is close to 520)
                if (clampedX >= 515) {
                    isTracing = false;
                    isMouseCalibrated = true;
                    ball.setAttribute('cx', '520');
                    ball.setAttribute('cy', '75');
                    ball.setAttribute('fill', 'var(--green)');
                    ball.setAttribute('r', '10');
                    label.textContent = "Mouse path verified!";
                    
                    displays.calibrationSuccess.classList.remove('hidden');
                    buttons.enrollComplete.disabled = false;
                    console.log("[BSB] Mouse calibration complete.");
                }
            }
        }

        function handleLeave() {
            if (!isMouseCalibrated) {
                // If we were tracing and got close to the end, count it as success on release/leave
                const ballX = parseFloat(ball.getAttribute('cx'));
                if (isTracing && ballX >= 480) {
                    isTracing = false;
                    isMouseCalibrated = true;
                    ball.setAttribute('cx', '520');
                    ball.setAttribute('cy', '75');
                    ball.setAttribute('fill', 'var(--green)');
                    ball.setAttribute('r', '10');
                    label.textContent = "Mouse path verified!";
                    
                    displays.calibrationSuccess.classList.remove('hidden');
                    buttons.enrollComplete.disabled = false;
                    console.log("[BSB] Mouse calibration complete via close-enough end touch.");
                    return;
                }

                isTracing = false;
                traceCoords = [];
                if (tracePath) tracePath.setAttribute('d', '');
                ball.setAttribute('cx', '40');
                ball.setAttribute('cy', '75');
                ball.setAttribute('fill', 'var(--cyan)');
                ball.setAttribute('r', '10');
                label.textContent = "Move cursor to START to begin tracing";
                console.log("[BSB] Tracing reset");
            }
        }

        area.addEventListener('mousemove', function(e) {
            handleInteraction(e.clientX, e.clientY);
        });

        area.addEventListener('touchmove', function(e) {
            if (e.touches && e.touches.length > 0) {
                // Prevent scrolling while tracing
                e.preventDefault();
                const touch = e.touches[0];
                handleInteraction(touch.clientX, touch.clientY);
            }
        }, { passive: false });

        area.addEventListener('touchstart', function(e) {
            if (e.touches && e.touches.length > 0) {
                e.preventDefault();
                const touch = e.touches[0];
                handleInteraction(touch.clientX, touch.clientY);
            }
        }, { passive: false });

        area.addEventListener('mouseleave', handleLeave);
        area.addEventListener('touchend', handleLeave);
    }

    buttons.enrollComplete.addEventListener('click', async function() {
        // Convert traceCoords to SDK-format mouse_events with timestamps
        const now = Date.now();
        const mouseEvents = traceCoords.map((pt, i) => ({
            event: 'move',
            x: Math.round(pt.x),
            y: Math.round(pt.y),
            timestamp: now - (traceCoords.length - i) * 50  // ~50ms intervals
        }));

        if (mouseEvents.length >= 5) {
            try {
                await fetch('/api/enroll-mouse', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: currentUsername, mouse_events: mouseEvents })
                });
            } catch (e) {
                console.warn('[BSB] Mouse enroll API failed (non-critical):', e);
            }
        }

        // Show success and terminate the enrollment session before redirecting
        const successDiv = document.getElementById('calibration-success-msg');
        if (successDiv) successDiv.textContent = '✓ Biometric profile registered. Redirecting to login...';
        if (sessionId) {
            fetch(`/api/session/terminate/${sessionId}`, { method: 'POST' }).catch(() => {});
            sessionId = null;
        }
        setTimeout(() => showView('username'), 1200);
    });

    // ==========================================
    // LOGIN & LAUNCH PORTAL
    // ==========================================
    buttons.loginBack.addEventListener('click', () => showView('username'));

    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', function(e) {
            e.preventDefault();
            handleLogin();
        });
    }

    async function handleLogin() {
        const pass = inputs.loginPass.value.trim();
        if (!pass) {
            alert("Please enter your password.");
            return;
        }

        if (pass !== userPassphrase) {
            alert("Invalid credentials. Enter the enrolled passphrase.");
            inputs.loginPass.value = "";
            TRUSTLAYER.extractKeyEvents(); 
            return;
        }

        const keyEvents = TRUSTLAYER.extractKeyEvents();
        const deviceFingerprint = TRUSTLAYER.getDeviceFingerprint();

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
                const errData = await response.json().catch(() => ({}));
                if (response.status === 423) {
                    alert(errData.detail || "Account temporarily locked due to too many failed attempts.");
                } else {
                    alert(errData.detail || "Login failed: Invalid behavioral signature.");
                }
                inputs.loginPass.value = "";
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
            
            TRUSTLAYER.init(sessionId, currentUsername);
            updateRiskMetrics(data.score, data.band, data.scoring_interval || 15);
            
            showView('portal');
            console.log("[BSB] Logged in successfully. Session:", sessionId);
            
        } catch (err) {
            console.error("Login Error:", err);
            alert("Error logging in.");
        }
    }

    buttons.logout.addEventListener('click', function() {
        if (sessionId) {
            fetch(`/api/session/terminate/${sessionId}`, { method: 'POST' }).catch(() => {});
        }
        TRUSTLAYER.destroy();
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
        await TRUSTLAYER.forceSubmitScore();

        // Check if session got frozen
        const sessionCheckRes = await fetch(`/api/session/${sessionId}`);
        const sessionCheck = await sessionCheckRes.json();
        if (!sessionCheck.advisory_mode && (sessionCheck.status === 'terminated' || sessionCheck.band.startsWith('RED'))) {
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
    window.addEventListener('TRUSTLAYER_update', function(e) {
        const data = e.detail;
        console.log("[BSB] Score updated:", data);
        updateRiskMetrics(data.score, data.band, data.scoring_interval);
    });

    window.addEventListener('TRUSTLAYER_freeze', function(e) {
        console.warn("[BSB] Session Frozen event received!");
        showFreezeOverlay();
    });

    window.addEventListener('TRUSTLAYER_challenge', function(e) {
        console.warn("[BSB] Step-up challenge requested!");
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
        TRUSTLAYER.destroy();
    }

    buttons.freezeReset.addEventListener('click', function() {
        overlays.freeze.classList.add('hidden');
        sessionId = null;
        currentUsername = "";
        inputs.username.value = "";
        showView('username');
    });

    function showChallengeModal() {
        const displayEl = document.getElementById('challenge-passphrase-display');
        if (displayEl) {
            displayEl.textContent = userPassphrase || "";
        }
        overlays.challenge.classList.remove('hidden');
        inputs.challenge.value = "";
        displays.challengeError.classList.add('hidden');
        inputs.challenge.focus();
        currentFocusFieldTs = Date.now();
    }

    const challengeForm = document.getElementById('challenge-form');
    if (challengeForm) {
        challengeForm.addEventListener('submit', function(e) {
            e.preventDefault();
            submitChallenge();
        });
    }

    async function submitChallenge() {
        const text = inputs.challenge.value.trim();
        if (text !== userPassphrase) {
            displays.challengeError.textContent = "Passphrase does not match exactly!";
            displays.challengeError.classList.remove('hidden');
            inputs.challenge.value = "";
            TRUSTLAYER.extractKeyEvents(); 
            return;
        }

        const keyEvents = TRUSTLAYER.extractKeyEvents();

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
        await TRUSTLAYER.forceSubmitScore();

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

    const otpForm = document.getElementById('otp-form');
    if (otpForm) {
        otpForm.addEventListener('submit', function(e) {
            e.preventDefault();
            submitOtp();
        });
    }

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

    async function processSuccessfulTransaction() {
        if (currentTransactionPayload && currentTransactionPayload.action_type === 'upi') {
            // Process verified UPI payment
            try {
                const response = await fetch('/api/upi', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: sessionId,
                        upi_id: currentTransactionPayload.upi_id,
                        amount: currentTransactionPayload.amount,
                        note: currentTransactionPayload.note || ""
                    })
                });
                const data = await response.json();
                if (response.ok && data.success) {
                    userSavingsBalance = data.new_balance;
                    updateBalanceDisplays();
                    alert(`UPI transfer of ₹${currentTransactionPayload.amount} to ${currentTransactionPayload.upi_id} successful!`);
                    inputs.upiVpa.value = "";
                    inputs.upiAmount.value = "";
                    fetchTransactionsFromServer();
                    switchBankTab('dashboard');
                } else {
                    alert(data.detail || "UPI transfer failed.");
                }
            } catch (e) {
                alert("Error processing UPI transfer.");
            }
            return;
        }

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
    // UTILITY BILL PAYMENTS HANDLER
    // ==========================================
    buttons.billSubmit.addEventListener('click', async function() {
        const category = inputs.billCategory.value;
        const consumer = inputs.billConsumer.value.trim();
        const amtStr = inputs.billAmount.value.trim();

        if (!consumer || !amtStr) {
            alert("Please fill all fields.");
            return;
        }

        const amount = parseFloat(amtStr);
        if (amount <= 0) {
            alert("Invalid payment amount.");
            return;
        }

        if (amount > userSavingsBalance) {
            alert("Insufficient balance in savings account.");
            return;
        }

        // Register action
        await fetch('/api/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, action_type: 'bill_payment' })
        });

        // Trigger telemetry submission
        await TRUSTLAYER.forceSubmitScore();

        // Check if session got frozen
        const sessionCheckRes = await fetch(`/api/session/${sessionId}`);
        const sessionCheck = await sessionCheckRes.json();
        if (!sessionCheck.advisory_mode && (sessionCheck.status === 'terminated' || sessionCheck.band.startsWith('RED'))) {
            overlays.freeze.classList.remove('hidden');
            return;
        }

        // Proceed to bill payment API
        try {
            const billerType = category.toLowerCase().replace(" recharge", "").replace(" prepaid / postpaid", "");
            const response = await fetch('/api/bill-payment', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    biller_type: billerType,
                    consumer_id: consumer,
                    amount: amount,
                    description: `${category} payment — ${consumer}`
                })
            });

            const data = await response.json();
            if (response.ok && data.success) {
                userSavingsBalance = data.new_balance;
                updateBalanceDisplays();
                alert(`Utility payment of ₹${amount} for ${category} successfully processed.`);
                inputs.billConsumer.value = "";
                inputs.billAmount.value = "";
                fetchTransactionsFromServer();
            } else {
                alert(data.detail || "Transaction failed.");
            }
        } catch (e) {
            alert("Error processing utility payment.");
        }
    });

    // ==========================================
    // UPI HANDLER
    // ==========================================
    buttons.upiSubmit.addEventListener('click', async function() {
        const vpa = inputs.upiVpa.value.trim();
        const amtStr = inputs.upiAmount.value.trim();

        if (!vpa || !amtStr) {
            alert("Please enter recipient UPI ID and amount.");
            return;
        }

        const amount = parseFloat(amtStr);
        if (amount <= 0) {
            alert("Invalid amount.");
            return;
        }

        if (amount > userSavingsBalance) {
            alert("Insufficient balance.");
            return;
        }

        currentTransactionPayload = {
            session_id: sessionId,
            action_type: 'upi',
            upi_id: vpa,
            amount: amount,
            note: ""
        };

        // Register action
        await fetch('/api/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, action_type: 'upi' })
        });

        // Trigger telemetry submission
        await TRUSTLAYER.forceSubmitScore();

        // Check if session got frozen
        const sessionCheckRes = await fetch(`/api/session/${sessionId}`);
        const sessionCheck = await sessionCheckRes.json();
        if (!sessionCheck.advisory_mode && (sessionCheck.status === 'terminated' || sessionCheck.band.startsWith('RED'))) {
            overlays.freeze.classList.remove('hidden');
            return;
        }

        // Proceed to UPI check
        sendUpiRequest();
    });

    async function sendUpiRequest() {
        try {
            const response = await fetch('/api/upi', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    upi_id: currentTransactionPayload.upi_id,
                    amount: currentTransactionPayload.amount
                })
            });

            const data = await response.json();

            if (response.ok) {
                if (data.requires_verification) {
                    showOtpModal();
                } else if (data.success) {
                    userSavingsBalance = data.new_balance;
                    updateBalanceDisplays();
                    alert(`UPI transfer of ₹${currentTransactionPayload.amount} to ${currentTransactionPayload.upi_id} successful!`);
                    inputs.upiVpa.value = "";
                    inputs.upiAmount.value = "";
                    fetchTransactionsFromServer();
                    switchBankTab('dashboard');
                } else {
                    alert(data.message || "UPI transfer failed.");
                }
            } else {
                alert(data.detail || "UPI transfer failed due to elevated risk.");
            }
        } catch (e) {
            console.error("UPI Error:", e);
            alert("Error processing UPI transfer.");
        }
    }

    // ==========================================
    // FIXED DEPOSITS HANDLER
    // ==========================================
    window.updateFdCalculation = function() {
        const amtStr = inputs.fdAmount.value.trim();
        const tenureSelect = inputs.fdTenure;
        const selectedOption = tenureSelect.options[tenureSelect.selectedIndex];
        const rate = parseFloat(selectedOption.getAttribute('data-rate')) || 6.8;
        
        const amount = amtStr ? parseFloat(amtStr) : 10000;
        const years = parseInt(tenureSelect.value) || 1;
        
        const interest = amount * (rate / 100) * years;
        const maturity = amount + interest;
        
        document.getElementById('fd-calc-maturity').textContent = `₹ ${maturity.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        document.getElementById('fd-calc-interest').textContent = `₹ ${interest.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    };
    
    inputs.fdAmount.addEventListener('input', updateFdCalculation);
    inputs.fdTenure.addEventListener('change', updateFdCalculation);

    buttons.fdSubmit.addEventListener('click', async function() {
        const amtStr = inputs.fdAmount.value.trim();
        const tenure = parseInt(inputs.fdTenure.value);

        if (!amtStr) {
            alert("Please enter deposit amount.");
            return;
        }

        const amount = parseFloat(amtStr);
        if (amount < 10000) {
            alert("Minimum Fixed Deposit booking amount is ₹10,000.");
            return;
        }

        if (amount > userSavingsBalance) {
            alert("Insufficient balance in savings account.");
            return;
        }

        // Register action
        await fetch('/api/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, action_type: 'fd_booking' })
        });

        // Trigger telemetry submission
        await TRUSTLAYER.forceSubmitScore();

        // Check if session got frozen
        const sessionCheckRes = await fetch(`/api/session/${sessionId}`);
        const sessionCheck = await sessionCheckRes.json();
        if (!sessionCheck.advisory_mode && (sessionCheck.status === 'terminated' || sessionCheck.band.startsWith('RED'))) {
            overlays.freeze.classList.remove('hidden');
            return;
        }

        // Proceed to FD API
        try {
            const response = await fetch('/api/fd', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    amount: amount,
                    tenure: tenure
                })
            });

            const data = await response.json();
            if (response.ok && data.success) {
                userSavingsBalance = data.new_balance;
                updateBalanceDisplays();
                alert(`Fixed Deposit of ₹${amount} for ${tenure} Year(s) booked successfully!\nInterest Earned: ₹${data.interest_earned.toFixed(2)}\nMaturity Amount: ₹${data.maturity_amount.toFixed(2)}`);
                inputs.fdAmount.value = "";
                fetchTransactionsFromServer();
            } else {
                alert(data.detail || "FD Booking failed.");
            }
        } catch (e) {
            alert("Error booking Fixed Deposit.");
        }
    });

    // ==========================================
    // CHANGE PASSWORD HANDLER
    // ==========================================
    buttons.profPassBtn.addEventListener('click', async function() {
        const oldPass = inputs.profOldPass.value;
        const newPass = inputs.profNewPass.value;

        if (!oldPass || !newPass) {
            alert("Please enter both current and new passwords.");
            return;
        }

        if (newPass.length < 8) {
            alert("New password must be at least 8 characters.");
            return;
        }

        // Register action
        await fetch('/api/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, action_type: 'change_password' })
        });

        // Trigger telemetry submission
        await TRUSTLAYER.forceSubmitScore();

        // Check if session got frozen
        const sessionCheckRes = await fetch(`/api/session/${sessionId}`);
        const sessionCheck = await sessionCheckRes.json();
        if (!sessionCheck.advisory_mode && (sessionCheck.status === 'terminated' || sessionCheck.band.startsWith('RED'))) {
            overlays.freeze.classList.remove('hidden');
            return;
        }

        // Proceed to Change Password API
        try {
            const response = await fetch('/api/profile/change-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    old_password: oldPass,
                    new_password: newPass
                })
            });

            const data = await response.json();
            if (response.ok && data.success) {
                alert("NetBanking login password successfully updated!");
                inputs.profOldPass.value = "";
                inputs.profNewPass.value = "";
            } else {
                alert(data.detail || "Failed to update password.");
            }
        } catch (e) {
            alert("Error updating NetBanking password.");
        }
    });

    // ==========================================
    // SUPPORT TICKET SUBMISSION
    // ==========================================
    buttons.supportSubmit.addEventListener('click', async function() {
        const category = inputs.supportCategory.value;
        const message = inputs.supportMessage.value.trim();

        if (!message) {
            alert("Please enter ticket description details.");
            return;
        }

        // Register action
        await fetch('/api/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, action_type: 'submit_support' })
        });

        // Trigger telemetry submission
        await TRUSTLAYER.forceSubmitScore();

        // Check if session got frozen
        const sessionCheckRes = await fetch(`/api/session/${sessionId}`);
        const sessionCheck = await sessionCheckRes.json();
        if (!sessionCheck.advisory_mode && (sessionCheck.status === 'terminated' || sessionCheck.band.startsWith('RED'))) {
            overlays.freeze.classList.remove('hidden');
            return;
        }

        // Proceed to Support ticket API
        try {
            const response = await fetch('/api/support/tickets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    category: category,
                    description: message
                })
            });

            const data = await response.json();
            if (response.ok && data.success) {
                alert(`Support ticket ${data.ticket.ticket_id} logged successfully!`);
                inputs.supportMessage.value = "";
                loadSupportTickets();
            } else {
                alert(data.detail || "Failed to log ticket.");
            }
        } catch (e) {
            alert("Error submitting support ticket.");
        }
    });

    // ==========================================
    // SERVER DATA LOADING FUNCTIONS
    // ==========================================
    async function fetchTransactionsFromServer() {
        try {
            const res = await fetch(`/api/transactions/${currentUsername}`);
            if (res.ok) {
                const data = await res.json();
                userTransactions = data.map(tx => {
                    const dateObj = new Date(tx.created_at * 1000);
                    const dateStr = dateObj.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
                    const isDebit = ["debit", "transfer", "bill", "upi", "deposit"].some(t => tx.txn_type.startsWith(t));
                    return {
                        date: dateStr,
                        ref: `TXN${tx.id.toString().padStart(6, '0')}`,
                        desc: tx.description,
                        type: isDebit ? "DEBIT" : "CREDIT",
                        debit: isDebit ? tx.amount : 0,
                        credit: isDebit ? 0 : tx.amount,
                        status: tx.status === "success" ? "Success" : "Pending"
                    };
                });
                renderTransactions();
            }
        } catch (e) {
            console.error("Error loading transactions from server:", e);
        }
    }

    window.loadUserProfile = async function() {
        try {
            const res = await fetch(`/api/profile/${currentUsername}`);
            if (res.ok) {
                const user = await res.json();
                document.getElementById('prof-first-name').textContent = user.first_name || '-';
                document.getElementById('prof-last-name').textContent = user.last_name || '-';
                document.getElementById('prof-email').textContent = user.email || '-';
                document.getElementById('prof-mobile').textContent = user.mobile || '-';
                document.getElementById('prof-city').textContent = user.city || '-';
            }
        } catch (e) {
            console.error("Error loading profile:", e);
        }
    };

    window.loadUserAuditLog = async function() {
        try {
            // Try the new endpoint first, fall back to old one
            let res = await fetch(`/api/security-events/${currentUsername}?limit=10`);
            if (!res.ok) res = await fetch(`/api/user/${currentUsername}/security-log?limit=10`);
            if (res.ok) {
                const data = await res.json();
                const events = data.events || [];
                const tbody = document.getElementById('profile-audit-table-body');
                tbody.innerHTML = '';
                if (events.length > 0) {
                    events.forEach(evt => {
                        const ts = evt.timestamp || evt.created_at || 0;
                        const dateStr = ts ? new Date(ts * 1000).toLocaleString() : '-';
                        const score = evt.risk_score != null ? Number(evt.risk_score).toFixed(1) : '-';
                        const statusText = evt.status || evt.event_type || 'SCORE_UPDATE';
                        const row = document.createElement('tr');
                        
                        let badgeClass = 'badge-green';
                        if (statusText.includes('FAIL') || statusText.includes('FROZEN') || statusText.includes('BLOCKED') || statusText.includes('BOT')) {
                            badgeClass = 'badge-red';
                        } else if (statusText.includes('AMBER') || statusText.includes('CHALLENGE') || statusText.includes('REAUTH')) {
                            badgeClass = 'badge-amber';
                        }
                        
                        row.innerHTML = `
                            <td>${dateStr}</td>
                            <td class="text-mono">${evt.device_class || 'DESKTOP'}</td>
                            <td class="text-mono">${evt.ip_address || '-'}</td>
                            <td class="fw-600">${score}</td>
                            <td><span class="badge ${badgeClass}">${statusText}</span></td>
                        `;
                        tbody.appendChild(row);
                    });
                } else {
                    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No security events recorded yet.</td></tr>';
                }
            }
        } catch (e) {
            console.error("Error loading security log:", e);
        }
    };

    window.loadSupportTickets = async function() {
        try {
            const res = await fetch(`/api/support/tickets/${currentUsername}`);
            if (res.ok) {
                const data = await res.json();
                const tbody = document.getElementById('support-tickets-table-body');
                tbody.innerHTML = '';
                if (data.tickets && data.tickets.length > 0) {
                    data.tickets.forEach(tkt => {
                        const dateStr = new Date(tkt.created_at * 1000).toLocaleString();
                        const descSummary = tkt.description.length > 50 ? tkt.description.substring(0, 47) + '...' : tkt.description;
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td class="text-mono fw-600 text-brand">${tkt.ticket_id}</td>
                            <td>${tkt.category}</td>
                            <td title="${tkt.description}">${descSummary}</td>
                            <td>${dateStr}</td>
                            <td><span class="badge badge-blue">${tkt.status}</span></td>
                        `;
                        tbody.appendChild(row);
                    });
                } else {
                    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No logged tickets found.</td></tr>';
                }
            }
        } catch (e) {
            console.error("Error loading support tickets:", e);
        }
    };

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
        if (isEnrollActive && !inputs.enroll.disabled) targetInput = inputs.enroll;
        else if (isLoginActive) targetInput = inputs.loginPass;
        else if (isChallengeActive) targetInput = inputs.challenge;

        if (!targetInput) {
            alert("Quick-Fill is only active on active Enrollment, Login, or step-up inputs.");
            return;
        }

        const text = userPassphrase;
        simulateTyping(targetInput, text, selectedPersona);
    });

    function simulateTyping(inputElement, text, persona) {
        inputElement.value = "";
        inputElement.focus();
        currentFocusFieldTs = Date.now();

        TRUSTLAYER.extractKeyEvents();

        const hud = document.getElementById('sim-telemetry-hud');
        const speedEl = document.getElementById('sim-key-speed');
        const dwellEl = document.getElementById('sim-avg-dwell');
        if (hud) hud.style.display = 'block';

        let index = 0;

        function typeNextChar() {
            if (index >= text.length) {
                setTimeout(() => {
                    const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter' });
                    inputElement.dispatchEvent(enterEvent);
                    setTimeout(() => {
                        if (hud) hud.style.display = 'none';
                    }, 2000);
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

            // Update live telemetry values
            let displayDwell = Math.round(dwellTime);
            let displayCpm = persona === 'bot' ? '> 20,000' : Math.round(60000 / (dwellTime + flightTime));
            if (speedEl) speedEl.textContent = displayCpm;
            if (dwellEl) dwellEl.textContent = displayDwell;

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
