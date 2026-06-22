const API      = 'http://localhost:5000';
const PAGE_SIZE = 50;

const PAYMENT_LABELS = {
    0: 'Flex Fare', 1: 'Credit Card', 2: 'Cash',
    3: 'No Charge', 4: 'Dispute', 5: 'Unknown', 6: 'Voided'
};

let mapInitialized = false;
let currentPage    = 0;
let currentTrips   = [];
let currentSort    = { column: 'pickup_datetime', direction: 'asc' };
let debounceTimer  = null;

/* ── API helper ── */
async function get(path) {
    const res = await fetch(API + path);
    if (!res.ok) throw new Error(res.status);
    return res.json();
}

/* ── Global filter state ── */
function getGlobalFilters() {
    return {
        borough:    document.getElementById('g-borough').value,
        time_of_day: document.getElementById('g-timeofday').value,
    };
}

function buildFilterQuery(extra = {}) {
    const f = { ...getGlobalFilters(), ...extra };
    const params = [];
    if (f.borough)     params.push(`borough=${encodeURIComponent(f.borough)}`);
    if (f.time_of_day) params.push(`time_of_day=${encodeURIComponent(f.time_of_day)}`);
    if (f.hour !== undefined && f.hour !== '') params.push(`hour=${f.hour}`);
    if (f.offset !== undefined) params.push(`offset=${f.offset}`);
    if (f.limit  !== undefined) params.push(`limit=${f.limit}`);
    return params.length ? '?' + params.join('&') : '';
}

async function applyGlobalFilters() {
    const borough    = document.getElementById('g-borough').value;
    const timeOfDay  = document.getElementById('g-timeofday').value;

    const btn = document.getElementById('apply-btn');
    btn.textContent = 'Applying…';
    btn.disabled    = true;

    const label = buildFilterLabel();

    if (label) {
        document.getElementById('filter-status').style.display = 'block';
        document.getElementById('filter-status-text').textContent = `Showing data for: ${label}`;
        updateSubtitles(label);
    } else {
        document.getElementById('filter-status').style.display = 'none';
        resetSubtitles();
    }

    currentPage = 0;

    await Promise.all([
        loadKPIs(),
        loadWhen(),
        reloadBoroughDoughnut(),
        reloadWhereFiltered(),
        loadHowMuch(),
    ]);

    loadTrips();

    btn.textContent = 'Apply Filters';
    btn.disabled    = false;
}

async function resetGlobalFilters() {
    document.getElementById('g-borough').value   = '';
    document.getElementById('g-timeofday').value = '';
    document.getElementById('filter-status').style.display = 'none';
    resetSubtitles();
    currentPage = 0;

    const btn = document.getElementById('apply-btn');
    btn.textContent = 'Applying…';
    btn.disabled    = true;

    await Promise.all([
        loadKPIs(),
        loadWhen(),
        loadWhere(),
        loadHowMuch(),
    ]);

    loadTrips();

    btn.textContent = 'Apply Filters';
    btn.disabled    = false;
}

/* ── Chart definitions ── */

const hourlyChart = new Chart(document.getElementById('c-hourly'), {
    data: {
        labels: [],
        datasets: [
            {
                type: 'bar', label: 'Trips', data: [],
                backgroundColor: 'rgba(45,106,159,0.55)',
                borderRadius: 4, yAxisID: 'yTrips', order: 2
            },
            {
                type: 'line', label: 'Avg Speed (mph)', data: [],
                borderColor: '#1e3a5f', backgroundColor: '#1e3a5f',
                pointBackgroundColor: '#1e3a5f', pointRadius: 3,
                tension: 0.35, yAxisID: 'ySpeed', order: 1
            }
        ]
    },
    options: {
        responsive: true,
        plugins: { legend: { display: true, position: 'top', align: 'end', labels: { boxWidth: 14, color: '#374151', font: { size: 12, weight: '600' } } } },
        scales: {
            x: { ticks: { color: '#9ca3af', maxTicksLimit: 12 }, grid: { color: '#dbeafe' } },
            yTrips: { position: 'left', ticks: { color: '#9ca3af', callback: v => v.toLocaleString() }, grid: { color: '#dbeafe' }, title: { display: true, text: 'Trips', color: '#9ca3af' } },
            ySpeed: { position: 'right', ticks: { color: '#9ca3af', callback: v => v + ' mph' }, grid: { display: false }, title: { display: true, text: 'Avg Speed (mph)', color: '#9ca3af' } }
        }
    }
});

