const API = 'http://localhost:5000';

let mapInitialized = false;
let fareChart, boroughFareChart;
let _whenTrips  = [];
let _whereTrips = [];
let _howTrips   = [];
let _allZones   = [];

/* ── Navigation ── */
function show(name, btn) {
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('section-' + name).classList.add('active');
    btn.classList.add('active');

    // Resize charts after the section is visible
    setTimeout(() => {
        if (fareChart) fareChart.resize();
        if (boroughFareChart) boroughFareChart.resize();
    }, 50);

    // Lazy-init map and reload data for the active section
    if (name === 'where') {
        initMap();
        loadWhere();
    } else if (name === 'when') {
        loadWhen();
    } else if (name === 'howmuch') {
        loadHowMuch();
    }
}

/* ── API helper ── */
async function get(path) {
    const res = await fetch(API + path);
    if (!res.ok) throw new Error(res.status);
    return res.json();
}

/* ── WHEN ── */
async function loadWhen() {
    try {
        const summaryRes = await get('/api/stats/summary');
        const s = summaryRes.data || summaryRes;
        document.getElementById('sb-total').textContent = Number(s.total_trips).toLocaleString();
        document.getElementById('sb-peak').textContent  = String(s.busiest_hour).padStart(2,'0') + ':00';
    } catch(e) {
        console.warn('Summary:', e.message);
    }

    try {
        const hourlyRes = await get('/api/insights/hourly');
        const hourly    = hourlyRes.data || hourlyRes;
        const summaryRes = await get('/api/stats/summary');
        const s          = summaryRes.data || summaryRes;

        fareChart.data.labels = hourly.map(h => h.hour + ':00');
        fareChart.data.datasets[0].data = hourly.map(h => h.trip_count);
        fareChart.data.datasets[0].backgroundColor = hourly.map(h =>
            'rgba(45,106,159,0.55)'
        );
        fareChart.data.datasets[1].data = hourly.map(h => h.avg_speed != null ? Number(h.avg_speed.toFixed(1)) : null);
        fareChart.update();
    } catch(e) {
        console.warn('Hourly:', e.message);
    }

    try {
        const tripsRes = await get('/api/trips?limit=50');
        _whenTrips = tripsRes.data || [];
        renderWhenTable(_whenTrips);
    } catch(e) {
        console.warn('Trips (when):', e.message);
    }

    try {
        const wkRes = await get('/api/insights/weekend-vs-weekday');
        renderWeekendComparison(wkRes.data || []);
    } catch(e) {
        console.warn('Weekend/weekday:', e.message);
    }
}

function renderWeekendComparison(data) {
    document.getElementById('wknd-comparison').innerHTML = data.map(d => `
        <div class="wknd-card">
            <div class="wknd-label">${d.day_type}</div>
            <div class="wknd-trips">${Number(d.total_trips).toLocaleString()}</div>
            <div class="wknd-meta">total trips</div>
            <div class="wknd-stats">
                <span>Avg fare <b>$${d.avg_fare}</b></span>
                <span>Avg speed <b>${d.avg_speed} mph</b></span>
                <span>Avg tip <b>${d.avg_tip_percentage}%</b></span>
            </div>
        </div>`).join('');
}

function renderWhenTable(data) {
    document.getElementById('tbody-when').innerHTML = data.map(t => `
        <tr>
            <td class="muted" style="font-family:monospace;font-size:12px">${(t.pickup_datetime || '—').slice(0,16)}</td>
            <td><b>${t.pu_borough || '—'}</b></td>
            <td class="muted">${t.trip_duration_minutes != null ? t.trip_duration_minutes.toFixed(1) + ' min' : '—'}</td>
            <td class="fare-when">$${t.fare_amount != null ? t.fare_amount.toFixed(2) : '—'}</td>
            <td class="muted">${t.time_of_day || '—'}</td>
        </tr>`).join('');
}

