"""
Project 3 — Quality Monitoring Alert System
Day 2: ML-Based Anomaly Detection

Context: Apple PQE — Pohang facility
Instead of fixed control limits (Day 1), we now use:
  1. Rolling Z-score   → detects sudden spikes
  2. Isolation Forest  → ML model that learns what "normal" looks like
                         and flags anything that doesn't fit

Why this matters:
Fixed SPC rules miss subtle multi-variable anomalies.
ML catches patterns a human wouldn't notice —
e.g., solder volume is fine AND temp is fine individually,
but their COMBINATION is unusual → bad joint incoming.

Author: [Your Name]
Role Context: Apple PQE Intern Candidate
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────
# 1. LOAD DAY 1 DATA
# ─────────────────────────────────────────────

def load_data():
    """Load the shift data generated on Day 1."""
    try:
        df = pd.read_csv('day1_shift_data.csv', parse_dates=['timestamp'])
        print(f"   ✅ Loaded {len(df)} samples from Day 1")
        return df
    except FileNotFoundError:
        print("   ❌ day1_shift_data.csv not found!")
        print("   → Run project3_day1_simulator.py first")
        exit()


# ─────────────────────────────────────────────
# 2. ROLLING Z-SCORE DETECTOR
# ─────────────────────────────────────────────

class RollingZScoreDetector:
    """
    Detects anomalies using a rolling window Z-score.

    Real Apple context:
    Instead of using the ENTIRE shift's mean (which gets
    pulled by drift), we use a rolling window of the last
    N samples. This makes the detector adaptive —
    it adjusts to slow drift but still catches sudden spikes.

    Z-score = (current value - rolling mean) / rolling std
    If |Z| > threshold → anomaly
    """

    def __init__(self, window=20, threshold=2.8):
        self.window = window        # look at last 20 samples
        self.threshold = threshold  # flag if > 2.8 standard deviations away

    def detect(self, series, kpi_name):
        """Returns a DataFrame with anomaly flags and Z-scores."""
        rolling_mean = series.rolling(window=self.window, min_periods=5).mean()
        rolling_std  = series.rolling(window=self.window, min_periods=5).std()

        z_scores = (series - rolling_mean) / rolling_std.replace(0, np.nan)
        is_anomaly = z_scores.abs() > self.threshold

        result = pd.DataFrame({
            'value': series,
            'rolling_mean': rolling_mean,
            'rolling_std': rolling_std,
            'z_score': z_scores,
            'zscore_anomaly': is_anomaly,
            'kpi': kpi_name
        })

        return result


# ─────────────────────────────────────────────
# 3. ISOLATION FOREST DETECTOR
# ─────────────────────────────────────────────

class IsolationForestDetector:
    """
    ML-based anomaly detection using Isolation Forest.

    How it works (simple):
    Imagine randomly drawing lines to "isolate" each data point.
    Normal points need MANY cuts to isolate (they're clustered).
    Anomalies need very FEW cuts (they're already alone).
    The model scores each point — low score = anomaly.

    Why it's powerful for Apple PQE:
    It looks at ALL 3 KPIs TOGETHER.
    So it catches cases where individual values look fine
    but their combination is abnormal —
    e.g., high temp + low solder volume at the same time
    = likely bad joint, even if each is within spec alone.
    """

    def __init__(self, contamination=0.05):
        # contamination = expected % of anomalies in data (5% here)
        self.model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100
        )
        self.scaler = StandardScaler()

    def fit_detect(self, df, feature_cols):
        """Train on data and return anomaly labels."""
        X = df[feature_cols].values
        X_scaled = self.scaler.fit_transform(X)

        # -1 = anomaly, 1 = normal (sklearn convention)
        labels = self.model.fit_predict(X_scaled)
        scores = self.model.score_samples(X_scaled)  # lower = more anomalous

        return labels, scores


# ─────────────────────────────────────────────
# 4. ALERT SEVERITY CLASSIFIER
# ─────────────────────────────────────────────

def classify_severity(z_score, if_label, value, usl, lsl):
    """
    Combines Z-score + Isolation Forest to assign severity.

    Priority logic (mirrors Apple's escalation policy):
    CRITICAL → out of spec OR both detectors agree it's anomalous
    WARNING  → one detector flags it, still within spec
    WATCH    → borderline Z-score, in spec
    NORMAL   → no flags
    """
    out_of_spec = value > usl or value < lsl
    z_flag = abs(z_score) > 2.8 if not np.isnan(z_score) else False
    if_flag = if_label == -1

    if out_of_spec or (z_flag and if_flag):
        return 'CRITICAL'
    elif z_flag or if_flag:
        return 'WARNING'
    elif abs(z_score) > 2.0 if not np.isnan(z_score) else False:
        return 'WATCH'
    else:
        return 'NORMAL'


# ─────────────────────────────────────────────
# 5. FULL ANALYSIS PIPELINE
# ─────────────────────────────────────────────

def run_analysis(df):
    """Run both detectors on all KPIs and combine results."""

    kpis = {
        'solder_volume_um3':      {'usl': 1150, 'lsl': 850,  'label': 'Solder Volume (μm³)'},
        'reflow_peak_temp_C':     {'usl': 255,  'lsl': 235,  'label': 'Reflow Peak Temp (°C)'},
        'bond_pull_strength_gf':  {'usl': 110,  'lsl': 50,   'label': 'Bond Pull Strength (gf)'}
    }

    # Isolation Forest on all 3 KPIs together (multi-variable)
    print("   Running Isolation Forest (multi-variable)...")
    ifd = IsolationForestDetector(contamination=0.05)
    if_labels, if_scores = ifd.fit_detect(df, list(kpis.keys()))
    df['if_label'] = if_labels
    df['if_score'] = if_scores

    # Rolling Z-score per KPI
    zsd = RollingZScoreDetector(window=20, threshold=2.8)
    results = {}

    for kpi, spec in kpis.items():
        print(f"   Running Z-score detector on {kpi}...")
        res = zsd.detect(df[kpi], kpi)
        res['if_label'] = if_labels
        res['if_score'] = if_scores
        res['sample_id'] = df['sample_id'].values
        res['timestamp'] = df['timestamp'].values

        # Classify each sample
        res['severity'] = res.apply(
            lambda row: classify_severity(
                row['z_score'], row['if_label'],
                row['value'], spec['usl'], spec['lsl']
            ), axis=1
        )

        results[kpi] = (res, spec)

    return results, df


# ─────────────────────────────────────────────
# 6. ALERT LOG
# ─────────────────────────────────────────────

def print_alert_log(results):
    """Print structured alert log — simulates what gets sent to engineer."""

    print("\n" + "="*65)
    print("  APPLE PQE — ML ANOMALY DETECTION REPORT")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Detectors: Rolling Z-Score + Isolation Forest")
    print("="*65)

    all_alerts = []

    for kpi, (res, spec) in results.items():
        critical = res[res['severity'] == 'CRITICAL']
        warning  = res[res['severity'] == 'WARNING']
        watch    = res[res['severity'] == 'WATCH']

        print(f"\n📊 {kpi.upper()}")
        print(f"   🔴 CRITICAL: {len(critical)} samples")
        print(f"   🟡 WARNING:  {len(warning)} samples")
        print(f"   👀 WATCH:    {len(watch)} samples")

        if len(critical) > 0:
            print(f"   First critical at sample #{int(critical.iloc[0]['sample_id'])}, "
                  f"value: {critical.iloc[0]['value']:.2f}")

        for _, row in critical.iterrows():
            all_alerts.append({
                'timestamp': row['timestamp'],
                'sample_id': int(row['sample_id']),
                'kpi': kpi,
                'value': row['value'],
                'z_score': round(row['z_score'], 2),
                'if_score': round(row['if_score'], 3),
                'severity': row['severity']
            })

    print("\n" + "="*65)
    print("  TOP 5 MOST ANOMALOUS SAMPLES (by Isolation Forest score)")
    print("="*65)

    alert_df = pd.DataFrame(all_alerts)
    if len(alert_df) > 0:
        top5 = alert_df.nsmallest(5, 'if_score')
        for _, row in top5.iterrows():
            print(f"  🔴 Sample #{row['sample_id']:3d} | {row['kpi']:30s} | "
                  f"Value: {row['value']:7.2f} | Z: {row['z_score']:5.2f} | "
                  f"IF Score: {row['if_score']:.3f}")

    print("="*65)
    return alert_df


# ─────────────────────────────────────────────
# 7. VISUALIZATION
# ─────────────────────────────────────────────

def plot_anomaly_dashboard(results, df):
    """
    3-panel dashboard showing:
    - Raw signal with anomalies highlighted by severity
    - Z-score over time
    - Isolation Forest anomaly score
    """

    kpis = list(results.keys())
    labels = ['Solder Volume (μm³)', 'Reflow Peak Temp (°C)', 'Bond Pull Strength (gf)']

    fig = plt.figure(figsize=(18, 15))
    fig.patch.set_facecolor('#0a0a0f')

    plt.suptitle(
        'Apple PQE — ML Anomaly Detection Dashboard | Pohang SMT Line A',
        fontsize=14, fontweight='bold', color='white', y=0.99
    )

    severity_colors = {
        'CRITICAL': '#FF3B30',
        'WARNING':  '#FF9500',
        'WATCH':    '#FFD60A',
        'NORMAL':   '#3A3A3C'
    }
    severity_sizes = {'CRITICAL': 80, 'WARNING': 50, 'WATCH': 25, 'NORMAL': 8}

    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.3)

    for idx, (kpi, label) in enumerate(zip(kpis, labels)):
        res, spec = results[kpi]
        x = res['sample_id'].values

        # Panel A: Raw signal + severity
        ax1 = fig.add_subplot(gs[idx, 0:2])
        ax1.set_facecolor('#12121a')

        ax1.plot(x, res['value'], color='#636366', linewidth=0.8, zorder=2)
        ax1.plot(x, res['rolling_mean'], color='#00D4FF',
                 linewidth=1.2, linestyle='--', alpha=0.8, label='Rolling Mean', zorder=3)

        for severity, color in severity_colors.items():
            mask = res['severity'] == severity
            if mask.any():
                ax1.scatter(x[mask], res['value'][mask],
                           color=color, s=severity_sizes[severity],
                           zorder=4, label=severity,
                           edgecolors='white' if severity == 'CRITICAL' else 'none',
                           linewidth=0.5)

        ax1.axhline(spec['usl'], color='#FF3B30', linewidth=1,
                   linestyle=':', alpha=0.7, label=f"USL: {spec['usl']}")
        ax1.axhline(spec['lsl'], color='#FF3B30', linewidth=1,
                   linestyle=':', alpha=0.7, label=f"LSL: {spec['lsl']}")

        ax1.set_title(label, fontsize=10, fontweight='bold',
                     color='#E5E5EA', pad=5)
        ax1.set_xlabel('Sample #', fontsize=7, color='#8E8E93')
        ax1.tick_params(colors='#8E8E93', labelsize=7)
        for spine in ['top', 'right']:
            ax1.spines[spine].set_visible(False)
        for spine in ['bottom', 'left']:
            ax1.spines[spine].set_color('#2C2C2E')

        n_crit = (res['severity'] == 'CRITICAL').sum()
        n_warn = (res['severity'] == 'WARNING').sum()
        ax1.text(0.01, 0.95,
                f"🔴 {n_crit} Critical  🟡 {n_warn} Warning",
                transform=ax1.transAxes, fontsize=7.5,
                color='#E5E5EA', verticalalignment='top',
                bbox=dict(boxstyle='round,pad=0.3',
                         facecolor='#1C1C1E', alpha=0.85))

        ax1.legend(loc='upper right', fontsize=6, ncol=3,
                  facecolor='#1C1C1E', edgecolor='#2C2C2E',
                  labelcolor='#E5E5EA')

        # Panel B: Z-score
        ax2 = fig.add_subplot(gs[idx, 2])
        ax2.set_facecolor('#12121a')

        z = res['z_score'].values
        colors_z = ['#FF3B30' if abs(v) > 2.8 else
                   '#FF9500' if abs(v) > 2.0 else
                   '#30D158' for v in z]

        ax2.bar(x, z, color=colors_z, alpha=0.7, width=1.0)
        ax2.axhline(2.8,  color='#FF3B30', linewidth=1, linestyle='--', alpha=0.7)
        ax2.axhline(-2.8, color='#FF3B30', linewidth=1, linestyle='--', alpha=0.7)
        ax2.axhline(0,    color='#636366', linewidth=0.8)

        ax2.set_title('Z-Score', fontsize=9, color='#E5E5EA', pad=5)
        ax2.set_xlabel('Sample #', fontsize=7, color='#8E8E93')
        ax2.tick_params(colors='#8E8E93', labelsize=7)
        for spine in ['top', 'right']:
            ax2.spines[spine].set_visible(False)
        for spine in ['bottom', 'left']:
            ax2.spines[spine].set_color('#2C2C2E')

    plt.savefig('day2_anomaly_dashboard.png',
                dpi=150, bbox_inches='tight', facecolor='#0a0a0f')
    plt.show()
    print("✅ Chart saved: day2_anomaly_dashboard.png")


# ─────────────────────────────────────────────
# 8. MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("🍎 Apple PQE — ML Anomaly Detection")
    print("   Day 2: Rolling Z-Score + Isolation Forest")
    print("─" * 50)

    print("\n[1/4] Loading Day 1 data...")
    df = load_data()

    print("\n[2/4] Running anomaly detectors...")
    results, df = run_analysis(df)

    print("\n[3/4] Generating alert log...")
    alert_df = print_alert_log(results)

    print("\n[4/4] Rendering dashboard...")
    plot_anomaly_dashboard(results, df)

    # Save for Day 3
    alert_df.to_csv('day2_alerts_ml.csv', index=False)
    print("\n✅ Day 2 complete! Files saved:")
    print("   • day2_anomaly_dashboard.png")
    print("   • day2_alerts_ml.csv  (use in Day 3 for database logging)")