const radarChart = new Chart(document.getElementById('c-radar'), {
    type: 'radar',
    data: {
        labels: ['Avg Fare ($)', 'Avg Distance (mi)', 'Avg Duration (min)', 'Avg Speed (mph)', 'Avg Tip (%)'],
        datasets: [
            { label: 'Weekday', data: [], borderColor: '#1e3a5f', backgroundColor: 'rgba(30,58,95,0.15)', pointBackgroundColor: '#1e3a5f', pointRadius: 4 },
            { label: 'Weekend', data: [], borderColor: '#FF6B35', backgroundColor: 'rgba(255,107,53,0.15)', pointBackgroundColor: '#FF6B35', pointRadius: 4 }
        ]
    },
    options: {
        responsive: true,
        plugins: { legend: { display: true, position: 'top', labels: { boxWidth: 14, color: '#374151', font: { size: 12, weight: '600' } } } },
        scales: { r: { ticks: { color: '#9ca3af', font: { size: 10 } }, grid: { color: '#dbeafe' }, pointLabels: { color: '#374151', font: { size: 12, weight: '600' } } } }
    }
});

const polarChart = new Chart(document.getElementById('c-polar'), {
    type: 'polarArea',
    data: { labels: [], datasets: [{ data: [], backgroundColor: [] }] },
    options: {
        responsive: true,
        plugins: { legend: { display: true, position: 'right', labels: { boxWidth: 12, font: { size: 11 } } } },
        scales: { r: { ticks: { display: false }, grid: { color: '#dbeafe' } } }
    }
});

const boroughDoughnut = new Chart(document.getElementById('c-borough-doughnut'), {
    type: 'doughnut',
    data: { labels: [], datasets: [{ data: [], backgroundColor: ['#1e3a5f','#2d6a9f','#f59e0b','#2EC4B6','#7C3AED','#6b7280'], borderWidth: 2 }] },
    options: {
        responsive: true,
        plugins: {
            legend: { display: true, position: 'bottom', labels: { boxWidth: 12, font: { size: 12 } } },
            tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed.toLocaleString()} trips (${((ctx.parsed / ctx.dataset.data.reduce((a,b)=>a+b,0))*100).toFixed(1)}%)` } }
        }
    }
});

const fareDistChart = new Chart(document.getElementById('c-fare-dist'), {
    type: 'bar',
    data: { labels: [], datasets: [{ data: [], backgroundColor: '#2d6a9f', borderRadius: 4 }] },
    options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
            x: { ticks: { color: '#9ca3af' }, grid: { display: false } },
            y: { ticks: { color: '#9ca3af', callback: v => v.toLocaleString() }, grid: { color: '#dbeafe' }, title: { display: true, text: 'Number of Trips', color: '#9ca3af' } }
        }
    }
});

const paymentChart = new Chart(document.getElementById('c-payment'), {
    type: 'doughnut',
    data: { labels: [], datasets: [{ data: [], backgroundColor: ['#1e3a5f','#2d6a9f','#f59e0b','#2EC4B6','#7C3AED'], borderWidth: 2 }] },
    options: {
        responsive: true,
        plugins: {
            legend: { display: true, position: 'bottom', labels: { boxWidth: 12, font: { size: 12 } } },
            tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed.toLocaleString()} trips (${((ctx.parsed / ctx.dataset.data.reduce((a,b)=>a+b,0))*100).toFixed(1)}%)` } }
        }
    }
});