function filterWhen() {
    const p   = document.getElementById('f-time').value;
    const q   = (document.getElementById('s-when').value || '').toLowerCase().trim();
    let data  = _whenTrips;
    if (p !== 'all') data = data.filter(t => (t.time_of_day || '').toLowerCase() === p);
    if (q) data = data.filter(t =>
        (t.pu_borough   || '').toLowerCase().includes(q) ||
        (t.time_of_day  || '').toLowerCase().includes(q) ||
        (t.pickup_datetime || '').includes(q)
    );
    renderWhenTable(data.length ? data : (q || p !== 'all' ? [] : _whenTrips));
}

/* ── WHERE ── */
async function loadWhere() {
    try {
        const summaryRes = await get('/api/stats/summary');
        const s = summaryRes.data || summaryRes;
        document.getElementById('sb-top-boro').textContent = s.busiest_borough || '—';
        document.getElementById('sb-avg-dist').textContent = s.avg_distance != null ? s.avg_distance.toFixed(1) + ' mi' : '—';
    } catch(e) {
        console.warn('Summary (where):', e.message);
    }

    try {
        const tripsRes = await get('/api/trips?limit=50');
        _whereTrips = tripsRes.data || [];
        renderWhereTable(_whereTrips);
    } catch(e) {
        console.warn('Trips (where):', e.message);
    }

    try {
        const zonesRes = await get('/api/zones');
        _allZones = zonesRes.data || [];
        populateZoneSelect('all');
    } catch(e) {
        console.warn('Zones:', e.message);
    }

    try {
        const topRes = await get('/api/insights/top-zones?k=10');
        renderTopZones(topRes.data || []);
    } catch(e) {
        console.warn('Top zones:', e.message);
    }
}

function populateZoneSelect(borough) {
    const sel   = document.getElementById('f-zone');
    const zones = borough === 'all'
        ? _allZones
        : _allZones.filter(z => z.borough === borough);
    sel.innerHTML = '<option value="all">All Zones</option>' +
        zones.map(z => `<option value="${z.zone_name}">${z.zone_name}</option>`).join('');
}

function renderTopZones(data) {
    document.getElementById('tbody-top-zones').innerHTML = data.map((z, i) => `
        <tr>
            <td class="muted">${i + 1}</td>
            <td><b>${z.zone}</b></td>
            <td class="muted">${z.borough}</td>
            <td class="fare-where">${(z.trip_count || 0).toLocaleString()}</td>
        </tr>`).join('');
}

function onBoroughChange() {
    const b = document.getElementById('f-borough').value;
    populateZoneSelect(b);
    filterWhere();
}

function renderWhereTable(data) {
    document.getElementById('tbody-where').innerHTML = data.map(t => `
        <tr>
            <td class="muted" style="font-family:monospace;font-size:12px">${(t.pickup_datetime || '—').slice(0,16)}</td>
            <td><b>${t.pu_borough || '—'}</b></td>
            <td>${t.trip_distance != null ? t.trip_distance.toFixed(1) + ' mi' : '—'}</td>
            <td class="fare-where">$${t.fare_amount != null ? t.fare_amount.toFixed(2) : '—'}</td>
            <td class="muted">${t.time_of_day || '—'}</td>
        </tr>`).join('');
}

function filterWhere() {
    const b  = document.getElementById('f-borough').value;
    const z  = document.getElementById('f-zone').value;
    const q  = (document.getElementById('s-where').value || '').toLowerCase().trim();
    let data = _whereTrips;
    if (b !== 'all') data = data.filter(t => (t.pu_borough || '').toLowerCase() === b.toLowerCase());
    if (z !== 'all') data = data.filter(t => (t.pu_zone || '') === z);
    if (q) data = data.filter(t =>
        (t.pu_borough   || '').toLowerCase().includes(q) ||
        (t.pu_zone      || '').toLowerCase().includes(q) ||
        (t.time_of_day  || '').toLowerCase().includes(q) ||
        (t.pickup_datetime || '').includes(q)
    );
    const active = q || b !== 'all' || z !== 'all';
    renderWhereTable(data.length ? data : (active ? [] : _whereTrips));
}

