/* ═══════════════════════════════════════════════════
   NYC Taxi Dashboard — app.js
   Connects to Flask backend at /api/trips and /api/stats
   Falls back to mock data if backend unreachable
═══════════════════════════════════════════════════ */

const API_BASE = 'http://127.0.0.1:5000/api';
const PAGE_SIZE = 15;

/* ── State ── */
const state = {
  trips: [],
  filtered: [],
  page: 1,
  sortCol: 'tpep_pickup_datetime',
  sortDir: 'desc',
  filters: {
    borough: '',
    hourStart: 0,
    hourEnd: 23,
    fareMax: 200,
  },
};

/* ── Chart instances ── */
let chartHourly = null;
let chartFare   = null;
let chartDist   = null;

/* ═══════════════════════════════════════════════════
   1. BOOT
═══════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  bindFilterEvents();
  bindTableSort();
  loadData();
});

/* ═══════════════════════════════════════════════════
   2. DATA LOADING — tries Flask, falls back to mock
═══════════════════════════════════════════════════ */
async function loadData() {
  try {
    const res = await fetch(`${API_BASE}/trips?limit=1000`);
    if (!res.ok) throw new Error('Backend not ready');
    const json = await res.json();
    state.trips = json.data ?? json;
    document.getElementById('last-updated').textContent =
      'Live data · ' + new Date().toLocaleTimeString();
  } catch {
    console.warn('Flask backend not reachable — using mock data');
    state.trips = generateMockData(500);
    document.getElementById('last-updated').textContent =
      'Mock data (backend offline)';
  }
  applyFilters();
}

/* ═══════════════════════════════════════════════════
   3. FILTERS
═══════════════════════════════════════════════════ */
function bindFilterEvents() {
  document.getElementById('btn-apply').addEventListener('click', readAndApply);
  document.getElementById('btn-reset').addEventListener('click', resetFilters);
}

function readAndApply() {
  state.filters.borough   = document.getElementById('filter-borough').value;
  state.filters.hourStart = parseInt(document.getElementById('filter-hour-start').value) || 0;
  state.filters.hourEnd   = parseInt(document.getElementById('filter-hour-end').value) || 23;
  state.filters.fareMax   = parseFloat(document.getElementById('filter-fare-max').value) || 999;
  state.sortCol = document.getElementById('filter-sort').value;
  state.sortDir = ['fare_amount', 'trip_distance', 'total_amount'].includes(state.sortCol) ? 'desc' : 'asc';
  state.page = 1;
  applyFilters();
}

function resetFilters() {
  document.getElementById('filter-borough').value   = '';
  document.getElementById('filter-hour-start').value = 0;
  document.getElementById('filter-hour-end').value   = 23;
  document.getElementById('filter-fare-max').value   = 200;
  document.getElementById('filter-sort').value        = 'tpep_pickup_datetime';
  state.filters = { borough: '', hourStart: 0, hourEnd: 23, fareMax: 200 };
  state.sortCol = 'tpep_pickup_datetime';
  state.sortDir = 'desc';
  state.page = 1;
  applyFilters();
}

function applyFilters() {
  const { borough, hourStart, hourEnd, fareMax } = state.filters;
  state.filtered = state.trips.filter(t => {
    const hour = getHour(t.tpep_pickup_datetime);
    if (borough && t.pu_borough !== borough) return false;
    if (hour < hourStart || hour > hourEnd) return false;
    if (t.fare_amount > fareMax) return false;
    return true;
  });
  sortTrips();
  renderAll();
}

function sortTrips() {
  const { sortCol, sortDir } = state;
  state.filtered.sort((a, b) => {
    let va = a[sortCol], vb = b[sortCol];
    if (sortCol === 'tpep_pickup_datetime') {
      va = new Date(va); vb = new Date(vb);
    }
    if (va < vb) return sortDir === 'asc' ? -1 : 1;
    if (va > vb) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });
}

/* ═══════════════════════════════════════════════════
   4. RENDER ALL
═══════════════════════════════════════════════════ */
function renderAll() {
  renderKPIs();
  renderChartHourly();
  renderChartFare();
  renderChartDist();
  renderTable();
}

/* ═══════════════════════════════════════════════════
   5. KPIs
═══════════════════════════════════════════════════ */
function renderKPIs() {
  const trips = state.filtered;
  const n = trips.length;

  document.getElementById('kpi-total').textContent =
    n.toLocaleString();

  document.getElementById('kpi-avg-fare').textContent = n
    ? '$' + (trips.reduce((s, t) => s + t.fare_amount, 0) / n).toFixed(2)
    : '—';

  document.getElementById('kpi-avg-dist').textContent = n
    ? (trips.reduce((s, t) => s + t.trip_distance, 0) / n).toFixed(1) + ' mi'
    : '—';

  if (n) {
    const hourCounts = Array(24).fill(0);
    trips.forEach(t => hourCounts[getHour(t.tpep_pickup_datetime)]++);
    const peak = hourCounts.indexOf(Math.max(...hourCounts));
    document.getElementById('kpi-peak-hour').textContent = formatHour(peak);
  } else {
    document.getElementById('kpi-peak-hour').textContent = '—';
  }
}