/* ── KPIs ── */
async function loadKPIs() {
    try {
        const res = await get('/api/stats/summary' + buildFilterQuery());
        const s   = res.data;
        document.getElementById('kpi-trips').textContent    = Number(s.total_trips).toLocaleString();
        document.getElementById('kpi-revenue').textContent  = s.total_revenue ? '$' + (s.total_revenue / 1e6).toFixed(1) + 'M' : '—';
        document.getElementById('kpi-fare').textContent     = '$' + s.avg_fare.toFixed(2);
        document.getElementById('kpi-duration').textContent = s.avg_duration.toFixed(1) + ' min';
        document.getElementById('kpi-speed').textContent    = s.avg_speed.toFixed(1) + ' mph';
        document.getElementById('kpi-hour').textContent     = String(s.busiest_hour).padStart(2, '0') + ':00';
        document.getElementById('kpi-borough').textContent  = s.busiest_borough;
    } catch(e) { console.warn('KPIs:', e.message); }
}

/* ── WHEN ── */
async function loadWhen() {
    try {
        const res    = await get('/api/insights/hourly' + buildFilterQuery());
        const hourly = res.data;
        hourlyChart.data.labels           = hourly.map(h => h.hour + ':00');
        hourlyChart.data.datasets[0].data = hourly.map(h => h.trip_count);
        hourlyChart.data.datasets[1].data = hourly.map(h => h.avg_speed != null ? Number(h.avg_speed.toFixed(1)) : null);
        hourlyChart.update();
    } catch(e) { console.warn('Hourly:', e.message); }

    try {
        const res = await get('/api/insights/weekend-vs-weekday' + buildFilterQuery());
        const data = res.data;
        let weekday = {}, weekend = {};
        data.forEach(d => { if (d.day_type === 'Weekday') weekday = d; else weekend = d; });

        document.getElementById('wknd-trips-weekday').textContent = Number(weekday.total_trips).toLocaleString();
        document.getElementById('wknd-trips-weekend').textContent = Number(weekend.total_trips).toLocaleString();

        const fasterDay  = weekday.avg_speed > weekend.avg_speed ? 'Weekdays' : 'Weekends';
        const speedDiff  = Math.abs(weekday.avg_speed - weekend.avg_speed).toFixed(1);
        const fareDiff   = Math.abs(weekday.avg_fare - weekend.avg_fare).toFixed(2);
        const higherFare = weekday.avg_fare > weekend.avg_fare ? 'Weekday' : 'Weekend';

        document.getElementById('wknd-insight-text').innerHTML =
            `<b>${fasterDay}</b> are faster by <b>${speedDiff} mph</b> on average,likely due to lighter traffic. ` +
            `<b>${higherFare}</b> trips cost more on average, with a $${fareDiff} fare difference. ` +
            `Weekend trips account for <b>${((weekend.total_trips / (weekday.total_trips + weekend.total_trips)) * 100).toFixed(1)}%</b> of all 2025 taxi activity.`;

        data.forEach(d => {
            const idx = d.day_type === 'Weekday' ? 0 : 1;
            radarChart.data.datasets[idx].data = [d.avg_fare, d.avg_distance, d.avg_duration, d.avg_speed, d.avg_tip_pct];
        });
        radarChart.update();
    } catch(e) { console.warn('Radar:', e.message); }
}

/* ── WHERE ── */
async function loadWhere() {
    loadWhereCharts();
    initMap();
}

async function loadWhereCharts() {
    try {
        const [zonesRes, boroughRes] = await Promise.all([
            get('/api/insights/top-zones'),
            get('/api/insights/borough-summary')
        ]);

        const data   = zonesRes.data;
        const colors = ['#1e3a5f','#2d6a9f','#3b82f6','#60a5fa','#93c5fd','#FF6B35','#f97316','#fb923c','#fdba74','#fed7aa','#f59e0b','#2EC4B6','#7C3AED','#10b981','#6b7280'];
        polarChart.data.labels                      = data.map(z => z.zone);
        polarChart.data.datasets[0].data            = data.map(z => z.trip_count);
        polarChart.data.datasets[0].backgroundColor = colors.slice(0, data.length);
        polarChart.update();

        const topZone        = data[0];
        const manhattanCount = data.filter(z => z.borough === 'Manhattan').length;
        document.getElementById('polar-insight').innerHTML =
            `The busiest pickup zone is <b>${topZone.zone}</b> (${topZone.borough}) with <b>${topZone.trip_count.toLocaleString()}</b> pickups in 2025. ` +
            `<b>${manhattanCount} of the top 15</b> zones are in Manhattan,confirming its dominance in yellow taxi activity.`;

        const bData  = boroughRes.data;
        boroughDoughnut.data.labels           = bData.map(b => b.borough);
        boroughDoughnut.data.datasets[0].data = bData.map(b => b.total_trips);
        boroughDoughnut.update();

        const top    = bData[0];
        const total  = bData.reduce((a, b) => a + b.total_trips, 0);
        const topPct = ((top.total_trips / total) * 100).toFixed(1);
        const second = bData[1];
        const secPct = ((second.total_trips / total) * 100).toFixed(1);
        document.getElementById('borough-doughnut-insight').innerHTML =
            `<b>${top.borough}</b> dominates yellow taxi pickups with <b>${topPct}%</b> of all 2025 trips. ` +
            `<b>${second.borough}</b> is a distant second at <b>${secPct}%</b>. ` +
            `The outer boroughs rely far less on yellow taxis,reflecting the city's transit geography.`;
    } catch(e) { console.warn('Where charts:', e.message); }
}