/* ── HOW MUCH ── */
async function loadHowMuch() {
    try {
        const summaryRes = await get('/api/stats/summary');
        const s = summaryRes.data || summaryRes;
        document.getElementById('sb-avg-fare').textContent  = s.avg_fare  != null ? '$' + s.avg_fare.toFixed(2)  : '—';
        document.getElementById('sb-avg-speed').textContent = s.avg_speed != null ? s.avg_speed.toFixed(1) + ' mph' : '—';
    } catch(e) {
        console.warn('Summary (howmuch):', e.message);
    }

    try {
        const boroughRes = await get('/api/insights/borough-summary');
        const boroughs   = boroughRes.data || boroughRes;
        boroughFareChart.data.labels = boroughs.map(b => b.borough);
        boroughFareChart.data.datasets[0].data = boroughs.map(b => b.avg_fare);
        boroughFareChart.update();
    } catch(e) {
        console.warn('Borough summary:', e.message);
    }

    try {
        const tripsRes = await get('/api/trips?limit=100');
        _howTrips = tripsRes.data || [];
        renderHowMuchTable(_howTrips);
    } catch(e) {
        console.warn('Trips (howmuch):', e.message);
    }
}

function renderHowMuchTable(data) {
    document.getElementById('tbody-howmuch').innerHTML = data.map(t => `
        <tr>
            <td class="muted" style="font-family:monospace;font-size:12px">${(t.pickup_datetime || '—').slice(0,16)}</td>
            <td><b>${t.pu_borough || '—'}</b></td>
            <td class="fare-money">$${t.fare_amount != null ? t.fare_amount.toFixed(2) : '—'}</td>
            <td class="muted">${t.tip_percentage != null ? t.tip_percentage.toFixed(1) + '%' : '—'}</td>
            <td class="muted">${t.trip_distance != null ? t.trip_distance.toFixed(1) + ' mi' : '—'}</td>
        </tr>`).join('');
}

function filterHowMuch() {
    const f  = document.getElementById('f-fare').value;
    const q  = (document.getElementById('s-howmuch').value || '').toLowerCase().trim();
    let data = _howTrips.filter(t => {
        const v = t.fare_amount || 0;
        return f === 'all'
            || (f === 'low'   && v <= 10)
            || (f === 'mid'   && v > 10 && v <= 25)
            || (f === 'high'  && v > 25 && v <= 50)
            || (f === 'vhigh' && v > 50);
    });
    if (q) data = data.filter(t =>
        (t.pu_borough  || '').toLowerCase().includes(q) ||
        (t.time_of_day || '').toLowerCase().includes(q) ||
        (t.pickup_datetime || '').includes(q)
    );
    renderHowMuchTable(data.length ? data : (q || f !== 'all' ? [] : _howTrips));
}

