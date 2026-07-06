/**
 * TRUSTLAYER — dashboard.js
 * Team SOLARIS | Cyber Security Hackathon 2026 | MNNIT Allahabad
 * 
 * Client-side script for Security Operations Center Dashboard.
 * Connects via WebSocket to receive live scores, events, and mouse paths.
 * Builds dynamic Chart.js timing comparisons, draws mouse trajectories,
 * and wires analyst action overrides.
 */

document.addEventListener('DOMContentLoaded', function() {
    // State
    let activeTab = 'monitor';
    let selectedSessionId = null;
    const sessionLastBands = {};
    const sessionSoundSilenced = {};
    let ws = null;
    let keystrokeChart = null;
    let overviewTrendChart = null;
    let overviewDonutChart = null;
    let overviewRadarChart = null;
    let featureImportanceChart = null;
    let sessionRiskTrendChart = null;
    let searchQuery = '';

    // ── Shared Audio Context (unlocked by user click) ─────────────
    let _audioCtx = null;
    let _audioEnabled = false;

    function enableAudioAlerts() {
        try {
            if (_audioEnabled) {
                _audioEnabled = false;
                const btn = document.getElementById('btn-enable-alerts');
                const lbl = document.getElementById('alert-btn-label');
                if (btn) {
                    btn.style.background = 'rgba(250,204,21,0.12)';
                    btn.style.borderColor = '#facc15';
                    btn.style.color = '#facc15';
                }
                if (lbl) lbl.textContent = '🔇 Alerts Silenced';
            } else {
                if (!_audioCtx) {
                    _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                }
                if (_audioCtx.state === 'suspended') {
                    _audioCtx.resume();
                }
                _audioEnabled = true;
                const btn = document.getElementById('btn-enable-alerts');
                const lbl = document.getElementById('alert-btn-label');
                if (btn) {
                    btn.style.background = 'rgba(34,197,94,0.15)';
                    btn.style.borderColor = '#22c55e';
                    btn.style.color = '#22c55e';
                }
                if (lbl) lbl.textContent = '🔔 Alerts Active';
                // Play a quick confirmation beep so the user knows it worked
                playThreatSound();
            }
        } catch (err) {
            console.warn('Could not toggle audio alerts:', err);
        }
    }
    // Expose globally so the HTML onclick can reach it
    window.enableAudioAlerts = enableAudioAlerts;

    function playThreatSound() {
        if (!_audioEnabled || !_audioCtx) return;
        try {
            if (_audioCtx.state === 'suspended') _audioCtx.resume();

            // First beep — high pitch (880 Hz)
            const osc1 = _audioCtx.createOscillator();
            const gain1 = _audioCtx.createGain();
            osc1.type = 'sine';
            osc1.frequency.setValueAtTime(880, _audioCtx.currentTime);
            gain1.gain.setValueAtTime(0.2, _audioCtx.currentTime);
            gain1.gain.exponentialRampToValueAtTime(0.001, _audioCtx.currentTime + 0.18);
            osc1.connect(gain1);
            gain1.connect(_audioCtx.destination);
            osc1.start(_audioCtx.currentTime);
            osc1.stop(_audioCtx.currentTime + 0.2);

            // Second beep — lower pitch (587 Hz), delayed 150ms
            const osc2 = _audioCtx.createOscillator();
            const gain2 = _audioCtx.createGain();
            osc2.type = 'sine';
            osc2.frequency.setValueAtTime(587.33, _audioCtx.currentTime + 0.15);
            gain2.gain.setValueAtTime(0.2, _audioCtx.currentTime + 0.15);
            gain2.gain.exponentialRampToValueAtTime(0.001, _audioCtx.currentTime + 0.42);
            osc2.connect(gain2);
            gain2.connect(_audioCtx.destination);
            osc2.start(_audioCtx.currentTime + 0.15);
            osc2.stop(_audioCtx.currentTime + 0.45);
        } catch (err) {
            console.warn('Audio playback failed:', err);
        }
    }

    function fmtScore(val, sessionCount) {
        // Show N/A for neutral 50.0 scores during cold start (< 3 sessions)
        if (val === null || val === undefined) return 'N/A';
        if ((sessionCount ?? 99) < 3 && Math.abs(val - 50.0) < 0.1) return 'N/A';
        return val.toFixed(0);
    }

    function updateProfileConfidence(sessionCount) {
        const count = sessionCount ?? 0;
        const WARM_THRESHOLD = 15;
        const pct = Math.min(100, (count / WARM_THRESHOLD) * 100);
        const profileBar   = document.getElementById('dd-profile-bar');
        const profileLabel = document.getElementById('dd-profile-label');
        const profileCount = document.getElementById('dd-session-count');
        if (profileBar) profileBar.style.width = pct + '%';
        if (profileCount) profileCount.textContent = `${count} / ${WARM_THRESHOLD} sessions`;
        if (profileLabel) {
            if (count === 0)       profileLabel.textContent = 'Cold start — using population prior';
            else if (count < 5)    profileLabel.textContent = 'Initializing — very limited data';
            else if (count < 15)   profileLabel.textContent = `Building (${count}/15) — mixed prior`;
            else                          profileLabel.textContent = '✓ Calibrated — fully personalized profile';
            profileLabel.style.color = count >= 15 ? 'var(--green)' : '#94a3b8';
        }
    }

    // Cache elements
    const elements = {
        statActive: document.getElementById('stat-active-sessions'),
        statAvgRisk: document.getElementById('stat-avg-risk'),
        statThreats: document.getElementById('stat-total-threats'),
        statFrozen: document.getElementById('stat-frozen-sessions'),
        
        sessionTableBody: document.getElementById('session-cards-container'),
        ddWorkspace: document.getElementById('deep-dive-workspace'),
        ddEmpty: document.getElementById('deep-dive-empty'),
        ddUsername: document.getElementById('dd-username'),
        ddSessionId: document.getElementById('dd-session-id'),
        ddRiskScore: document.getElementById('dd-risk-score'),
        ddRiskBadge: document.getElementById('dd-risk-badge'),
        ddShapList: document.getElementById('dd-shap-list'),
        ddSessionLogs: document.getElementById('dd-session-logs'),
        ddMouseCanvas: document.getElementById('dd-mouse-canvas'),
        
        mouseStraightness: document.getElementById('mouse-straightness'),
        mouseClickFreq: document.getElementById('mouse-click-freq'),
        mouseVariance: document.getElementById('mouse-variance'),
        
        globalLogFeed: document.getElementById('global-log-feed'),
        wsStatus: document.getElementById('ws-status'),
        wsIndicator: document.getElementById('ws-indicator'),
        
        btnFreeze: document.getElementById('btn-force-freeze'),
        btnUnfreeze: document.getElementById('btn-force-unfreeze'),
        btnSoftReset: document.getElementById('btn-soft-reset'),
        btnHardReset: document.getElementById('btn-hard-reset')
    };

    // Initialize HTTP data load
    initDashboard();

    // ==========================================
    // INITIALIZATION & REST API
    // ==========================================
    async function initDashboard() {
        initOverviewCharts();
        await fetchStats();
        await fetchSessions();
        await fetchGlobalLogs();
        connectWebSocket();

        // Setup historical search bar event listeners
        const searchInput = document.getElementById('sidebar-user-search');
        const clearBtn = document.getElementById('clear-search-btn');
        if (searchInput) {
            searchInput.addEventListener('input', function() {
                searchQuery = searchInput.value.trim();
                if (clearBtn) {
                    clearBtn.style.display = searchQuery ? 'inline' : 'none';
                }
                if (activeTab !== 'monitor' && searchQuery) {
                    switchTab('monitor');
                }
                fetchSessions();
            });
        }
        if (clearBtn) {
            clearBtn.addEventListener('click', function() {
                searchInput.value = '';
                searchQuery = '';
                clearBtn.style.display = 'none';
                fetchSessions();
            });
        }

        // Setup historical search execute listener
        const executeSearchBtn = document.getElementById('btn-execute-search');
        if (executeSearchBtn) {
            executeSearchBtn.addEventListener('click', executeSearch);
        }
    }

    async function fetchStats() {
        try {
            const r = await fetch('/api/dashboard/stats');
            const data = await r.json();
            updateStatsCards(data);
        } catch (e) { console.error("Error fetching stats:", e); }
    }

    async function fetchSessions() {
        try {
            const url = searchQuery ? `/api/dashboard/sessions?username=${encodeURIComponent(searchQuery)}` : '/api/dashboard/sessions';
            const r = await fetch(url);
            const sessions = await r.json();
            renderSessionsTable(sessions);
        } catch (e) { console.error("Error fetching sessions:", e); }
    }

    async function fetchGlobalLogs() {
        try {
            const r = await fetch('/api/dashboard/logs');
            const logs = await r.json();
            renderGlobalLogs(logs);
        } catch (e) { console.error("Error fetching logs:", e); }
    }

    function updateStatsCards(stats) {
        elements.statActive.textContent = stats.active_sessions || 0;
        elements.statFrozen.textContent = stats.frozen_sessions || 0;
        elements.statThreats.textContent = stats.threats_today || 0;
        elements.statAvgRisk.textContent = (stats.avg_risk !== undefined) ? stats.avg_risk.toFixed(1) : "0.0";

        // Update Donut Chart (Alert Triage Resolutions)
        if (!overviewDonutChart) {
            initOverviewCharts();
        }
        if (overviewDonutChart && stats.resolution_stats) {
            const res = stats.resolution_stats;
            overviewDonutChart.data.datasets[0].data = [
                res.confirmed_fraud || 0,
                res.false_positives || 0,
                res.pending_triage || 0
            ];
            overviewDonutChart.update();
        }

        // Update Overview System Risk Trend Chart using 1-minute time series
        if (!overviewTrendChart) {
            initOverviewCharts();
        }
        if (overviewTrendChart && stats.trends) {
            overviewTrendChart.data.labels = stats.trends.labels;
            overviewTrendChart.data.datasets[0].data = stats.trends.scores;
            overviewTrendChart.data.datasets[0].label = 'System Risk Index (Avg)';
            overviewTrendChart.update();
        }

        // Wire model performance metrics
        const kpiF1 = document.getElementById('kpi-f1-score');
        const kpiFP = document.getElementById('kpi-fp-suppression');
        const kpiResp = document.getElementById('kpi-response-time');
        if (kpiF1) kpiF1.textContent = stats.f1_score || 'Pending validation';
        if (kpiFP) kpiFP.textContent = stats.fp_suppression || 'Pending validation';
        if (kpiResp) kpiResp.textContent = stats.avg_response_time || 'Pending validation';

        // Wire threat vector progress bars
        const botVal = stats.vectors?.bot || 0;
        const keyVal = stats.vectors?.keystroke || 0;
        const mouseVal = stats.vectors?.mouse || 0;
        const totalVectors = botVal + keyVal + mouseVal || 1;

        const botPct = Math.round((botVal / totalVectors) * 100);
        const keyPct = Math.round((keyVal / totalVectors) * 100);
        const mousePct = Math.round((mouseVal / totalVectors) * 100);

        const botBar = document.getElementById('vector-bot-bar');
        const botPctText = document.getElementById('vector-bot-pct');
        if (botBar) botBar.style.width = `${botPct}%`;
        if (botPctText) botPctText.textContent = `${botPct}%`;

        const keyBar = document.getElementById('vector-keystroke-bar');
        const keyPctText = document.getElementById('vector-keystroke-pct');
        if (keyBar) keyBar.style.width = `${keyPct}%`;
        if (keyPctText) keyPctText.textContent = `${keyPct}%`;

        const mouseBar = document.getElementById('vector-mouse-bar');
        const mousePctText = document.getElementById('vector-mouse-pct');
        if (mouseBar) mouseBar.style.width = `${mousePct}%`;
        if (mousePctText) mousePctText.textContent = `${mousePct}%`;

        // Update 7-band spectrum
        updateRiskSpectrum(stats.band_counts);
    }

    function updateRiskSpectrum(bandCounts) {
        if (!bandCounts) return;
        
        const bands = [
            { id: 'green', key: 'GREEN', label: 'GREEN' },
            { id: 'amber-low', key: 'AMBER_LOW', label: 'AMBER L' },
            { id: 'amber-mid', key: 'AMBER_MID', label: 'AMBER M' },
            { id: 'amber-high', key: 'AMBER_HIGH', label: 'AMBER H' },
            { id: 'red-low', key: 'RED_LOW', label: 'RED L' },
            { id: 'red-high', key: 'RED_HIGH', label: 'RED H' },
            { id: 'red-critical', key: 'RED_CRITICAL', label: 'CRITICAL' }
        ];

        const totalActive = Object.values(bandCounts).reduce((a, b) => a + b, 0);

        if (totalActive === 0) {
            bands.forEach(b => {
                const bar = document.getElementById(`spectrum-${b.id}`);
                const countSpan = document.getElementById(`spectrum-${b.id}-count`);
                if (countSpan) countSpan.textContent = '0';
                if (bar) {
                    if (b.id === 'green') {
                        bar.style.display = 'flex';
                        bar.style.width = '100%';
                    } else {
                        bar.style.display = 'none';
                        bar.style.width = '0%';
                    }
                }
            });
            return;
        }

        bands.forEach(b => {
            const bar = document.getElementById(`spectrum-${b.id}`);
            const countSpan = document.getElementById(`spectrum-${b.id}-count`);
            const count = bandCounts[b.key] || 0;

            if (countSpan) countSpan.textContent = count;

            if (bar) {
                if (count === 0) {
                    bar.style.display = 'none';
                    bar.style.width = '0%';
                } else {
                    bar.style.display = 'flex';
                    const pct = (count / totalActive) * 100;
                    bar.style.width = `${pct}%`;
                }
            }
        });
    }

    // ==========================================
    // WEBSOCKET COMMUNICATIONS
    // ==========================================
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        const wsUrl = `${protocol}${window.location.host}/ws/dashboard`;

        ws = new WebSocket(wsUrl);

        ws.onopen = function() {
            console.log("[Dashboard] WS connection established.");
            elements.wsStatus.textContent = "Engine Connected (live)";
            elements.wsIndicator.classList.remove('Disconnected');
        };

        ws.onmessage = function(event) {
            if (event.data === 'pong') return;
            
            try {
                const data = JSON.parse(event.data);
                handleWsEvent(data);
            } catch (err) {
                console.error("[Dashboard] Error parsing WS event:", err);
            }
        };

        ws.onclose = function() {
            console.warn("[Dashboard] WS disconnected. Retrying in 5s...");
            elements.wsStatus.textContent = "Reconnecting...";
            elements.wsIndicator.classList.add('Disconnected');
            setTimeout(connectWebSocket, 5000);
        };
    }

    function handleWsEvent(evt) {
        console.log("[Dashboard] WS Event received:", evt.type, evt);

        // Update overall stats card on every event
        fetchStats();

        switch (evt.type) {
            case 'connected':
                updateStatsCards(evt.stats);
                break;
            case 'session_created':
                addSessionToTable(evt);
                appendGlobalLog({
                    timestamp: Date.now() / 1000,
                    event_type: 'LOGIN_OK',
                    username: evt.username,
                    risk_score: evt.score,
                    risk_band: evt.band,
                    details: { message: "User session initialized." }
                });
                break;
            case 'score_update':
                updateSessionInTable(evt);
                appendGlobalLog({
                    timestamp: evt.timestamp || Date.now() / 1000,
                    event_type: evt.is_bot ? 'BOT_DETECTED' : 'SCORE_UPDATE',
                    username: evt.username,
                    risk_score: evt.score,
                    risk_band: evt.band,
                    details: { score: evt.score, keystroke: evt.keystroke_score, mouse: evt.mouse_score }
                });

                // Play threat sound if score enters RED bands and has not been acknowledged/deep-dived
                const isRed = evt.band && (evt.band.startsWith('RED') || evt.is_bot);
                const prevBand = sessionLastBands[evt.session_id] || 'GREEN';
                const newBand = evt.band || 'GREEN';
                sessionLastBands[evt.session_id] = newBand;

                if (!isRed) {
                    sessionSoundSilenced[evt.session_id] = false;
                } else {
                    const isOpened = (selectedSessionId === evt.session_id);
                    if (isOpened) {
                        sessionSoundSilenced[evt.session_id] = true;
                    } else {
                        // Play sound if not already silenced or if it just transitioned back to RED
                        if (!prevBand.startsWith('RED') || !sessionSoundSilenced[evt.session_id]) {
                            playThreatSound();
                        }
                    }
                }

                // If selected session matches, update deep-dive
                if (selectedSessionId && (evt.session_id === selectedSessionId || selectedSessionId.startsWith(evt.session_id.substring(0, 8)))) {
                    updateDeepDiveWorkspace(evt);
                }
                break;
            case 'reauth_success':
            case 'reauth_fail':
                appendGlobalLog({
                    timestamp: Date.now() / 1000,
                    event_type: evt.type.toUpperCase(),
                    username: evt.username,
                    risk_score: evt.new_score,
                    risk_band: evt.band || 'GREEN',
                    details: { message: evt.type === 'reauth_success' ? "Typing verification passed" : "Typing verification failed" }
                });
                fetchSessions();
                break;
            case 'session_frozen':
                appendGlobalLog({
                    timestamp: Date.now() / 1000,
                    event_type: 'SESSION_FROZEN',
                    username: evt.username,
                    details: { reason: evt.reason }
                });
                fetchSessions();
                if (selectedSessionId && selectedSessionId.startsWith(evt.session_id.substring(0, 8))) {
                    elements.ddRiskBadge.textContent = "FROZEN";
                    elements.ddRiskBadge.className = "badge badge-critical";
                }
                break;
            case 'false_positive':
                appendGlobalLog({
                    timestamp: Date.now() / 1000,
                    event_type: 'REAUTH_SUCCESS',
                    username: evt.username,
                    details: { message: "Session marked false-positive" }
                });
                fetchSessions();
                break;
            case 'simulated_alert':
                appendGlobalLog(evt.alert);
                break;
            case 'demo_reset':
            case 'soft_reset':
                console.log("[Dashboard] Reset signal. Refreshing all...");
                selectedSessionId = null;
                elements.ddWorkspace.classList.add('hidden');
                elements.ddEmpty.classList.remove('hidden');
                fetchSessions();
                fetchGlobalLogs();
                break;
        }
        if (activeTab === 'frozen') {
            fetchFrozenSessions();
        }
    }

    // ==========================================
    // SESSIONS LIST CARDS RENDER
    // ==========================================
    function renderSessionsTable(sessions) {
        elements.sessionTableBody.innerHTML = '';
        if (sessions.length === 0) {
            elements.sessionTableBody.innerHTML = `
                <div class="col-12 text-center text-muted p-6" style="background: rgba(255,255,255,0.01); border: 1px dashed var(--border); border-radius: var(--radius-lg); width: 100%;">
                    <i class="ti ti-circle-check-filled" style="color: var(--green); font-size: 1.5rem; display: block; margin-bottom: 0.5rem;"></i>
                    No active security threats or anomalous sessions monitored in this cycle.
                </div>
            `;
            updateOverviewCharts([]);
            return;
        }

        sessions.forEach(s => {
            const card = createSessionCard(s);
            elements.sessionTableBody.appendChild(card);
        });

        // Update operations overview charts dynamically
        updateOverviewCharts(sessions);
    }

    function createSessionCard(s) {
        const isTerminated = ['terminated', 'red_low', 'red_high', 'red_critical'].includes(s.status);
        const card = document.createElement('div');
        card.id = `card-${s.session_id}`;
        const isBotCrit = (s.band === 'RED_CRITICAL' && s.risk_score >= 97);
        card.className = `alert-card ${selectedSessionId === s.session_id ? 'selected' : ''} ${isTerminated ? 'terminated' : ''} ${isBotCrit ? 'bot-flash' : ''}`;
        
        let formattedTimestamp = 'Unknown Date';
        if (s.created_at) {
            const dateObj = new Date(s.created_at * 1000);
            const timeStr = dateObj.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            const dateStr = dateObj.toLocaleDateString([], { month: 'short', day: 'numeric' });
            formattedTimestamp = `${dateStr} @ ${timeStr}`;
        }

        // Map IP to Country Flag
        function getIPCountryFlag(ip) {
            if (!ip) return '🌐';
            const cleanIp = ip.trim();
            if (cleanIp === '127.0.0.1' || cleanIp === '::1' || cleanIp === 'localhost' || cleanIp.startsWith('192.168.') || cleanIp.startsWith('10.')) {
                return '💻';
            }
            if (cleanIp.startsWith('103.') || cleanIp.startsWith('122.') || cleanIp.startsWith('115.') || cleanIp.startsWith('223.')) {
                return '<img src="https://flagcdn.com/w20/in.png" style="width: 16px; height: auto; vertical-align: middle; border-radius: 2px; box-shadow: 0 0 2px rgba(255,255,255,0.25);" alt="IN">';
            }
            if (cleanIp.startsWith('104.') || cleanIp.startsWith('198.') || cleanIp.startsWith('172.') || cleanIp.startsWith('52.')) {
                return '<img src="https://flagcdn.com/w20/us.png" style="width: 16px; height: auto; vertical-align: middle; border-radius: 2px; box-shadow: 0 0 2px rgba(255,255,255,0.25);" alt="US">';
            }
            if (cleanIp.startsWith('91.') || cleanIp.startsWith('95.') || cleanIp.startsWith('185.')) {
                return '<img src="https://flagcdn.com/w20/ru.png" style="width: 16px; height: auto; vertical-align: middle; border-radius: 2px; box-shadow: 0 0 2px rgba(255,255,255,0.25);" alt="RU">';
            }
            if (cleanIp.startsWith('45.') || cleanIp.startsWith('82.')) {
                return '<img src="https://flagcdn.com/w20/gb.png" style="width: 16px; height: auto; vertical-align: middle; border-radius: 2px; box-shadow: 0 0 2px rgba(255,255,255,0.25);" alt="GB">';
            }
            return '🌐';
        }
        const flag = getIPCountryFlag(s.ip_address);
        
        // Severity mapping (7-band alignment)
        const severity = s.band || 'GREEN';
        let severityClass = 'badge-green';
        let scoreColor = 'var(--green)';
        
        switch (severity) {
            case 'GREEN':
                severityClass = 'badge-green';
                scoreColor = 'var(--green)';
                break;
            case 'AMBER_LOW':
            case 'AMBER_MID':
                severityClass = 'badge-amber';
                scoreColor = 'var(--amber)';
                break;
            case 'AMBER_HIGH':
                severityClass = 'badge-orange';
                scoreColor = 'var(--orange)';
                break;
            case 'RED_LOW':
            case 'RED_HIGH':
                severityClass = 'badge-red';
                scoreColor = 'var(--red)';
                break;
            case 'RED_CRITICAL':
                severityClass = 'badge-critical';
                scoreColor = 'var(--red-critical)';
                break;
            default:
                severityClass = 'badge-green';
                scoreColor = 'var(--green)';
                break;
        }

        // Threat source heuristic mapping
        let source = 'Identity / API';
        if (s.is_bot) {
            source = 'Endpoint / Bot Heuristics';
        } else if (s.risk_score > 50) {
            source = 'Identity / Biometrics Drift';
        } else if (s.risk_score > 20) {
            source = 'Session / Context Anomaly';
        }

        card.innerHTML = `
            <div class="alert-card-header">
                <div>
                    <h4 style="margin: 0; color: #fff; font-size: 0.95rem; display: flex; align-items: center; gap: 6px;">
                        ${s.username} 
                        ${isTerminated ? '<span class="text-xs text-muted fw-normal" style="opacity: 0.75; font-size: 10px;">(Offline)</span>' : ''}
                        ${s.is_dismissed ? '<span style="font-size:0.55rem; font-weight:800; background:rgba(34,197,94,0.15); color:#4ade80; border:1px solid rgba(74,222,128,0.25); padding:1px 6px; border-radius:99px; text-transform:uppercase;">\u2713 Cleared</span>' : ''}
                    </h4>
                    <span class="text-mono text-xs text-muted">${s.session_id.substring(0, 8)}...</span>
                    <span class="text-xs text-muted" style="display: block; margin-top: 3px; font-size: 10px;">
                        <i class="ti ti-clock" style="font-size: 10px; margin-right: 2px;"></i> ${formattedTimestamp}
                    </span>
                </div>
                <span class="badge ${severityClass} text-xs">${severity}</span>
            </div>
            
            <div class="alert-card-body">
                <div>
                    <span class="text-xs text-muted" style="display: block; margin-bottom: 2px;">Source / Vector</span>
                    <span class="text-xs text-mono" style="color: var(--cyan); font-weight: 600;">${source}</span>
                    
                    <span class="text-xs text-muted" style="display: block; margin-top: 6px; margin-bottom: 2px;">Client Location</span>
                    <span class="text-xs text-mono" style="color: #fff; font-weight: 600; display: flex; align-items: center; gap: 4px;">
                        <span style="font-size: 1.1rem; line-height: 1;">${flag}</span>
                        <span style="font-size: 11px; opacity: 0.85;">${s.ip_address || 'Unknown IP'}</span>
                    </span>
                </div>
                <div class="alert-card-score-wrapper">
                    <span class="text-xs text-muted" style="display: block; margin-bottom: 2px;">Risk Index</span>
                    <span class="alert-card-score" style="color: ${scoreColor}; font-weight: 800; font-family: var(--font-mono); font-size: 1.4rem;">${s.risk_score.toFixed(1)}</span>
                </div>
            </div>

            <div class="alert-card-footer">
                <span class="text-xs text-muted">Actions: ${s.action_count || 0}</span>
                ${(() => {
                    const sc = s.session_count ?? 0;
                    if (s.is_enrolled && sc >= 15)
                        return `<span style="font-size:0.6rem;font-weight:700;padding:1px 6px;border-radius:99px;background:rgba(34,197,94,0.12);color:#4ade80;border:1px solid rgba(74,222,128,0.25);">\u2713 Calibrated</span>`;
                    if (s.is_enrolled && sc >= 3)
                        return `<span style="font-size:0.6rem;font-weight:700;padding:1px 6px;border-radius:99px;background:rgba(251,191,36,0.12);color:#fbbf24;border:1px solid rgba(251,191,36,0.25);">\u27F3 Building (${sc}/15)</span>`;
                    return `<span style="font-size:0.6rem;font-weight:700;padding:1px 6px;border-radius:99px;background:rgba(148,163,184,0.1);color:#64748b;border:1px solid rgba(100,116,139,0.2);">\u25CC Cold Start</span>`;
                })()}
                <div class="flex gap-1">
                    <button class="btn btn-secondary btn-sm px-2 py-1 investigate-btn" style="font-size: 0.72rem; padding: 0.25rem 0.5rem; height: auto;"><i class="ti ti-zoom-in" style="font-size:0.75rem;"></i> Investigate</button>
                    ${s.is_dismissed ? '' : '<button class="btn btn-ghost btn-sm px-2 py-1 dismiss-btn" style="font-size: 0.72rem; padding: 0.25rem 0.5rem; color: var(--text-secondary); height: auto;">Dismiss</button>'}
                </div>
            </div>
        `;

        // Event listener for Investigate button or card click
        card.querySelector('.investigate-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            selectSession(s.session_id);
        });
        card.addEventListener('click', () => selectSession(s.session_id));
        
        const dismissBtn = card.querySelector('.dismiss-btn');
        if (dismissBtn) {
            dismissBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (confirm(`Dismiss alert for user ${s.username}?`)) {
                try {
                    const response = await fetch(`/api/admin/false-positive/${s.session_id}`, { method: 'POST' });
                    if (response.ok) {
                        showToast("Alert dismissed and marked false-positive", "success");
                        fetchSessions();
                    }
                } catch (err) {
                    console.error(err);
                }
            }
        });
    }

        return card;
    }

    function addSessionToTable(s) {
        // Remove empty placeholder row if present
        if (elements.sessionTableBody.innerHTML.includes('No active security threats')) {
            elements.sessionTableBody.innerHTML = '';
        }

        const formatted = {
            session_id: s.session_id,
            username: s.username,
            status: 'active',
            duration_sec: 0,
            action_count: 0,
            risk_score: s.score,
            band: s.band,
            created_at: s.created_at || (Date.now() / 1000),
            ip_address: s.ip_address || '127.0.0.1'
        };
        const card = createSessionCard(formatted);
        card.classList.add('pulse-pop');
        elements.sessionTableBody.appendChild(card);
        fetchSessions(); // refresh stats and charts
    }

    function updateSessionInTable(s) {
        const cardId = `card-${s.session_id}`;
        const existingCard = document.getElementById(cardId);
        
        if (existingCard) {
            // If the session has escalated to RED, remove it from active sessions list immediately
            if (s.band && s.band.startsWith('RED')) {
                existingCard.remove();
                fetchSessions();
                fetchFrozenSessions();
                return;
            }

            let existingIP = '127.0.0.1';
            const ipEl = existingCard.querySelector('.alert-card-body span[style*="opacity: 0.85"]');
            if (ipEl) existingIP = ipEl.textContent.trim();

            const formatted = {
                session_id: s.session_id,
                username: s.username,
                status: s.band.startsWith('RED') ? 'frozen' : 'active',
                duration_sec: 15, // placeholder
                action_count: s.action_count || 3, // placeholder
                risk_score: s.score,
                band: s.band,
                created_at: s.created_at || s.timestamp || (Date.now() / 1000),
                ip_address: s.ip_address || existingIP || '127.0.0.1'
            };
            const newCard = createSessionCard(formatted);
            existingCard.replaceWith(newCard);
        } else {
            fetchSessions();
        }
    }

    function applyBadgeColor(badge, band) {
        badge.className = "badge";
        switch (band) {
            case 'GREEN':
                badge.classList.add('badge-green');
                break;
            case 'AMBER_LOW':
            case 'AMBER_MID':
                badge.classList.add('badge-amber');
                break;
            case 'AMBER_HIGH':
                badge.classList.add('badge-orange');
                break;
            case 'RED_LOW':
            case 'RED_HIGH':
                badge.classList.add('badge-red');
                break;
            case 'RED_CRITICAL':
                badge.classList.add('badge-critical');
                break;
            default:
                badge.classList.add('badge-gray');
                break;
        }
    }

    function getPlainEnglishAlert(feature, defaultLabel) {
        const mapping = {
            'bot_detection': 'Automated replay signature detected (Bot)',
            'device_match': 'Device fingerprint mismatch (New Device)',
            'time_of_day_risk': 'Unusual out-of-hours session activity',
            'is_enrolled': 'No enrolled typing model available',
            'mean_hold_time': 'Anomalous keystroke dwell/hold pattern',
            'std_hold_time': 'Irregular typing speed consistency',
            'flight_time_enrollment': 'Passphrase typing cadence deviation',
            'mean_flight_time': 'Anomalous key-to-key transition flight time',
            'trajectory_straightness': 'Highly straight mouse path (Bot/Script indicator)',
            'mouse_mean_velocity': 'Anomalous mouse cursor movement velocity',
            'scroll_speed_mean': 'Abnormal scroll velocity signature',
            'click_frequency': 'Rapid mouse click frequency deviation',
            'direction_changes_per_sec': 'Jittery cursor trajectory pattern',
            'metadata_score': 'Contextual security parameter anomaly',
            'keystroke_score': 'Biometric keystroke timing signature drift',
            'mouse_score': 'Cursor trajectory biometrics deviation'
        };
        
        if (mapping[feature]) return mapping[feature];
        
        const lowerLabel = (defaultLabel || '').toLowerCase();
        if (lowerLabel.includes('hold duration')) return 'Anomalous key hold duration';
        if (lowerLabel.includes('flight duration') || lowerLabel.includes('flight time')) return 'Anomalous key transition cadence';
        if (lowerLabel.includes('straightness')) return 'Linear/Non-human cursor movement';
        if (lowerLabel.includes('velocity') || lowerLabel.includes('speed')) return 'Irregular cursor speed profile';
        if (lowerLabel.includes('bot')) return 'Bot signature detected';
        if (lowerLabel.includes('ip') || lowerLabel.includes('location')) return 'Unusual network locator/IP anomaly';
        
        return defaultLabel || feature;
    }

    function updateGuardrailsCard(band) {
        const card = document.getElementById('session-restrictions-card');
        const badge = document.getElementById('dd-restriction-badge');
        const text = document.getElementById('dd-restriction-text');
        if (!card || !badge || !text) return;

        let borderLeft = '4px solid var(--green)';
        let badgeText = 'INACTIVE';
        let badgeClass = 'badge badge-green';
        let guardrailText = 'No active guardrails. Full transactional capabilities enabled.';

        switch (band) {
            case 'GREEN':
                borderLeft = '4px solid var(--green)';
                badgeText = 'INACTIVE';
                badgeClass = 'badge badge-green';
                guardrailText = 'No active guardrails. Full transactional capabilities enabled.';
                break;
            case 'AMBER_LOW':
                borderLeft = '4px solid var(--amber)';
                badgeText = 'MFA CHALLENGE';
                badgeClass = 'badge badge-amber';
                guardrailText = 'Out-of-band MFA verification prompted for high-value transactions.';
                break;
            case 'AMBER_MID':
                borderLeft = '4px solid var(--amber)';
                badgeText = 'STRICT LIMITS';
                badgeClass = 'badge badge-amber';
                guardrailText = 'Multi-factor authentication required for ALL fund transfers. Limits capped at INR 10,000.';
                break;
            case 'AMBER_HIGH':
                borderLeft = '4px solid var(--orange)';
                badgeText = 'CHALLENGE REQ';
                badgeClass = 'badge badge-orange';
                guardrailText = 'Transactions blocked. Out-of-band verification required to resume session.';
                break;
            case 'RED_LOW':
                borderLeft = '4px solid var(--red)';
                badgeText = 'SUSPENDED';
                badgeClass = 'badge badge-red';
                guardrailText = 'Session frozen. High-value transactions suspended. Analyst review required.';
                break;
            case 'RED_HIGH':
                borderLeft = '4px solid var(--red)';
                badgeText = 'LOCKED';
                badgeClass = 'badge badge-red';
                guardrailText = 'Account locked. All transactions blocked. Re-authentication failed.';
                break;
            case 'RED_CRITICAL':
                borderLeft = '4px solid var(--red-critical)';
                badgeText = 'BLOCKED';
                badgeClass = 'badge badge-critical';
                guardrailText = 'Critical security freeze. Automatic device IP ban. Fraud team dispatched.';
                break;
            default:
                borderLeft = '4px solid var(--green)';
                badgeText = 'INACTIVE';
                badgeClass = 'badge badge-green';
                guardrailText = 'No active guardrails. Full transactional capabilities enabled.';
                break;
        }

        card.style.borderLeft = borderLeft;
        badge.textContent = badgeText;
        badge.className = badgeClass;
        text.textContent = guardrailText;
    }

    async function renderSessionRiskHeartbeatChart(sid, currentScore = 0.0) {
        try {
            const res = await fetch(`/api/dashboard/session/${sid}/history`);
            const data = await res.json();
            let history = data.history || [];
            
            // If history is empty, initialize it with a starting green baseline and the current score
            if (history.length === 0) {
                const nowSec = Date.now() / 1000;
                history = [
                    {
                        timestamp: nowSec - 60,
                        score: 0.1,
                        band: 'GREEN'
                    },
                    {
                        timestamp: nowSec,
                        score: currentScore !== undefined && currentScore !== null ? currentScore : 0.1,
                        band: (currentScore >= 60) ? 'RED_LOW' : (currentScore >= 35) ? 'AMBER_LOW' : 'GREEN'
                    }
                ];
            } else if (history.length === 1) {
                // If there's only 1 point in the history, prepend a green baseline point 60 seconds earlier
                // so Chart.js has at least two points to draw a line segment
                const firstPoint = history[0];
                history.unshift({
                    timestamp: firstPoint.timestamp - 60,
                    score: 0.1,
                    band: 'GREEN'
                });
            }
            
            const scores = history.map(h => typeof h === 'object' && h !== null ? h.score : h);
            const labels = history.map((h, idx) => {
                if (typeof h === 'object' && h !== null && h.timestamp) {
                    return new Date(h.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                }
                return `Cycle ${idx + 1}`;
            });
            
            if (sessionRiskTrendChart) {
                sessionRiskTrendChart.destroy();
            }
            
            const ctx = document.getElementById('session-risk-trend-chart').getContext('2d');
            if (!ctx) return;
            
            const gradient = ctx.createLinearGradient(0, 0, 0, 140);
            gradient.addColorStop(0, 'rgba(59, 130, 246, 0.35)'); // Brand cobalt gradient
            gradient.addColorStop(0.5, 'rgba(59, 130, 246, 0.15)');
            gradient.addColorStop(1, 'rgba(59, 130, 246, 0.01)');
            
            sessionRiskTrendChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Risk Index',
                        data: scores,
                        borderColor: 'var(--brand)',
                        borderWidth: 2,
                        tension: 0.3,
                        pointBackgroundColor: scores.map(val => val >= 60 ? 'var(--red)' : val >= 35 ? 'var(--amber)' : 'var(--green)'),
                        pointBorderColor: '#0f172a',
                        pointBorderWidth: 1,
                        pointRadius: 3.5,
                        pointHoverRadius: 5.5,
                        backgroundColor: gradient,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        x: {
                            ticks: { color: '#94a3b8', font: { family: 'Outfit', size: 9 } },
                            grid: { display: false }
                        },
                        y: {
                            min: 0,
                            max: 100,
                            ticks: { color: '#94a3b8', font: { family: 'Outfit', size: 9 }, stepSize: 20 },
                            grid: { color: 'rgba(255, 255, 255, 0.05)' }
                        }
                    }
                }
            });
        } catch (e) {
            console.error("Error loading risk heartbeat history:", e);
        }
    }

    function closeDeepDive() {
        selectedSessionId = null;
        const cards = elements.sessionTableBody.querySelectorAll('.alert-card');
        cards.forEach(c => c.classList.remove('selected'));
        
        elements.ddWorkspace.classList.add('hidden');
        elements.ddEmpty.classList.remove('hidden');
        
        // Refresh overview charts
        fetchSessions();
    }
    window.closeDeepDive = closeDeepDive;

    async function selectSession(fullId) {
        if (selectedSessionId === fullId) {
            closeDeepDive();
            return;
        }

        // Highlight card
        const cards = elements.sessionTableBody.querySelectorAll('.alert-card');
        cards.forEach(c => c.classList.remove('selected'));
        
        const selectedCard = document.getElementById(`card-${fullId}`);
        if (selectedCard) selectedCard.classList.add('selected');

        selectedSessionId = fullId;
        sessionSoundSilenced[fullId] = true;
        
        elements.ddEmpty.classList.add('hidden');
        elements.ddWorkspace.classList.remove('hidden');
        
        // Auto-scroll deep dive workspace panel into view
        elements.ddWorkspace.scrollIntoView({ behavior: 'smooth', block: 'start' });

        try {
            const rSession = await fetch(`/api/dashboard/sessions`);
            const sessions = await rSession.json();
            let sessionData = sessions.find(s => s.session_id === selectedSessionId);

            if (!sessionData) {
                const rFrozen = await fetch(`/api/dashboard/sessions/frozen`);
                const frozenSessions = await rFrozen.json();
                sessionData = frozenSessions.find(s => s.session_id === selectedSessionId);
            }

            if (sessionData) {
                // Determine initials and real name
                let initials = "HA";
                let realName = "Hari Ahir";
                if (sessionData.username.toLowerCase().startsWith('h')) {
                    initials = "HA";
                    realName = "Hari Ahir";
                } else if (sessionData.username.toLowerCase().startsWith('p')) {
                    initials = "PS";
                    realName = "Priya Sharma";
                } else {
                    initials = sessionData.username.substring(0, 2).toUpperCase();
                    realName = sessionData.username;
                }
                const initialsEl = document.getElementById('dd-avatar-initials');
                if (initialsEl) initialsEl.textContent = initials;
                elements.ddUsername.textContent = realName;
                
                // Set status dot color
                const statusDot = document.getElementById('dd-status-dot');
                if (statusDot) {
                    statusDot.className = 'status-dot';
                    if (sessionData.band === 'GREEN') statusDot.classList.add('dot-green');
                    else if (sessionData.band.startsWith('AMBER')) statusDot.classList.add('dot-amber');
                    else statusDot.classList.add('dot-red');
                }

                elements.ddSessionId.textContent = `Session ID: ${selectedSessionId}`;
                elements.ddRiskScore.textContent = sessionData.risk_score.toFixed(1);
                
                // Set score color class dynamically
                elements.ddRiskScore.className = 'score-number';
                if (sessionData.risk_score >= 60) elements.ddRiskScore.classList.add('red');
                else if (sessionData.risk_score >= 35) elements.ddRiskScore.classList.add('amber');
                else elements.ddRiskScore.classList.add('green');

                elements.ddRiskBadge.textContent = sessionData.band;
                applyBadgeColor(elements.ddRiskBadge, sessionData.band);

                // Toggle Freeze / Unfreeze override button state
                const isFrozen = ['terminated', 'red_low', 'red_high', 'red_critical'].includes(sessionData.status);
                if (elements.btnFreeze) {
                    if (isFrozen) {
                        elements.btnFreeze.innerHTML = '<i class="ti ti-check"></i> Unfreeze Session';
                        elements.btnFreeze.className = 'btn btn-success btn-sm flex-1';
                    } else {
                        elements.btnFreeze.innerHTML = '<i class="ti ti-alert-triangle"></i> Force Freeze';
                        elements.btnFreeze.className = 'btn btn-danger btn-sm flex-1';
                    }
                }

                // Populate Diagnostics
                document.getElementById('dd-ip-address').textContent = sessionData.ip_address || '127.0.0.1';
                document.getElementById('dd-interval').textContent = `${sessionData.scoring_interval || 30}s`;
                document.getElementById('dd-user-agent').textContent = sessionData.user_agent || 'Unknown Client';
                updateProfileConfidence(sessionData.session_count);

                // Update charts, breakdowns and restrictions
                updateShapBreakdown(sessionData.last_breakdown);
                renderKeystrokeChart(sessionData.last_breakdown);
                drawMouseTrajectory(sessionData.last_breakdown);
                renderFeatureImportanceChart();
                fetchAndRenderSessionHeartbeatLogs(selectedSessionId);
                renderSessionRiskHeartbeatChart(selectedSessionId, sessionData.risk_score);
                updateGuardrailsCard(sessionData.band);

                // Render intruder label panel
                renderIntruderLabelPanel(selectedSessionId);
            }
        } catch (e) {
            console.error("Error loading deep dive details:", e);
        }
    }

    function updateDeepDiveWorkspace(evt) {
        elements.ddRiskScore.textContent = evt.score.toFixed(1);
        
        elements.ddRiskScore.className = 'score-number';
        if (evt.score >= 60) elements.ddRiskScore.classList.add('red');
        else if (evt.score >= 35) elements.ddRiskScore.classList.add('amber');
        else elements.ddRiskScore.classList.add('green');

        elements.ddRiskBadge.textContent = evt.band;
        applyBadgeColor(elements.ddRiskBadge, evt.band);

        // Toggle Freeze / Unfreeze override button state
        const isFrozen = ['terminated', 'red_low', 'red_high', 'red_critical'].includes(evt.status);
        if (elements.btnFreeze) {
            if (isFrozen) {
                elements.btnFreeze.innerHTML = '<i class="ti ti-check"></i> Unfreeze Session';
                elements.btnFreeze.className = 'btn btn-success btn-sm flex-1';
            } else {
                elements.btnFreeze.innerHTML = '<i class="ti ti-alert-triangle"></i> Force Freeze';
                elements.btnFreeze.className = 'btn btn-danger btn-sm flex-1';
            }
        }

        // Update metadata live
        if (evt.ip_address) document.getElementById('dd-ip-address').textContent = evt.ip_address;
        if (evt.scoring_interval) document.getElementById('dd-interval').textContent = `${evt.scoring_interval}s`;
        if (evt.user_agent) document.getElementById('dd-user-agent').textContent = evt.user_agent;

        // Profile confidence
        updateProfileConfidence(evt.session_count);

        // Find matching breakdown object
        const breakdownPayload = {
            all_contributors: evt.all_contributors || [],
            top_contributors: evt.top_contributors || [],
            mouse_samples: evt.mouse_samples || []
        };

        updateShapBreakdown(breakdownPayload);
        renderKeystrokeChart(breakdownPayload);
        drawMouseTrajectory(breakdownPayload);
        renderFeatureImportanceChart();
        fetchAndRenderSessionHeartbeatLogs(selectedSessionId);
        renderSessionRiskHeartbeatChart(selectedSessionId, evt.score);
        updateGuardrailsCard(evt.band);
    }

    function updateShapBreakdown(breakdownObj) {
        elements.ddShapList.innerHTML = '';
        if (!breakdownObj || !breakdownObj.top_contributors || breakdownObj.top_contributors.length === 0) {
            elements.ddShapList.innerHTML = '<p class="text-xs text-muted">No anomaly triggers active.</p>';
            return;
        }

        breakdownObj.top_contributors.forEach(c => {
            if (c.contribution <= 0.5) return;
            
            const item = document.createElement('div');
            item.className = 'breakdown-item';
            if (c.contribution > 15) item.classList.add('high');
            else if (c.contribution > 5) item.classList.add('med');

            const alertTitle = getPlainEnglishAlert(c.feature, c.label);

            item.innerHTML = `
                <div class="breakdown-label" title="${alertTitle}">${alertTitle}</div>
                <div class="breakdown-bar-wrap">
                    <div class="breakdown-bar-fill" style="width: ${c.contribution}%"></div>
                </div>
                <div class="breakdown-value text-mono">+${c.contribution.toFixed(0)}</div>
            `;
            elements.ddShapList.appendChild(item);
        });
    }

    function renderKeystrokeChart(breakdownObj) {
        if (!breakdownObj || !breakdownObj.all_contributors) return;

        // Filter aggregate keystroke features measured in ms
        const msFeatures = breakdownObj.all_contributors.filter(c => 
            c.unit === 'ms' && (c.feature.includes('hold') || c.feature.includes('flight'))
        );

        if (msFeatures.length === 0) return;

        const labels = msFeatures.map(c => c.label.replace('Mean ', '').replace('key ', ''));
        const observedData = msFeatures.map(c => c.observed);
        const baselineData = msFeatures.map(c => c.baseline_mean);

        if (keystrokeChart) {
            keystrokeChart.destroy();
        }

        const ctx = document.getElementById('keystroke-chart').getContext('2d');
        
        // Create gradients
        const gradientObs = ctx.createLinearGradient(0, 0, 0, 150);
        gradientObs.addColorStop(0, 'rgba(6, 182, 212, 0.85)'); // Cyan
        gradientObs.addColorStop(1, 'rgba(6, 182, 212, 0.1)');

        const gradientBase = ctx.createLinearGradient(0, 0, 0, 150);
        gradientBase.addColorStop(0, 'rgba(99, 102, 241, 0.45)'); // Indigo
        gradientBase.addColorStop(1, 'rgba(99, 102, 241, 0.05)');

        keystrokeChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Observed Time (ms)',
                        data: observedData,
                        backgroundColor: gradientObs,
                        borderColor: 'rgba(6, 182, 212, 0.9)',
                        borderWidth: 1.5,
                        borderRadius: 4
                    },
                    {
                        label: 'Enrolled Baseline (ms)',
                        data: baselineData,
                        backgroundColor: gradientBase,
                        borderColor: 'rgba(99, 102, 241, 0.5)',
                        borderWidth: 1.5,
                        borderRadius: 4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: { 
                            color: '#e2e8f0', 
                            font: { family: 'Outfit', size: 10, weight: 600 } 
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: '#94a3b8', font: { family: 'Outfit', size: 9 } },
                        grid: { color: 'rgba(30, 58, 138, 0.15)' }
                    },
                    y: {
                        ticks: { color: '#94a3b8', font: { family: 'Outfit', size: 9 } },
                        grid: { color: 'rgba(30, 58, 138, 0.15)' }
                    }
                }
            }
        });
    }

    function drawMouseTrajectory(breakdownObj) {
        const canvas = elements.ddMouseCanvas;
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Fetch stats features for labels
        if (breakdownObj && breakdownObj.all_contributors) {
            const straight = breakdownObj.all_contributors.find(c => c.feature === 'trajectory_straightness');
            const speed = breakdownObj.all_contributors.find(c => c.feature === 'mouse_mean_velocity');
            const scroll = breakdownObj.all_contributors.find(c => c.feature === 'scroll_speed_mean');
            
            elements.mouseStraightness.textContent = straight ? straight.observed.toFixed(3) : '-';
            elements.mouseClickFreq.textContent = speed ? `${(speed.observed * 100).toFixed(1)} px/ms` : '-';
            elements.mouseVariance.textContent = scroll ? scroll.observed.toFixed(1) : '-';
        }

        // Clear background with scientific grid layout
        ctx.fillStyle = '#0b111e';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Canvas Outline
        ctx.strokeStyle = 'rgba(59, 130, 246, 0.2)';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(0, 0, canvas.width, canvas.height);

        // Draw grid lines
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.035)';
        ctx.lineWidth = 0.5;
        const step = 20;
        for (let i = step; i < canvas.width; i += step) {
            ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, canvas.height); ctx.stroke();
        }
        for (let i = step; i < canvas.height; i += step) {
            ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(canvas.width, i); ctx.stroke();
        }

        // Draw clean screen-relative axes
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
        ctx.lineWidth = 1;
        // Y Axis at X = 15
        ctx.beginPath(); ctx.moveTo(15, 0); ctx.lineTo(15, canvas.height); ctx.stroke();
        // X Axis at Y = canvas.height - 15
        ctx.beginPath(); ctx.moveTo(0, canvas.height - 15); ctx.lineTo(canvas.width, canvas.height - 15); ctx.stroke();

        // Axis Tick Labels
        ctx.fillStyle = 'rgba(148, 163, 184, 0.55)';
        ctx.font = '7px var(--font-mono)';
        ctx.fillText('(0,0)', 3, canvas.height - 5);
        ctx.fillText('X Axis (px)', canvas.width - 55, canvas.height - 5);
        ctx.fillText('Y Axis (px)', 3, 10);

        // Security Telemetry HUD Labels
        ctx.fillStyle = 'rgba(14, 165, 233, 0.65)';
        ctx.font = '8px var(--font-mono)';
        ctx.fillText('COORDINATE SYSTEM: TELEMETRY CANVAS', 22, 14);
        ctx.fillText('TRACKING RESOLUTION: DYNAMIC PLOT', 22, 24);

        const samples = breakdownObj ? breakdownObj.mouse_samples : null;
        if (!samples || samples.length === 0) {
            ctx.fillStyle = 'rgba(255, 255, 255, 0.25)';
            ctx.font = '11px var(--font-sans)';
            ctx.fillText("No mouse coordinates recorded in this cycle.", 20, 75);
            return;
        }

        // Project coordinate boundaries to fit canvas size
        const padding = 20;
        const xs = samples.map(s => s.x);
        const ys = samples.map(s => s.y);
        const minX = Math.min(...xs), maxX = Math.max(...xs);
        const minY = Math.min(...ys), maxY = Math.max(...ys);

        const rangeX = (maxX - minX) || 1;
        const rangeY = (maxY - minY) || 1;

        // Draw coordinates line trail
        ctx.beginPath();
        samples.forEach((s, idx) => {
            const canvasX = padding + ((s.x - minX) / rangeX) * (canvas.width - 2 * padding);
            const canvasY = padding + ((s.y - minY) / rangeY) * (canvas.height - 2 * padding);
            
            if (idx === 0) ctx.moveTo(canvasX, canvasY);
            else ctx.lineTo(canvasX, canvasY);
        });

        // Set path color based on straightness/bot markers
        let pathColor = '#10b981'; // Green (human)
        const isBot = breakdownObj.is_bot || (samples.length > 5 && (maxX - minX < 2 || maxY - minY < 2)); // straight line
        if (isBot) pathColor = '#f43f5e'; // Rose (bot)
        
        ctx.strokeStyle = pathColor;
        ctx.lineWidth = 2.5;
        // Neon Glow effect
        ctx.shadowBlur = 8;
        ctx.shadowColor = pathColor;
        ctx.stroke();
        
        // Reset shadow for other drawings
        ctx.shadowBlur = 0;

        // Draw start/end target elements
        if (samples.length > 0) {
            // Start node
            const startX = padding + ((samples[0].x - minX) / rangeX) * (canvas.width - 2 * padding);
            const startY = padding + ((samples[0].y - minY) / rangeY) * (canvas.height - 2 * padding);
            ctx.fillStyle = '#3b82f6';
            ctx.beginPath(); ctx.arc(startX, startY, 4, 0, 2 * Math.PI); ctx.fill();
            // Start Ring
            ctx.strokeStyle = 'rgba(59, 130, 246, 0.5)';
            ctx.beginPath(); ctx.arc(startX, startY, 8, 0, 2 * Math.PI); ctx.stroke();

            // End node
            const endX = padding + ((samples[samples.length-1].x - minX) / rangeX) * (canvas.width - 2 * padding);
            const endY = padding + ((samples[samples.length-1].y - minY) / rangeY) * (canvas.height - 2 * padding);
            ctx.fillStyle = '#f59e0b';
            ctx.beginPath(); ctx.arc(endX, endY, 4, 0, 2 * Math.PI); ctx.fill();
            // End Ring
            ctx.strokeStyle = 'rgba(245, 158, 11, 0.5)';
            ctx.beginPath(); ctx.arc(endX, endY, 8, 0, 2 * Math.PI); ctx.stroke();
        }
    }

    async function fetchAndRenderSessionHeartbeatLogs(sid) {
        try {
            const r = await fetch(`/api/dashboard/session/${sid}/logs`);
            const sessionLogs = await r.json();

            elements.ddSessionLogs.innerHTML = '';
            if (sessionLogs.length === 0) {
                elements.ddSessionLogs.innerHTML = '<p class="text-center text-muted text-xs p-4">No events logged yet.</p>';
                return;
            }

            sessionLogs.forEach(l => {
                const item = createLogItemMarkup(l);
                elements.ddSessionLogs.appendChild(item);
            });

            // Scroll to the bottom to make the latest log visible after browser layout pass
            setTimeout(() => {
                elements.ddSessionLogs.scrollTop = elements.ddSessionLogs.scrollHeight;
            }, 60);
        } catch (e) {
            console.error("Error loading session audit logs:", e);
        }
    }

    // ==========================================
    // SECURITY EVENT FEED
    // ==========================================
    function renderGlobalLogs(logs) {
        elements.globalLogFeed.innerHTML = '';
        if (logs.length === 0) {
            elements.globalLogFeed.innerHTML = '<p class="text-center text-muted p-4">Awaiting security events from Bharat Suraksha Bank...</p>';
            return;
        }

        logs.forEach(l => {
            const item = createLogItemMarkup(l);
            elements.globalLogFeed.appendChild(item);
        });
    }

    function appendGlobalLog(l) {
        // Remove empty state
        if (elements.globalLogFeed.innerHTML.includes('Awaiting security events')) {
            elements.globalLogFeed.innerHTML = '';
        }

        const item = createLogItemMarkup(l);
        elements.globalLogFeed.insertBefore(item, elements.globalLogFeed.firstChild);

        // Keep global log feed under 100 items
        if (elements.globalLogFeed.children.length > 100) {
            elements.globalLogFeed.removeChild(elements.globalLogFeed.lastChild);
        }
    }

    function createLogItemMarkup(l) {
        const item = document.createElement('div');
        item.className = `log-item event-${l.event_type}`;

        const timeString = new Date(l.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

        let detailString = '';
        if (l.event_type === 'SCORE_UPDATE') {
            const kScore = fmtScore(l.details.keystroke_score, l.details.session_count);
            const mScore = fmtScore(l.details.mouse_score, l.details.session_count);
            detailString = `Score: ${l.risk_score.toFixed(1)} [K:${kScore} M:${mScore}]`;
        } else if (l.event_type === 'BOT_DETECTED') {
            detailString = `Blocked: ${l.details.reason || 'Bot Heuristics Triggered'}`;
        } else if (l.details.message) {
            detailString = l.details.message;
        }

        item.innerHTML = `
            <span class="log-time">${timeString}</span>
            <div class="log-content">
                <div class="log-type">${l.event_type}</div>
                <div class="log-user">User: <strong>${l.username}</strong></div>
                <div class="log-detail">${detailString}</div>
            </div>
        `;
        return item;
    }

    // ==========================================
    // OVERRIDE CONTROLS (HTTP POSTS)
    // ==========================================
    elements.btnFreeze.addEventListener('click', async function() {
        if (!selectedSessionId) return;
        
        const btnText = elements.btnFreeze.textContent.trim();
        const isUnfreezeAction = btnText.includes("Unfreeze");
        
        if (isUnfreezeAction) {
            if (!confirm("Are you sure you want to UNFREEZE this session and restore access?")) return;
            try {
                const response = await fetch(`/api/admin/false-positive/${selectedSessionId}`, { method: 'POST' });
                if (response.ok) {
                    alert("Session unfrozen and access restored.");
                    fetchSessions();
                    setTimeout(() => { selectSession(selectedSessionId); }, 300);
                } else { alert("Failed to unfreeze session."); }
            } catch (err) { console.error("Error unfreezing session:", err); }
        } else {
            if (!confirm("Are you sure you want to FORCE FREEZE this session? This blocks the client UI immediately.")) return;
            try {
                const response = await fetch(`/api/admin/freeze/${selectedSessionId}`, { method: 'POST' });
                if (response.ok) {
                    alert("Session frozen successfully.");
                    fetchSessions();
                    setTimeout(() => { selectSession(selectedSessionId); }, 300);
                } else { alert("Failed to freeze session."); }
            } catch (err) { console.error("Error freezing session:", err); }
        }
    });

    elements.btnUnfreeze.addEventListener('click', async function() {
        if (!selectedSessionId) return;
        if (!confirm("Are you sure you want to mark this as a FALSE POSITIVE and restore session access?")) return;

        try {
            const response = await fetch(`/api/admin/false-positive/${selectedSessionId}`, { method: 'POST' });
            if (response.ok) {
                alert("Session unfreezed and risk reset.");
                fetchSessions();
                setTimeout(() => { selectSession(selectedSessionId); }, 300);
            } else { alert("Failed to restore session."); }
        } catch (err) { console.error("Error unfreezing session:", err); }
    });

    elements.btnSoftReset.addEventListener('click', async function() {
        if (!confirm("Clear active sessions but retain user enrollment databases?")) return;
        try {
            const response = await fetch('/api/admin/soft-reset', { method: 'POST' });
            if (response.ok) alert("Active sessions cleared.");
        } catch (err) { console.error(err); }
    });

    elements.btnHardReset.addEventListener('click', async function() {
        if (!confirm("WARNING: This resets the complete in-memory database, clearing all user enrollments and session logs. Continue?")) return;
        try {
            const response = await fetch('/api/admin/reset', { method: 'POST' });
            if (response.ok) alert("Complete database reset completed.");
        } catch (err) { console.error(err); }
    });

    // ==========================================
    // SIDEBAR NAVIGATION TAB SWITCHES
    // ==========================================
    window.switchTab = function(tabName) {
        activeTab = tabName;
        
        // Remove active class from all nav items
        document.getElementById('nav-item-monitor').classList.remove('active');
        document.getElementById('nav-item-threats').classList.remove('active');
        const navItemData = document.getElementById('nav-item-datacollection');
        if (navItemData) navItemData.classList.remove('active');
        const navItemFrozen = document.getElementById('nav-item-frozen');
        if (navItemFrozen) navItemFrozen.classList.remove('active');
        const navItemSearch = document.getElementById('nav-item-search');
        if (navItemSearch) navItemSearch.classList.remove('active');
        
        // Add hidden class to all tabs
        document.getElementById('tab-monitor').classList.add('hidden');
        document.getElementById('tab-threats').classList.add('hidden');
        const tabData = document.getElementById('tab-datacollection');
        if (tabData) tabData.classList.add('hidden');
        const tabFrozen = document.getElementById('tab-frozen');
        if (tabFrozen) tabFrozen.classList.add('hidden');
        const tabSearch = document.getElementById('tab-search');
        if (tabSearch) tabSearch.classList.add('hidden');

        // Show selected tab and active nav item
        const activeNav = document.getElementById(`nav-item-${tabName}`);
        const activeTabEl = document.getElementById(`tab-${tabName}`);
        if (activeNav) activeNav.classList.add('active');
        if (activeTabEl) activeTabEl.classList.remove('hidden');

        // Load summaries or triggers based on tab opened
        if (tabName === 'datacollection') {
            fetchDataCollectionSummary();
        } else if (tabName === 'frozen') {
            fetchFrozenSessions();
        }
    };


    // ==========================================
    // STREAM 6A — INTRUDER SESSION LABELING
    // ==========================================

    /**
     * Render the "Data Collection" panel inside the session deep-dive drawer.
     * Called by renderDeepDive() / selectSession() after showing session details.
     */
    function renderIntruderLabelPanel(sessionId) {
        const existingPanel = document.getElementById('intruder-label-panel');
        if (existingPanel) existingPanel.remove();

        const panel = document.createElement('div');
        panel.id = 'intruder-label-panel';
        panel.style.cssText = `
            margin-top: 20px;
            padding: 16px;
            background: rgba(251,191,36,0.08);
            border: 1px solid rgba(251,191,36,0.3);
            border-radius: 10px;
        `;
        panel.innerHTML = `
            <div style="font-size:12px;font-weight:600;color:#fbbf24;margin-bottom:10px;letter-spacing:0.05em;">
                🔬 DATA COLLECTION — INTRUDER LABELING
            </div>
            <p style="font-size:11px;color:#94a3b8;margin-bottom:12px;line-height:1.5;">
                Use after a friend/family member has completed their test sessions on this account.
                Labeling marks sessions as intruder for XGBoost retraining.
            </p>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
                <button id="btn-label-this-session"
                    onclick="labelIntruderSession('${sessionId}', false)"
                    style="padding:8px 14px;background:rgba(251,191,36,0.15);border:1px solid #fbbf24;
                           color:#fbbf24;border-radius:6px;font-size:11px;cursor:pointer;font-weight:600;">
                    Mark This Session as Intruder
                </button>
                <button id="btn-label-all-recent"
                    onclick="labelIntruderSession('${sessionId}', true)"
                    style="padding:8px 14px;background:rgba(239,68,68,0.15);border:1px solid #ef4444;
                           color:#ef4444;border-radius:6px;font-size:11px;cursor:pointer;font-weight:600;">
                    Mark All Recent Sessions (30 min) as Intruder
                </button>
            </div>
            <div id="intruder-label-result" style="margin-top:10px;font-size:11px;color:#22c55e;display:none;"></div>
        `;

        // Append to the deep-dive workspace
        const workspace = document.getElementById('deep-dive-workspace');
        if (workspace) workspace.appendChild(panel);
    }

    window.labelIntruderSession = async function(sessionId, labelAllRecent) {
        const confirmMsg = labelAllRecent
            ? `Mark ALL sessions for this user in the last 30 minutes as INTRUDER?\n\nThis cannot be undone and will affect XGBoost training data.`
            : `Mark session ${sessionId.substring(0,8)}... as INTRUDER?\n\nThis cannot be undone.`;

        if (!confirm(confirmMsg)) return;

        try {
            const res = await fetch('/api/admin/label-intruder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, label_all_recent: labelAllRecent })
            });
            const data = await res.json();

            const resultEl = document.getElementById('intruder-label-result');
            if (res.ok && resultEl) {
                const count = data.sessions_labeled || 1;
                resultEl.style.display = 'block';
                resultEl.style.color = '#22c55e';
                resultEl.textContent = `✓ ${count} session(s) labeled as intruder. Data collection updated.`;
            } else if (resultEl) {
                resultEl.style.display = 'block';
                resultEl.style.color = '#ef4444';
                resultEl.textContent = `Error: ${data.detail || 'Unknown error'}`;
            }
        } catch (err) {
            console.error('Error labeling intruder session:', err);
            showToast('Failed to label session — check connection', 'error');
        }
    };

    // No window hook needed as renderIntruderLabelPanel is called directly in local selectSession


    // ==========================================
    // STREAM 6B — DATA COLLECTION SUMMARY PANEL
    // ==========================================

    async function fetchDataCollectionSummary() {
        const container = document.getElementById('data-collection-panel-content');
        if (!container) return;
        
        // Show loading indicator only if container is empty
        if (!container.innerHTML || container.innerHTML.trim() === '' || container.innerHTML.includes('No users yet')) {
            container.innerHTML = '<p style="color:#94a3b8;font-size:12px;">Loading...</p>';
        }

        const btn = document.getElementById('btn-refresh-data-collection');
        let origHtml = '↻ Refresh';
        if (btn) {
            btn.disabled = true;
            origHtml = btn.innerHTML;
            btn.innerHTML = '⏳ Refreshing...';
        }

        try {
            const res = await fetch('/api/admin/data-collection-summary');
            const data = await res.json();
            
            // Add a small 200ms delay to make the refresh action feel solid/perceptible
            await new Promise(resolve => setTimeout(resolve, 200));
            
            renderDataCollectionSummary(data, container);
        } catch (err) {
            if (container.innerHTML.includes('Loading...')) {
                container.innerHTML = '<p style="color:#ef4444;font-size:12px;">Failed to load summary</p>';
            } else {
                showToast("Failed to refresh data collection summary", "error");
            }
        } finally {
            const newBtn = document.getElementById('btn-refresh-data-collection');
            if (newBtn) {
                newBtn.disabled = false;
                newBtn.innerHTML = origHtml;
            }
        }
    }

    async function triggerXGBoostRetraining(force = false) {
        const btn = document.getElementById('btn-trigger-retrain');
        const forceBtn = document.getElementById('btn-force-retrain');
        
        const origText = btn ? btn.innerHTML : '';
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="ti ti-loader" style="display:inline-block;animation: spin 1s linear infinite;margin-right:4px;"></i> Retraining...';
        }
        if (forceBtn) forceBtn.disabled = true;
        
        try {
            const response = await fetch(`/api/admin/retrain?force=${force}`, {
                method: 'POST'
            });
            const data = await response.json();
            
            if (response.ok && data.success) {
                const r = data.report;
                showToast(`Retraining successful! Accuracy: ${(r.accuracy*100).toFixed(1)}%`, 'success');
                alert(`XGBoost Retraining Complete!\n\nMetrics:\n- Accuracy: ${(r.accuracy*100).toFixed(1)}%\n- Recall: ${(r.recall*100).toFixed(1)}%\n- Precision: ${(r.precision*100).toFixed(1)}%\n- F1 Score: ${(r.f1*100).toFixed(1)}%\n- Real session samples: ${r.real_samples}\n- Labeled intruders: ${r.intruder_sessions}\n\nNewly retrained model reloaded and active on server!`);
                fetchDataCollectionSummary();
                // Also refresh main screen stats to update charts / weights
                fetchStats();
                fetchSessions();
            } else {
                showToast(data.detail || "Retraining failed", 'error');
                alert(`Retraining Failed:\n\n${data.detail || "Unknown error"}`);
            }
        } catch (e) {
            showToast("Error contacting retraining API", 'error');
            alert("Error contacting retraining API.");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = origText;
            }
            if (forceBtn) forceBtn.disabled = false;
        }
    }

    window.fetchDataCollectionSummary = fetchDataCollectionSummary;
    window.triggerXGBoostRetraining = triggerXGBoostRetraining;

    function renderDataCollectionSummary(data, container) {
        const totals = data.totals || {};
        const users  = data.users  || [];

        const readyColor = totals.ready_for_retraining ? '#22c55e' : '#f59e0b';
        const readyText  = totals.ready_for_retraining
            ? '✓ Ready for XGBoost retraining!'
            : `Need ${Math.max(0, 20 - (totals.total_intruders || 0))} more intruder sessions`;

        let rows = users.map(u => `
            <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                <td style="padding:8px 12px;color:#e2e8f0;">${u.username}</td>
                <td style="padding:8px 12px;">
                    <span style="background:rgba(99,102,241,0.2);color:#a5b4fc;padding:2px 8px;border-radius:4px;font-size:10px;">
                        ${u.device_class}
                    </span>
                </td>
                <td style="padding:8px 12px;color:#94a3b8;">
                    <span style="color:${(u.session_count||0) >= 10 ? '#22c55e' : '#f59e0b'}">
                        ${u.session_count || 0}
                    </span> / 15
                </td>
                <td style="padding:8px 12px;">
                    ${u.enrolled
                        ? '<span style="color:#22c55e;"><i class="ti ti-circle-check-filled" style="vertical-align:middle;margin-right:2px;"></i>Enrolled</span>'
                        : '<span style="color:#f59e0b;"><i class="ti ti-loader" style="vertical-align:middle;margin-right:2px;"></i>Pending</span>'}
                </td>
                <td style="padding:8px 12px;color:${(u.intruder_count||0)>0 ? '#ef4444' : '#94a3b8'};">
                    ${u.intruder_count || 0}
                </td>
            </tr>
        `).join('');

        container.innerHTML = `
            <!-- Totals row -->
            <div style="display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap;">
                <div style="flex:1;min-width:100px;background:rgba(99,102,241,0.1);border:1px solid rgba(99,102,241,0.2);border-radius:8px;padding:12px;text-align:center;">
                    <div style="font-size:22px;font-weight:700;color:#a5b4fc;">${totals.total_users || 0}</div>
                    <div style="font-size:10px;color:#94a3b8;margin-top:4px;">Total Users</div>
                </div>
                <div style="flex:1;min-width:100px;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.2);border-radius:8px;padding:12px;text-align:center;">
                    <div style="font-size:22px;font-weight:700;color:#22c55e;">${totals.total_sessions || 0}</div>
                    <div style="font-size:10px;color:#94a3b8;margin-top:4px;">Total Sessions</div>
                </div>
                <div style="flex:1;min-width:100px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.2);border-radius:8px;padding:12px;text-align:center;">
                    <div style="font-size:22px;font-weight:700;color:#ef4444;">${totals.total_intruders || 0}</div>
                    <div style="font-size:10px;color:#94a3b8;margin-top:4px;">Intruder Sessions</div>
                </div>
            </div>

            <!-- Retraining readiness & action buttons -->
            <div style="margin-bottom:16px;padding:12px 14px;border-radius:8px;
                        background:rgba(${totals.ready_for_retraining ? '34,197,94' : '245,158,11'},0.08);
                        border:1px solid rgba(${totals.ready_for_retraining ? '34,197,94' : '245,158,11'},0.25);
                        font-size:12px;color:${readyColor};">
                <div style="font-weight:600;margin-bottom:4px;">${readyText}</div>
                <span style="color:#94a3b8;font-size:10px;">
                    Retraining integrates user telemetry patterns from the SQLite database to update decision boundaries.
                </span>
                <div style="margin-top:12px;display:flex;gap:10px;">
                    <button id="btn-trigger-retrain" onclick="triggerXGBoostRetraining()" 
                            style="padding:8px 16px;background:var(--cyan);border:none;color:#000;
                                   font-weight:700;border-radius:6px;font-size:11px;cursor:pointer;
                                   display:inline-flex;align-items:center;gap:6px;transition:opacity 0.2s;">
                        <i class="ti ti-bolt"></i> Retrain XGBoost Classifier
                    </button>
                    ${totals.ready_for_retraining ? '' : `
                    <button id="btn-force-retrain" onclick="triggerXGBoostRetraining(true)" 
                            style="padding:8px 16px;background:rgba(245,158,11,0.15);border:1px solid rgba(245,158,11,0.3);
                                   color:#fbbf24;font-weight:600;border-radius:6px;font-size:11px;cursor:pointer;transition:background 0.2s;">
                        ⚡ Force Retrain (Demo Mode)
                    </button>
                    `}
                </div>
            </div>

            <!-- User table -->
            <table style="width:100%;border-collapse:collapse;font-size:11px;">
                <thead>
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.1);">
                        <th style="padding:6px 12px;color:#64748b;font-weight:600;text-align:left;">User</th>
                        <th style="padding:6px 12px;color:#64748b;font-weight:600;text-align:left;">Device</th>
                        <th style="padding:6px 12px;color:#64748b;font-weight:600;text-align:left;">Sessions</th>
                        <th style="padding:6px 12px;color:#64748b;font-weight:600;text-align:left;">Status</th>
                        <th style="padding:6px 12px;color:#64748b;font-weight:600;text-align:left;">Intruders</th>
                    </tr>
                </thead>
                <tbody>${rows || '<tr><td colspan="5" style="padding:16px;text-align:center;color:#475569;">No users yet</td></tr>'}</tbody>
            </table>
            <button id="btn-refresh-data-collection" onclick="fetchDataCollectionSummary()"
                style="margin-top:12px;padding:6px 14px;background:rgba(99,102,241,0.15);border:1px solid rgba(99,102,241,0.3);
                       color:#a5b4fc;border-radius:6px;font-size:11px;cursor:pointer;">
                ↻ Refresh
            </button>
        `;
    }

    // Auto-refresh data collection summary every 60 seconds if visible
    setInterval(() => {
        if (activeTab === 'datacollection') fetchDataCollectionSummary();
    }, 60000);


    // ==========================================
    // BONUS B2 — ADVISORY MODE TOGGLE
    // ==========================================

    let currentMode = 'active';

    async function fetchCurrentMode() {
        try {
            const res = await fetch('/api/admin/mode');
            const data = await res.json();
            currentMode = data.mode || 'active';
            updateModeToggleUI(currentMode);
        } catch (e) { /* non-critical */ }
    }

    function updateModeToggleUI(mode) {
        const btn = document.getElementById('btn-mode-toggle');
        const badge = document.getElementById('overview-mode-badge') || document.getElementById('mode-badge');
        if (!btn) return;

        if (mode === 'advisory') {
            btn.innerHTML = '<i class="ti ti-eye" style="margin-right: 6px;"></i> Advisory Mode — Click to Activate';
            btn.style.background = 'rgba(99,102,241,0.2)';
            btn.style.borderColor = '#6366f1';
            btn.style.color = '#a5b4fc';
            if (badge) { 
                badge.innerHTML = '<i class="ti ti-eye"></i> ADVISORY MODE'; 
                badge.className = 'badge badge-blue flex items-center gap-1';
                badge.style.color = '#a5b4fc'; 
                badge.style.borderColor = 'rgba(99, 102, 241, 0.3)';
                badge.style.background = 'rgba(99, 102, 241, 0.1)';
            }
        } else {
            btn.innerHTML = '<i class="ti ti-alert-triangle" style="margin-right: 6px;"></i> Active Mode — Click for Advisory';
            btn.style.background = 'rgba(239,68,68,0.15)';
            btn.style.borderColor = '#ef4444';
            btn.style.color = '#ef4444';
            if (badge) { 
                badge.innerHTML = '<i class="ti ti-shield-check"></i> ACTIVE MODE'; 
                badge.className = 'badge badge-red flex items-center gap-1';
                badge.style.color = '#ef4444'; 
                badge.style.borderColor = 'rgba(239, 68, 68, 0.3)';
                badge.style.background = 'rgba(239, 68, 68, 0.1)';
            }
        }
    }

    window.toggleAdvisoryMode = async function() {
        const newMode = currentMode === 'active' ? 'advisory' : 'active';
        const confirmMsg = newMode === 'advisory'
            ? 'Switch to ADVISORY MODE?\n\nThe system will continue scoring but will NOT challenge or freeze users. Risk scores remain visible on this dashboard.'
            : 'Switch to ACTIVE MODE?\n\nThe system will resume applying friction (challenges, freezes) to high-risk sessions.';

        if (!confirm(confirmMsg)) return;

        try {
            const res = await fetch('/api/admin/set-mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode: newMode })
            });
            if (res.ok) {
                currentMode = newMode;
                updateModeToggleUI(newMode);
                showToast(`System switched to ${newMode.toUpperCase()} mode`, newMode === 'advisory' ? 'info' : 'warning');
            }
        } catch (err) {
            console.error('Error toggling mode:', err);
        }
    };

    // Load current mode on startup
    fetchCurrentMode();

    // Handle mode_changed events from WebSocket
    function handleModeChanged(data) {
        currentMode = data.mode || 'active';
        updateModeToggleUI(currentMode);
    }

    // ==========================================
    // TOAST NOTIFICATION HELPER
    // ==========================================
    function showToast(message, type = 'info') {
        const existing = document.getElementById('dashboard-toast');
        if (existing) existing.remove();

        const colors = {
            info:    { bg: 'rgba(99,102,241,0.9)',  border: '#6366f1' },
            success: { bg: 'rgba(34,197,94,0.9)',   border: '#22c55e' },
            warning: { bg: 'rgba(245,158,11,0.9)',  border: '#f59e0b' },
            error:   { bg: 'rgba(239,68,68,0.9)',   border: '#ef4444' },
        };
        const c = colors[type] || colors.info;

        const toast = document.createElement('div');
        toast.id = 'dashboard-toast';
        toast.style.cssText = `
            position:fixed;bottom:24px;right:24px;z-index:9999;
            background:${c.bg};border:1px solid ${c.border};
            color:#fff;padding:12px 20px;border-radius:10px;
            font-size:13px;font-weight:500;
            box-shadow:0 4px 20px rgba(0,0,0,0.4);
            animation:fadeIn 0.3s ease;
        `;
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3500);
    }
    window.showToast = showToast;

    // ==========================================
    // OPERATIONS OVERVIEW AND FEATURE IMPORTANCE CHARTS (Chart.js)
    // ==========================================
    function initOverviewCharts() {
        // Line chart for Triage Risk Score Trends
        const trendCtx = document.getElementById('overview-trend-chart');
        if (trendCtx) {
            const ctx = trendCtx.getContext('2d');
            const grad = ctx.createLinearGradient(0, 0, 0, 200);
            grad.addColorStop(0, 'rgba(59, 130, 246, 0.4)');
            grad.addColorStop(1, 'rgba(59, 130, 246, 0.0)');
            
            overviewTrendChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: ['10 mins ago', '8 mins ago', '6 mins ago', '4 mins ago', '2 mins ago', 'Just Now'],
                    datasets: [{
                        label: 'Risk Score',
                        data: [12, 18, 15, 29, 22, 25],
                        borderColor: '#3b82f6',
                        backgroundColor: grad,
                        fill: true,
                        tension: 0.4,
                        borderWidth: 2,
                        pointRadius: 3,
                        pointBackgroundColor: '#3b82f6'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        x: { ticks: { color: '#94a3b8', font: { size: 9 } }, grid: { color: 'rgba(255,255,255,0.03)' } },
                        y: { min: 0, max: 100, ticks: { color: '#94a3b8', font: { size: 9 } }, grid: { color: 'rgba(255,255,255,0.03)' } }
                    }
                }
            });
        }

        // Donut chart for Alert Triage Resolutions
        const donutCtx = document.getElementById('overview-donut-chart');
        if (donutCtx) {
            overviewDonutChart = new Chart(donutCtx.getContext('2d'), {
                type: 'doughnut',
                data: {
                    labels: ['Confirmed Fraud', 'False Positives', 'Pending Triage'],
                    datasets: [{
                        data: [0, 0, 1],
                        backgroundColor: ['#ef4444', '#10b981', '#f59e0b'],
                        borderWidth: 2,
                        borderColor: '#1e293b'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: '#e2e8f0', boxWidth: 10, font: { size: 9, weight: 600 } }
                        }
                    },
                    cutout: '65%'
                }
            });
        }

        // Radar chart for Detection Layer Contributions
        const radarCtx = document.getElementById('overview-radar-chart');
        if (radarCtx) {
            overviewRadarChart = new Chart(radarCtx.getContext('2d'), {
                type: 'radar',
                data: {
                    labels: [
                        'Keystroke Dynamics',
                        'Mouse Trajectory',
                        'Client Network',
                        'Device Fingerprint',
                        'Temporal Context',
                        'Bot Heuristics'
                    ],
                    datasets: [{
                        label: 'Relative Telemetry Contributions',
                        data: [10, 10, 10, 10, 10, 10],
                        backgroundColor: 'rgba(14, 165, 233, 0.25)',
                        borderColor: '#0ea5e9',
                        pointBackgroundColor: '#0ea5e9',
                        borderWidth: 1.5,
                        pointRadius: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    layout: {
                        padding: {
                            left: 45,
                            right: 45,
                            top: 15,
                            bottom: 15
                        }
                    },
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        r: {
                            angleLines: { color: 'rgba(255,255,255,0.05)' },
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            pointLabels: { color: '#94a3b8', font: { size: 8, family: 'Outfit' } },
                            ticks: { display: false },
                            min: 0,
                            max: 100
                        }
                    }
                }
            });
        }
    }

    function updateOverviewCharts(sessions) {
        if (!overviewDonutChart && !overviewTrendChart && !overviewRadarChart) {
            initOverviewCharts();
        }

        const modeBadge = document.getElementById('overview-mode-badge');
        if (modeBadge) {
            modeBadge.textContent = currentMode.toUpperCase() + ' MODE';
            if (currentMode === 'advisory') {
                modeBadge.innerHTML = '<i class="ti ti-eye"></i> ADVISORY MODE';
                modeBadge.className = 'badge badge-blue flex items-center gap-1';
                modeBadge.style.color = '#a5b4fc';
                modeBadge.style.borderColor = 'rgba(99, 102, 241, 0.3)';
                modeBadge.style.background = 'rgba(99, 102, 241, 0.1)';
            } else {
                modeBadge.innerHTML = '<i class="ti ti-shield-check"></i> ACTIVE MODE';
                modeBadge.className = 'badge badge-red flex items-center gap-1';
                modeBadge.style.color = '#ef4444';
                modeBadge.style.borderColor = 'rgba(239, 68, 68, 0.3)';
                modeBadge.style.background = 'rgba(239, 68, 68, 0.1)';
            }
        }

        if (!sessions || sessions.length === 0) {
            if (overviewRadarChart) {
                overviewRadarChart.data.datasets[0].data = [10, 10, 10, 10, 10, 10];
                overviewRadarChart.update();
            }
            return;
        }

        // Trend Risk Score Mean is now updated via the stats system time-series API

        // Radar Detection Layer contributions mapping
        let keystrokeTotal = 0;
        let mouseTotal = 0;
        let networkTotal = 0;
        let deviceTotal = 0;
        let temporalTotal = 0;
        let botTotal = 0;

        sessions.forEach(s => {
            const breakdown = s.last_breakdown || {};
            const contributors = breakdown.all_contributors || [];

            // 1. Keystroke
            const keystroke = contributors.find(c => c.feature.includes('hold') || c.feature.includes('flight')) || { contribution: s.risk_score * 0.4 };
            keystrokeTotal += keystroke.contribution || (s.risk_score * 0.4);

            // 2. Mouse
            const mouse = contributors.find(c => c.feature.includes('mouse') || c.feature.includes('trajectory')) || { contribution: s.risk_score * 0.4 };
            mouseTotal += mouse.contribution || (s.risk_score * 0.4);

            // 3. Network
            const network = contributors.find(c => c.feature.includes('ip') || c.feature.includes('network') || c.feature.includes('location')) || { contribution: s.risk_score * 0.05 };
            networkTotal += network.contribution || (s.risk_score * 0.05);

            // 4. Device
            const device = contributors.find(c => c.feature === 'device_match') || { contribution: s.device_match === false ? 60 : 10 };
            deviceTotal += device.contribution || (s.device_match === false ? 60 : 10);

            // 5. Temporal
            const temporal = contributors.find(c => c.feature === 'time_of_day_risk') || { contribution: s.time_of_day_risk ? s.time_of_day_risk * 100 : 10 };
            temporalTotal += temporal.contribution || (s.time_of_day_risk ? s.time_of_day_risk * 100 : 10);

            // 6. Bot
            const bot = contributors.find(c => c.feature === 'bot_detection') || { contribution: s.is_bot ? 95 : 5 };
            botTotal += bot.contribution || (s.is_bot ? 95 : 5);
        });

        const N = sessions.length;
        if (overviewRadarChart) {
            overviewRadarChart.data.datasets[0].data = [
                keystrokeTotal / N,
                mouseTotal / N,
                networkTotal / N,
                deviceTotal / N,
                temporalTotal / N,
                botTotal / N
            ];
            overviewRadarChart.update();
        }
    }

    async function renderFeatureImportanceChart() {
        try {
            const r = await fetch('/api/admin/model-metadata');
            const data = await r.json();
            
            let importances = {
                "keystroke_score": 0.454,
                "metadata_score":  0.250,
                "mouse_score":     0.209,
                "is_enrolled":     0.088
            };
            
            if (data && data.fusion_model && data.fusion_model.feature_importances) {
                importances = data.fusion_model.feature_importances;
            }
            
            const rawKeys = Object.keys(importances);
            const rawValues = Object.values(importances);

            // Sort importances descending
            const pairs = rawKeys.map((k, i) => [k, rawValues[i]]);
            pairs.sort((a, b) => b[1] - a[1]);

            const labels = pairs.map(p => {
                const k = p[0];
                if (k === 'keystroke_score') return 'Keystroke LSTM';
                if (k === 'metadata_score')  return 'Contextual Rules';
                if (k === 'mouse_score')     return 'Mouse LSTM';
                if (k === 'is_enrolled')     return 'Enrollment Status';
                if (k === 'time_of_day_risk') return 'Time of Day';
                if (k === 'device_match')    return 'Device Match';
                return k;
            });
            const values = pairs.map(p => p[1] * 100);

            if (featureImportanceChart) {
                featureImportanceChart.destroy();
            }

            const fiCtx = document.getElementById('feature-importance-chart');
            if (!fiCtx) return;

            const ctx = fiCtx.getContext('2d');
            featureImportanceChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'XGBoost Importance (%)',
                        data: values,
                        backgroundColor: 'rgba(99, 102, 241, 0.75)',
                        borderColor: '#6366f1',
                        borderWidth: 1.5,
                        borderRadius: 4
                    }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        x: { ticks: { color: '#94a3b8', font: { size: 8 } }, grid: { color: 'rgba(255,255,255,0.03)' } },
                        y: { ticks: { color: '#e2e8f0', font: { size: 8, weight: 600 } }, grid: { display: false } }
                    }
                }
            });
        } catch (e) {
            console.error("Error rendering feature importance chart:", e);
        }
    }

    // Extend WS message handler to process mode_changed events
    const _origHandleWS = window._handleWSMessage;
    window._handleWSMessage = function(data) {
        if (_origHandleWS) _origHandleWS(data);
        if (data.type === 'mode_changed') handleModeChanged(data);
    };

    // ==========================================
    // TAB CONTROLLERS: FROZEN & HISTORIC SEARCH
    // ==========================================

    function fetchFrozenSessions() {
        const container = document.getElementById('frozen-sessions-container');
        if (!container) return;
        container.innerHTML = '<p class="text-center text-muted p-4 col-12">Loading frozen sessions...</p>';
        
        fetch('/api/dashboard/sessions/frozen')
            .then(r => r.json())
            .then(sessions => {
                container.innerHTML = '';
                if (sessions.length === 0) {
                    container.innerHTML = `
                        <div class="col-12 text-center text-muted p-6" style="background: rgba(255,255,255,0.01); border: 1px dashed var(--border); border-radius: var(--radius-lg); width: 100%;">
                            <i class="ti ti-circle-check-filled" style="color: var(--green); font-size: 1.5rem; display: block; margin-bottom: 0.5rem;"></i>
                            No frozen or suspended sessions currently active in the environment.
                        </div>
                    `;
                    return;
                }
                
                sessions.forEach(s => {
                    const card = document.createElement('div');
                    card.className = 'alert-card border-red';
                    card.style.borderLeft = '4px solid var(--red)';
                    card.style.background = 'rgba(239, 68, 68, 0.03)';
                    
                    const dateObj = new Date(s.created_at * 1000);
                    const formattedTime = `${dateObj.toLocaleDateString()} @ ${dateObj.toLocaleTimeString()}`;
                    
                    card.innerHTML = `
                        <div class="alert-card-header" style="display:flex; justify-content:space-between; align-items:start;">
                            <div>
                                <h4 style="margin: 0; color: #fff; font-size: 0.95rem;">${s.username}</h4>
                                <span class="text-mono text-xs text-muted" style="font-size:10px;">${s.session_id.substring(0, 12)}...</span>
                                <span class="text-xs text-muted" style="display: block; margin-top: 3px; font-size: 10px;">🕒 ${formattedTime}</span>
                            </div>
                            <span class="badge badge-red text-xs">FROZEN</span>
                        </div>
                        <div class="alert-card-body" style="display:flex; justify-content:space-between; margin-top: 10px; border-top: 1px dashed var(--border); padding-top: 8px;">
                            <div>
                                <span class="text-xs text-muted" style="display: block; margin-bottom: 2px;">IP Address</span>
                                <span class="text-xs text-mono" style="color: #fff;">${s.ip_address || '127.0.0.1'}</span>
                            </div>
                            <div class="alert-card-score-wrapper" style="text-align:right;">
                                <span class="text-xs text-muted" style="display: block; margin-bottom: 2px;">Risk Index</span>
                                <span class="alert-card-score red" style="font-weight: 800; font-family: var(--font-mono); font-size: 1.25rem;">${s.risk_score.toFixed(1)}</span>
                            </div>
                        </div>
                        <div class="alert-card-footer" style="display:flex; justify-content:space-between; align-items:center; border-top:1px dashed var(--border); padding-top:8px; margin-top:8px;">
                            <span class="text-xs text-muted">Actions: ${s.action_count || 0}</span>
                            <button class="btn btn-primary btn-sm px-2 py-1" onclick="investigateSessionRedirect('${s.session_id}')" style="font-size: 0.72rem; padding: 0.25rem 0.5rem; height: auto;">
                                <i class="ti ti-zoom-in" style="font-size:0.75rem;"></i> Investigate
                            </button>
                        </div>
                    `;
                    container.appendChild(card);
                });
            })
            .catch(e => {
                console.error("Error fetching frozen sessions:", e);
                container.innerHTML = '<p class="text-center text-muted p-4 col-12">Failed to load frozen sessions.</p>';
            });
    }
    window.fetchFrozenSessions = fetchFrozenSessions;

    function executeSearch() {
        const username = document.getElementById('search-username-input').value.trim();
        const range = document.getElementById('search-time-range').value;
        const severity = document.getElementById('search-risk-severity').value;
        const tbody = document.getElementById('search-results-table-body');
        
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted p-6">Executing search query...</td></tr>';
        
        const queryParams = new URLSearchParams({
            username: username,
            range: range,
            severity: severity
        });
        
        fetch(`/api/dashboard/sessions/search?${queryParams.toString()}`)
            .then(r => r.json())
            .then(sessions => {
                tbody.innerHTML = '';
                if (sessions.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted p-6">No historical sessions found matching search criteria.</td></tr>';
                    return;
                }
                
                sessions.forEach(s => {
                    const dateObj = new Date(s.created_at * 1000);
                    const dateStr = `${dateObj.toLocaleDateString()} ${dateObj.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`;
                    const isTerminated = ['terminated', 'red_low', 'red_high', 'red_critical'].includes(s.status);
                    
                    // Device browser mapping short name
                    let device = 'Browser';
                    if (s.user_agent) {
                        if (s.user_agent.toLowerCase().includes('android')) device = 'Android Mobile';
                        else if (s.user_agent.toLowerCase().includes('iphone')) device = 'iPhone iOS';
                        else if (s.user_agent.toLowerCase().includes('windows')) device = 'Windows PC';
                        else if (s.user_agent.toLowerCase().includes('macintosh')) device = 'Mac OSX';
                        else if (s.user_agent.toLowerCase().includes('linux')) device = 'Linux PC';
                    }
                    
                    const row = document.createElement('tr');
                    row.style.borderBottom = '1px solid var(--border)';
                    row.innerHTML = `
                        <td style="padding: 0.75rem 1rem; color: #fff; font-weight: 600;">${s.username}</td>
                        <td style="padding: 0.75rem 1rem;" class="text-mono text-xs">${s.session_id.substring(0, 12)}...</td>
                        <td style="padding: 0.75rem 1rem;" class="text-muted text-xs">${dateStr}</td>
                        <td style="padding: 0.75rem 1rem;" class="text-mono text-xs">${s.ip_address || '127.0.0.1'}</td>
                        <td style="padding: 0.75rem 1rem;" class="text-xs">${device}</td>
                        <td style="padding: 0.75rem 1rem;"><strong class="text-mono text-xs" style="color: ${s.risk_score >= 60 ? 'var(--red)' : s.risk_score >= 35 ? 'var(--amber)' : 'var(--green)'};">${s.risk_score.toFixed(1)}</strong></td>
                        <td style="padding: 0.75rem 1rem;"><span class="badge ${isTerminated ? 'badge-secondary' : s.risk_score >= 60 ? 'badge-red' : s.risk_score >= 35 ? 'badge-amber' : 'badge-green'}" style="font-size:10px;">${s.status.toUpperCase()}</span></td>
                        <td style="padding: 0.75rem 1rem; text-align: center;">
                            <button class="btn btn-secondary btn-sm" onclick="investigateSessionRedirect('${s.session_id}')" style="padding: 0.25rem 0.5rem; font-size: 10px; height: auto;">
                                <i class="ti ti-zoom-in"></i> Audit
                            </button>
                        </td>
                    `;
                    tbody.appendChild(row);
                });
            })
            .catch(e => {
                console.error("Error executing database search:", e);
                tbody.innerHTML = '<tr><td colspan="8" class="text-center text-red p-4">Failed to query historical sessions database.</td></tr>';
            });
    }
    window.executeSearch = executeSearch;

    function investigateSessionRedirect(sessionId) {
        // 1. Switch back to Real-Time Monitor tab
        switchTab('monitor');
        
        // 2. Select this session in Deep Dive
        setTimeout(() => {
            selectSession(sessionId);
        }, 300);
    }
    window.investigateSessionRedirect = investigateSessionRedirect;

    // --- Biometrics Reference Guide Panel Listeners ---
    const btnGuideToggle = document.getElementById('btn-guide-toggle');
    const btnCloseGuide = document.getElementById('btn-close-guide');
    const guidePanel = document.getElementById('biometrics-guide-panel');
    const guideSearch = document.getElementById('guide-search');

    if (btnGuideToggle && guidePanel) {
        btnGuideToggle.addEventListener('click', function() {
            guidePanel.style.transform = 'translateX(0)';
        });
    }

    if (btnCloseGuide && guidePanel) {
        btnCloseGuide.addEventListener('click', function() {
            guidePanel.style.transform = 'translateX(100%)';
        });
    }

    if (guideSearch) {
        guideSearch.addEventListener('input', function(e) {
            const query = e.target.value.toLowerCase().trim();
            const cards = document.querySelectorAll('.guide-card');
            
            cards.forEach(card => {
                let cardHasMatch = false;
                const h4 = card.querySelector('h4');
                const titleText = h4 ? h4.textContent.toLowerCase() : '';
                
                // If the main title matches, show everything in this card
                if (query !== '' && titleText.includes(query)) {
                    cardHasMatch = true;
                    const items = card.querySelectorAll('.guide-item');
                    items.forEach(item => item.style.display = 'block');
                } else {
                    const items = card.querySelectorAll('.guide-item');
                    items.forEach(item => {
                        const strong = item.querySelector('strong');
                        const span = item.querySelector('span');
                        const itemTitle = strong ? strong.textContent.toLowerCase() : '';
                        const itemDesc = span ? span.textContent.toLowerCase() : '';
                        
                        if (query === '' || itemTitle.includes(query) || itemDesc.includes(query)) {
                            item.style.display = 'block';
                            cardHasMatch = true;
                        } else {
                            item.style.display = 'none';
                        }
                    });
                }
                
                if (query === '') {
                    card.style.display = 'block';
                    const items = card.querySelectorAll('.guide-item');
                    items.forEach(item => item.style.display = 'block');
                } else if (cardHasMatch) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    }

});