async function reloadBoroughDoughnut() {
    try {
        const res   = await get('/api/insights/borough-summary' + buildFilterQuery());
        const bData = res.data;
        boroughDoughnut.data.labels           = bData.map(b => b.borough);
        boroughDoughnut.data.datasets[0].data = bData.map(b => b.total_trips);
        boroughDoughnut.update();
    } catch(e) { console.warn('Borough doughnut reload:', e.message); }
}

/* ── MAP ── */
async function initMap() {
    if (mapInitialized) return;
    mapInitialized = true;

    const map = L.map('map', { scrollWheelZoom: false }).setView([40.730, -73.935], 11);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap &copy; CARTO', maxZoom: 19
    }).addTo(map);

    function zoneColor(t) {
        return t > 0.6 ? '#1e3a5f' : t > 0.3 ? '#2d6a9f' : t > 0.1 ? '#93c5fd' : t > 0 ? '#dbeafe' : '#f3f4f6';
    }

    try {
        const geojson  = await get('/api/geojson');
        const maxTrips = Math.max(1, ...geojson.features.map(f => f.properties.trip_count || 0));

        L.geoJSON(geojson, {
            style: feature => ({ fillColor: zoneColor((feature.properties.trip_count || 0) / maxTrips), color: '#fff', weight: 0.5, fillOpacity: 0.75 }),
            onEachFeature: (feature, layer) => {
                const p = feature.properties;
                layer.bindPopup(`<b>${p.zone || p.Zone || '—'}</b><br>${p.borough || '—'}<br>${(p.trip_count || 0).toLocaleString()} trips`);
                layer.on('mouseover', () => layer.setStyle({ fillOpacity: 1, weight: 1.5 }));
                layer.on('mouseout',  () => layer.setStyle({ fillOpacity: 0.75, weight: 0.5 }));
            }
        }).addTo(map);

        document.getElementById('map-insight').innerHTML =
            `Darker zones indicate higher pickup density. <b>Midtown and Upper East Side</b> are the darkest,the heart of NYC yellow taxi demand. ` +
            `<b>JFK and LaGuardia</b> airports appear prominently in Queens. Outer boroughs show significantly lighter activity.`;
    } catch(e) { console.warn('Map failed:', e.message); }
}

