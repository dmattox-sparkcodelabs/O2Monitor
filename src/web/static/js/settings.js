// O2 Monitor Settings Page JavaScript

(function() {
    'use strict';

    // DOM Elements
    const elements = {
        // SpO2 thresholds
        spo2Alarm: document.getElementById('spo2-alarm'),
        spo2Duration: document.getElementById('spo2-duration'),
        spo2Warning: document.getElementById('spo2-warning'),
        // AVAPS thresholds
        avapsOn: document.getElementById('avaps-on'),
        avapsOff: document.getElementById('avaps-off'),
        // Audio
        audioVolume: document.getElementById('audio-volume'),
        volumeDisplay: document.getElementById('volume-display'),
        // PagerDuty
        pagerdutyKey: document.getElementById('pagerduty-key'),
        pagerdutyStatus: document.getElementById('pagerduty-status'),
        // Healthchecks
        healthchecksUrl: document.getElementById('healthchecks-url'),
        healthchecksStatus: document.getElementById('healthchecks-status'),
        // Device
        plugIp: document.getElementById('plug-ip'),
        discoverPlugsBtn: document.getElementById('discover-plugs'),
        discoveredDevices: document.getElementById('discovered-devices'),
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
            const response = await fetch('/api/config', { credentials: 'same-origin' });
            if (!response.ok) throw new Error('Failed to load config');

            const config = await response.json();
            populateForm(config);
        } catch (error) {
            console.error('Error loading config:', error);
        }
    }

    // Populate form with config values
    function populateForm(config) {
        // SpO2 thresholds
        if (config.thresholds && config.thresholds.spo2) {
            if (elements.spo2Alarm) elements.spo2Alarm.value = config.thresholds.spo2.alarm_level || 90;
            if (elements.spo2Duration) elements.spo2Duration.value = config.thresholds.spo2.alarm_duration_seconds || 30;
            if (elements.spo2Warning) elements.spo2Warning.value = config.thresholds.spo2.warning_level || 92;
        }

        // AVAPS thresholds
        if (config.thresholds && config.thresholds.avaps) {
            if (elements.avapsOn) elements.avapsOn.value = config.thresholds.avaps.on_watts || 3.0;
            if (elements.avapsOff) elements.avapsOff.value = config.thresholds.avaps.off_watts || 2.0;
        }

        // Audio settings
        if (config.alerting && config.alerting.local_audio) {
            if (elements.audioVolume) {
                elements.audioVolume.value = config.alerting.local_audio.volume || 90;
                updateVolumeDisplay();
            }
        }

        // Device settings
        if (config.devices && config.devices.smart_plug) {
            if (elements.plugIp) elements.plugIp.value = config.devices.smart_plug.ip_address || '';
        }

        // Update integration statuses
        updateIntegrationStatus('pagerduty', config.alerting?.pagerduty?.routing_key);
        updateIntegrationStatus('healthchecks', config.alerting?.healthchecks?.ping_url);
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
    }

    // Update volume display
    function updateVolumeDisplay() {
        if (elements.volumeDisplay && elements.audioVolume) {
            elements.volumeDisplay.textContent = elements.audioVolume.value + '%';
        }
    }

    // Update integration status indicator
    function updateIntegrationStatus(integration, hasConfig) {
        const statusEl = document.getElementById(integration + '-status');
        const indicatorEl = statusEl?.previousElementSibling;

        if (statusEl) {
            statusEl.textContent = hasConfig ? 'Configured' : 'Not Configured';
        }
        if (indicatorEl && indicatorEl.classList.contains('status-indicator')) {
            indicatorEl.classList.remove('connected', 'disconnected');
            indicatorEl.classList.add(hasConfig ? 'connected' : 'disconnected');
        }
    }

    // Discover smart plugs
    async function discoverPlugs() {
        elements.discoverPlugsBtn.disabled = true;
        elements.discoverPlugsBtn.textContent = 'Discovering...';
        elements.discoveredDevices.innerHTML = '<p>Scanning network...</p>';
        elements.discoveredDevices.style.display = 'block';

        try {
            const response = await fetch('/api/devices/discover', {
                credentials: 'same-origin',
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

            const response = await fetch('/api/config', {
                credentials: 'same-origin',
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to save settings');
            }

            elements.saveStatus.textContent = 'Settings saved successfully';
            elements.saveStatus.style.color = '#4CAF50';

            // Update integration statuses
            updateIntegrationStatus('pagerduty', config.alerting?.pagerduty?.routing_key);
            updateIntegrationStatus('healthchecks', config.alerting?.healthchecks?.ping_url);

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

    // Build config object from form
    function buildConfigObject() {
        const config = {
            thresholds: {
                spo2: {
                    alarm_level: parseInt(elements.spo2Alarm.value),
                    alarm_duration_seconds: parseInt(elements.spo2Duration.value),
                    warning_level: parseInt(elements.spo2Warning.value)
                },
                avaps: {
                    on_watts: parseFloat(elements.avapsOn.value),
                    off_watts: parseFloat(elements.avapsOff.value)
                }
            },
            alerting: {
                local_audio: {
                    volume: parseInt(elements.audioVolume.value)
                }
            },
            devices: {
                smart_plug: {
                    ip_address: elements.plugIp.value.trim()
                }
            }
        };

        // Only include PagerDuty key if provided
        const pdKey = elements.pagerdutyKey.value.trim();
        if (pdKey) {
            config.alerting.pagerduty = {
                routing_key: pdKey
            };
        }

        // Only include Healthchecks URL if provided
        const hcUrl = elements.healthchecksUrl.value.trim();
        if (hcUrl) {
            config.alerting.healthchecks = {
                ping_url: hcUrl
            };
        }

        return config;
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
