/**
 * BehaviorShield — sdk.js
 * Team SOLARIS | Cyber Security Hackathon 2026 | MNNIT Allahabad
 * 
 * Silent behavioral telemetry collector. Runs on bank.html.
 * Captures keystroke timings, mouse dynamics, and device fingerprint data.
 * Manages periodic background scoring calls and handles dynamic scoring intervals.
 */

const BehaviorShield = (function() {
    // Configuration
    const CONFIG = {
        DEFAULT_INTERVAL_MS: 30000, // 30 seconds (Green)
        AMBER_LOW_INTERVAL_MS: 10000, // 10 seconds (Amber Low)
        API_SCORE_URL: '/api/score',
        PASSPHRASE_LENGTH: 17
    };

    // State variables
    let sessionId = null;
    let username = null;
    let scoringTimer = null;
    let currentIntervalMs = CONFIG.DEFAULT_INTERVAL_MS;

    // Telemetry buffers
    let keyEventsBuffer = [];
    let mouseSamplesBuffer = [];
    let clickDwells = [];

    // Timing helper
    let lastMouseMoveTime = 0;
    let mouseMoveSampleRateMs = 50; // sample mouse at 20Hz (every 50ms)

    // Keydown tracker to pair keydown/keyup events and map them to input positions
    const activeKeys = {}; // keycode -> position
    let fieldFocusTimestamp = null;
    let targetInputElements = new Set();

    // Browser automation flag
    const isWebDriver = !!(navigator.webdriver || window.document.documentElement.getAttribute('webdriver') || window.callPhantom || window._phantom);

    /**
     * Generate the device fingerprint object to be sent to /api/login
     */
    function getDeviceFingerprint() {
        return {
            user_agent: navigator.userAgent,
            screen_width: window.screen.width,
            screen_height: window.screen.height,
            color_depth: window.screen.colorDepth || 24,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
            language: navigator.language || 'en-US'
        };
    }

    /**
     * Start capturing mouse movements, clicks, and scrolls globally
     */
    function startGlobalMouseCapture() {
        // Track mousemove
        window.addEventListener('mousemove', function(e) {
            const now = Date.now();
            if (now - lastMouseMoveTime >= mouseMoveSampleRateMs) {
                mouseSamplesBuffer.push({
                    timestamp: now,
                    x: e.clientX,
                    y: e.clientY,
                    event: 'move'
                });
                lastMouseMoveTime = now;
                // Limit buffer size to prevent memory leaks
                if (mouseSamplesBuffer.length > 5000) {
                    mouseSamplesBuffer.shift();
                }
            }
        }, { passive: true });

        // Track click down
        let activeClicks = {};
        window.addEventListener('mousedown', function(e) {
            const now = Date.now();
            mouseSamplesBuffer.push({
                timestamp: now,
                x: e.clientX,
                y: e.clientY,
                event: 'click_down'
            });
            activeClicks[e.button || 0] = now;
        }, { passive: true });

        // Track click up and compute click dwell
        window.addEventListener('mouseup', function(e) {
            const now = Date.now();
            mouseSamplesBuffer.push({
                timestamp: now,
                x: e.clientX,
                y: e.clientY,
                event: 'click_up'
            });
            const clickStart = activeClicks[e.button || 0];
            if (clickStart) {
                const dwell = now - clickStart;
                clickDwells.push(dwell);
                delete activeClicks[e.button || 0];
            }
        }, { passive: true });

        // Track scroll wheel events
        window.addEventListener('wheel', function(e) {
            mouseSamplesBuffer.push({
                timestamp: Date.now(),
                x: e.clientX,
                y: e.clientY,
                event: 'scroll',
                scroll_delta: Math.abs(e.deltaY)
            });
        }, { passive: true });
    }

    /**
     * Register input element for keystroke capture
     * @param {HTMLInputElement} element 
     */
    function registerInput(element) {
        if (!element || targetInputElements.has(element)) return;
        targetInputElements.add(element);

        element.addEventListener('focus', function() {
            fieldFocusTimestamp = Date.now();
        });

        element.addEventListener('keydown', function(e) {
            const now = Date.now();
            let pos = -1;

            if (e.key === 'Backspace') {
                pos = -1;
            } else if (e.key.length === 1) {
                // Determine 1-indexed position of where the character will go
                pos = element.selectionStart + 1;
            } else {
                return; // Ignore control keys other than Backspace
            }

            // Store position of active key to pair it on keyup
            activeKeys[e.code] = pos;

            keyEventsBuffer.push({
                timestamp: now,
                event: 'down',
                position: pos
            });
            
            // Limit buffer size
            if (keyEventsBuffer.length > 1000) keyEventsBuffer.shift();
        });

        element.addEventListener('keyup', function(e) {
            const now = Date.now();
            const pos = activeKeys[e.code];
            if (pos !== undefined) {
                keyEventsBuffer.push({
                    timestamp: now,
                    event: 'up',
                    position: pos
                });
                delete activeKeys[e.code];
            } else if (e.key === 'Backspace') {
                keyEventsBuffer.push({
                    timestamp: now,
                    event: 'up',
                    position: -1
                });
            }
        });
    }

    /**
     * Compute average click dwell time
     */
    function getMeanClickDwell() {
        if (clickDwells.length === 0) return 120.0; // human average fallback
        const sum = clickDwells.reduce((a, b) => a + b, 0);
        return sum / clickDwells.length;
    }

    /**
     * Trigger scoring call to backend and broadcast local updates
     */
    async function performScoringCycle() {
        if (!sessionId) return;

        // Copy and clear buffers
        const keyEvents = [...keyEventsBuffer];
        const mouseSamples = [...mouseSamplesBuffer];
        const meanClickDwell = getMeanClickDwell();

        keyEventsBuffer = [];
        mouseSamplesBuffer = [];
        clickDwells = [];

        try {
            const response = await fetch(CONFIG.API_SCORE_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    key_events: keyEvents,
                    mouse_samples: mouseSamples,
                    click_dwell_mean: meanClickDwell,
                    webdriver_flag: isWebDriver
                })
            });

            if (!response.ok) {
                console.error('BehaviorShield scoring request failed:', response.statusText);
                return;
            }

            const data = await response.json();
            
            // Dispatch result event so page logic can respond
            const shieldEvent = new CustomEvent('behaviorshield_update', { detail: data });
            window.dispatchEvent(shieldEvent);

            // Handle actions or trigger freezes
            if (data.action === 'FREEZE_SESSION' || data.action === 'FREEZE_AND_ALERT' || data.action === 'SILENT_BLOCK') {
                stopScoringLoop();
                window.dispatchEvent(new CustomEvent('behaviorshield_freeze', { detail: data }));
            } else if (data.action === 'SOFT_CHALLENGE' || data.action === 'FULL_CHALLENGE') {
                window.dispatchEvent(new CustomEvent('behaviorshield_challenge', { detail: data }));
            }

            // Dynamically adjust polling interval
            const serverIntervalMs = (data.scoring_interval || 30) * 1000;
            if (serverIntervalMs !== currentIntervalMs) {
                console.log(`[BehaviorShield] Interval adjusted to ${serverIntervalMs / 1000}s`);
                currentIntervalMs = serverIntervalMs;
                restartScoringLoop();
            }

        } catch (err) {
            console.error('BehaviorShield error in scoring cycle:', err);
        }
    }

    function startScoringLoop() {
        stopScoringLoop();
        scoringTimer = setInterval(performScoringCycle, currentIntervalMs);
    }

    function stopScoringLoop() {
        if (scoringTimer) {
            clearInterval(scoringTimer);
            scoringTimer = null;
        }
    }

    function restartScoringLoop() {
        stopScoringLoop();
        startScoringLoop();
    }

    /**
     * Public API
     */
    return {
        /**
         * Initialize the SDK for a session
         * @param {string} sid - The active session ID
         * @param {string} user - Username of the current user
         */
        init: function(sid, user) {
            sessionId = sid;
            username = user;
            currentIntervalMs = CONFIG.DEFAULT_INTERVAL_MS;
            
            keyEventsBuffer = [];
            mouseSamplesBuffer = [];
            clickDwells = [];
            
            startGlobalMouseCapture();
            startScoringLoop();
            
            console.log(`[BehaviorShield] Telemetry SDK initialized for session: ${sid}`);
        },

        /**
         * Register a specific input field for keyboard monitoring
         * @param {HTMLInputElement} inputElement 
         */
        monitorInput: function(inputElement) {
            registerInput(inputElement);
        },

        /**
         * Manually get current keystroke buffer and clear it (e.g. for login or enrollment submissions)
         */
        extractKeyEvents: function() {
            const events = [...keyEventsBuffer];
            keyEventsBuffer = [];
            return events;
        },

        /**
         * Get client metadata fingerprint
         */
        getDeviceFingerprint: getDeviceFingerprint,

        /**
         * Get field focus timestamp
         */
        getFieldFocusTimestamp: function() {
            return fieldFocusTimestamp;
        },

        /**
         * Force manual scoring submit (useful on submit buttons)
         */
        forceSubmitScore: performScoringCycle,

        /**
         * Stop tracking and periodic updates
         */
        destroy: function() {
            stopScoringLoop();
            sessionId = null;
            username = null;
            targetInputElements.clear();
            console.log('[BehaviorShield] Telemetry SDK stopped and cleaned up.');
        }
    };
})();

// Export global variable
window.BehaviorShield = BehaviorShield;
