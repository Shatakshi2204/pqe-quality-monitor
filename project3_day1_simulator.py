"""
Project 3 — Quality Monitoring Alert System
Day 1: Manufacturing Data Simulator + SPC Foundation

Context: Apple PQE — Pohang facility monitors micro-joining process quality
(e.g., solder paste volume, reflow temperature, bond strength)
in real-time. This simulates that sensor data stream.

Author: [Your Name]
Role Context: Apple PQE Intern Candidate
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────
# 1. MANUFACTURING PROCESS SIMULATOR
# ─────────────────────────────────────────────

class ManufacturingDataSimulator:
    """
    Simulates sensor readings from a Surface Mount Technology (SMT) line.
    
    Real Apple context:
    - Solder paste volume (measured by SPI machine) must be within spec
    - Reflow oven temperature profiles affect joint quality
    - Bond pull strength (destructive test) validates micro-joining
    
    We simulate 3 KPIs (Key Process Indicators) over 8 hours of production.
    """
    
    def __init__(self, seed=42):
        np.random.seed(seed)
        self.process_specs = {
            'solder_volume_um3': {
                'target': 1000,   # target volume in cubic micrometers
                'usl': 1150,      # Upper Spec Limit
                'lsl': 850,       # Lower Spec Limit
                'natural_std': 35 # normal process variation (sigma)
            },
            'reflow_peak_temp_C': {
                'target': 245,
                'usl': 255,
                'lsl': 235,
                'natural_std': 2.5
            },
            'bond_pull_strength_gf': {
                'target': 80,
                'usl': 110,
                'lsl': 50,
                'natural_std': 5
            }
        }
    
    def generate_shift_data(self, hours=8, samples_per_hour=30):
        """
        Generate one production shift of data.
        Injects 3 types of real-world quality events:
          1. Gradual drift (oven temperature slowly rising — heater issue)
          2. Sudden shift (new solder paste batch — different viscosity)
          3. Random spikes (machine vibration, operator error)
        """
        n = hours * samples_per_hour
        timestamps = [datetime(2024, 3, 15, 8, 0) + timedelta(minutes=2*i) for i in range(n)]
        
        data = {'timestamp': timestamps}
        
        for kpi, spec in self.process_specs.items():
            values = self._generate_kpi_signal(n, spec, kpi)
            data[kpi] = values
        
        df = pd.DataFrame(data)
        df['sample_id'] = range(1, n + 1)
        df['shift'] = 'Day'
        df['operator'] = np.random.choice(['Kim_J', 'Park_S', 'Lee_H'], n)
        
        return df
    
    def _generate_kpi_signal(self, n, spec, kpi_name):
        """Generate realistic signal with injected anomalies."""
        target = spec['target']
        std = spec['natural_std']
        
        # Base: normal process noise (what you see on a control chart in spec)
        values = np.random.normal(target, std, n)
        
        # Anomaly 1: Gradual drift starting at 60% of shift
        # Real cause: oven calibration drift, paste viscosity change over time
        drift_start = int(n * 0.60)
        drift_magnitude = std * 2.5  # 2.5 sigma drift = process shift
        drift = np.linspace(0, drift_magnitude, n - drift_start)
        values[drift_start:] += drift
        
        # Anomaly 2: Sudden step change at 35% (e.g., new paste cartridge loaded)
        step_start = int(n * 0.35)
        step_end = int(n * 0.45)
        values[step_start:step_end] += std * 1.8
        
        # Anomaly 3: Random spikes (machine hiccups, measurement outliers)
        n_spikes = np.random.randint(3, 7)
        spike_idx = np.random.choice(n, n_spikes, replace=False)
        values[spike_idx] += np.random.choice([-1, 1], n_spikes) * std * 3.5
        
        return np.round(values, 2)


# ─────────────────────────────────────────────
# 2. SPC (STATISTICAL PROCESS CONTROL) ENGINE
# ─────────────────────────────────────────────

class SPCEngine:
    """
    Implements Western Electric Rules for control chart violations.
    
    Apple PQE context:
    SPC is how you detect that a process is going OUT OF CONTROL
    before it produces defective parts. Same concept used in
    Apple's supply chain audits of manufacturers like the
    Pohang facility.
    
    Control Limits (≠ Spec Limits):
    - Control limits = what the PROCESS naturally does (±3σ from mean)
    - Spec limits = what the CUSTOMER needs
    A process can be in control but out of spec (bad centering),
    or out of control but within spec (unpredictable, risky).
    """
    
    def __init__(self, baseline_samples=30):
        self.baseline_n = baseline_samples
    
    def calculate_control_limits(self, values):
        """Use first N samples as baseline (process assumed stable at start of shift)."""
        baseline = values[:self.baseline_n]
        mean = np.mean(baseline)
        std = np.std(baseline, ddof=1)
        
        return {
            'mean': mean,
            'ucl': mean + 3 * std,   # Upper Control Limit
            'lcl': mean - 3 * std,   # Lower Control Limit
            'ucl_1s': mean + std,    # 1-sigma zone
            'lcl_1s': mean - std,
            'ucl_2s': mean + 2 * std,
            'lcl_2s': mean - 2 * std,
            'std': std
        }
    
    def detect_violations(self, values, limits):
        """
        Western Electric Rules — industry standard for SPC alerts.
        Returns list of (index, rule_name, severity) tuples.
        """
        violations = []
        mean = limits['mean']
        std = limits['std']
        ucl = limits['ucl']
        lcl = limits['lcl']
        
        for i, v in enumerate(values):
            # Rule 1: Beyond 3σ — CRITICAL (immediate alert)
            if v > ucl or v < lcl:
                violations.append((i, 'Rule1_3sigma', 'CRITICAL'))
            
            # Rule 2: 2 of 3 consecutive beyond 2σ — WARNING
            if i >= 2:
                window = values[i-2:i+1]
                beyond_2s = sum(1 for x in window if abs(x - mean) > 2 * std)
                if beyond_2s >= 2:
                    violations.append((i, 'Rule2_2of3_2sigma', 'WARNING'))
            
            # Rule 3: 4 of 5 consecutive beyond 1σ — WARNING
            if i >= 4:
                window = values[i-4:i+1]
                beyond_1s = sum(1 for x in window if abs(x - mean) > std)
                if beyond_1s >= 4:
                    violations.append((i, 'Rule3_4of5_1sigma', 'WARNING'))
            
            # Rule 4: 8 consecutive on same side of mean — DRIFT ALERT
            if i >= 7:
                window = values[i-7:i+1]
                above = all(x > mean for x in window)
                below = all(x < mean for x in window)
                if above or below:
                    violations.append((i, 'Rule4_8consec_trend', 'DRIFT'))
        
        return violations
    
    def calculate_cpk(self, values, usl, lsl):
        """
        Cpk = Process Capability Index.
        Cpk > 1.33 = capable process (Apple typically requires ≥ 1.67)
        Cpk < 1.0  = process producing defects
        """
        mean = np.mean(values)
        std = np.std(values, ddof=1)
        cpu = (usl - mean) / (3 * std)
        cpl = (mean - lsl) / (3 * std)
        cpk = min(cpu, cpl)
        return round(cpk, 3)


# ─────────────────────────────────────────────
# 3. VISUALIZATION: CONTROL CHART DASHBOARD
# ─────────────────────────────────────────────

def plot_control_charts(df, spc, simulator):
    """
    Renders a 3-panel SPC control chart dashboard.
    This is the core visual output of a quality monitoring system.
    """
    
    kpis = list(simulator.process_specs.keys())
    kpi_labels = ['Solder Volume (μm³)', 'Reflow Peak Temp (°C)', 'Bond Pull Strength (gf)']
    
    fig, axes = plt.subplots(3, 1, figsize=(16, 14))
    fig.patch.set_facecolor('#0a0a0f')
    
    plt.suptitle(
        'Apple PQE — Quality Monitoring System | Pohang SMT Line A | Shift: Day',
        fontsize=14, fontweight='bold', color='white', y=0.98
    )
    
    color_map = {'CRITICAL': '#FF3B30', 'WARNING': '#FF9500', 'DRIFT': '#FFD60A'}
    
    for idx, (kpi, label) in enumerate(zip(kpis, kpi_labels)):
        ax = axes[idx]
        ax.set_facecolor('#12121a')
        
        values = df[kpi].values
        spec = simulator.process_specs[kpi]
        limits = spc.calculate_control_limits(values)
        violations = spc.detect_violations(values, limits)
        cpk = spc.calculate_cpk(values, spec['usl'], spec['lsl'])
        
        x = df['sample_id'].values
        
        # Plot zones (shaded σ bands)
        ax.fill_between(x, limits['lcl'], limits['ucl'], alpha=0.08, color='#00D4FF', label='±3σ zone')
        ax.fill_between(x, limits['lcl_2s'], limits['ucl_2s'], alpha=0.10, color='#30D158', label='±2σ zone')
        ax.fill_between(x, limits['lcl_1s'], limits['ucl_1s'], alpha=0.12, color='#34C759', label='±1σ zone')
        
        # Control lines
        ax.axhline(limits['mean'], color='#00D4FF', linewidth=1.5, linestyle='-', alpha=0.9, label=f"Mean: {limits['mean']:.1f}")
        ax.axhline(limits['ucl'], color='#FF9500', linewidth=1, linestyle='--', alpha=0.8, label=f"UCL: {limits['ucl']:.1f}")
        ax.axhline(limits['lcl'], color='#FF9500', linewidth=1, linestyle='--', alpha=0.8, label=f"LCL: {limits['lcl']:.1f}")
        
        # Spec limits
        ax.axhline(spec['usl'], color='#FF3B30', linewidth=1.5, linestyle=':', alpha=0.9, label=f"USL: {spec['usl']}")
        ax.axhline(spec['lsl'], color='#FF3B30', linewidth=1.5, linestyle=':', alpha=0.9, label=f"LSL: {spec['lsl']}")
        
        # Main data line
        ax.plot(x, values, color='white', linewidth=0.8, alpha=0.7, zorder=3)
        ax.scatter(x, values, color='#E5E5EA', s=8, alpha=0.6, zorder=4)
        
        # Violations
        viol_idx = set()
        for v_i, rule, severity in violations:
            if v_i not in viol_idx:
                ax.scatter(x[v_i], values[v_i],
                          color=color_map[severity], s=60, zorder=6,
                          edgecolors='white', linewidth=0.5)
                viol_idx.add(v_i)
        
        # Stats box
        n_critical = sum(1 for _, r, s in violations if s == 'CRITICAL')
        n_warning = sum(1 for _, r, s in violations if s == 'WARNING')
        n_drift = sum(1 for _, r, s in violations if s == 'DRIFT')
        
        cpk_color = '#30D158' if cpk >= 1.33 else ('#FF9500' if cpk >= 1.0 else '#FF3B30')
        stats_text = (f"Cpk: {cpk}  |  🔴 Critical: {n_critical}  "
                     f"🟡 Warning: {n_warning}  🟠 Drift: {n_drift}")
        
        ax.set_title(label, fontsize=11, fontweight='bold', color='#E5E5EA', pad=6)
        ax.set_xlabel('Sample #', fontsize=8, color='#8E8E93')
        ax.set_ylabel(label.split('(')[1].replace(')', '') if '(' in label else '', fontsize=8, color='#8E8E93')
        ax.tick_params(colors='#8E8E93', labelsize=7)
        ax.spines['bottom'].set_color('#2C2C2E')
        ax.spines['left'].set_color('#2C2C2E')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        # Cpk annotation
        ax.text(0.01, 0.92, stats_text, transform=ax.transAxes,
               fontsize=8, color=cpk_color, verticalalignment='top',
               bbox=dict(boxstyle='round,pad=0.3', facecolor='#1C1C1E', alpha=0.8))
        
        legend = ax.legend(loc='upper right', fontsize=6.5, ncol=4,
                          facecolor='#1C1C1E', edgecolor='#2C2C2E',
                          labelcolor='#E5E5EA')
    
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.savefig('day1_control_charts.png', 
                dpi=150, bbox_inches='tight', facecolor='#0a0a0f')
    plt.show()
    print("✅ Chart saved: day1_control_charts.png")


# ─────────────────────────────────────────────
# 4. ALERT REPORT GENERATOR
# ─────────────────────────────────────────────

def generate_alert_summary(df, spc, simulator):
    """Generate a structured alert report — simulates what gets sent to the engineer on call."""
    
    print("\n" + "="*65)
    print("  APPLE PQE — QUALITY ALERT SUMMARY REPORT")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Line: Pohang SMT Line A  |  Shift: Day")
    print("="*65)
    
    alert_log = []
    
    for kpi, spec in simulator.process_specs.items():
        values = df[kpi].values
        limits = spc.calculate_control_limits(values)
        violations = spc.detect_violations(values, limits)
        cpk = spc.calculate_cpk(values, spec['usl'], spec['lsl'])
        
        print(f"\n📊 KPI: {kpi.upper()}")
        print(f"   Target: {spec['target']}  |  LSL: {spec['lsl']}  |  USL: {spec['usl']}")
        print(f"   Process Mean: {np.mean(values):.2f}  |  Std Dev: {np.std(values):.2f}")
        
        cpk_status = "✅ CAPABLE" if cpk >= 1.33 else ("⚠️  MARGINAL" if cpk >= 1.0 else "🔴 NOT CAPABLE")
        print(f"   Cpk: {cpk}  →  {cpk_status}")
        
        if violations:
            unique_violations = {}
            for v_i, rule, severity in violations:
                key = (rule, severity)
                unique_violations[key] = unique_violations.get(key, 0) + 1
            
            print(f"   Violations detected:")
            for (rule, severity), count in unique_violations.items():
                emoji = {'CRITICAL': '🔴', 'WARNING': '🟡', 'DRIFT': '🟠'}[severity]
                print(f"     {emoji} {severity}: {rule.replace('_', ' ')} — {count} occurrences")
                alert_log.append({
                    'kpi': kpi, 'rule': rule, 'severity': severity,
                    'count': count, 'cpk': cpk
                })
        else:
            print(f"   ✅ No violations detected")
    
    print("\n" + "="*65)
    print("  ACTION ITEMS")
    print("="*65)
    
    critical_kpis = [a['kpi'] for a in alert_log if a['severity'] == 'CRITICAL']
    if critical_kpis:
        print(f"\n  🔴 IMMEDIATE ACTION REQUIRED:")
        for kpi in set(critical_kpis):
            print(f"     • Halt line, investigate {kpi}")
            print(f"       → Run X-ray inspection on last 50 units")
            print(f"       → Check SPI (Solder Paste Inspection) machine calibration")
    
    drift_kpis = [a['kpi'] for a in alert_log if a['severity'] == 'DRIFT']
    if drift_kpis:
        print(f"\n  🟠 DRIFT INVESTIGATION:")
        for kpi in set(drift_kpis):
            print(f"     • Schedule oven profiler check for {kpi}")
            print(f"       → Review reflow temperature log with Probe Station continuity test")
    
    print("\n" + "="*65)
    
    return pd.DataFrame(alert_log)


# ─────────────────────────────────────────────
# 5. MAIN EXECUTION
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("🍎 Apple PQE — Quality Monitoring Alert System")
    print("   Day 1: Data Simulator + SPC Foundation")
    print("─" * 50)
    
    # Generate simulated shift data
    print("\n[1/3] Simulating 8-hour production shift data...")
    simulator = ManufacturingDataSimulator(seed=42)
    df = simulator.generate_shift_data(hours=8, samples_per_hour=30)
    print(f"   ✅ Generated {len(df)} samples across 3 KPIs")
    print(f"   Sample:\n{df[['timestamp','sample_id','solder_volume_um3','reflow_peak_temp_C','bond_pull_strength_gf']].head(3).to_string(index=False)}")
    
    # Run SPC analysis
    print("\n[2/3] Running SPC analysis...")
    spc = SPCEngine(baseline_samples=30)
    alert_df = generate_alert_summary(df, spc, simulator)
    
    # Plot dashboard
    print("\n[3/3] Rendering control chart dashboard...")
    plot_control_charts(df, spc, simulator)
    
    # Save data for Day 2
    df.to_csv('/mnt/user-data/outputs/day1_shift_data.csv', index=False)
    alert_df.to_csv('/mnt/user-data/outputs/day1_alerts.csv', index=False)
    print("\n✅ Day 1 complete. Files saved:")
    print("   • day1_control_charts.png")
    print("   • day1_shift_data.csv  (use in Day 2 for ML-based alerting)")
    print("   • day1_alerts.csv      (violation log)")