/* ═══════════════════════════════════════════════════
   6. CHARTS
═══════════════════════════════════════════════════ */

/* Shared chart defaults */
const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: {
      ticks: { color: '#555e7a', font: { size: 11 } },
      grid: { color: 'rgba(255,255,255,0.04)' },
    },
    y: {
      ticks: { color: '#555e7a', font: { size: 11 } },
      grid: { color: 'rgba(255,255,255,0.06)' },
    },
  },
};

function renderChartHourly() {
  const hourCounts = Array(24).fill(0);
  state.filtered.forEach(t => hourCounts[getHour(t.tpep_pickup_datetime)]++);

  const labels = Array.from({ length: 24 }, (_, i) => formatHour(i));

  if (chartHourly) chartHourly.destroy();
  chartHourly = new Chart(document.getElementById('chart-hourly'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Trips',
        data: hourCounts,
        backgroundColor: 'rgba(79,142,247,0.65)',
        borderColor: '#4f8ef7',
        borderWidth: 1,
        borderRadius: 3,
      }],
    },
    options: {
      ...CHART_DEFAULTS,
      scales: {
        ...CHART_DEFAULTS.scales,
        x: { ...CHART_DEFAULTS.scales.x, ticks: { ...CHART_DEFAULTS.scales.x.ticks, autoSkip: false, maxRotation: 45 } },
      },
    },
  });
}

function renderChartFare() {
  const boroughs = ['Manhattan', 'Queens', 'Brooklyn', 'Bronx', 'Staten Island'];
  const avgs = boroughs.map(b => {
    const bTrips = state.filtered.filter(t => t.pu_borough === b);
    if (!bTrips.length) return 0;
    return parseFloat((bTrips.reduce((s, t) => s + t.fare_amount, 0) / bTrips.length).toFixed(2));
  });

  if (chartFare) chartFare.destroy();
  chartFare = new Chart(document.getElementById('chart-fare'), {
    type: 'bar',
    data: {
      labels: boroughs,
      datasets: [{
        label: 'Avg fare ($)',
        data: avgs,
        backgroundColor: [
          'rgba(247,195,79,0.7)',
          'rgba(247,195,79,0.55)',
          'rgba(247,195,79,0.45)',
          'rgba(247,195,79,0.35)',
          'rgba(247,195,79,0.25)',
        ],
        borderColor: '#f7c34f',
        borderWidth: 1,
        borderRadius: 3,
      }],
    },
    options: {
      ...CHART_DEFAULTS,
      indexAxis: 'y',
      scales: {
        x: { ...CHART_DEFAULTS.scales.x, ticks: { ...CHART_DEFAULTS.scales.x.ticks, callback: v => '$' + v } },
        y: { ...CHART_DEFAULTS.scales.y },
      },
    },
  });
}

function renderChartDist() {
  /* Bucket distances into 1-mile bins up to 20 miles */
  const bins = Array(20).fill(0);
  state.filtered.forEach(t => {
    const b = Math.min(Math.floor(t.trip_distance), 19);
    if (b >= 0) bins[b]++;
  });
  const labels = bins.map((_, i) => `${i}–${i + 1}`);

  if (chartDist) chartDist.destroy();
  chartDist = new Chart(document.getElementById('chart-dist'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Trips',
        data: bins,
        backgroundColor: 'rgba(61,214,140,0.55)',
        borderColor: '#3dd68c',
        borderWidth: 1,
        borderRadius: 2,
      }],
    },
    options: {
      ...CHART_DEFAULTS,
      scales: {
        x: { ...CHART_DEFAULTS.scales.x,
          title: { display: true, text: 'Miles', color: '#555e7a', font: { size: 11 } } },
        y: { ...CHART_DEFAULTS.scales.y },
      },
    },
  });
}

/* ═══════════════════════════════════════════════════
   7. TABLE
═══════════════════════════════════════════════════ */
function renderTable() {
  const total = state.filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  state.page = Math.min(state.page, totalPages);

  const start = (state.page - 1) * PAGE_SIZE;
  const pageTrips = state.filtered.slice(start, start + PAGE_SIZE);

  document.getElementById('table-count').textContent =
    total.toLocaleString() + ' trip' + (total !== 1 ? 's' : '');

  const tbody = document.getElementById('trips-tbody');
  if (!pageTrips.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="table-empty">No trips match the current filters.</td></tr>';
    document.getElementById('pagination').innerHTML = '';
    return;
  }

  tbody.innerHTML = pageTrips.map(t => `
    <tr>
      <td>${formatDateTime(t.tpep_pickup_datetime)}</td>
      <td>${t.pu_borough || '—'}</td>
      <td>${parseFloat(t.trip_distance).toFixed(1)}</td>
      <td>$${parseFloat(t.fare_amount).toFixed(2)}</td>
      <td>$${parseFloat(t.tip_amount ?? 0).toFixed(2)}</td>
      <td>$${parseFloat(t.total_amount).toFixed(2)}</td>
      <td>${paymentBadge(t.payment_type)}</td>
    </tr>
  `).join('');

  renderPagination(tota