/* ── HOW MUCH ── */
async function loadHowMuch() {
    try {
        const res = await get('/api/insights/fare-distribution' + buildFilterQuery());
        const data = res.data;
        fareDistChart.data.labels              = data.map(d => d.fare_bucket);
        fareDistChart.data.datasets[0].data    = data.map(d => d.trip_count);
        fareDistChart.update();

        const peak    = data.reduce((a, b) => a.trip_count > b.trip_count ? a : b);
        const total   = data.reduce((a, b) => a + b.trip_count, 0);
        const peakPct = ((peak.trip_count / total) * 100).toFixed(1);
        document.getElementById('fare-dist-insight').innerHTML =
            `Most NYC yellow taxi trips fall in the <b>${peak.fare_bucket}</b> fare range, accounting for <b>${peakPct}%</b> of all trips. ` +
            `Short Manhattan hops dominate the fare landscape,reflecting the city's dense urban environment.`;
    } catch(e) { console.warn('Fare dist:', e.message); }

    try {
        const res = await get('/api/insights/payment-breakdown' + buildFilterQuery());
        const data = res.data;
        paymentChart.data.labels              = data.map(d => d.label);
        paymentChart.data.datasets[0].data    = data.map(d => d.trip_count);
        paymentChart.update();

        const top    = data[0];
        const second = data[1];
        document.getElementById('payment-insight').innerHTML =
            `<b>${top.percentage}%</b> of all trips are paid by <b>${top.label}</b>. ` +
            `<b>${second.label}</b> accounts for <b>${second.percentage}%</b>. ` +
            `Note: cash tip amounts are not recorded by TLC,tip percentage data reflects card payments only.`;
    } catch(e) { console.warn('Payment:', e.message); }
}

/* ── EXPLORE,Trips with sort + pagination ── */
function resetAndLoad() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => { currentPage = 0; loadTrips(); }, 400);
}

async function loadTrips() {
    const hourInput = document.getElementById('f-hour-explore').value;
    const offset    = currentPage * PAGE_SIZE;

    const extra = { offset, limit: PAGE_SIZE };
    if (hourInput !== '') extra.hour = hourInput;

    try {
        document.getElementById('tbody-explore').innerHTML =
            `<tr><td colspan="8" style="text-align:center;color:#9ca3af;padding:24px;">Loading…</td></tr>`;

        const res = await get('/api/trips' + buildFilterQuery(extra));
        currentTrips = res.data;

        document.getElementById('trip-count-label').textContent =
            `Showing ${offset + 1}–${offset + currentTrips.length} trips`;

        document.getElementById('btn-prev').disabled = currentPage === 0;
        document.getElementById('btn-next').disabled = currentTrips.length < PAGE_SIZE;
        document.getElementById('page-label').textContent = `Page ${currentPage + 1}`;

        renderTrips();
    } catch(e) { console.warn('Trips:', e.message); }
}

function renderTrips() {
    const sorted = [...currentTrips].sort((a, b) => {
        let va = a[currentSort.column] ?? '';
        let vb = b[currentSort.column] ?? '';
        if (typeof va === 'string') va = va.toLowerCase();
        if (typeof vb === 'string') vb = vb.toLowerCase();
        if (va < vb) return currentSort.direction === 'asc' ? -1 : 1;
        if (va > vb) return currentSort.direction === 'asc' ? 1 : -1;
        return 0;
    });

    document.getElementById('tbody-explore').innerHTML = sorted.map(t => `
        <tr>
            <td class="muted" style="font-family:monospace;font-size:12px">${(t.pickup_datetime || '—').slice(0,16)}</td>
            <td><b>${t.pu_borough || '—'}</b></td>
            <td class="muted">${t.pu_zone || '—'}</td>
            <td class="muted">${t.trip_duration_minutes != null ? t.trip_duration_minutes.toFixed(1) + ' min' : '—'}</td>
            <td class="muted">${t.trip_distance != null ? t.trip_distance.toFixed(1) + ' mi' : '—'}</td>
            <td class="fare-when">$${t.fare_amount != null ? t.fare_amount.toFixed(2) : '—'}</td>
            <td class="muted">${t.tip_percentage != null ? t.tip_percentage.toFixed(1) + '%' : '—'}</td>
            <td class="muted">${PAYMENT_LABELS[t.payment_type] || '—'}</td>
        </tr>`).join('');
}

function nextPage() { currentPage++; loadTrips(); window.scrollTo({ top: document.getElementById('tbody-explore').offsetTop - 200, behavior: 'smooth' }); }
function prevPage() { if (currentPage > 0) { currentPage--; loadTrips(); } }

/* ── Column sort ── */
document.querySelectorAll('th.sortable').forEach(th => {
    th.addEventListener('click', () => {
        const col = th.dataset.col;
        if (currentSort.column === col) {
            currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
        } else {
            currentSort.column    = col;
            currentSort.direction = 'asc';
        }

        document.querySelectorAll('th.sortable').forEach(h => {
            h.classList.remove('active');
            h.querySelector('.sort-icon').textContent = '';
        });
        th.classList.add('active');
        th.querySelector('.sort-icon').textContent = currentSort.direction === 'asc' ? '▲' : '▼';

        renderTrips();
    });
});

