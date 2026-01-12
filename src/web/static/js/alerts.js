// O2 Monitor Alerts Page JavaScript

(function() {
    'use strict';

    // DOM Elements
    const elements = {
        severityFilter: document.getElementById('severity-filter'),
        typeFilter: document.getElementById('type-filter'),
        timeFilter: document.getElementById('time-filter'),
        refreshBtn: document.getElementById('refresh-alerts'),
        activeAlertsSection: document.getElementById('active-alerts-section'),
        activeAlertsList: document.getElementById('active-alerts-list'),
        alertsTbody: document.getElementById('alerts-tbody'),
        noAlerts: document.getElementById('no-alerts'),
        alertsTable: document.getElementById('alerts-table')
    };

    // Initialize
    function init() {
        setupEventListeners();
        loadAlerts();
    }

    // Set up event listeners
    function setupEventListeners() {
        if (elements.severityFilter) {
            elements.severityFilter.addEventListener('change', loadAlerts);
        }
        if (elements.typeFilter) {
            elements.typeFilter.addEventListener('change', loadAlerts);
        }
        if (elements.timeFilter) {
            elements.timeFilter.addEventListener('change', loadAlerts);
        }
        if (elements.refreshBtn) {
            elements.refreshBtn.addEventListener('click', loadAlerts);
        }
    }

    // Load alerts from API
    async function loadAlerts() {
        try {
            const hours = parseInt(elements.timeFilter.value) || 24;
            const severity = elements.severityFilter.value;
            const type = elements.typeFilter.value;

            const params = new URLSearchParams({
                hours: hours,
                limit: 500
            });

            if (severity) params.append('severity', severity);
            if (type) params.append('type', type);

            const response = await fetch('/api/alerts?' + params, { credentials: 'same-origin' });
            if (!response.ok) throw new Error('Failed to fetch alerts');

            const data = await response.json();
            displayAlerts(data.alerts || []);
            displayActiveAlerts(data.active || []);
        } catch (error) {
            console.error('Error loading alerts:', error);
        }
    }

    // Display active alerts
    function displayActiveAlerts(alerts) {
        if (!alerts || alerts.length === 0) {
            elements.activeAlertsSection.style.display = 'none';
            return;
        }

        elements.activeAlertsSection.style.display = 'block';
        elements.activeAlertsList.innerHTML = alerts.map(alert => {
            const severityClass = getSeverityClass(alert.severity);
            return `
                <div class="alert-item ${severityClass}">
                    <div class="alert-header">
                        <span class="alert-type">${formatAlertType(alert.alert_type)}</span>
                        <span class="alert-time">${formatTime(new Date(alert.timestamp))}</span>
                    </div>
                    <div class="alert-message">${escapeHtml(alert.message)}</div>
                    ${alert.spo2_at_trigger ? `<div class="alert-detail">SpO2: ${alert.spo2_at_trigger}%</div>` : ''}
                    <div class="alert-actions">
                        <button class="btn btn-sm btn-primary" onclick="acknowledgeAlert('${alert.id}')">Acknowledge</button>
                    </div>
                </div>
            `;
        }).join('');
    }

    // Display alerts in table
    function displayAlerts(alerts) {
        if (!alerts || alerts.length === 0) {
            elements.alertsTable.style.display = 'none';
            elements.noAlerts.style.display = 'block';
            return;
        }

        elements.alertsTable.style.display = 'table';
        elements.noAlerts.style.display = 'none';

        elements.alertsTbody.innerHTML = alerts.map(alert => {
            const time = new Date(alert.timestamp);
            const severityClass = getSeverityClass(alert.severity);
            const statusBadge = getStatusBadge(alert);

            return `
                <tr>
                    <td>${formatTime(time)}</td>
                    <td>${formatAlertType(alert.alert_type)}</td>
                    <td><span class="severity-badge ${severityClass}">${alert.severity}</span></td>
                    <td>${escapeHtml(alert.message)}</td>
                    <td>${alert.spo2_at_trigger ? alert.spo2_at_trigger + '%' : '--'}</td>
                    <td>${statusBadge}</td>
                    <td>
                        ${!alert.acknowledged_at ?
                            `<button class="btn btn-sm" onclick="acknowledgeAlert('${alert.id}')">Ack</button>` :
                            ''}
                    </td>
                </tr>
            `;
        }).join('');
    }

    // Get severity CSS class
    function getSeverityClass(severity) {
        const classes = {
            'critical': 'critical',
            'warning': 'warning',
            'info': 'info'
        };
        return classes[severity] || '';
    }

    // Get status badge HTML
    function getStatusBadge(alert) {
        if (alert.resolved_at) {
            return '<span class="status-badge resolved">Resolved</span>';
        } else if (alert.acknowledged_at) {
            return '<span class="status-badge acknowledged">Acknowledged</span>';
        } else {
            return '<span class="status-badge active">Active</span>';
        }
    }

    // Format alert type
    function formatAlertType(type) {
        const types = {
            'spo2_low': 'SpO2 Low',
            'ble_disconnect': 'BLE Disconnect',
            'system_error': 'System Error',
            'test': 'Test Alert'
        };
        return types[type] || type;
    }

    // Format time
    function formatTime(date) {
        return date.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    // Escape HTML to prevent XSS
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Acknowledge alert (global function for onclick)
    window.acknowledgeAlert = async function(alertId) {
        try {
            const response = await fetch(`/api/alerts/${alertId}/acknowledge`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'same-origin'
            });

            if (!response.ok) throw new Error('Failed to acknowledge alert');

            loadAlerts(); // Refresh the list
        } catch (error) {
            console.error('Error acknowledging alert:', error);
            alert('Failed to acknowledge alert');
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
