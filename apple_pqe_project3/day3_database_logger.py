"""
Project 3 — Quality Monitoring Alert System
Day 3: SQLite Database Logger

Context: Apple PQE — Pohang facility
Every alert detected by Day 1 (SPC) and Day 2 (ML) now gets
logged permanently into a database. This enables:
  - Trend analysis across multiple shifts
  - Traceability (which operator, which machine, which batch)
  - Audit trail for Apple's supplier quality reviews
  - Foundation for the live dashboard (Day 5)

Real Apple context:
Manufacturing execution systems (MES) at Apple supplier sites
log every process event to a database. PQEs query this data
to find patterns — e.g., "Monday morning shifts always have
more solder volume violations" → operator training issue.

Author: [Your Name]
Role Context: Apple PQE Intern Candidate
"""

import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from datetime import datetime, timedelta
import os
import warnings
warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────
# 1. DATABASE SETUP
# ─────────────────────────────────────────────

class QualityDatabase:
    """
    SQLite database for quality alert logging.

    Tables:
    - shifts       : one row per production shift
    - samples      : every sensor reading (240 per shift)
    - alerts       : every violation detected
    - summary      : shift-level Cpk and stats

    Real Apple context:
    This mirrors the structure of MES databases used at
    Apple's contract manufacturers. PQEs write SQL queries
    to pull reports like "show me all CRITICAL alerts
    from Line A in the last 7 days."
    """

    def __init__(self, db_path='apple_pqe_quality.db'):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self._create_tables()
        print(f"   ✅ Database connected: {db_path}")

    def _create_tables(self):
        """Create all tables if they don't exist."""

        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS shifts (
                shift_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                date         TEXT,
                shift_name   TEXT,
                line         TEXT,
                operator     TEXT,
                total_samples INTEGER,
                created_at   TEXT
            );

            CREATE TABLE IF NOT EXISTS samples (
                sample_id         INTEGER,
                shift_id          INTEGER,
                timestamp         TEXT,
                operator          TEXT,
                solder_volume     REAL,
                reflow_temp       REAL,
                bond_strength     REAL,
                FOREIGN KEY (shift_id) REFERENCES shifts(shift_id)
            );

            CREATE TABLE IF NOT EXISTS alerts (
                alert_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_id     INTEGER,
                sample_id    INTEGER,
                timestamp    TEXT,
                kpi          TEXT,
                value        REAL,
                severity     TEXT,
                detector     TEXT,
                z_score      REAL,
                if_score     REAL,
                acknowledged INTEGER DEFAULT 0,
                created_at   TEXT,
                FOREIGN KEY (shift_id) REFERENCES shifts(shift_id)
            );

            CREATE TABLE IF NOT EXISTS summary (
                summary_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_id     INTEGER,
                kpi          TEXT,
                mean_value   REAL,
                std_value    REAL,
                cpk          REAL,
                n_critical   INTEGER,
                n_warning    INTEGER,
                n_watch      INTEGER,
                created_at   TEXT,
                FOREIGN KEY (shift_id) REFERENCES shifts(shift_id)
            );
        """)
        self.conn.commit()

    def log_shift(self, date, shift_name, line, operator, total_samples):
        """Register a new production shift."""
        self.cursor.execute("""
            INSERT INTO shifts (date, shift_name, line, operator, total_samples, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (date, shift_name, line, operator, total_samples,
              datetime.now().isoformat()))
        self.conn.commit()
        return self.cursor.lastrowid

    def log_samples(self, shift_id, df):
        """Bulk insert all sensor readings for a shift."""
        records = []
        for _, row in df.iterrows():
            records.append((
                int(row['sample_id']), shift_id,
                str(row['timestamp']), row['operator'],
                row['solder_volume_um3'],
                row['reflow_peak_temp_C'],
                row['bond_pull_strength_gf']
            ))
        self.cursor.executemany("""
            INSERT INTO samples
            (sample_id, shift_id, timestamp, operator,
             solder_volume, reflow_temp, bond_strength)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, records)
        self.conn.commit()
        print(f"   ✅ Logged {len(records)} samples")

    def log_alert(self, shift_id, sample_id, timestamp, kpi,
                  value, severity, detector, z_score=None, if_score=None):
        """Log a single quality alert."""
        self.cursor.execute("""
            INSERT INTO alerts
            (shift_id, sample_id, timestamp, kpi, value,
             severity, detector, z_score, if_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (shift_id, sample_id, str(timestamp), kpi, value,
              severity, detector, z_score, if_score,
              datetime.now().isoformat()))
        self.conn.commit()

    def log_summary(self, shift_id, kpi, mean, std, cpk,
                    n_critical, n_warning, n_watch):
        """Log shift-level summary statistics."""
        self.cursor.execute("""
            INSERT INTO summary
            (shift_id, kpi, mean_value, std_value, cpk,
             n_critical, n_warning, n_watch, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (shift_id, kpi, mean, std, cpk,
              n_critical, n_warning, n_watch,
              datetime.now().isoformat()))
        self.conn.commit()

    def query(self, sql, params=()):
        """Run any SQL query and return as DataFrame."""
        return pd.read_sql_query(sql, self.conn, params=params)

    def close(self):
        self.conn.close()


# ─────────────────────────────────────────────
# 2. SIMULATE MULTIPLE SHIFTS
# ─────────────────────────────────────────────

def simulate_multi_shift_data(n_shifts=5):
    """
    Simulate 5 shifts of production data.
    Each shift has slightly different process conditions —
    mimics real factory variation across days/operators.
    """
    import sys
    sys.path.insert(0, '.')

    shifts = []
    shift_names = ['Day', 'Night', 'Day', 'Night', 'Day']
    operators   = ['Kim_J', 'Park_S', 'Lee_H', 'Kim_J', 'Park_S']
    base_date   = datetime(2024, 3, 15)

    specs = {
        'solder_volume_um3':     {'target': 1000, 'usl': 1150, 'lsl': 850,  'std': 35},
        'reflow_peak_temp_C':    {'target': 245,  'usl': 255,  'lsl': 235,  'std': 2.5},
        'bond_pull_strength_gf': {'target': 80,   'usl': 110,  'lsl': 50,   'std': 5}
    }

    for i in range(n_shifts):
        np.random.seed(i * 10)
        n = 240
        date = base_date + timedelta(days=i//2)
        timestamps = [date + timedelta(minutes=2*j) for j in range(n)]

        data = {'timestamp': timestamps,
                'sample_id': range(1, n+1),
                'shift': shift_names[i],
                'operator': operators[i]}

        # Each shift has different severity of process issues
        drift_severity = [2.5, 1.5, 3.0, 1.0, 2.0][i]

        for kpi, spec in specs.items():
            vals = np.random.normal(spec['target'], spec['std'], n)
            drift_start = int(n * 0.6)
            vals[drift_start:] += np.linspace(0, spec['std'] * drift_severity,
                                               n - drift_start)
            spike_idx = np.random.choice(n, 5, replace=False)
            vals[spike_idx] += np.random.choice([-1,1], 5) * spec['std'] * 3.2
            data[kpi] = np.round(vals, 2)

        shifts.append((pd.DataFrame(data), shift_names[i], operators[i],
                       date.strftime('%Y-%m-%d')))

    return shifts, specs


# ─────────────────────────────────────────────
# 3. PROCESS AND LOG ALL SHIFTS
# ─────────────────────────────────────────────

def calculate_cpk(values, usl, lsl):
    mean = np.mean(values)
    std  = np.std(values, ddof=1)
    if std == 0:
        return 0
    return round(min((usl - mean)/(3*std), (mean - lsl)/(3*std)), 3)

def detect_alerts(df, specs):
    """Simple Z-score detection for multi-shift logging."""
    alerts = []
    for kpi, spec in specs.items():
        vals   = df[kpi].values
        mean   = np.mean(vals[:30])
        std    = np.std(vals[:30], ddof=1) or 1
        z_scores = (vals - mean) / std

        for i, (v, z) in enumerate(zip(vals, z_scores)):
            out_of_spec = v > spec['usl'] or v < spec['lsl']
            if abs(z) > 2.8 or out_of_spec:
                severity = 'CRITICAL' if (out_of_spec or abs(z) > 3.5) else 'WARNING'
                alerts.append({
                    'sample_id': int(df['sample_id'].iloc[i]),
                    'timestamp': df['timestamp'].iloc[i],
                    'kpi': kpi, 'value': round(v, 2),
                    'severity': severity, 'detector': 'Z-Score',
                    'z_score': round(z, 3), 'if_score': None
                })
    return alerts


def populate_database(db):
    """Simulate 5 shifts and log everything to the database."""
    print("   Simulating 5 production shifts...")
    shifts, specs = simulate_multi_shift_data(n_shifts=5)

    for shift_df, shift_name, operator, date in shifts:
        # Log shift
        shift_id = db.log_shift(
            date=date, shift_name=shift_name,
            line='Pohang_SMT_LineA', operator=operator,
            total_samples=len(shift_df)
        )

        # Log samples
        db.log_samples(shift_id, shift_df)

        # Detect and log alerts
        alerts = detect_alerts(shift_df, specs)
        for a in alerts:
            db.log_alert(
                shift_id=shift_id,
                sample_id=a['sample_id'],
                timestamp=a['timestamp'],
                kpi=a['kpi'],
                value=a['value'],
                severity=a['severity'],
                detector=a['detector'],
                z_score=a['z_score'],
                if_score=a['if_score']
            )

        # Log summary stats
        for kpi, spec in specs.items():
            vals = shift_df[kpi].values
            cpk  = calculate_cpk(vals, spec['usl'], spec['lsl'])
            kpi_alerts = [a for a in alerts if a['kpi'] == kpi]
            db.log_summary(
                shift_id=shift_id, kpi=kpi,
                mean=round(np.mean(vals), 2),
                std=round(np.std(vals), 2),
                cpk=cpk,
                n_critical=sum(1 for a in kpi_alerts if a['severity']=='CRITICAL'),
                n_warning =sum(1 for a in kpi_alerts if a['severity']=='WARNING'),
                n_watch   =0
            )

        print(f"   ✅ Shift logged: {date} {shift_name} | "
              f"Operator: {operator} | Alerts: {len(alerts)}")

    return specs


# ─────────────────────────────────────────────
# 4. ANALYTICS QUERIES
# ─────────────────────────────────────────────

def run_analytics(db):
    """
    Real SQL queries a PQE engineer would run.
    This is what you show in your portfolio and interview.
    """

    print("\n" + "="*65)
    print("  APPLE PQE — DATABASE ANALYTICS REPORT")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*65)

    # Query 1: Alert summary by KPI
    q1 = db.query("""
        SELECT kpi,
               severity,
               COUNT(*) as count
        FROM alerts
        GROUP BY kpi, severity
        ORDER BY kpi, severity
    """)
    print("\n📊 QUERY 1: Alert counts by KPI and severity")
    print(q1.to_string(index=False))

    # Query 2: Cpk trend across shifts
    q2 = db.query("""
        SELECT s.date, s.shift_name, s.operator,
               sm.kpi, sm.cpk, sm.n_critical
        FROM summary sm
        JOIN shifts s ON sm.shift_id = s.shift_id
        ORDER BY s.shift_id, sm.kpi
    """)
    print("\n📊 QUERY 2: Cpk trend across shifts")
    print(q2.to_string(index=False))

    # Query 3: Worst operator (most critical alerts)
    q3 = db.query("""
        SELECT s.operator,
               COUNT(*) as total_critical
        FROM alerts a
        JOIN shifts s ON a.shift_id = s.shift_id
        WHERE a.severity = 'CRITICAL'
        GROUP BY s.operator
        ORDER BY total_critical DESC
    """)
    print("\n📊 QUERY 3: Critical alerts by operator")
    print(q3.to_string(index=False))

    # Query 4: Most problematic time window
    q4 = db.query("""
        SELECT CAST(sample_id/30 AS INT) * 30 as sample_window,
               COUNT(*) as alerts,
               severity
        FROM alerts
        WHERE severity = 'CRITICAL'
        GROUP BY sample_window
        ORDER BY alerts DESC
        LIMIT 5
    """)
    print("\n📊 QUERY 4: Highest alert density (sample windows)")
    print(q4.to_string(index=False))

    return q1, q2, q3, q4


# ─────────────────────────────────────────────
# 5. VISUALIZATION
# ─────────────────────────────────────────────

def plot_database_analytics(db):
    """4-panel analytics dashboard from database queries."""

    fig = plt.figure(figsize=(16, 12))
    fig.patch.set_facecolor('#0a0a0f')
    plt.suptitle(
        'Apple PQE — Multi-Shift Database Analytics | Pohang SMT Line A',
        fontsize=13, fontweight='bold', color='white', y=0.99
    )

    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35)
    axes = [fig.add_subplot(gs[i//2, i%2]) for i in range(4)]
    for ax in axes:
        ax.set_facecolor('#12121a')
        for spine in ['top','right']:
            ax.spines[spine].set_visible(False)
        for spine in ['bottom','left']:
            ax.spines[spine].set_color('#2C2C2E')
        ax.tick_params(colors='#8E8E93', labelsize=8)

    kpi_short = {
        'solder_volume_um3':     'Solder Vol',
        'reflow_peak_temp_C':    'Reflow Temp',
        'bond_pull_strength_gf': 'Bond Strength'
    }

    # Chart 1: Alerts by KPI and severity
    ax = axes[0]
    q = db.query("""
        SELECT kpi, severity, COUNT(*) as count
        FROM alerts GROUP BY kpi, severity
    """)
    kpis = q['kpi'].unique()
    x = np.arange(len(kpis))
    w = 0.25
    colors = {'CRITICAL': '#FF3B30', 'WARNING': '#FF9500'}
    for j, sev in enumerate(['CRITICAL', 'WARNING']):
        counts = [q[(q['kpi']==k) & (q['severity']==sev)]['count'].sum()
                  for k in kpis]
        ax.bar(x + j*w, counts, w, label=sev,
               color=colors[sev], alpha=0.85)
    ax.set_xticks(x + w/2)
    ax.set_xticklabels([kpi_short.get(k, k) for k in kpis],
                       color='#E5E5EA', fontsize=8)
    ax.set_title('Alerts by KPI & Severity', color='#E5E5EA',
                fontsize=10, fontweight='bold')
    ax.legend(facecolor='#1C1C1E', edgecolor='#2C2C2E',
             labelcolor='#E5E5EA', fontsize=8)
    ax.set_ylabel('Count', color='#8E8E93', fontsize=8)

    # Chart 2: Cpk trend across shifts
    ax = axes[1]
    q2 = db.query("""
        SELECT s.shift_id, sm.kpi, sm.cpk
        FROM summary sm JOIN shifts s ON sm.shift_id = s.shift_id
        ORDER BY s.shift_id
    """)
    kpi_colors = {'solder_volume_um3': '#00D4FF',
                  'reflow_peak_temp_C': '#FF9500',
                  'bond_pull_strength_gf': '#30D158'}
    for kpi, color in kpi_colors.items():
        subset = q2[q2['kpi'] == kpi]
        ax.plot(subset['shift_id'], subset['cpk'], 'o-',
               color=color, linewidth=1.5, markersize=5,
               label=kpi_short[kpi])
    ax.axhline(1.33, color='#FF3B30', linestyle='--',
              linewidth=1, alpha=0.7, label='Min Cpk (1.33)')
    ax.set_title('Cpk Trend Across Shifts', color='#E5E5EA',
                fontsize=10, fontweight='bold')
    ax.set_xlabel('Shift #', color='#8E8E93', fontsize=8)
    ax.set_ylabel('Cpk', color='#8E8E93', fontsize=8)
    ax.legend(facecolor='#1C1C1E', edgecolor='#2C2C2E',
             labelcolor='#E5E5EA', fontsize=7)

    # Chart 3: Alerts by operator
    ax = axes[2]
    q3 = db.query("""
        SELECT s.operator, a.severity, COUNT(*) as count
        FROM alerts a JOIN shifts s ON a.shift_id = s.shift_id
        GROUP BY s.operator, a.severity
    """)
    operators = q3['operator'].unique()
    x = np.arange(len(operators))
    for j, sev in enumerate(['CRITICAL', 'WARNING']):
        counts = [q3[(q3['operator']==op) & (q3['severity']==sev)]['count'].sum()
                  for op in operators]
        ax.bar(x + j*w, counts, w, label=sev,
               color=colors[sev], alpha=0.85)
    ax.set_xticks(x + w/2)
    ax.set_xticklabels(operators, color='#E5E5EA', fontsize=8)
    ax.set_title('Alerts by Operator', color='#E5E5EA',
                fontsize=10, fontweight='bold')
    ax.legend(facecolor='#1C1C1E', edgecolor='#2C2C2E',
             labelcolor='#E5E5EA', fontsize=8)
    ax.set_ylabel('Count', color='#8E8E93', fontsize=8)

    # Chart 4: Alert density over sample window
    ax = axes[3]
    q4 = db.query("""
        SELECT CAST(sample_id/10 AS INT)*10 as window,
               COUNT(*) as alerts
        FROM alerts WHERE severity='CRITICAL'
        GROUP BY window ORDER BY window
    """)
    ax.bar(q4['window'], q4['alerts'], width=8,
          color='#FF3B30', alpha=0.8)
    ax.set_title('Critical Alert Density Over Shift', color='#E5E5EA',
                fontsize=10, fontweight='bold')
    ax.set_xlabel('Sample Window', color='#8E8E93', fontsize=8)
    ax.set_ylabel('Critical Alerts', color='#8E8E93', fontsize=8)

    plt.savefig('day3_database_analytics.png',
               dpi=150, bbox_inches='tight', facecolor='#0a0a0f')
    plt.show()
    print("✅ Chart saved: day3_database_analytics.png")


# ─────────────────────────────────────────────
# 6. MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("🍎 Apple PQE — Database Logger")
    print("   Day 3: SQLite Multi-Shift Logging + Analytics")
    print("─" * 50)

    # Remove old DB if exists (fresh start)
    if os.path.exists('apple_pqe_quality.db'):
        os.remove('apple_pqe_quality.db')

    print("\n[1/4] Setting up database...")
    db = QualityDatabase('apple_pqe_quality.db')

    print("\n[2/4] Logging 5 shifts of production data...")
    specs = populate_database(db)

    print("\n[3/4] Running analytics queries...")
    run_analytics(db)

    print("\n[4/4] Rendering analytics dashboard...")
    plot_database_analytics(db)

    db.close()

    print("\n✅ Day 3 complete! Files saved:")
    print("   • apple_pqe_quality.db      (your quality database)")
    print("   • day3_database_analytics.png")
    print("\n💡 You can open apple_pqe_quality.db in DB Browser for SQLite")
    print("   to explore the data visually — free download at sqlitebrowser.org")
