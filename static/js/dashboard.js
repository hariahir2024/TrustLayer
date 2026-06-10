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
            <td class="text-mono text-sm">${s.session_id}</td>
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
            session_id: s.session_id.substring(0, 8) + '...',
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
        const rowId = `row-${s.session_id.substring(0, 8)}...`;
        const existingRow = document.getElementById(rowId);
        
        if (existingRow) {
            const formatted = {
                session_id: s.session_id.substring(0, 8) + '...',
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
                elements.ddSessionId.textContent = `Session UUID: ${selectedSessionId}`;
                elements.ddRiskScore.textContent = sessionData.risk_score.toFixed(1);
                elements.ddRiskBadge.textContent = sessionData.band;
                applyBadgeColor(elements.ddRiskBadge, sessionData.band);

                // Update charts and breakdowns
                updateShapBreakdown(sessionData.last_breakdown);
                renderKeystrokeChart(sessionData.last_breakdown);
                drawMouseTrajectory(sessionData.last_breakdown);
                fetchAndRenderSessionHeartbeatLogs(selectedSessionId);
            }
        } catch (e) {
            console.error("Error loading deep dive details:", e);
        }
    }

    function updateDeepDiveWorkspace(evt) {
        elements.ddRiskScore.textContent = evt.score.toFixed(1);
        elements.ddRiskBadge.textContent = evt.band;
        applyBadgeColor(elements.ddRiskBadge, evt.band);

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
        keystrokeChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Observed Time (ms)',
                        data: observedData,
                        backgroundColor: '#3b82f6',
                        borderColor: '#2563eb',
                        borderWidth: 1
                    },
                    {
                        label: 'Enrolled Baseline (ms)',
                        data: baselineData,
                        backgroundColor: 'rgba(255, 255, 255, 0.15)',
                        borderColor: 'rgba(255, 255, 255, 0.3)',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: { color: '#94a3b8', font: { size: 10 } }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: '#94a3b8', font: { size: 9 } },
                        grid: { color: 'rgba(255,255,255,0.03)' }
                    },
                    y: {
                        ticks: { color: '#94a3b8', font: { size: 9 } },
                        grid: { color: 'rgba(255,255,255,0.03)' }
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

        const samples = breakdownObj ? breakdownObj.mouse_samples : null;
        if (!samples || samples.length === 0) {
            ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
            ctx.font = '11px sans-serif';
            ctx.fillText("No mouse coordinates recorded in this cycle.", 20, 70);
            return;
        }

        // Project coordinate boundaries to fit canvas size
        const padding = 15;
        const xs = samples.map(s => s.x);
        const ys = samples.map(s => s.y);
        const minX = Math.min(...xs), maxX = Math.max(...xs);
        const minY = Math.min(...ys), maxY = Math.max(...ys);

        const rangeX = (maxX - minX) || 1;
        const rangeY = (maxY - minY) || 1;

        // Draw grid
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.02)';
        ctx.lineWidth = 1;
        for (let i = 20; i < canvas.width; i += 20) {
            ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, canvas.height); ctx.stroke();
        }
        for (let i = 20; i < canvas.height; i += 20) {
            ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(canvas.width, i); ctx.stroke();
        }

        // Draw lines
        ctx.beginPath();
        samples.forEach((s, idx) => {
            const canvasX = padding + ((s.x - minX) / rangeX) * (canvas.width - 2 * padding);
            const canvasY = padding + ((s.y - minY) / rangeY) * (canvas.height - 2 * padding);
            
            if (idx === 0) ctx.moveTo(canvasX, canvasY);
            else ctx.lineTo(canvasX, canvasY);
        });

        // Set path color based on straightness/bot markers
        let pathColor = '#10b981'; // Green
        const isBot = breakdownObj.is_bot || (samples.length > 5 && (maxX - minX < 2 || maxY - minY < 2)); // straight line
        if (isBot) pathColor = '#ef4444'; // Red (bot)
        
        ctx.strokeStyle = pathColor;
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Draw nodes for start/end
        if (samples.length > 0) {
            // Start node
            const startX = padding + ((samples[0].x - minX) / rangeX) * (canvas.width - 2 * padding);
            const startY = padding + ((samples[0].y - minY) / rangeY) * (canvas.height - 2 * padding);
            ctx.fillStyle = '#3b82f6';
            ctx.beginPath(); ctx.arc(startX, startY, 4, 0, 2 * Math.PI); ctx.fill();

            // End node
            const endX = padding + ((samples[samples.length-1].x - minX) / rangeX) * (canvas.width - 2 * padding);
            const endY = padding + ((samples[samples.length-1].y - minY) / rangeY) * (canvas.height - 2 * padding);
            ctx.fillStyle = '#f59e0b';
            ctx.beginPath(); ctx.arc(endX, endY, 4, 0, 2 * Math.PI); ctx.fill();
        }
    }

    async function fetchAndRenderSessionHeartbeatLogs(sid) {
        try {
            const r = await fetch('/api/dashboard/logs');
            const allLogs = await r.json();
            
            // Filter logs for this session (either full session_id or truncated comparison)
            const sessionLogs = allLogs.filter(l => 
                l.session_id === sid || sid.startsWith(l.session_id.substring(0, 8))
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
            elements.globalLogFeed.innerHTML = '<p class="text-center text-muted p-4">Awaiting security events from Vishwa Bank...</p>';
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
        document.getElementById('nav-item-monitor').classList.remove('active');
        document.getElementById('nav-item-threats').classList.remove('active');
        
        document.getElementById('tab-monitor').classList.add('hidden');
        document.getElementById('tab-threats').classList.add('hidden');

        document.getElementById(`nav-item-${tabName}`).classList.add('active');
        document.getElementById(`tab-${tabName}`).classList.remove('hidden');
    };
});
