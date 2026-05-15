(function () {
    'use strict';

    // Register the zoom plugin (loaded from CDN)
    if (window.Chart && window['chartjs-plugin-zoom']) {
        Chart.register(window['chartjs-plugin-zoom']);
    }

    // Plugin: rewrite the date row on the x-axis after autoSkip has filtered
    // ticks down to the visible set. The tick.callback can't see which ticks
    // will be hidden, so closure-based attribution there gets "consumed" by
    // ticks that end up auto-skipped — leaving the first VISIBLE tick of a
    // new day with no date below it.
    const dateRowPlugin = {
        id: 'dateRowPlugin',
        afterUpdate(chart) {
            const xScale = chart.scales && chart.scales.x;
            if (!xScale || !xScale.ticks) return;
            const pad = n => String(n).padStart(2, '0');
            let lastDate = null;
            for (const tick of xScale.ticks) {
                if (!Array.isArray(tick.label) || tick.label.length < 2) continue;
                const d = new Date(tick.value);
                const dateStr =
                    d.getFullYear() + '-' +
                    pad(d.getMonth() + 1) + '-' +
                    pad(d.getDate());
                const showDate = lastDate !== dateStr;
                tick.label[1] = showDate ? dateStr : ' ';
                if (showDate) lastDate = dateStr;
            }
        },
    };
    if (window.Chart) Chart.register(dateRowPlugin);

    const nightSelect = document.getElementById('night-select');
    const showHrToggle = document.getElementById('show-hr');
    const content = document.getElementById('content');
    let chart = null;
    // Bounds of the loaded night's data (ms epoch)
    let dataMin = null;
    let dataMax = null;
    // Currently selected window size in hours, or null for "fit all"
    let windowHours = null;

    // Keep the scrollbar thumb sized correctly when the viewport resizes
    window.addEventListener('resize', () => {
        if (chart) placeThumb();
    });

    function fmtDuration(seconds) {
        if (!seconds) return '0';
        const s = Math.round(seconds);
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        if (h > 0) return `${h}h ${m}m`;
        return `${m}m`;
    }

    function classifyMin(min) {
        if (min == null) return '';
        if (min < 85) return 'stat-bad';
        if (min < 90) return 'stat-warn';
        return 'stat-good';
    }

    function classifyPct(pct) {
        if (pct >= 5) return 'stat-bad';
        if (pct >= 1) return 'stat-warn';
        return 'stat-good';
    }

    function classifyOdi(odi) {
        if (odi >= 30) return 'stat-bad';
        if (odi >= 15) return 'stat-warn';
        if (odi >= 5) return 'stat-warn';
        return 'stat-good';
    }

    function renderEmpty(msg) {
        content.innerHTML = `<div class="empty">${msg}</div>`;
    }

    function renderNight(data) {
        const s = data.summary;
        if (!s.reading_count) {
            renderEmpty('No readings for this night.');
            return;
        }

        const statsHtml = `
            <div class="stats-grid">
                <div class="stat">
                    <div class="stat-label">Duration</div>
                    <div class="stat-value">${fmtDuration(s.duration_seconds)}</div>
                </div>
                <div class="stat">
                    <div class="stat-label">Mean SpO2</div>
                    <div class="stat-value">${s.mean_spo2}<span class="stat-unit">%</span></div>
                </div>
                <div class="stat">
                    <div class="stat-label">Min SpO2</div>
                    <div class="stat-value ${classifyMin(s.min_spo2)}">${s.min_spo2}<span class="stat-unit">%</span></div>
                </div>
                <div class="stat">
                    <div class="stat-label">Time &lt; 90%</div>
                    <div class="stat-value ${classifyPct(s.pct_below_90)}">${fmtDuration(s.time_below_90_seconds)}<span class="stat-unit">(${s.pct_below_90}%)</span></div>
                </div>
                <div class="stat">
                    <div class="stat-label">Time &lt; 88%</div>
                    <div class="stat-value ${classifyPct(s.pct_below_88)}">${fmtDuration(s.time_below_88_seconds)}<span class="stat-unit">(${s.pct_below_88}%)</span></div>
                </div>
                <div class="stat">
                    <div class="stat-label">ODI3</div>
                    <div class="stat-value ${classifyOdi(s.odi3_per_hour)}">${s.odi3_per_hour}<span class="stat-unit">/hr</span></div>
                </div>
                <div class="stat">
                    <div class="stat-label">ODI4</div>
                    <div class="stat-value ${classifyOdi(s.odi4_per_hour)}">${s.odi4_per_hour}<span class="stat-unit">/hr</span></div>
                </div>
                <div class="stat">
                    <div class="stat-label">Mean HR</div>
                    <div class="stat-value">${s.mean_hr ?? '--'}<span class="stat-unit">bpm</span></div>
                </div>
            </div>
            <div class="chart-wrap"><canvas id="spo2-chart"></canvas></div>
            <div class="scrubber-wrap">
                <div class="scrubber-row">
                    <span class="scrubber-time" id="window-start">--</span>
                    <div class="scrollbar" id="scrollbar">
                        <div class="scrollbar-thumb" id="scrollbar-thumb"></div>
                    </div>
                    <span class="scrubber-time right" id="window-end">--</span>
                </div>
            </div>
        `;
        content.innerHTML = statsHtml;

        renderChart(data.readings);
        wireZoomControls();
    }

    function wireZoomControls() {
        document.querySelectorAll('.zoom-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const v = btn.getAttribute('data-hours');
                setActiveZoomBtn(btn);
                if (v === 'all') {
                    windowHours = null;
                    applyAllRange();
                } else {
                    windowHours = parseFloat(v);
                    // Snap window to the latest data (right-aligned)
                    applyWindowEnd(dataMax);
                }
                updateScrubberFromChart();
                updateWindowLabels();
            });
        });
        wireScrollbar();
    }

    function wireScrollbar() {
        const track = document.getElementById('scrollbar');
        const thumb = document.getElementById('scrollbar-thumb');
        if (!track || !thumb) return;

        let dragging = false;
        let dragStartX = 0;
        let dragStartLeft = 0;

        function trackWidth() { return track.clientWidth; }
        function thumbWidth() { return thumb.offsetWidth; }

        function panToThumbLeftPx(leftPx) {
            // Convert thumb left in px to chart x.min
            if (dataMin == null || dataMax == null || !chart) return;
            const xmin = chart.options.scales.x.min;
            const xmax = chart.options.scales.x.max;
            const spanMs = xmax - xmin;
            if (spanMs >= dataMax - dataMin) return; // window covers all data
            const trackPx = trackWidth();
            const thumbPx = thumbWidth();
            const availablePx = Math.max(1, trackPx - thumbPx);
            const clampedLeft = Math.max(0, Math.min(availablePx, leftPx));
            const pct = clampedLeft / availablePx;
            const newMin = dataMin + pct * ((dataMax - dataMin) - spanMs);
            const newMax = newMin + spanMs;
            chart.options.scales.x.min = newMin;
            chart.options.scales.x.max = newMax;
            chart.update('none');
            updateWindowLabels();
            placeThumb();  // re-sync in case of clamping
        }

        thumb.addEventListener('mousedown', e => {
            e.preventDefault();
            dragging = true;
            dragStartX = e.clientX;
            dragStartLeft = parseFloat(thumb.style.left || '0');
            thumb.classList.add('dragging');
        });

        // Clicking on the track (but not on the thumb) jumps the thumb so its
        // center lands at the click position.
        track.addEventListener('mousedown', e => {
            if (e.target === thumb) return;
            const rect = track.getBoundingClientRect();
            const clickX = e.clientX - rect.left;
            const desiredLeft = clickX - thumbWidth() / 2;
            panToThumbLeftPx(desiredLeft);
        });

        window.addEventListener('mousemove', e => {
            if (!dragging) return;
            const dx = e.clientX - dragStartX;
            panToThumbLeftPx(dragStartLeft + dx);
        });

        window.addEventListener('mouseup', () => {
            if (!dragging) return;
            dragging = false;
            thumb.classList.remove('dragging');
        });
    }

    function placeThumb() {
        const track = document.getElementById('scrollbar');
        const thumb = document.getElementById('scrollbar-thumb');
        if (!track || !thumb || dataMin == null || dataMax == null || !chart) return;
        const trackPx = track.clientWidth;
        if (trackPx <= 0) return;
        const xmin = chart.options.scales.x.min;
        const xmax = chart.options.scales.x.max;
        const spanMs = xmax - xmin;
        const totalSpan = dataMax - dataMin;
        if (totalSpan <= 0) {
            thumb.style.width = '100%';
            thumb.style.left = '0px';
            return;
        }
        // Thumb size = (current window / total data) — clamped to a minimum
        // visible width so deep zooms don't disappear.
        const widthPct = Math.min(1, spanMs / totalSpan);
        const minThumbPx = 20;
        let thumbPx = Math.max(minThumbPx, widthPct * trackPx);
        thumbPx = Math.min(thumbPx, trackPx);
        thumb.style.width = thumbPx + 'px';

        // Thumb position
        if (spanMs >= totalSpan) {
            thumb.style.left = '0px';
        } else {
            const available = Math.max(1, trackPx - thumbPx);
            const startPct = (xmin - dataMin) / (totalSpan - spanMs);
            const clamped = Math.max(0, Math.min(1, startPct));
            thumb.style.left = (clamped * available) + 'px';
        }
    }

    function setActiveZoomBtn(activeBtn) {
        document.querySelectorAll('.zoom-btn').forEach(b => b.classList.toggle('active', b === activeBtn));
    }

    function applyAllRange() {
        if (!chart || dataMin == null || dataMax == null) return;
        chart.options.scales.x.min = dataMin;
        chart.options.scales.x.max = dataMax;
        chart.update('none');
    }

    function applyWindowEnd(endMs) {
        if (!chart || windowHours == null) return;
        const spanMs = windowHours * 3600 * 1000;
        let max = Math.min(endMs, dataMax);
        let min = max - spanMs;
        if (min < dataMin) {
            min = dataMin;
            max = Math.min(dataMin + spanMs, dataMax);
        }
        chart.options.scales.x.min = min;
        chart.options.scales.x.max = max;
        chart.update('none');
    }

    // Keep the scrollbar thumb in sync with the chart's x range.
    function updateScrubberFromChart() {
        placeThumb();
    }

    function updateWindowLabels() {
        const startEl = document.getElementById('window-start');
        const endEl = document.getElementById('window-end');
        if (!chart || !startEl || !endEl) return;
        const xmin = chart.options.scales.x.min;
        const xmax = chart.options.scales.x.max;
        startEl.textContent = formatTimestamp(xmin);
        endEl.textContent = formatTimestamp(xmax);
    }

    function formatTimestamp(ms) {
        if (ms == null) return '--';
        const d = new Date(ms);
        const pad = n => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }

    function renderChart(readings) {
        // Compute ms-epoch bounds so the zoom buttons and scrubber have stable references
        if (readings.length) {
            dataMin = new Date(readings[0].timestamp).getTime();
            dataMax = new Date(readings[readings.length - 1].timestamp).getTime();
        } else {
            dataMin = dataMax = null;
        }
        // Default to "All" on every load so a new night opens at full extent
        windowHours = null;

        // Per-render state to dedupe duplicate same-minute ticks that Chart.js
        // sometimes emits at day boundaries (a "major" tick alongside a regular
        // minute tick — both labeled e.g. "00:00"). Date-row assignment happens
        // in dateRowPlugin.afterUpdate after autoSkip has run.
        let __lastMinuteKey = null;

        const spo2Points = readings.map(r => ({ x: r.timestamp, y: r.spo2 }));
        const hrPoints = readings.map(r => ({ x: r.timestamp, y: r.heart_rate }));

        const datasets = [
            {
                label: 'SpO2',
                data: spo2Points,
                borderColor: '#4dabf7',
                backgroundColor: 'rgba(77, 171, 247, 0.1)',
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.1,
                yAxisID: 'y-spo2',
            },
        ];

        if (showHrToggle.checked) {
            datasets.push({
                label: 'Heart Rate',
                data: hrPoints,
                borderColor: '#ff6b6b',
                backgroundColor: 'rgba(255, 107, 107, 0.1)',
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.1,
                yAxisID: 'y-hr',
            });
        }

        const ctx = document.getElementById('spo2-chart');
        if (chart) chart.destroy();

        chart = new Chart(ctx, {
            type: 'line',
            data: { datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            // Force HH:mm at every unit — the date appears only on
                            // the first tick and day-change ticks (see callback below).
                            tooltipFormat: 'yyyy-MM-dd HH:mm:ss',
                            displayFormats: {
                                millisecond: 'HH:mm',
                                second: 'HH:mm',
                                minute: 'HH:mm',
                                hour: 'HH:mm',
                                day: 'HH:mm',
                                week: 'HH:mm',
                                month: 'HH:mm',
                                quarter: 'HH:mm',
                                year: 'HH:mm',
                            },
                        },
                        title: { display: true, text: 'Time', color: '#8a96a7' },
                        ticks: {
                            color: '#8a96a7',
                            maxRotation: 0,
                            autoSkip: true,
                            autoSkipPadding: 20,
                            // Always return a two-line label so every tick has the
                            // same height. Only the first tick and day-change ticks
                            // show the date; others get a non-breaking space so the
                            // row keeps its reserved height (no vertical jumping
                            // when panning brings a new tick into view).
                            callback: function (value, index, ticksArr) {
                                const ts = (ticksArr[index] && ticksArr[index].value) != null
                                    ? ticksArr[index].value
                                    : value;
                                const d = new Date(ts);
                                const pad = n => String(n).padStart(2, '0');
                                // Format time directly — getLabelForValue uses
                                // displayFormats.datetime which has a verbose
                                // locale default ("May 14, 2026, 10:43:12 PM").
                                const timeLabel = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
                                // Reset dedupe state at the start of each render pass
                                if (index === 0) __lastMinuteKey = null;
                                // Suppress duplicate ticks within the same minute
                                // (Chart.js emits major-tick + regular-tick at day
                                // boundaries; both end up labeled "00:00").
                                const minuteKey =
                                    d.getFullYear() + '-' +
                                    pad(d.getMonth() + 1) + '-' +
                                    pad(d.getDate()) + 'T' + timeLabel;
                                if (minuteKey === __lastMinuteKey) {
                                    return null;
                                }
                                __lastMinuteKey = minuteKey;
                                // Always emit a 2-line label so every tick reserves the
                                // same vertical space. The dateRowPlugin replaces the
                                // second line with the actual date after autoSkip, so
                                // attribution is based on the VISIBLE tick set.
                                return [timeLabel,' '];
                            },
                        },
                        grid: { color: 'rgba(138, 150, 167, 0.1)' },
                    },
                    'y-spo2': {
                        position: 'left',
                        min: 70, max: 100,
                        title: { display: true, text: 'SpO2 (%)', color: '#4dabf7' },
                        ticks: { color: '#4dabf7', callback: v => v + '%' },
                        grid: { color: 'rgba(138, 150, 167, 0.1)' },
                    },
                    'y-hr': {
                        position: 'right',
                        display: showHrToggle.checked,
                        min: 40, max: 140,
                        title: { display: true, text: 'Heart Rate (bpm)', color: '#ff6b6b' },
                        ticks: { color: '#ff6b6b', callback: v => v + ' bpm' },
                        grid: { drawOnChartArea: false },
                    },
                },
                plugins: {
                    legend: { labels: { color: '#e4e6eb' } },
                    tooltip: { mode: 'index', intersect: false },
                    annotation: {},
                    zoom: {
                        pan: {
                            enabled: true,
                            mode: 'x',
                            onPanComplete: () => {
                                // User dragged the chart — figure out the window size
                                // they ended up with and reflect it in the toolbar/scrubber.
                                if (!chart) return;
                                const xmin = chart.options.scales.x.min;
                                const xmax = chart.options.scales.x.max;
                                windowHours = (xmax - xmin) / 3600000;
                                syncToolbarFromWindow();
                                updateScrubberFromChart();
                                updateWindowLabels();
                            },
                        },
                        zoom: {
                            wheel: { enabled: true },
                            pinch: { enabled: true },
                            mode: 'x',
                            onZoomComplete: () => {
                                if (!chart) return;
                                const xmin = chart.options.scales.x.min;
                                const xmax = chart.options.scales.x.max;
                                windowHours = (xmax - xmin) / 3600000;
                                syncToolbarFromWindow();
                                updateScrubberFromChart();
                                updateWindowLabels();
                            },
                        },
                        limits: {
                            x: { min: 'original', max: 'original' },
                        },
                    },
                },
            },
        });

        // Apply initial range + sync UI
        applyAllRange();
        updateScrubberFromChart();
        updateWindowLabels();
    }

    function syncToolbarFromWindow() {
        // Snap to a preset button if the window is close to one of them
        const presets = [0.25, 1, 6, 12, 24];
        let match = null;
        for (const h of presets) {
            if (Math.abs(windowHours - h) / h < 0.1) { match = h; break; }
        }
        document.querySelectorAll('.zoom-btn').forEach(b => {
            const v = b.getAttribute('data-hours');
            const isMatch = (match != null && v === String(match));
            b.classList.toggle('active', isMatch);
        });
        // If no preset matched, also clear "All" highlight (user is in a custom zoom)
        if (match == null && windowHours != null) {
            const allBtn = document.querySelector('.zoom-btn[data-hours="all"]');
            if (allBtn) allBtn.classList.remove('active');
        }
    }

    async function loadNight(night) {
        renderEmpty('Loading...');
        try {
            const res = await fetch(`/api/night/${night}`);
            const data = await res.json();
            renderNight(data);
        } catch (e) {
            renderEmpty('Failed to load night data.');
            console.error(e);
        }
    }

    async function init() {
        try {
            const res = await fetch('/api/nights');
            const data = await res.json();
            const nights = data.nights || [];
            if (!nights.length) {
                renderEmpty('No data yet. Run the capture script and let it record overnight.');
                return;
            }
            nightSelect.innerHTML = nights.map(n =>
                `<option value="${n.night_date}">${n.night_date} (${n.reading_count} readings)</option>`
            ).join('');
            nightSelect.addEventListener('change', () => loadNight(nightSelect.value));
            showHrToggle.addEventListener('change', () => loadNight(nightSelect.value));
            await loadNight(nights[0].night_date);
        } catch (e) {
            renderEmpty('Failed to load nights list.');
            console.error(e);
        }
    }

    init();
})();
