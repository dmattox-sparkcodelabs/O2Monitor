// O2 Monitor Dashboard JavaScript

(function() {
    'use strict';

    // Fetch wrapper that handles 401 redirects
    async function apiFetch(url, options = {}) {
        const response = await fetch(url, { credentials: 'same-origin', ...options });
        if (response.status === 401) {
            window.location.href = '/auth/login';
            throw new Error('Unauthorized');
        }
        return response;
    }

    // State
    let spo2Chart = null;
    let updateInterval = null;
    let chartRange = 6; // hours

    // DOM Elements
    const elements = {
        refreshProgress: document.getElementById('refresh-progress'),
        stateBanner: document.getElementById('state-banner'),
        stateText: document.getElementById('state-text'),
        spo2Value: document.getElementById('spo2-value'),
        spo2Status: document.getElementById('spo2-status'),
        hrValue: document.getElementById('hr-value'),
        hrStatus: document.getElementById('hr-status'),
        avapsStatus: document.getElementById('avaps-status'),
        avapsPower: document.getElementById('avaps-power'),
        bleIndicator: document.getElementById('ble-indicator'),
        bleStatus: document.getElementById('ble-status'),
        batteryIndicator: document.getElementById('battery-indicator'),
        batteryValue: document.getElementById('battery-value'),
        lastReading: document.getElementById('last-reading'),
        uptime: document.getElementById('uptime'),
        silenceBanner: document.getElementById('silence-banner'),
        silenceRemaining: document.getElementById('silence-remaining'),
        testAlertBtn: document.getElementById('test-alert-btn'),
        silenceBtn: document.getElementById('silence-btn'),
        unsilenceBtn: document.getElementById('unsilence-btn')
    };

    // State class to CSS class mapping
    const stateClasses = {
        'initializing': 'state-initializing',
        'normal': 'state-normal',
        'therapy_active': 'state-therapy_active',
        'low_spo2_warning': 'state-low_spo2_warning',
        'alarm': 'state-alarm',
        'disconnected': 'state-disconnected',
        'silenced': 'state-silenced',
        'late_reading': 'state-late_reading'
    };

    // Reading staleness is now handled by backend:
    // 0-10s = normal, 10-30s = late_reading, >30s = disconnected

    // Initialize dashboard
    function init() {
        console.log('Dashboard init starting...');
        // Get refresh progress element (must be done after DOM ready)
        elements.refreshProgress = document.getElementById('refresh-progress');
        console.log('Refresh progress element:', elements.refreshProgress);
        try {
            initChart();
            console.log('Chart initialized');
        } catch (e) {
            console.error('Chart init error:', e);
        }
        setupEventListeners();
        console.log('Event listeners set up');
        updateDashboard();
        console.log('First update triggered');
        startAutoRefresh();
        console.log('Auto-refresh started');
    }

    // SpO2 threshold levels
    const SPO2_ALARM_LEVEL = 90;
    const SPO2_WARNING_LEVEL = 92;

    // Plugin to draw threshold background zones
    const thresholdZonesPlugin = {
        id: 'thresholdZones',
        beforeDraw: function(chart) {
            const ctx = chart.ctx;
            const chartArea = chart.chartArea;
            const yScale = chart.scales.y;

            if (!chartArea) return;

            // Calculate pixel positions for thresholds
            const yMin = yScale.min;
            const yMax = yScale.max;
            const alarmY = yScale.getPixelForValue(SPO2_ALARM_LEVEL);
            const warningY = yScale.getPixelForValue(SPO2_WARNING_LEVEL);
            const bottomY = yScale.getPixelForValue(yMin);

            ctx.save();

            // Red zone: below alarm level (90%)
            ctx.fillStyle = 'rgba(244, 67, 54, 0.2)';
            ctx.fillRect(
                chartArea.left,
                alarmY,
                chartArea.right - chartArea.left,
                bottomY - alarmY
            );

            // Yellow zone: between alarm (90%) and warning (92%)
            ctx.fillStyle = 'rgba(255, 152, 0, 0.2)';
            ctx.fillRect(
                chartArea.left,
                warningY,
                chartArea.right - chartArea.left,
                alarmY - warningY
            );

            ctx.restore();
        }
    };

    // Initialize the SpO2 chart
    function initChart() {
        const ctx = document.getElementById('spo2-chart');
        if (!ctx) return;

        spo2Chart = new Chart(ctx, {
            type: 'line',
            data: {
                datasets: [{
                    label: 'SpO2 %',
                    data: [],
                    borderColor: '#2196F3',
                    backgroundColor: 'rgba(33, 150, 243, 0.1)',
                    fill: true,
                    tension: 0.2,
                    pointRadius: 0,
                    pointHitRadius: 10
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            unit: 'minute',
                            displayFormats: {
                                minute: 'h:mm a'
                            }
                        },
                        title: {
                            display: true,
                            text: 'Time'
                        }
                    },
                    y: {
                        min: 80,
                        max: 100,
                        title: {
                            display: true,
                            text: 'SpO2 %'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                },
                interaction: {
                    intersect: false,
                    mode: 'index'
                }
            },
            plugins: [thresholdZonesPlugin]
        });
    }

    // Set up event listeners
    function setupEventListeners() {
        // Test alert button
        if (elements.testAlertBtn) {
            elements.testAlertBtn.addEventListener('click', testAlert);
        }

        // Silence button
        if (elements.silenceBtn) {
            elements.silenceBtn.addEventListener('click', silenceAlerts);
        }

        // Unsilence button
        if (elements.unsilenceBtn) {
            elements.unsilenceBtn.addEventListener('click', unsilenceAlerts);
        }

        // Chart range buttons
        document.querySelectorAll('.chart-controls .btn').forEach(btn => {
            btn.addEventListener('click', function() {
                document.querySelectorAll('.chart-controls .btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                chartRange = parseInt(this.dataset.range);
                // Update chart title
                const chartTitle = document.getElementById('chart-title');
                if (chartTitle) {
                    chartTitle.textContent = 'SpO2 Trend (Last ' + chartRange + ' Hour' + (chartRange > 1 ? 's' : '') + ')';
                }
                loadChartData();
            });
        });
    }

    // Reset refresh progress bar animation
    function resetRefreshProgress() {
        console.log('resetRefreshProgress called, element:', elements.refreshProgress);
        if (elements.refreshProgress) {
            // Remove animation class to reset
            elements.refreshProgress.classList.remove('animating');
            // Force reflow to restart animation
            void elements.refreshProgress.offsetWidth;
            // Add animation class back
            elements.refreshProgress.classList.add('animating');
            console.log('Animation class added');
        } else {
            console.log('Progress element not found!');
        }
    }

    // Update dashboard with latest data
    async function updateDashboard() {
        console.log('updateDashboard called');
        resetRefreshProgress();
        try {
            console.log('Fetching /api/status...');
            const response = await apiFetch('/api/status');
            console.log('Response status:', response.status);
            if (!response.ok) throw new Error('Failed to fetch status: ' + response.status);

            const data = await response.json();
            console.log('Got data:', data);
            updateUI(data);
        } catch (error) {
            console.error('Error updating dashboard:', error);
        }
    }

    // Update UI with status data
    function updateUI(data) {
        // Backend now handles late_reading and disconnected states based on reading age
        // 0-10s = normal, 10-30s = late_reading, >30s = disconnected
        const effectiveState = data.state;

        // Update state banner
        updateStateBanner(effectiveState);

        // Update vitals - show "--" when disconnected, late reading, or no vitals data
        const showVitals = data.vitals && effectiveState !== 'disconnected' && effectiveState !== 'late_reading';
        if (showVitals) {
            const vitals = data.vitals;

            // SpO2
            elements.spo2Value.textContent = vitals.spo2 || '--';
            if (vitals.spo2 && vitals.spo2 < 90) {
                elements.spo2Status.textContent = 'LOW';
                elements.spo2Status.style.color = '#f44336';
            } else if (vitals.spo2 && vitals.spo2 < 92) {
                elements.spo2Status.textContent = 'Warning';
                elements.spo2Status.style.color = '#FF9800';
            } else if (vitals.spo2) {
                elements.spo2Status.textContent = 'Normal';
                elements.spo2Status.style.color = '#4CAF50';
            } else {
                elements.spo2Status.textContent = '';
            }

            // Heart Rate
            elements.hrValue.textContent = vitals.heart_rate || '--';
            if (vitals.heart_rate && (vitals.heart_rate < 50 || vitals.heart_rate > 120)) {
                elements.hrStatus.textContent = 'Abnormal';
                elements.hrStatus.style.color = '#FF9800';
            } else {
                elements.hrStatus.textContent = '';
            }
        } else {
            // No vitals or disconnected - show dashes
            elements.spo2Value.textContent = '--';
            elements.hrValue.textContent = '--';
            elements.spo2Status.textContent = '';
            elements.hrStatus.textContent = '';
        }

        // AVAPS status
        if (data.avaps) {
            const isOn = data.avaps.state === 'on';
            elements.avapsStatus.textContent = isOn ? 'ON' : 'OFF';
            elements.avapsStatus.style.color = isOn ? '#4CAF50' : '#9E9E9E';
            if (data.avaps.power_watts !== null) {
                elements.avapsPower.textContent = data.avaps.power_watts.toFixed(1) + 'W';
            }
        }

        // BLE status
        if (data.ble) {
            const connected = data.ble.connected;
            elements.bleIndicator.className = 'status-indicator ' + (connected ? 'connected' : 'disconnected');
            elements.bleStatus.textContent = connected ? 'Connected' : 'Disconnected';

            // Battery
            if (data.ble.battery_level !== null) {
                elements.batteryValue.textContent = data.ble.battery_level + '%';
                elements.batteryIndicator.className = 'status-indicator ' +
                    (data.ble.battery_level > 20 ? 'connected' : 'disconnected');
            }

            // Last reading time
            if (data.ble.last_reading_time) {
                const lastTime = new Date(data.ble.last_reading_time);
                const now = new Date();
                const diffSec = Math.floor((now - lastTime) / 1000);
                elements.lastReading.textContent = formatDuration(diffSec) + ' ago';
            }
        }

        // System info
        if (data.system) {
            // Uptime
            if (data.system.uptime_seconds) {
                elements.uptime.textContent = formatDuration(data.system.uptime_seconds);
            }

            // Silence status
            if (data.system.alerts_silenced && data.system.silence_remaining_seconds > 0) {
                const remaining = Math.ceil(data.system.silence_remaining_seconds / 60);
                elements.silenceBanner.style.display = 'block';
                elements.silenceRemaining.textContent = remaining;
                elements.silenceBtn.style.display = 'none';
                elements.unsilenceBtn.style.display = 'inline-block';
            } else {
                elements.silenceBanner.style.display = 'none';
                elements.silenceBtn.style.display = 'inline-block';
                elements.unsilenceBtn.style.display = 'none';
            }
        }
    }

    // Update state banner
    function updateStateBanner(state) {
        // Remove all state classes
        Object.values(stateClasses).forEach(cls => {
            elements.stateBanner.classList.remove(cls);
        });

        // Add current state class
        const stateClass = stateClasses[state] || 'state-normal';
        elements.stateBanner.classList.add(stateClass);

        // Update text
        const stateNames = {
            'initializing': 'INITIALIZING',
            'normal': 'NORMAL',
            'therapy_active': 'THERAPY ACTIVE',
            'low_spo2_warning': 'LOW SPO2 WARNING',
            'alarm': 'ALARM',
            'disconnected': 'DISCONNECTED',
            'silenced': 'SILENCED',
            'late_reading': 'LATE READING'
        };

        elements.stateText.textContent = stateNames[state] || state.toUpperCase();
    }

    // Load chart data
    async function loadChartData() {
        try {
            const endTime = new Date();
            const startTime = new Date(endTime - chartRange * 60 * 60 * 1000);

            // Calculate appropriate limit based on range
            // At ~17 readings/min, we need: 1h=1020, 6h=6120, 24h=24480
            // Use generous limits to handle varying data rates
            const limit = chartRange <= 1 ? 2000 : chartRange <= 6 ? 8000 : 30000;

            const params = new URLSearchParams({
                start: startTime.toISOString(),
                end: endTime.toISOString(),
                limit: limit
            });

            const response = await apiFetch('/api/readings?' + params);
            if (!response.ok) throw new Error('Failed to fetch readings');

            const data = await response.json();

            if (spo2Chart && data.readings) {
                spo2Chart.data.datasets[0].data = data.readings.map(r => ({
                    x: new Date(r.timestamp),
                    y: r.spo2
                }));
                spo2Chart.update('none');
            }
        } catch (error) {
            console.error('Error loading chart data:', error);
        }
    }

    // Test alert
    async function testAlert() {
        try {
            elements.testAlertBtn.disabled = true;
            elements.testAlertBtn.textContent = 'Testing...';

            const response = await apiFetch('/api/alerts/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) throw new Error('Failed to trigger test alert');

            const data = await response.json();
            alert(data.message || 'Test alert triggered');
        } catch (error) {
            console.error('Error triggering test alert:', error);
            alert('Failed to trigger test alert');
        } finally {
            elements.testAlertBtn.disabled = false;
            elements.testAlertBtn.textContent = 'Test Alert';
        }
    }

    // Silence alerts
    async function silenceAlerts() {
        try {
            const response = await apiFetch('/api/alerts/silence', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ duration_minutes: 30 })
            });

            if (!response.ok) throw new Error('Failed to silence alerts');

            updateDashboard();
        } catch (error) {
            console.error('Error silencing alerts:', error);
            alert('Failed to silence alerts');
        }
    }

    // Unsilence alerts
    async function unsilenceAlerts() {
        try {
            const response = await apiFetch('/api/alerts/unsilence', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) throw new Error('Failed to unsilence alerts');

            updateDashboard();
        } catch (error) {
            console.error('Error unsilencing alerts:', error);
            alert('Failed to unsilence alerts');
        }
    }

    // Format duration
    function formatDuration(seconds) {
        if (seconds < 60) {
            return seconds + 's';
        } else if (seconds < 3600) {
            return Math.floor(seconds / 60) + 'm';
        } else if (seconds < 86400) {
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            return h + 'h ' + m + 'm';
        } else {
            const d = Math.floor(seconds / 86400);
            const h = Math.floor((seconds % 86400) / 3600);
            return d + 'd ' + h + 'h';
        }
    }

    // Start auto-refresh
    function startAutoRefresh() {
        // Update status every 5 seconds
        updateInterval = setInterval(updateDashboard, 5000);

        // Load chart data initially and every minute
        loadChartData();
        setInterval(loadChartData, 60000);
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
