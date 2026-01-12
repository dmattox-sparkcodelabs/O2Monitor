// O2 Monitor History Page JavaScript

(function() {
    'use strict';

    // State
    let spo2Chart = null;
    let hrChart = null;
    let currentHours = 24;

    // DOM Elements
    const elements = {
        spo2Avg: document.getElementById('spo2-avg'),
        spo2Min: document.getElementById('spo2-min'),
        spo2Max: document.getElementById('spo2-max'),
        readingCount: document.getElementById('reading-count'),
        startDate: document.getElementById('start-date'),
        endDate: document.getElementById('end-date'),
        loadRangeBtn: document.getElementById('load-range'),
        readingsTbody: document.getElementById('readings-tbody')
    };

    // Initialize
    function init() {
        initCharts();
        setupEventListeners();
        setDefaultDates();
        loadData(currentHours);
    }

    // SpO2 threshold levels (configurable)
    const SPO2_ALARM_LEVEL = 90;
    const SPO2_WARNING_LEVEL = 92;

    // Heart rate threshold levels (configurable)
    const HR_LOW_ALARM = 50;      // Severe bradycardia
    const HR_LOW_WARNING = 60;    // Mild bradycardia
    const HR_HIGH_WARNING = 100;  // Tachycardia warning
    const HR_HIGH_ALARM = 120;    // Severe tachycardia

    // Plugin to draw SpO2 threshold background zones
    const spo2ZonesPlugin = {
        id: 'spo2Zones',
        beforeDraw: function(chart) {
            const ctx = chart.ctx;
            const chartArea = chart.chartArea;
            const yScale = chart.scales.y;

            if (!chartArea) return;

            const yMin = yScale.min;
            const alarmY = yScale.getPixelForValue(SPO2_ALARM_LEVEL);
            const warningY = yScale.getPixelForValue(SPO2_WARNING_LEVEL);
            const bottomY = yScale.getPixelForValue(yMin);

            ctx.save();

            // Red zone: below alarm level (90%)
            ctx.fillStyle = 'rgba(244, 67, 54, 0.2)';
            ctx.fillRect(chartArea.left, alarmY, chartArea.right - chartArea.left, bottomY - alarmY);

            // Yellow zone: between alarm (90%) and warning (92%)
            ctx.fillStyle = 'rgba(255, 152, 0, 0.2)';
            ctx.fillRect(chartArea.left, warningY, chartArea.right - chartArea.left, alarmY - warningY);

            ctx.restore();
        }
    };

    // Plugin to draw HR threshold background zones
    const hrZonesPlugin = {
        id: 'hrZones',
        beforeDraw: function(chart) {
            const ctx = chart.ctx;
            const chartArea = chart.chartArea;
            const yScale = chart.scales.y;

            if (!chartArea) return;

            const yMin = yScale.min;
            const yMax = yScale.max;
            const lowAlarmY = yScale.getPixelForValue(HR_LOW_ALARM);
            const lowWarningY = yScale.getPixelForValue(HR_LOW_WARNING);
            const highWarningY = yScale.getPixelForValue(HR_HIGH_WARNING);
            const highAlarmY = yScale.getPixelForValue(HR_HIGH_ALARM);
            const bottomY = yScale.getPixelForValue(yMin);
            const topY = yScale.getPixelForValue(yMax);

            ctx.save();

            // Red zone: below low alarm (severe bradycardia <50)
            ctx.fillStyle = 'rgba(244, 67, 54, 0.2)';
            ctx.fillRect(chartArea.left, lowAlarmY, chartArea.right - chartArea.left, bottomY - lowAlarmY);

            // Yellow zone: between low alarm and low warning (mild bradycardia 50-60)
            ctx.fillStyle = 'rgba(255, 152, 0, 0.2)';
            ctx.fillRect(chartArea.left, lowWarningY, chartArea.right - chartArea.left, lowAlarmY - lowWarningY);

            // Yellow zone: between high warning and high alarm (tachycardia 100-120)
            ctx.fillRect(chartArea.left, highAlarmY, chartArea.right - chartArea.left, highWarningY - highAlarmY);

            // Red zone: above high alarm (severe tachycardia >120)
            ctx.fillStyle = 'rgba(244, 67, 54, 0.2)';
            ctx.fillRect(chartArea.left, topY, chartArea.right - chartArea.left, highAlarmY - topY);

            ctx.restore();
        }
    };

    // Initialize charts
    function initCharts() {
        // SpO2 Chart
        const spo2Ctx = document.getElementById('spo2-history-chart');
        if (spo2Ctx) {
            spo2Chart = new Chart(spo2Ctx, {
                type: 'line',
                data: {
                    datasets: [{
                        label: 'SpO2 %',
                        data: [],
                        borderColor: '#2196F3',
                        backgroundColor: 'rgba(33, 150, 243, 0.1)',
                        fill: true,
                        tension: 0.2,
                        pointRadius: 1,
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
                                unit: 'hour',
                                displayFormats: {
                                    hour: 'MMM d, h:mm a'
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
                plugins: [spo2ZonesPlugin]
            });
        }

        // Heart Rate Chart
        const hrCtx = document.getElementById('hr-history-chart');
        if (hrCtx) {
            hrChart = new Chart(hrCtx, {
                type: 'line',
                data: {
                    datasets: [{
                        label: 'Heart Rate BPM',
                        data: [],
                        borderColor: '#f44336',
                        backgroundColor: 'rgba(244, 67, 54, 0.1)',
                        fill: true,
                        tension: 0.2,
                        pointRadius: 1,
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
                                unit: 'hour',
                                displayFormats: {
                                    hour: 'MMM d, h:mm a'
                                }
                            },
                            title: {
                                display: true,
                                text: 'Time'
                            }
                        },
                        y: {
                            min: 40,
                            max: 140,
                            title: {
                                display: true,
                                text: 'Heart Rate BPM'
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
                plugins: [hrZonesPlugin]
            });
        }
    }

    // Set up event listeners
    function setupEventListeners() {
        // Preset buttons
        document.querySelectorAll('.date-preset-buttons .btn').forEach(btn => {
            btn.addEventListener('click', function() {
                document.querySelectorAll('.date-preset-buttons .btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                currentHours = parseInt(this.dataset.hours);
                loadData(currentHours);
            });
        });

        // Custom range button
        if (elements.loadRangeBtn) {
            elements.loadRangeBtn.addEventListener('click', loadCustomRange);
        }
    }

    // Set default dates
    function setDefaultDates() {
        const now = new Date();
        const yesterday = new Date(now - 24 * 60 * 60 * 1000);

        if (elements.endDate) {
            elements.endDate.value = formatDateTimeLocal(now);
        }
        if (elements.startDate) {
            elements.startDate.value = formatDateTimeLocal(yesterday);
        }
    }

    // Format date for datetime-local input
    function formatDateTimeLocal(date) {
        const d = new Date(date);
        d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
        return d.toISOString().slice(0, 16);
    }

    // Load data for specified hours
    async function loadData(hours) {
        const endTime = new Date();
        const startTime = new Date(endTime - hours * 60 * 60 * 1000);
        await fetchAndDisplayData(startTime, endTime);
    }

    // Load custom date range
    async function loadCustomRange() {
        const startTime = new Date(elements.startDate.value);
        const endTime = new Date(elements.endDate.value);

        if (isNaN(startTime.getTime()) || isNaN(endTime.getTime())) {
            alert('Please select valid start and end dates');
            return;
        }

        if (startTime >= endTime) {
            alert('Start date must be before end date');
            return;
        }

        // Remove active from preset buttons
        document.querySelectorAll('.date-preset-buttons .btn').forEach(b => b.classList.remove('active'));

        await fetchAndDisplayData(startTime, endTime);
    }

    // Fetch and display data
    async function fetchAndDisplayData(startTime, endTime) {
        try {
            const params = new URLSearchParams({
                start: startTime.toISOString(),
                end: endTime.toISOString(),
                limit: 5000
            });

            const response = await fetch('/api/readings?' + params, { credentials: 'same-origin' });
            if (!response.ok) throw new Error('Failed to fetch readings');

            const data = await response.json();
            updateStats(data);
            updateCharts(data.readings || []);
            updateTable(data.readings || []);
        } catch (error) {
            console.error('Error loading history data:', error);
        }
    }

    // Update statistics
    function updateStats(data) {
        if (data.stats) {
            elements.spo2Avg.textContent = data.stats.spo2_avg ? data.stats.spo2_avg.toFixed(1) : '--';
            elements.spo2Min.textContent = data.stats.spo2_min || '--';
            elements.spo2Max.textContent = data.stats.spo2_max || '--';
        } else {
            elements.spo2Avg.textContent = '--';
            elements.spo2Min.textContent = '--';
            elements.spo2Max.textContent = '--';
        }

        elements.readingCount.textContent = data.readings ? data.readings.length : 0;
    }

    // Update charts
    function updateCharts(readings) {
        if (spo2Chart) {
            spo2Chart.data.datasets[0].data = readings.map(r => ({
                x: new Date(r.timestamp),
                y: r.spo2
            }));
            spo2Chart.update('none');
        }

        if (hrChart) {
            hrChart.data.datasets[0].data = readings.map(r => ({
                x: new Date(r.timestamp),
                y: r.heart_rate
            }));
            hrChart.update('none');
        }
    }

    // Update data table
    function updateTable(readings) {
        if (!elements.readingsTbody) return;

        // Show last 100 readings in reverse order (most recent first)
        const recentReadings = readings.slice(-100).reverse();

        elements.readingsTbody.innerHTML = recentReadings.map(r => {
            const time = new Date(r.timestamp);
            const spo2Class = r.spo2 < 90 ? 'style="color: #f44336; font-weight: bold;"' : '';

            return `
                <tr>
                    <td>${formatTime(time)}</td>
                    <td ${spo2Class}>${r.spo2}%</td>
                    <td>${r.heart_rate} BPM</td>
                    <td>${r.avaps_on ? 'ON' : 'OFF'}</td>
                    <td>${r.is_valid ? 'Yes' : 'No'}</td>
                </tr>
            `;
        }).join('');

        if (recentReadings.length === 0) {
            elements.readingsTbody.innerHTML = `
                <tr>
                    <td colspan="5" class="no-data">No readings found for the selected time period.</td>
                </tr>
            `;
        }
    }

    // Format time
    function formatTime(date) {
        return date.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            second: '2-digit',
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