function buildFilterLabel() {
    const borough   = document.getElementById('g-borough').value;
    const timeOfDay = document.getElementById('g-timeofday').value;
    const parts     = [];
    if (borough)   parts.push(borough);
    if (timeOfDay) parts.push(timeOfDay);
    return parts.join(' · ');
}

function updateSubtitles(label) {
    const suffix = `,filtered by ${label}`;
    document.getElementById('sub-hourly').textContent          = 'Trip volume and average speed across every hour of the day' + suffix;
    document.getElementById('sub-radar').textContent           = 'Weekday vs Weekend,how the city moves differently' + suffix;
    document.getElementById('sub-map').textContent             = 'Mapping pickup activity across all 263 NYC taxi zones' + suffix;
    document.getElementById('sub-polar').textContent           = 'Top 15 busiest pickup zones' + suffix;
    document.getElementById('sub-borough-doughnut').textContent = 'Trip share by borough' + suffix;
    document.getElementById('sub-fare-dist').textContent       = 'Fare distribution across all trips' + suffix;
    document.getElementById('sub-payment').textContent         = 'How passengers prefer to pay' + suffix;
}

function resetSubtitles() {
    document.getElementById('sub-hourly').textContent          = 'Trip volume and average speed across every hour of the day';
    document.getElementById('sub-radar').textContent           = 'Weekday vs Weekend,how the city moves differently';
    document.getElementById('sub-map').textContent             = 'Mapping pickup activity across all 263 NYC taxi zones';
    document.getElementById('sub-polar').textContent           = 'Top 15 busiest pickup zones';
    document.getElementById('sub-borough-doughnut').textContent = 'Trip share by borough';
    document.getElementById('sub-fare-dist').textContent       = 'Fare distribution across all trips';
    document.getElementById('sub-payment').textContent         = 'How passengers prefer to pay';
}

async function reloadWhereFiltered() {
    try {
        const [zonesRes, boroughRes] = await Promise.all([
            get('/api/insights/top-zones' + buildFilterQuery()),
            get('/api/insights/borough-summary' + buildFilterQuery())
        ]);

        const data   = zonesRes.data;
        const colors = ['#1e3a5f','#2d6a9f','#3b82f6','#60a5fa','#93c5fd','#FF6B35','#f97316','#fb923c','#fdba74','#fed7aa','#f59e0b','#2EC4B6','#7C3AED','#10b981','#6b7280'];
        polarChart.data.labels                      = data.map(z => z.zone);
        polarChart.data.datasets[0].data            = data.map(z => z.trip_count);
        polarChart.data.datasets[0].backgroundColor = colors.slice(0, data.length);
        polarChart.update();

        if (data.length > 0) {
            const topZone        = data[0];
            const manhattanCount = data.filter(z => z.borough === 'Manhattan').length;
            document.getElementById('polar-insight').innerHTML =
                `The busiest pickup zone is <b>${topZone.zone}</b> (${topZone.borough}) with <b>${topZone.trip_count.toLocaleString()}</b> pickups. ` +
                `<b>${manhattanCount} of the top ${data.length}</b> zones are in Manhattan.`;
        }

        const bData  = boroughRes.data;
        boroughDoughnut.data.labels           = bData.map(b => b.borough);
        boroughDoughnut.data.datasets[0].data = bData.map(b => b.total_trips);
        boroughDoughnut.update();

        if (bData.length > 0) {
            const top    = bData[0];
            const total  = bData.reduce((a, b) => a + b.total_trips, 0);
            const topPct = ((top.total_trips / total) * 100).toFixed(1);
            document.getElementById('borough-doughnut-insight').innerHTML =
                `<b>${top.borough}</b> leads with <b>${topPct}%</b> of filtered trips. `;
        }
    } catch(e) { console.warn('Where filtered:', e.message); }
}

/* ── Init ── */
loadKPIs();
loadWhen();
loadWhere();
loadHowMuch();
loadTrips();