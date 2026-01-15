// O2 Monitor Settings Page JavaScript

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

    // DOM Elements
    const elements = {
        // Alert table
        alertTable: document.getElementById('alert-table'),

        // Sleep hours
        sleepStart: document.getElementById('sleep-start'),
        sleepEnd: document.getElementById('sleep-end'),

        // AVAPS thresholds
        avapsOn: document.getElementById('avaps-on'),
        avapsWindow: document.getElementById('avaps-window'),

        // Audio
        audioVolume: document.getElementById('audio-volume'),
        volumeDisplay: document.getElementById('volume-display'),

        // PagerDuty
        pagerdutyKey: document.getElementById('pagerduty-key'),

        // Healthchecks
        healthchecksUrl: document.getElementById('healthchecks-url'),

        // Device
        plugIp: document.getElementById('plug-ip'),
        discoverPlugsBtn: document.getElementById('discover-plugs'),
        discoveredDevices: document.getElementById('discovered-devices'),

        // Bluetooth & Timeouts
        adapter1Name: document.getElementById('adapter1-name'),
        adapter2Name: document.getElementById('adapter2-name'),
        readInterval: document.getElementById('read-interval'),
        lateReading: document.getElementById('late-reading'),
        switchTimeout: document.getElementById('switch-timeout'),
        bounceInterval: document.getElementById('bounce-interval'),
        respawnDelay: document.getElementById('respawn-delay'),
        btRestartThreshold: document.getElementById('bt-restart-threshold'),

        // Save
        saveBtn: document.getElementById('save-settings'),
        saveStatus: document.getElementById('save-status')
    };

    // Initialize
    function init() {
        loadCurrentConfig();
        setupEventListeners();
    }

    // Load current configuration
    async function loadCurrentConfig() {
        try {
            const response = await apiFetch('/api/config');
            if (!response.ok) throw new Error('Failed to load config');

            const config = await response.json();
            populateForm(config);
        } catch (error) {
            console.error('Error loading config:', error);
        }
    }

    // Populate form with config values
    function populateForm(config) {
        // Populate alert table
        if (config.alerts) {
            const alertTypes = ['spo2_critical_off_therapy', 'spo2_critical_on_therapy', 'spo2_warning',
                               'hr_high', 'hr_low', 'disconnect',
                               'no_therapy_at_night_info', 'no_therapy_at_night_high',
                               'battery_warning', 'battery_critical', 'adapter_disconnect'];

            alertTypes.forEach(alertType => {
                const alertData = config.alerts[alertType];
                if (alertData) {
                    populateAlertRow(alertType, alertData);
                }
            });

            // Sleep hours
            if (config.alerts.sleep_hours) {
                setValue('sleepStart', config.alerts.sleep_hours.start);
                setValue('sleepEnd', config.alerts.sleep_hours.end);
            }
        }

        // AVAPS thresholds
        if (config.thresholds && config.thresholds.avaps) {
            setValue('avapsOn', config.thresholds.avaps.on_watts);
            setValue('avapsWindow', config.thresholds.avaps.window_minutes);
        }

        // Audio settings
        if (config.alerting && config.alerting.local_audio) {
            setValue('audioVolume', config.alerting.local_audio.volume);
            updateVolumeDisplay();
        }

        // PagerDuty settings
        if (config.alerting && config.alerting.pagerduty) {
            setValue('pagerdutyKey', config.alerting.pagerduty.routing_key);
        }

        // Healthchecks settings
        if (config.alerting && config.alerting.healthchecks) {
            setValue('healthchecksUrl', config.alerting.healthchecks.ping_url);
        }

        // Device settings
        if (config.devices && config.devices.smart_plug) {
            setValue('plugIp', config.devices.smart_plug.ip_address);
        }

        // Bluetooth & Timeouts
        if (config.bluetooth) {
            // Adapter names
            if (config.bluetooth.adapters && config.bluetooth.adapters.length > 0) {
                setValue('adapter1Name', config.bluetooth.adapters[0]?.name);
                if (config.bluetooth.adapters.length > 1) {
                    setValue('adapter2Name', config.bluetooth.adapters[1]?.name);
                }
            }
            setValue('readInterval', config.bluetooth.read_interval_seconds);
            setValue('lateReading', config.bluetooth.late_reading_seconds);
            setValue('switchTimeout', config.bluetooth.switch_timeout_minutes);
            setValue('bounceInterval', config.bluetooth.bounce_interval_minutes);
            setValue('respawnDelay', config.bluetooth.respawn_delay_seconds);
            setValue('btRestartThreshold', config.bluetooth.bt_restart_threshold_minutes);
        }
    }

    // Populate a single alert row in the table
    function populateAlertRow(alertType, data) {
        const row = document.querySelector(`tr[data-alert="${alertType}"]`);
        if (!row) return;

        const enabledCheckbox = row.querySelector('.alert-enabled');
        const thresholdInput = row.querySelector('.alert-threshold');
        const durationInput = row.querySelector('.alert-duration');
        const severitySelect = row.querySelector('.alert-severity');
        const bypassCheckbox = row.querySelector('.alert-bypass-therapy');
        const resendInput = row.querySelector('.alert-resend');

        if (enabledCheckbox && data.enabled !== undefined) {
            enabledCheckbox.checked = data.enabled;
        }
        if (thresholdInput && data.threshold !== undefined) {
            thresholdInput.value = data.threshold;
        }
        if (durationInput && data.duration_seconds !== undefined) {
            // Convert seconds to minutes for display
            durationInput.value = (data.duration_seconds / 60).toFixed(1).replace(/\.0$/, '');
        }
        if (severitySelect && data.severity) {
            severitySelect.value = data.severity;
        }
        if (bypassCheckbox && data.bypass_on_therapy !== undefined) {
            bypassCheckbox.checked = data.bypass_on_therapy;
        }
        if (resendInput && data.resend_interval_seconds !== undefined) {
            // Convert seconds to minutes for display
            resendInput.value = (data.resend_interval_seconds / 60).toFixed(1).replace(/\.0$/, '');
        }
    }

    // Helper to set value if element exists
    function setValue(elementName, value) {
        if (elements[elementName] && value !== undefined && value !== null) {
            elements[elementName].value = value;
        }
    }

    // Set up event listeners
    function setupEventListeners() {
        // Volume slider
        if (elements.audioVolume) {
            elements.audioVolume.addEventListener('input', updateVolumeDisplay);
        }

        // Discover plugs button
        if (elements.discoverPlugsBtn) {
            elements.discoverPlugsBtn.addEventListener('click', discoverPlugs);
        }

        // Save button
        if (elements.saveBtn) {
            elements.saveBtn.addEventListener('click', saveSettings);
        }

        // Test alert buttons (per row)
        document.querySelectorAll('.btn-test').forEach(btn => {
            btn.addEventListener('click', function() {
                const alertType = this.getAttribute('data-alert-type');
                testSpecificAlert(alertType, this);
            });
        });
    }

    // Trigger test alert for a specific alert type
    async function testSpecificAlert(alertType, button) {
        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = '...';

        try {
            const response = await apiFetch('/api/alerts/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ alert_type: alertType })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to trigger test alert');
            }

            const data = await response.json();

            // Brief success indication
            button.textContent = '✓';
            button.classList.add('btn-success');
            setTimeout(() => {
                button.textContent = originalText;
                button.classList.remove('btn-success');
            }, 1500);

        } catch (error) {
            console.error('Error triggering test alert:', error);
            button.textContent = '✗';
            button.classList.add('btn-error');
            setTimeout(() => {
                button.textContent = originalText;
                button.classList.remove('btn-error');
            }, 1500);
            alert('Failed to trigger test alert: ' + error.message);
        } finally {
            button.disabled = false;
        }
    }

    // Update volume display
    function updateVolumeDisplay() {
        if (elements.volumeDisplay && elements.audioVolume) {
            elements.volumeDisplay.textContent = elements.audioVolume.value + '%';
        }
    }

    // Discover smart plugs
    async function discoverPlugs() {
        elements.discoverPlugsBtn.disabled = true;
        elements.discoverPlugsBtn.textContent = 'Discovering...';
        elements.discoveredDevices.innerHTML = '<p>Scanning network...</p>';
        elements.discoveredDevices.style.display = 'block';

        try {
            const response = await apiFetch('/api/devices/discover', {
                method: 'POST'
            });

            if (!response.ok) throw new Error('Discovery failed');

            const data = await response.json();
            displayDiscoveredDevices(data.devices || []);
        } catch (error) {
            console.error('Error discovering devices:', error);
            elements.discoveredDevices.innerHTML = '<p class="error">Discovery failed. Make sure devices are on the same network.</p>';
        } finally {
            elements.discoverPlugsBtn.disabled = false;
            elements.discoverPlugsBtn.textContent = 'Discover Devices';
        }
    }

    // Display discovered devices
    function displayDiscoveredDevices(devices) {
        if (devices.length === 0) {
            elements.discoveredDevices.innerHTML = '<p>No devices found on the network.</p>';
            return;
        }

        elements.discoveredDevices.innerHTML = `
            <p>Found ${devices.length} device(s):</p>
            <ul class="device-list">
                ${devices.map(device => `
                    <li>
                        <strong>${escapeHtml(device.alias || 'Unknown')}</strong>
                        <span class="device-ip">${escapeHtml(device.ip)}</span>
                        <button class="btn btn-sm" onclick="selectDevice('${escapeHtml(device.ip)}')">Select</button>
                    </li>
                `).join('')}
            </ul>
        `;
    }

    // Select a discovered device (global function for onclick)
    window.selectDevice = function(ip) {
        if (elements.plugIp) {
            elements.plugIp.value = ip;
        }
        elements.discoveredDevices.style.display = 'none';
    };

    // Save settings
    async function saveSettings() {
        elements.saveBtn.disabled = true;
        elements.saveStatus.textContent = 'Saving...';
        elements.saveStatus.style.color = '';

        try {
            const config = buildConfigObject();

            const response = await apiFetch('/api/config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to save settings');
            }

            elements.saveStatus.textContent = 'Settings saved successfully';
            elements.saveStatus.style.color = '#4CAF50';

            // Clear status after 3 seconds
            setTimeout(() => {
                elements.saveStatus.textContent = '';
            }, 3000);
        } catch (error) {
            console.error('Error saving settings:', error);
            elements.saveStatus.textContent = 'Error: ' + error.message;
            elements.saveStatus.style.color = '#f44336';
        } finally {
            elements.saveBtn.disabled = false;
        }
    }

    // Build config object from form (table-based)
    function buildConfigObject() {
        const config = {
            alerts: {},
            thresholds: {
                avaps: {
                    on_watts: parseFloat(elements.avapsOn?.value || 30.0),
                    window_minutes: parseInt(elements.avapsWindow?.value || 5)
                }
            },
            alerting: {
                local_audio: {
                    volume: parseInt(elements.audioVolume?.value || 90)
                }
            },
            devices: {
                smart_plug: {
                    ip_address: (elements.plugIp?.value || '').trim()
                }
            },
            bluetooth: {
                adapter_names: [
                    (elements.adapter1Name?.value || 'Adapter 1').trim(),
                    (elements.adapter2Name?.value || 'Adapter 2').trim()
                ],
                read_interval_seconds: parseInt(elements.readInterval?.value || 5),
                late_reading_seconds: parseInt(elements.lateReading?.value || 30),
                switch_timeout_minutes: parseInt(elements.switchTimeout?.value || 5),
                bounce_interval_minutes: parseInt(elements.bounceInterval?.value || 1),
                respawn_delay_seconds: parseInt(elements.respawnDelay?.value || 15),
                bt_restart_threshold_minutes: parseInt(elements.btRestartThreshold?.value || 5)
            }
        };

        // Build alerts from table
        const alertTypes = ['spo2_critical_off_therapy', 'spo2_critical_on_therapy', 'spo2_warning',
                           'hr_high', 'hr_low', 'disconnect',
                           'no_therapy_at_night_info', 'no_therapy_at_night_high',
                           'battery_warning', 'battery_critical', 'adapter_disconnect'];

        alertTypes.forEach(alertType => {
            const alertData = getAlertRowData(alertType);
            if (alertData) {
                config.alerts[alertType] = alertData;
            }
        });

        // Sleep hours
        config.alerts.sleep_hours = {
            start: elements.sleepStart?.value || '22:00',
            end: elements.sleepEnd?.value || '07:00'
        };

        // Only include PagerDuty key if provided
        const pdKey = (elements.pagerdutyKey?.value || '').trim();
        if (pdKey) {
            config.alerting.pagerduty = { routing_key: pdKey };
        }

        // Only include Healthchecks URL if provided
        const hcUrl = (elements.healthchecksUrl?.value || '').trim();
        if (hcUrl) {
            config.alerting.healthchecks = { ping_url: hcUrl };
        }

        return config;
    }

    // Get data from a single alert row
    function getAlertRowData(alertType) {
        const row = document.querySelector(`tr[data-alert="${alertType}"]`);
        if (!row) return null;

        const enabledCheckbox = row.querySelector('.alert-enabled');
        const thresholdInput = row.querySelector('.alert-threshold');
        const durationInput = row.querySelector('.alert-duration');
        const severitySelect = row.querySelector('.alert-severity');
        const bypassCheckbox = row.querySelector('.alert-bypass-therapy');
        const resendInput = row.querySelector('.alert-resend');

        const data = {
            enabled: enabledCheckbox ? enabledCheckbox.checked : true,
            severity: severitySelect ? severitySelect.value : 'warning',
            bypass_on_therapy: bypassCheckbox ? bypassCheckbox.checked : false
        };

        // Only include threshold if input exists
        if (thresholdInput) {
            data.threshold = parseInt(thresholdInput.value);
        }

        // Only include duration if input exists (not N/A)
        // Convert minutes to seconds for storage
        if (durationInput) {
            data.duration_seconds = Math.round(parseFloat(durationInput.value) * 60);
        }

        // Only include resend interval if input exists
        // Convert minutes to seconds for storage
        if (resendInput) {
            data.resend_interval_seconds = Math.round(parseFloat(resendInput.value) * 60);
        }

        return data;
    }

    // Escape HTML to prevent XSS
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
