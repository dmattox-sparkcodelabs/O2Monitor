// O2 Monitor Alert Popup - Global notification for active alerts

(function() {
    'use strict';

    // Configuration
    const POLL_INTERVAL = 10000; // Check for alerts every 10 seconds
    const DISMISSED_STORAGE_KEY = 'o2monitor_dismissed_alerts';

    // State
    let currentAlert = null;
    let dismissedAlerts = new Set();
    let pollTimer = null;

    // DOM Elements
    const popup = document.getElementById('alert-popup');
    const severityEl = document.getElementById('alert-severity');
    const messageEl = document.getElementById('alert-message');
    const timeEl = document.getElementById('alert-time');
    const acknowledgeBtn = document.getElementById('alert-acknowledge');
    const dismissBtn = document.getElementById('alert-dismiss');

    // Initialize
    function init() {
        if (!popup) return; // Not logged in or element missing

        loadDismissedAlerts();
        setupEventListeners();
        checkForAlerts(); // Initial check
        startPolling();
    }

    // Load dismissed alerts from session storage
    function loadDismissedAlerts() {
        try {
            const stored = sessionStorage.getItem(DISMISSED_STORAGE_KEY);
            if (stored) {
                dismissedAlerts = new Set(JSON.parse(stored));
            }
        } catch (e) {
            console.error('Error loading dismissed alerts:', e);
        }
    }

    // Save dismissed alerts to session storage
    function saveDismissedAlerts() {
        try {
            sessionStorage.setItem(DISMISSED_STORAGE_KEY, JSON.stringify([...dismissedAlerts]));
        } catch (e) {
            console.error('Error saving dismissed alerts:', e);
        }
    }

    // Set up event listeners
    function setupEventListeners() {
        if (acknowledgeBtn) {
            acknowledgeBtn.addEventListener('click', acknowledgeAlert);
        }
        if (dismissBtn) {
            dismissBtn.addEventListener('click', dismissAlert);
        }
    }

    // Start polling for alerts
    function startPolling() {
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = setInterval(checkForAlerts, POLL_INTERVAL);
    }

    // Check for active alerts
    async function checkForAlerts() {
        try {
            const response = await fetch('/api/alerts/active', {
                credentials: 'same-origin'
            });

            if (response.status === 401) {
                // Not logged in, stop polling
                if (pollTimer) clearInterval(pollTimer);
                return;
            }

            if (!response.ok) return;

            const data = await response.json();
            const alerts = data.alerts || [];

            // Filter out dismissed alerts and find the most severe
            const activeAlerts = alerts.filter(a => !dismissedAlerts.has(a.id));

            if (activeAlerts.length > 0) {
                // Sort by severity (critical > high > warning > info)
                const severityOrder = { critical: 0, high: 1, warning: 2, info: 3 };
                activeAlerts.sort((a, b) =>
                    (severityOrder[a.severity] || 4) - (severityOrder[b.severity] || 4)
                );
                showAlert(activeAlerts[0]);
            } else {
                hideAlert();
            }
        } catch (error) {
            console.error('Error checking for alerts:', error);
        }
    }

    // Show alert popup
    function showAlert(alert) {
        currentAlert = alert;

        // Update content
        severityEl.textContent = alert.severity.toUpperCase();
        severityEl.className = 'alert-popup-severity severity-' + alert.severity;
        messageEl.textContent = alert.message;
        timeEl.textContent = formatTime(alert.timestamp);

        // Update popup class for severity styling
        popup.className = 'alert-popup severity-' + alert.severity;

        // Show popup
        popup.classList.remove('hidden');
    }

    // Hide alert popup
    function hideAlert() {
        currentAlert = null;
        popup.classList.add('hidden');
    }

    // Acknowledge the current alert
    async function acknowledgeAlert() {
        if (!currentAlert) return;

        const alertId = currentAlert.id;
        acknowledgeBtn.disabled = true;
        acknowledgeBtn.textContent = 'Acknowledging...';

        try {
            const response = await fetch(`/api/alerts/${alertId}/acknowledge`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                throw new Error('Failed to acknowledge alert');
            }

            // Remove from dismissed set (it's now acknowledged in DB)
            dismissedAlerts.delete(alertId);
            saveDismissedAlerts();

            // Hide popup and refresh
            hideAlert();
            checkForAlerts();

        } catch (error) {
            console.error('Error acknowledging alert:', error);
            alert('Failed to acknowledge alert: ' + error.message);
        } finally {
            acknowledgeBtn.disabled = false;
            acknowledgeBtn.textContent = 'Acknowledge';
        }
    }

    // Dismiss alert (hide without acknowledging)
    function dismissAlert() {
        if (!currentAlert) return;

        // Add to dismissed set (just for this session)
        dismissedAlerts.add(currentAlert.id);
        saveDismissedAlerts();

        hideAlert();
    }

    // Format timestamp
    function formatTime(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        });
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