/* ── Map (lazy init) ── */
async function initMap() {
    if (mapInitialized) return;
    mapInitialized = true;

    const map = L.map('map', { scrollWheelZoom: false }).setView([40.730, -73.935], 11);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap &copy; CARTO',
        maxZoom: 19
    }).addTo(map);

    function zoneColor(t) {
        return t > 0.6 ? '#c2410c'
             : t > 0.3 ? '#FF6B35'
             : t > 0.1 ? '#fdba74'
             : t > 0   ? '#fed7aa'
             :            '#e5e7eb';
    }

    try {
        const [geoRes, topRes] = await Promise.all([
            fetch('https://data.cityofnewyork.us/api/geospatial/755u-8jsi?method=export&type=GeoJSON'),
            get('/api/insights/top-zones?k=50')
        ]);

        const geojson  = await geoRes.json();
        const topZones = topRes.data || [];

        const tripCount = {};
        topZones.forEach(z => { tripCount[z.zone_name] = z.trip_count || 0; });
        const maxTrips = Math.max(1, ...Object.values(tripCount));

        L.geoJSON(geojson, {
            style: feature => {
                const trips = tripCount[feature.properties.zone] || 0;
                return {
                    fillColor: zoneColor(trips / maxTrips),
                    color: '#fff', weight: 0.5, fillOpacity: 0.75
                };
            },
            onEachFeature: (feature, layer) => {
                const name  = feature.properties.zone;
                const boro  = feature.properties.borough;
                const trips = tripCount[name] || 0;
                layer.bindPopup(`<b>${name}</b><br>${boro}<br>${trips.toLocaleString()} trips`);
                layer.on('mouseover', () => layer.setStyle({ fillOpacity: 1, weight: 1.5 }));
                layer.on('mouseout',  () => layer.setStyle({ fillOpacity: 0.75, weight: 0.5 }));
            }
        }).addTo(map);
    } catch(e) {
        console.warn('Map GeoJSON failed, using fallback:', e.message);
        [
            { name:'Midtown Manhattan',  lat:40.7549, lng:-73.9840 },
            { name:'Lower Manhattan',    lat:40.7074, lng:-74.0113 },
            { name:'JFK Airport',        lat:40.6413, lng:-73.7781 },
            { name:'Downtown Brooklyn',  lat:40.6928, lng:-73.9903 },
            { name:'LaGuardia Airport',  lat:40.7769, lng:-73.8740 },
        ].forEach(z => {
            L.circleMarker([z.lat, z.lng], {
                radius: 10, fillColor: '#FF6B35', color: '#fff', weight: 2, fillOpacity: 0.8
            }).bindPopup(`<b>${z.name}</b>`).addTo(map);
        });
    }
}

/* ── Charts (start empty — all data comes from API) ── */
fareChart = new Chart(document.getElementById('c-fare'), {
    data: {
        labels: [],
        datasets: [
            {
                type: 'bar',
                label: 'Trips',
                data: [],
                backgroundColor: [],
                borderRadius: 4,
                yAxisID: 'yTrips',
                order: 2
            },
            {
                type: 'line',
                label: 'Avg speed (mph)',
                data: [],
                borderColor: '#1e3a5f',
                backgroundColor: '#1e3a5f',
                pointBackgroundColor: '#1e3a5f',
                pointRadius: 3,
                tension: 0.35,
                yAxisID: 'ySpeed',
                order: 1
            }
        ]
    },
    options: {
        responsive: true,
        plugins: { legend: { display: true, position: 'top', align: 'end', labels: { boxWidth: 14, color: '#374151', font: { size: 12, weight: '600' } } } },
        scales: {
            x: { ticks: { color: '#9ca3af', maxTicksLimit: 12 }, grid: { display: true, color: '#dbeafe' } },
            yTrips: {
                position: 'left',
                ticks: { color: '#9ca3af', callback: v => v.toLocaleString() },
                grid: { color: '#dbeafe' },
                title: { display: true, text: 'Trips', color: '#9ca3af' }
            },
            ySpeed: {
                position: 'right',
                ticks: { color: '#9ca3af', callback: v => v + ' mph' },
                grid: { display: false },
                title: { display: true, text: 'Avg speed (mph)', color: '#9ca3af' }
            }
        }
    }
});

boroughFareChart = new Chart(document.getElementById('c-borough-fare'), {
    type: 'bar',
    data: {
        labels: [],
        datasets: [{
            data: [],
            backgroundColor: ['#1e3a5f','#FF6B35','#f59e0b','#2EC4B6','#7C3AED'],
            borderRadius: 6,
        }]
    },
    options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
            x: { ticks: { color: '#9ca3af' }, grid: { display: false } },
            y: { ticks: { color: '#9ca3af', callback: v => '$' + v }, grid: { color: '#f9fafb' } }
        }
    }
});

/* ── Init ── */
// Only load the default active section on startup; other sections load on tab click
loadWhen();