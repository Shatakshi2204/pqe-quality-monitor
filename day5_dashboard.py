"""
Project 3 — Quality Monitoring Alert System
Day 5: Live Web Dashboard

Context: Apple PQE — Pohang facility
A browser-based dashboard that displays:
  - Live alert feed (CRITICAL / WARNING / WATCH)
  - Cpk trend across shifts
  - Alert breakdown by KPI and operator
  - Real-time stats summary

Tech stack:
  - Flask     : lightweight Python web server
  - Chart.js  : interactive charts in browser
  - SQLite    : reads from your Day 3 database
  - Auto-refresh every 30 seconds (simulates live feed)

Real Apple context:
Apple's supplier sites use MES dashboards on large screens
on the factory floor. Engineers glance at them to know
if any line needs attention. This is that dashboard.

Author: [Your Name]
Role Context: Apple PQE Intern Candidate
"""

from flask import Flask, render_template_string, jsonify
import sqlite3
import pandas as pd
from datetime import datetime
import os

app = Flask(__name__)
DB_PATH = 'apple_pqe_quality.db'

# ─────────────────────────────────────────────
# 1. DATABASE HELPERS
# ─────────────────────────────────────────────

def query_db(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df


def get_summary_stats():
    total_alerts  = query_db("SELECT COUNT(*) as n FROM alerts").iloc[0]['n']
    critical      = query_db("SELECT COUNT(*) as n FROM alerts WHERE severity='CRITICAL'").iloc[0]['n']
    warning       = query_db("SELECT COUNT(*) as n FROM alerts WHERE severity='WARNING'").iloc[0]['n']
    total_samples = query_db("SELECT SUM(total_samples) as n FROM shifts").iloc[0]['n']
    avg_cpk       = query_db("SELECT ROUND(AVG(cpk),3) as n FROM summary").iloc[0]['n']
    return {
        'total_alerts':  int(total_alerts),
        'critical':      int(critical),
        'warning':       int(warning),
        'total_samples': int(total_samples),
        'avg_cpk':       float(avg_cpk)
    }


def get_recent_alerts(limit=20):
    df = query_db(f"""
        SELECT a.alert_id, a.sample_id, a.timestamp,
               a.kpi, a.value, a.severity, a.detector,
               s.operator, s.shift_name, s.date
        FROM alerts a
        JOIN shifts s ON a.shift_id = s.shift_id
        ORDER BY a.alert_id DESC
        LIMIT {limit}
    """)
    return df.to_dict(orient='records')


def get_cpk_trend():
    df = query_db("""
        SELECT s.shift_id, s.date, s.shift_name,
               sm.kpi, sm.cpk
        FROM summary sm
        JOIN shifts s ON sm.shift_id = s.shift_id
        ORDER BY s.shift_id
    """)
    return df.to_dict(orient='records')


def get_alerts_by_kpi():
    df = query_db("""
        SELECT kpi, severity, COUNT(*) as count
        FROM alerts
        GROUP BY kpi, severity
        ORDER BY kpi, severity
    """)
    return df.to_dict(orient='records')


def get_alerts_by_operator():
    df = query_db("""
        SELECT s.operator, a.severity, COUNT(*) as count
        FROM alerts a
        JOIN shifts s ON a.shift_id = s.shift_id
        GROUP BY s.operator, a.severity
        ORDER BY s.operator
    """)
    return df.to_dict(orient='records')


# ─────────────────────────────────────────────
# 2. HTML DASHBOARD TEMPLATE
# ─────────────────────────────────────────────

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Apple PQE — Quality Monitor</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      font-family: -apple-system, 'SF Pro Display', Arial, sans-serif;
      background: #0a0a0f;
      color: #e5e5ea;
      min-height: 100vh;
    }

    /* ── Header ── */
    .header {
      background: linear-gradient(135deg, #1c1c1e 0%, #0a0a0f 100%);
      border-bottom: 1px solid #2c2c2e;
      padding: 18px 32px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky; top: 0; z-index: 100;
    }
    .header-left { display: flex; align-items: center; gap: 14px; }
    .apple-logo { font-size: 26px; }
    .header-title { font-size: 17px; font-weight: 700; color: #fff; }
    .header-sub { font-size: 12px; color: #8e8e93; margin-top: 2px; }
    .live-badge {
      display: flex; align-items: center; gap: 6px;
      background: #1c3a1c; border: 1px solid #30d158;
      border-radius: 20px; padding: 5px 12px;
      font-size: 12px; color: #30d158; font-weight: 600;
    }
    .live-dot {
      width: 7px; height: 7px; border-radius: 50%;
      background: #30d158;
      animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.8); }
    }

    /* ── Layout ── */
    .container { padding: 24px 32px; max-width: 1400px; margin: auto; }

    /* ── Stat Cards ── */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 14px; margin-bottom: 24px;
    }
    .stat-card {
      background: #1c1c1e;
      border: 1px solid #2c2c2e;
      border-radius: 12px;
      padding: 18px 20px;
      transition: transform 0.2s;
    }
    .stat-card:hover { transform: translateY(-2px); }
    .stat-label { font-size: 11px; color: #8e8e93; text-transform: uppercase;
                  letter-spacing: 0.5px; margin-bottom: 8px; }
    .stat-value { font-size: 28px; font-weight: 700; }
    .stat-critical { color: #ff3b30; }
    .stat-warning  { color: #ff9500; }
    .stat-normal   { color: #30d158; }
    .stat-blue     { color: #0a84ff; }
    .stat-white    { color: #ffffff; }

    /* ── Charts Grid ── */
    .charts-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px; margin-bottom: 24px;
    }
    .chart-card {
      background: #1c1c1e;
      border: 1px solid #2c2c2e;
      border-radius: 12px;
      padding: 20px;
    }
    .chart-title {
      font-size: 13px; font-weight: 700;
      color: #e5e5ea; margin-bottom: 16px;
      display: flex; align-items: center; gap: 8px;
    }
    .chart-wrap { position: relative; height: 220px; }

    /* ── Alert Feed ── */
    .alert-feed {
      background: #1c1c1e;
      border: 1px solid #2c2c2e;
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 24px;
    }
    .feed-header {
      display: flex; justify-content: space-between;
      align-items: center; margin-bottom: 16px;
    }
    .feed-title { font-size: 13px; font-weight: 700; color: #e5e5ea; }
    .feed-count { font-size: 11px; color: #8e8e93; }

    .alert-table { width: 100%; border-collapse: collapse; }
    .alert-table th {
      text-align: left; font-size: 11px; color: #8e8e93;
      text-transform: uppercase; letter-spacing: 0.5px;
      padding: 8px 12px; border-bottom: 1px solid #2c2c2e;
    }
    .alert-table td {
      padding: 10px 12px; font-size: 12px;
      border-bottom: 1px solid #1a1a1c;
    }
    .alert-table tr:hover td { background: #2c2c2e; }
    .alert-table tr:last-child td { border-bottom: none; }

    .badge {
      display: inline-block; padding: 3px 8px;
      border-radius: 6px; font-size: 10px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.5px;
    }
    .badge-CRITICAL { background: rgba(255,59,48,0.2);  color: #ff3b30;
                      border: 1px solid rgba(255,59,48,0.4); }
    .badge-WARNING  { background: rgba(255,149,0,0.2);  color: #ff9500;
                      border: 1px solid rgba(255,149,0,0.4); }
    .badge-WATCH    { background: rgba(255,214,10,0.2); color: #ffd60a;
                      border: 1px solid rgba(255,214,10,0.4); }

    .kpi-pill {
      display: inline-block; padding: 2px 8px;
      background: #2c2c2e; border-radius: 6px;
      font-size: 11px; color: #aeaeb2;
    }

    /* ── Footer ── */
    .footer {
      text-align: center; padding: 20px;
      font-size: 11px; color: #48484a;
      border-top: 1px solid #1c1c1e;
    }

    /* ── Refresh bar ── */
    .refresh-bar {
      height: 2px; background: #2c2c2e;
      margin-bottom: 20px; border-radius: 2px; overflow: hidden;
    }
    .refresh-progress {
      height: 100%; background: #0a84ff; width: 100%;
      animation: shrink 30s linear infinite;
    }
    @keyframes shrink { from { width: 100%; } to { width: 0%; } }
  </style>
</head>
<body>

  <!-- Header -->
  <div class="header">
    <div class="header-left">
      <div class="apple-logo"></div>
      <div>
        <div class="header-title">Product Quality Engineering — Monitor</div>
        <div class="header-sub">Pohang SMT Line A &nbsp;·&nbsp; <span id="clock"></span></div>
      </div>
    </div>
    <div class="live-badge">
      <div class="live-dot"></div>
      LIVE
    </div>
  </div>

  <div class="container">

    <!-- Refresh bar -->
    <div class="refresh-bar"><div class="refresh-progress"></div></div>

    <!-- Stat Cards -->
    <div class="stats-grid" id="stats-grid">
      <div class="stat-card">
        <div class="stat-label">Total Samples</div>
        <div class="stat-value stat-white" id="stat-samples">—</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Total Alerts</div>
        <div class="stat-value stat-blue" id="stat-total">—</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Critical</div>
        <div class="stat-value stat-critical" id="stat-critical">—</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Warning</div>
        <div class="stat-value stat-warning" id="stat-warning">—</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Avg Cpk</div>
        <div class="stat-value" id="stat-cpk"
             style="color:#30d158">—</div>
      </div>
    </div>

    <!-- Charts Row -->
    <div class="charts-grid">

      <div class="chart-card">
        <div class="chart-title">📈 Cpk Trend Across Shifts</div>
        <div class="chart-wrap">
          <canvas id="cpkChart"></canvas>
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-title">🔴 Alerts by KPI & Severity</div>
        <div class="chart-wrap">
          <canvas id="kpiChart"></canvas>
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-title">👷 Alerts by Operator</div>
        <div class="chart-wrap">
          <canvas id="operatorChart"></canvas>
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-title">📊 Alert Severity Distribution</div>
        <div class="chart-wrap">
          <canvas id="severityChart"></canvas>
        </div>
      </div>

    </div>

    <!-- Alert Feed -->
    <div class="alert-feed">
      <div class="feed-header">
        <div class="feed-title">⚡ Live Alert Feed</div>
        <div class="feed-count" id="feed-count">Loading...</div>
      </div>
      <table class="alert-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Time</th>
            <th>KPI</th>
            <th>Value</th>
            <th>Severity</th>
            <th>Detector</th>
            <th>Operator</th>
            <th>Shift</th>
          </tr>
        </thead>
        <tbody id="alert-tbody">
          <tr><td colspan="8" style="text-align:center;color:#8e8e93;
              padding:20px;">Loading alerts...</td></tr>
        </tbody>
      </table>
    </div>

  </div>

  <div class="footer">
    Apple PQE Quality Monitoring System &nbsp;·&nbsp;
    Pohang, Korea &nbsp;·&nbsp;
    Auto-refreshes every 30 seconds
  </div>

  <script>
    // ── Clock ──
    function updateClock() {
      document.getElementById('clock').textContent =
        new Date().toLocaleString('en-US', {
          weekday:'short', month:'short', day:'numeric',
          hour:'2-digit', minute:'2-digit', second:'2-digit'
        });
    }
    setInterval(updateClock, 1000);
    updateClock();

    // ── Chart defaults ──
    Chart.defaults.color = '#8e8e93';
    Chart.defaults.borderColor = '#2c2c2e';
    Chart.defaults.font.family = '-apple-system, Arial, sans-serif';
    Chart.defaults.font.size = 11;

    const KPI_SHORT = {
      'solder_volume_um3':     'Solder Vol',
      'reflow_peak_temp_C':    'Reflow Temp',
      'bond_pull_strength_gf': 'Bond Strength'
    };

    let cpkChart, kpiChart, operatorChart, severityChart;

    // ── Load all data ──
    async function loadDashboard() {
      const [stats, alerts, cpk, kpiData, opData] = await Promise.all([
        fetch('/api/stats').then(r => r.json()),
        fetch('/api/alerts').then(r => r.json()),
        fetch('/api/cpk').then(r => r.json()),
        fetch('/api/kpi_alerts').then(r => r.json()),
        fetch('/api/operator_alerts').then(r => r.json())
      ]);

      updateStats(stats);
      updateAlertFeed(alerts);
      renderCpkChart(cpk);
      renderKpiChart(kpiData);
      renderOperatorChart(opData);
      renderSeverityChart(kpiData);
    }

    // ── Stats ──
    function updateStats(s) {
      document.getElementById('stat-samples').textContent =
        s.total_samples.toLocaleString();
      document.getElementById('stat-total').textContent   = s.total_alerts;
      document.getElementById('stat-critical').textContent = s.critical;
      document.getElementById('stat-warning').textContent  = s.warning;
      const cpkEl = document.getElementById('stat-cpk');
      cpkEl.textContent = s.avg_cpk;
      cpkEl.style.color = s.avg_cpk >= 1.33 ? '#30d158' :
                          s.avg_cpk >= 1.0  ? '#ff9500' : '#ff3b30';
    }

    // ── Alert Feed ──
    function updateAlertFeed(alerts) {
      document.getElementById('feed-count').textContent =
        `Showing ${alerts.length} most recent`;
      const tbody = document.getElementById('alert-tbody');
      tbody.innerHTML = alerts.map(a => `
        <tr>
          <td style="color:#636366">#${a.alert_id}</td>
          <td style="color:#aeaeb2">${a.timestamp.slice(0,16)}</td>
          <td><span class="kpi-pill">${KPI_SHORT[a.kpi] || a.kpi}</span></td>
          <td style="font-weight:600">${parseFloat(a.value).toFixed(2)}</td>
          <td><span class="badge badge-${a.severity}">${a.severity}</span></td>
          <td style="color:#636366">${a.detector || 'SPC'}</td>
          <td>${a.operator}</td>
          <td style="color:#636366">${a.shift_name}</td>
        </tr>
      `).join('');
    }

    // ── Cpk Chart ──
    function renderCpkChart(data) {
      const kpis = ['solder_volume_um3','reflow_peak_temp_C','bond_pull_strength_gf'];
      const colors = ['#00d4ff','#ff9500','#30d158'];
      const shifts = [...new Set(data.map(d => `S${d.shift_id}`))];

      const datasets = kpis.map((kpi, i) => ({
        label: KPI_SHORT[kpi],
        data: shifts.map((_, si) => {
          const row = data.find(d => `S${d.shift_id}` === shifts[si] && d.kpi === kpi);
          return row ? row.cpk : null;
        }),
        borderColor: colors[i],
        backgroundColor: colors[i] + '22',
        tension: 0.4, pointRadius: 4,
        borderWidth: 2, fill: false
      }));

      if (cpkChart) cpkChart.destroy();
      cpkChart = new Chart(document.getElementById('cpkChart'), {
        type: 'line',
        data: { labels: shifts, datasets },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { position: 'top' } },
          scales: {
            y: {
              grid: { color: '#2c2c2e' },
              ticks: { color: '#8e8e93' }
            },
            x: { grid: { color: '#2c2c2e' }, ticks: { color: '#8e8e93' } }
          },
          annotation: {
            annotations: [{
              type: 'line', yMin: 1.33, yMax: 1.33,
              borderColor: '#ff3b30', borderDash: [4,4]
            }]
          }
        }
      });
    }

    // ── KPI Alerts Chart ──
    function renderKpiChart(data) {
      const kpis = [...new Set(data.map(d => d.kpi))];
      const severities = ['CRITICAL','WARNING'];
      const colors = { CRITICAL: '#ff3b30', WARNING: '#ff9500' };

      const datasets = severities.map(sev => ({
        label: sev,
        data: kpis.map(k => {
          const row = data.find(d => d.kpi===k && d.severity===sev);
          return row ? row.count : 0;
        }),
        backgroundColor: colors[sev] + 'cc',
        borderColor: colors[sev],
        borderWidth: 1, borderRadius: 4
      }));

      if (kpiChart) kpiChart.destroy();
      kpiChart = new Chart(document.getElementById('kpiChart'), {
        type: 'bar',
        data: { labels: kpis.map(k => KPI_SHORT[k] || k), datasets },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { position: 'top' } },
          scales: {
            y: { grid: { color: '#2c2c2e' }, ticks: { color: '#8e8e93' },
                 stacked: false },
            x: { grid: { color: '#2c2c2e' }, ticks: { color: '#8e8e93' } }
          }
        }
      });
    }

    // ── Operator Chart ──
    function renderOperatorChart(data) {
      const operators = [...new Set(data.map(d => d.operator))];
      const severities = ['CRITICAL','WARNING'];
      const colors = { CRITICAL: '#ff3b30', WARNING: '#ff9500' };

      const datasets = severities.map(sev => ({
        label: sev,
        data: operators.map(op => {
          const row = data.find(d => d.operator===op && d.severity===sev);
          return row ? row.count : 0;
        }),
        backgroundColor: colors[sev] + 'cc',
        borderColor: colors[sev],
        borderWidth: 1, borderRadius: 4
      }));

      if (operatorChart) operatorChart.destroy();
      operatorChart = new Chart(document.getElementById('operatorChart'), {
        type: 'bar',
        data: { labels: operators, datasets },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { position: 'top' } },
          scales: {
            y: { grid: { color: '#2c2c2e' }, ticks: { color: '#8e8e93' } },
            x: { grid: { color: '#2c2c2e' }, ticks: { color: '#8e8e93' } }
          }
        }
      });
    }

    // ── Severity Donut ──
    function renderSeverityChart(data) {
      const critical = data.filter(d=>d.severity==='CRITICAL')
                           .reduce((s,d)=>s+d.count,0);
      const warning  = data.filter(d=>d.severity==='WARNING')
                           .reduce((s,d)=>s+d.count,0);

      if (severityChart) severityChart.destroy();
      severityChart = new Chart(document.getElementById('severityChart'), {
        type: 'doughnut',
        data: {
          labels: ['Critical','Warning'],
          datasets: [{
            data: [critical, warning],
            backgroundColor: ['#ff3b30cc','#ff9500cc'],
            borderColor: ['#ff3b30','#ff9500'],
            borderWidth: 2, hoverOffset: 6
          }]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          cutout: '65%',
          plugins: {
            legend: { position: 'bottom' }
          }
        }
      });
    }

    // ── Auto refresh every 30s ──
    loadDashboard();
    setInterval(loadDashboard, 30000);
  </script>
</body>
</html>
"""

# ─────────────────────────────────────────────
# 3. FLASK ROUTES
# ─────────────────────────────────────────────

@app.route('/')
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/stats')
def api_stats():
    return jsonify(get_summary_stats())

@app.route('/api/alerts')
def api_alerts():
    return jsonify(get_recent_alerts(20))

@app.route('/api/cpk')
def api_cpk():
    return jsonify(get_cpk_trend())

@app.route('/api/kpi_alerts')
def api_kpi_alerts():
    return jsonify(get_alerts_by_kpi())

@app.route('/api/operator_alerts')
def api_operator_alerts():
    return jsonify(get_alerts_by_operator())


# ─────────────────────────────────────────────
# 4. MAIN
# ─────────────────────────────────────────────

if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        print("❌ Database not found!")
        print("   → Run day3_database_logger.py first")
        exit()

    print("🍎 Apple PQE — Live Web Dashboard")
    print("   Day 5: Flask Dashboard Server")
    print("─" * 50)
    print("\n✅ Dashboard starting...")
    print("   Open your browser and go to:")
    print("\n   👉  http://127.0.0.1:5000\n")
    print("   Press Ctrl+C to stop the server")
    print("─" * 50)

    app.run(debug=False, port=5000)