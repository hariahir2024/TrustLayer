/**
 * BehaviorShield — dashboard.js
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
    let ws = null;
    let keystrokeChart = null;

    // Cache elements
    const elements = {
        statActive: document.getElementById('stat-active-sessions'),
        statAvgRisk: document.getElementById('stat-avg-risk'),
        statThreats: document.getElementById('stat-total-threats'),
        statFrozen: document.getElementById('stat-frozen-sessions'),
        
        sessionTableBody: document.getElementById('session-table-body'),
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
        await fetchStats();
        await fetchSessions();
        await fetchGlobalLogs();
        connectWebSocket();
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
            const r = await fetch('/api/dashboard/sessions');
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
        // Average risk placeholder logic
        elements.statAvgRisk.textContent = (stats.active_sessions > 0) ? "24.5" : "0.0";
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
    }

    // ==========================================
    // SESSIONS LIST TABLE RENDER
    // ==========================================
    function renderSessionsTable(sessions) {
        elements.sessionTableBody.innerHTML = '';
        if (sessions.length === 0) {
            elements.sessionTableBody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center text-muted">No active sessions currently monitored.</td>
                </tr>
            `;
            return;
        }

        sessions.forEach(s => {
            const tr = createSessionRow(s);
            elements.sessionTableBody.appendChild(tr);
        });
    }

    function createSessionRow(s) {
        const tr = document.createElement('tr');
        tr.id = `row-${s.session_id}`;
        tr.style.cursor = 'pointer';
        tr.className = selectedSessionId === s.session_id ? 'row-red' : ''; // highlight if selected

        // Event listener to trigger deep dive
        tr.addEventListener('click', () => selectSession(s.session_id));

        let statusDotClass = 'dot-green';
        if (s.band.startsWith('AMBER')) statusDotClass = 'dot-amber';
        if (s.band.startsWith('RED')) statusDotClass = 'dot-red';
        if (s.status === 'terminated') statusDotClass = 'dot-gray';

        tr.innerHTML = `
            <td class="text-mono text-sm">${s.session_id.substring(0, 8)}...</td>
            <td><strong>${s.username}</strong></td>
            <td>
                <span class="flex items-center gap-2">
                    <span class="status-dot ${statusDotClass}"></span>
                    ${s.status.toUpperCase()}
                </span>
            </td>
            <td>
                <span class="text-xs text-muted">Dur: ${s.duration_sec}s • Actions: ${s.action_count}</span>
            </td>
            <td class="text-mono text-brand fw-600">${s.risk_score.toFixed(1)}</td>
            <td><span class="risk-badge badge" data-band="${s.band}">${s.band}</span></td>
        `;

        // Apply data band classes dynamically
        const badge = tr.querySelector('.risk-badge');
        applyBadgeColor(badge, s.band);

        return tr;
    }

    function addSessionToTable(s) {
        // Remove empty placeholder row if present
        if (elements.sessionTableBody.innerHTML.includes('No active sessions')) {
            elements.sessionTableBody.innerHTML = '';
        }

        const formatted = {
            session_id: s.session_id,
            username: s.username,
            status: 'active',
            duration_sec: 0,
            action_count: 0,
            risk_score: s.score,
            band: s.band
        };
        const row = createSessionRow(formatted);
        elements.sessionTableBody.appendChild(row);
    }

    function updateSessionInTable(s) {
        const rowId = `row-${s.session_id}`;
        const existingRow = document.getElementById(rowId);
        
        if (existingRow) {
            const formatted = {
                session_id: s.session_id,
                username: s.username,
                status: s.band.startsWith('RED') ? 'frozen' : 'active',
                duration_sec: 15, // placeholder
                action_count: 3, // placeholder
                risk_score: s.score,
                band: s.band
            };
            const newRow = createSessionRow(formatted);
            existingRow.replaceWith(newRow);
        } else {
            fetchSessions();
        }
    }

    function applyBadgeColor(badge, band) {
        badge.className = "badge";
        if (band === 'GREEN') badge.classList.add('badge-green');
        else if (band.startsWith('AMBER')) badge.classList.add('badge-amber');
        else if (band === 'AMBER_HIGH') badge.classList.add('badge-orange');
        else badge.classList.add('badge-red');
    }

    // ==========================================
    // DEEP-DIVE WORKSPACE
    // ==========================================
    async function selectSession(fullId) {
        // Highlight row
        const rows = elements.sessionTableBody.querySelectorAll('tr');
        rows.forEach(r => r.classList.remove('row-red'));
        
        const selectedRow = document.getElementById(`row-${fullId}`);
        if (selectedRow) selectedRow.classList.add('row-red');

        selectedSessionId = fullId;
        
        elements.ddEmpty.classList.add('hidden');
        elements.ddWorkspace.classList.remove('hidden');

        // Fetch deep-dive historical records
        try {
            // Need to fetch full details including logs & history
            const rSession = await fetch(`/api/dashboard/sessions`);
            const sessions = await rSession.json();
            const sessionData = sessions.find(s => s.session_id === selectedSessionId);

            if (sessionData) {
                elements.ddUsername.textContent = sessionData.username;
                elements.ddSessionId.textContent = `Session ID: ${selectedSessionId}`;
                elements.ddRiskScore.textContent = sessionData.risk_score.toFixed(1);
                elements.ddRiskBadge.textContent = sessionData.band;
                applyBadgeColor(elements.ddRiskBadge, sessionData.band);

                // Populate Diagnostics
                document.getElementById('dd-ip-address').textContent = sessionData.ip_address || '127.0.0.1';
                document.getElementById('dd-interval').textContent = `${sessionData.scoring_interval || 30}s`;
                document.getElementById('dd-user-agent').textContent = sessionData.user_agent || 'Unknown Client';

                // Update charts and breakdowns
                updateShapBreakdown(sessionData.last_breakdown);
                renderKeystrokeChart(sessionData.last_breakdown);
                drawMouseTrajectory(sessionData.last_breakdown);
                fetchAndRenderSessionHeartbeatLogs(selectedSessionId);

                // Render intruder label panel (Stream 6A)
                renderIntruderLabelPanel(selectedSessionId);
            }
        } catch (e) {
            console.error("Error loading deep dive details:", e);
        }
    }

    function updateDeepDiveWorkspace(evt) {
        elements.ddRiskScore.textContent = evt.score.toFixed(1);
        elements.ddRiskBadge.textContent = evt.band;
        applyBadgeColor(elements.ddRiskBadge, evt.band);

        // Update metadata live
        if (evt.ip_address) document.getElementById('dd-ip-address').textContent = evt.ip_address;
        if (evt.scoring_interval) document.getElementById('dd-interval').textContent = `${evt.scoring_interval}s`;
        if (evt.user_agent) document.getElementById('dd-user-agent').textContent = evt.user_agent;

        // Find matching breakdown object
        const fakeBreakdownObj = {
            all_contributors: evt.all_contributors || [],
            top_contributors: evt.top_contributors || [],
            mouse_samples: evt.mouse_samples || []
        };

        updateShapBreakdown(fakeBreakdownObj);
        renderKeystrokeChart(fakeBreakdownObj);
        drawMouseTrajectory(fakeBreakdownObj);
        fetchAndRenderSessionHeartbeatLogs(selectedSessionId);
    }

    function updateShapBreakdown(breakdownObj) {
        elements.ddShapList.innerHTML = '';
        if (!breakdownObj || !breakdownObj.top_contributors || breakdownObj.top_contributors.length === 0) {
            elements.ddShapList.innerHTML = '<p class="text-xs text-muted">No anomaly triggers active.</p>';
            return;
        }

        breakdownObj.top_contributors.forEach(c => {
            if (c.contribution <= 0.5) return; // ignore tiny contributions
            
            const item = document.createElement('div');
            item.className = 'breakdown-item';
            if (c.contribution > 15) item.classList.add('high');
            else if (c.contribution > 5) item.classList.add('med');

            item.innerHTML = `
                <div class="breakdown-label" title="${c.label}">${c.label}</div>
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

        // Draw tactical radar grid pattern background
        ctx.strokeStyle = 'rgba(6, 182, 212, 0.06)';
        ctx.lineWidth = 1;
        
        // Draw vertical/horizontal grid lines
        for (let i = 25; i < canvas.width; i += 25) {
            ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, canvas.height); ctx.stroke();
        }
        for (let i = 25; i < canvas.height; i += 25) {
            ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(canvas.width, i); ctx.stroke();
        }

        // Draw central crosshairs and radar circles
        const cx = canvas.width / 2;
        const cy = canvas.height / 2;
        ctx.strokeStyle = 'rgba(6, 182, 212, 0.12)';
        ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, canvas.height); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(0, cy); ctx.lineTo(canvas.width, cy); ctx.stroke();
        
        ctx.beginPath(); ctx.arc(cx, cy, 30, 0, 2 * Math.PI); ctx.stroke();
        ctx.beginPath(); ctx.arc(cx, cy, 60, 0, 2 * Math.PI); ctx.stroke();

        // Canvas HUD Label Overlay
        ctx.fillStyle = 'rgba(6, 182, 212, 0.45)';
        ctx.font = '8px var(--font-mono)';
        ctx.fillText('TARGET SECTOR: BS-SEC-9', 8, 12);
        ctx.fillText('RESOLVER: ACTIVE', 8, 22);

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
            const r = await fetch('/api/dashboard/logs');
            const allLogs = await r.json();
            
            // Filter logs for this session (either full session_id or truncated comparison)
            const sessionLogs = allLogs.filter(l => 
                l.session_id && (l.session_id === sid || sid.startsWith(l.session_id.substring(0, 8)))
            );

            elements.ddSessionLogs.innerHTML = '';
            if (sessionLogs.length === 0) {
                elements.ddSessionLogs.innerHTML = '<p class="text-center text-muted text-xs p-4">No events logged yet.</p>';
                return;
            }

            sessionLogs.forEach(l => {
                const item = createLogItemMarkup(l);
                elements.ddSessionLogs.appendChild(item);
            });
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
            detailString = `Score: ${l.risk_score.toFixed(1)} [K:${l.details.keystroke?.toFixed(0)} M:${l.details.mouse?.toFixed(0)}]`;
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
        if (!confirm("Are you sure you want to FORCE FREEZE this session? This blocks the client UI immediately.")) return;

        try {
            // Need to convert truncated ID back or extract it from selectedSessionId
            const response = await fetch(`/api/admin/freeze/${selectedSessionId}`, { method: 'POST' });
            if (response.ok) {
                alert("Session frozen successfully.");
                fetchSessions();
            } else { alert("Failed to freeze session."); }
        } catch (err) { console.error("Error freezing session:", err); }
    });

    elements.btnUnfreeze.addEventListener('click', async function() {
        if (!selectedSessionId) return;
        if (!confirm("Are you sure you want to mark this as a FALSE POSITIVE and restore session access?")) return;

        try {
            const response = await fetch(`/api/admin/false-positive/${selectedSessionId}`, { method: 'POST' });
            if (response.ok) {
                const data = await response.json();
                alert("Session unfreezed and risk reset.");
                selectSession(selectedSessionId);
                fetchSessions();
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
        
        // Add hidden class to all tabs
        document.getElementById('tab-monitor').classList.add('hidden');
        document.getElementById('tab-threats').classList.add('hidden');
        const tabData = document.getElementById('tab-datacollection');
        if (tabData) tabData.classList.add('hidden');

        // Show selected tab and active nav item
        const activeNav = document.getElementById(`nav-item-${tabName}`);
        const activeTabEl = document.getElementById(`tab-${tabName}`);
        if (activeNav) activeNav.classList.add('active');
        if (activeTabEl) activeTabEl.classList.remove('hidden');

        // Load data collection summary when that tab is opened
        if (tabName === 'datacollection') {
            fetchDataCollectionSummary();
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
        container.innerHTML = '<p style="color:#94a3b8;font-size:12px;">Loading...</p>';

        try {
            const res = await fetch('/api/admin/data-collection-summary');
            const data = await res.json();
            renderDataCollectionSummary(data, container);
        } catch (err) {
            container.innerHTML = '<p style="color:#ef4444;font-size:12px;">Failed to load summary</p>';
        }
    }

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
                        ? '<span style="color:#22c55e;">✅ Enrolled</span>'
                        : '<span style="color:#f59e0b;">⏳ Pending</span>'}
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

            <!-- Retraining readiness -->
            <div style="margin-bottom:16px;padding:10px 14px;border-radius:8px;
                        background:rgba(${totals.ready_for_retraining ? '34,197,94' : '245,158,11'},0.08);
                        border:1px solid rgba(${totals.ready_for_retraining ? '34,197,94' : '245,158,11'},0.25);
                        font-size:12px;color:${readyColor};">
                ${readyText}
                ${totals.ready_for_retraining
                    ? '<br><span style="color:#94a3b8;font-size:10px;">Run: python scripts/retrain_xgb_augmented.py</span>'
                    : ''}
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
            <button onclick="fetchDataCollectionSummary()"
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
        const badge = document.getElementById('mode-badge');
        if (!btn) return;

        if (mode === 'advisory') {
            btn.textContent = '👁️ Advisory Mode — Click to Activate';
            btn.style.background = 'rgba(99,102,241,0.2)';
            btn.style.borderColor = '#6366f1';
            btn.style.color = '#a5b4fc';
            if (badge) { badge.textContent = 'ADVISORY'; badge.style.color = '#a5b4fc'; }
        } else {
            btn.textContent = '🔴 Active Mode — Click for Advisory';
            btn.style.background = 'rgba(239,68,68,0.15)';
            btn.style.borderColor = '#ef4444';
            btn.style.color = '#ef4444';
            if (badge) { badge.textContent = 'ACTIVE'; badge.style.color = '#ef4444'; }
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

    // Extend WS message handler to process mode_changed events
    const _origHandleWS = window._handleWSMessage;
    window._handleWSMessage = function(data) {
        if (_origHandleWS) _origHandleWS(data);
        if (data.type === 'mode_changed') handleModeChanged(data);
    };

});

