"""
Project 3 — Quality Monitoring Alert System
Day 4: Automated Email Alert Engine

Context: Apple PQE — Pohang facility
When a CRITICAL alert is detected on the SMT line,
the system automatically emails the engineer on call.

Real Apple context:
In actual factories, alert systems are connected to:
- Email / SMS to on-call engineers
- Slack/Teams notifications
- MES dashboards
- Escalation chains (if no response in 15 min → alert manager)

We build the email engine + a full alert dispatcher
that decides WHO gets notified based on severity.

NOTE: This uses Gmail's SMTP server.
You'll need to set up a Gmail App Password (instructions below).
Even without sending real email, the simulation mode shows
exactly what would be sent — fully portfolio-ready.

Author: [Your Name]
Role Context: Apple PQE Intern Candidate
"""

import sqlite3
import smtplib
import pandas as pd
import numpy as np
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
import json
import os
import time

# ─────────────────────────────────────────────
# 1. ALERT DISPATCHER CONFIG
# ─────────────────────────────────────────────

# Escalation matrix — who gets notified for what
# In a real Apple factory, this would be in a config file
ESCALATION_MATRIX = {
    'CRITICAL': {
        'recipients': ['pqe_engineer@apple.com', 'line_supervisor@apple.com'],
        'subject_prefix': '🔴 [CRITICAL] Apple PQE Alert',
        'response_time_min': 15,
        'escalate_to': 'quality_manager@apple.com'
    },
    'WARNING': {
        'recipients': ['pqe_engineer@apple.com'],
        'subject_prefix': '🟡 [WARNING] Apple PQE Alert',
        'response_time_min': 60,
        'escalate_to': 'line_supervisor@apple.com'
    },
    'WATCH': {
        'recipients': ['pqe_engineer@apple.com'],
        'subject_prefix': '👀 [WATCH] Apple PQE Alert',
        'response_time_min': 240,
        'escalate_to': None
    }
}

KPI_ACTIONS = {
    'solder_volume_um3': [
        'Check SPI (Solder Paste Inspection) machine calibration',
        'Inspect paste cartridge — may need replacement',
        'Run X-ray on last 50 units to check joint quality',
        'Review stencil for clogging or damage'
    ],
    'reflow_peak_temp_C': [
        'Run oven profiler immediately',
        'Check thermocouple calibration',
        'Review reflow profile settings',
        'Inspect conveyor belt speed'
    ],
    'bond_pull_strength_gf': [
        'Perform destructive pull test on 5 samples',
        'Check under SEM for fracture mode (cohesive vs adhesive)',
        'Review bonding parameters — force, temperature, time',
        'Run FTIR on bond interface to check for contamination'
    ]
}

KPI_LABELS = {
    'solder_volume_um3':     'Solder Volume (μm³)',
    'reflow_peak_temp_C':    'Reflow Peak Temperature (°C)',
    'bond_pull_strength_gf': 'Bond Pull Strength (gf)'
}

SPECS = {
    'solder_volume_um3':     {'target': 1000, 'usl': 1150, 'lsl': 850},
    'reflow_peak_temp_C':    {'target': 245,  'usl': 255,  'lsl': 235},
    'bond_pull_strength_gf': {'target': 80,   'usl': 110,  'lsl': 50}
}


# ─────────────────────────────────────────────
# 2. EMAIL BUILDER
# ─────────────────────────────────────────────

class AlertEmailBuilder:
    """
    Builds professional HTML alert emails.
    Same structure used in real manufacturing alert systems.
    """

    def build_html(self, alert_data, severity):
        """Build a rich HTML email body."""

        kpi      = alert_data['kpi']
        value    = alert_data['value']
        spec     = SPECS.get(kpi, {})
        actions  = KPI_ACTIONS.get(kpi, [])
        label    = KPI_LABELS.get(kpi, kpi)
        config   = ESCALATION_MATRIX[severity]

        deviation = ((value - spec.get('target', value)) /
                     spec.get('target', 1) * 100)

        color_map = {
            'CRITICAL': '#FF3B30',
            'WARNING':  '#FF9500',
            'WATCH':    '#FFD60A'
        }
        alert_color = color_map.get(severity, '#888')

        actions_html = ''.join(
            f'<li style="margin:6px 0;">{a}</li>' for a in actions
        )

        html = f"""
        <html><body style="font-family: -apple-system, Arial, sans-serif;
                           background:#f5f5f7; margin:0; padding:20px;">

          <div style="max-width:600px; margin:auto; background:white;
                      border-radius:12px; overflow:hidden;
                      box-shadow:0 4px 20px rgba(0,0,0,0.1);">

            <!-- Header -->
            <div style="background:{alert_color}; padding:24px 32px;">
              <div style="color:white; font-size:13px; opacity:0.85;">
                APPLE INC. — PRODUCT QUALITY ENGINEERING
              </div>
              <div style="color:white; font-size:22px; font-weight:700;
                          margin-top:6px;">
                {severity} Quality Alert
              </div>
              <div style="color:white; font-size:12px; opacity:0.75;
                          margin-top:4px;">
                Pohang SMT Line A · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
              </div>
            </div>

            <!-- Alert Details -->
            <div style="padding:28px 32px;">
              <table style="width:100%; border-collapse:collapse;">
                <tr>
                  <td style="padding:8px 0; color:#86868b; font-size:13px;
                              width:40%;">KPI</td>
                  <td style="padding:8px 0; font-weight:600;
                              font-size:13px;">{label}</td>
                </tr>
                <tr style="background:#f5f5f7;">
                  <td style="padding:8px; color:#86868b; font-size:13px;">
                    Measured Value</td>
                  <td style="padding:8px; font-weight:700; font-size:16px;
                              color:{alert_color};">{value:.2f}</td>
                </tr>
                <tr>
                  <td style="padding:8px 0; color:#86868b; font-size:13px;">
                    Target</td>
                  <td style="padding:8px 0; font-size:13px;">
                    {spec.get('target', 'N/A')}</td>
                </tr>
                <tr style="background:#f5f5f7;">
                  <td style="padding:8px; color:#86868b; font-size:13px;">
                    Spec Limits</td>
                  <td style="padding:8px; font-size:13px;">
                    LSL: {spec.get('lsl','N/A')} · USL: {spec.get('usl','N/A')}
                  </td>
                </tr>
                <tr>
                  <td style="padding:8px 0; color:#86868b; font-size:13px;">
                    Deviation from Target</td>
                  <td style="padding:8px 0; font-size:13px;
                              color:{alert_color}; font-weight:600;">
                    {deviation:+.1f}%</td>
                </tr>
                <tr style="background:#f5f5f7;">
                  <td style="padding:8px; color:#86868b; font-size:13px;">
                    Sample ID</td>
                  <td style="padding:8px; font-size:13px;">
                    #{alert_data.get('sample_id','N/A')}</td>
                </tr>
                <tr>
                  <td style="padding:8px 0; color:#86868b; font-size:13px;">
                    Detector</td>
                  <td style="padding:8px 0; font-size:13px;">
                    {alert_data.get('detector','SPC')}</td>
                </tr>
              </table>

              <!-- Required Actions -->
              <div style="margin-top:24px; padding:16px;
                          background:#fff3f3; border-left:4px solid {alert_color};
                          border-radius:4px;">
                <div style="font-weight:700; font-size:14px;
                            margin-bottom:10px; color:#1d1d1f;">
                  ⚡ Required Actions
                </div>
                <ol style="margin:0; padding-left:20px;
                           font-size:13px; color:#1d1d1f; line-height:1.6;">
                  {actions_html}
                </ol>
              </div>

              <!-- Response Time -->
              <div style="margin-top:16px; padding:12px 16px;
                          background:#f0f8ff; border-radius:8px;
                          font-size:12px; color:#555;">
                ⏱ Required response time: <strong>{config['response_time_min']} minutes</strong>
                {f"· Escalates to {config['escalate_to']} if unacknowledged"
                 if config['escalate_to'] else ''}
              </div>
            </div>

            <!-- Footer -->
            <div style="background:#f5f5f7; padding:16px 32px;
                        font-size:11px; color:#86868b; text-align:center;">
              Apple PQE Quality Monitoring System · Pohang, Korea ·
              Auto-generated alert · Do not reply
            </div>
          </div>
        </body></html>
        """
        return html

    def build_plain(self, alert_data, severity):
        """Plain text fallback for email clients that don't render HTML."""
        kpi    = alert_data['kpi']
        label  = KPI_LABELS.get(kpi, kpi)
        config = ESCALATION_MATRIX[severity]
        actions = KPI_ACTIONS.get(kpi, [])

        lines = [
            f"APPLE PQE — {severity} QUALITY ALERT",
            f"Pohang SMT Line A | {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "=" * 50,
            f"KPI:    {label}",
            f"Value:  {alert_data['value']:.2f}",
            f"Sample: #{alert_data.get('sample_id', 'N/A')}",
            "",
            "REQUIRED ACTIONS:",
        ]
        for i, a in enumerate(actions, 1):
            lines.append(f"  {i}. {a}")
        lines += [
            "",
            f"Response required within: {config['response_time_min']} min",
            "Apple PQE Quality Monitoring System"
        ]
        return "\n".join(lines)


# ─────────────────────────────────────────────
# 3. EMAIL SENDER
# ─────────────────────────────────────────────

class EmailSender:
    """
    Sends emails via Gmail SMTP.

    HOW TO SET UP REAL EMAIL SENDING:
    1. Go to myaccount.google.com
    2. Security → 2-Step Verification → ON
    3. Search "App passwords" → Create one for "Mail"
    4. Copy the 16-character password
    5. Replace SENDER_EMAIL and APP_PASSWORD below

    For portfolio/demo: simulation mode shows exactly
    what would be sent without needing credentials.
    """

    def __init__(self, sender_email=None, app_password=None):
        self.sender_email = sender_email
        self.app_password = app_password
        self.simulation_mode = not (sender_email and app_password)

        if self.simulation_mode:
            print("   ℹ️  Running in SIMULATION MODE")
            print("      (Add Gmail credentials to send real emails)")

    def send(self, to_emails, subject, html_body, plain_body):
        """Send email or simulate sending."""

        if self.simulation_mode:
            return self._simulate(to_emails, subject, plain_body)

        try:
            msg = MIMEMultipart('alternative')
            msg['From']    = self.sender_email
            msg['To']      = ', '.join(to_emails)
            msg['Subject'] = subject

            msg.attach(MIMEText(plain_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))

            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(self.sender_email, self.app_password)
                server.sendmail(self.sender_email, to_emails, msg.as_string())

            print(f"   ✅ Email sent to: {', '.join(to_emails)}")
            return True

        except Exception as e:
            print(f"   ❌ Email failed: {e}")
            return False

    def _simulate(self, to_emails, subject, plain_body):
        """Print what the email would contain."""
        print(f"\n   {'─'*50}")
        print(f"   📧 SIMULATED EMAIL")
        print(f"   TO:      {', '.join(to_emails)}")
        print(f"   SUBJECT: {subject}")
        print(f"   BODY PREVIEW:")
        for line in plain_body.split('\n')[:12]:
            print(f"      {line}")
        print(f"   {'─'*50}")
        return True


# ─────────────────────────────────────────────
# 4. ALERT ENGINE
# ─────────────────────────────────────────────

class AlertEngine:
    """
    Main engine: reads alerts from database,
    dispatches emails, logs dispatch history.
    """

    def __init__(self, db_path='apple_pqe_quality.db',
                 sender_email=None, app_password=None):
        self.db_path = db_path
        self.builder = AlertEmailBuilder()
        self.sender  = EmailSender(sender_email, app_password)
        self.dispatch_log = []

    def load_alerts(self, severity_filter=None, limit=10):
        """Load unacknowledged alerts from database."""
        conn = sqlite3.connect(self.db_path)

        query = """
            SELECT a.alert_id, a.shift_id, a.sample_id,
                   a.timestamp, a.kpi, a.value,
                   a.severity, a.detector, a.z_score, a.if_score,
                   s.operator, s.line
            FROM alerts a
            JOIN shifts s ON a.shift_id = s.shift_id
            WHERE a.acknowledged = 0
        """
        params = []
        if severity_filter:
            query += " AND a.severity = ?"
            params.append(severity_filter)

        query += " ORDER BY a.alert_id DESC LIMIT ?"
        params.append(limit)

        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df

    def dispatch(self, alert_row, severity):
        """Build and send alert email for one alert."""
        config = ESCALATION_MATRIX.get(severity)
        if not config:
            return

        alert_data = {
            'kpi':       alert_row['kpi'],
            'value':     alert_row['value'],
            'sample_id': alert_row['sample_id'],
            'detector':  alert_row.get('detector', 'SPC'),
            'operator':  alert_row.get('operator', 'Unknown'),
            'timestamp': alert_row.get('timestamp', '')
        }

        subject = (f"{config['subject_prefix']} | "
                  f"{KPI_LABELS.get(alert_row['kpi'], alert_row['kpi'])} | "
                  f"Sample #{alert_row['sample_id']}")

        html  = self.builder.build_html(alert_data, severity)
        plain = self.builder.build_plain(alert_data, severity)

        success = self.sender.send(config['recipients'], subject, html, plain)

        self.dispatch_log.append({
            'alert_id':   alert_row['alert_id'],
            'kpi':        alert_row['kpi'],
            'severity':   severity,
            'value':      alert_row['value'],
            'recipients': config['recipients'],
            'sent_at':    datetime.now().isoformat(),
            'success':    success
        })

        return success

    def run(self, max_alerts=6):
        """
        Main dispatch loop.
        Processes CRITICAL first, then WARNING.
        """
        print("\n" + "="*65)
        print("  APPLE PQE — ALERT ENGINE RUNNING")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*65)

        total_sent = 0

        for severity in ['CRITICAL', 'WARNING']:
            alerts = self.load_alerts(severity_filter=severity,
                                      limit=max_alerts//2)

            if len(alerts) == 0:
                print(f"\n   ✅ No {severity} alerts pending")
                continue

            print(f"\n   Processing {len(alerts)} {severity} alerts...")

            for _, row in alerts.iterrows():
                self.dispatch(row, severity)
                total_sent += 1
                time.sleep(0.3)  # small delay between sends

        print(f"\n{'='*65}")
        print(f"  DISPATCH COMPLETE: {total_sent} alerts processed")
        print(f"{'='*65}")

        return pd.DataFrame(self.dispatch_log)

    def save_dispatch_log(self, log_df, path='day4_dispatch_log.csv'):
        """Save dispatch history to CSV."""
        log_df.to_csv(path, index=False)
        print(f"\n   ✅ Dispatch log saved: {path}")

    def print_summary(self, log_df):
        """Print dispatch summary report."""
        print("\n" + "="*65)
        print("  DISPATCH SUMMARY")
        print("="*65)

        if len(log_df) == 0:
            print("  No alerts dispatched.")
            return

        print(f"\n  Total dispatched : {len(log_df)}")
        print(f"  Critical         : {(log_df['severity']=='CRITICAL').sum()}")
        print(f"  Warning          : {(log_df['severity']=='WARNING').sum()}")
        print(f"  Success rate     : {log_df['success'].mean()*100:.0f}%")

        print("\n  By KPI:")
        for kpi, group in log_df.groupby('kpi'):
            label = KPI_LABELS.get(kpi, kpi)
            print(f"    {label}: {len(group)} alerts dispatched")

        print("\n  Sample email content saved to: day4_sample_email.html")
        print("="*65)


# ─────────────────────────────────────────────
# 5. SAVE SAMPLE EMAIL AS HTML FILE
# ─────────────────────────────────────────────

def save_sample_email():
    """
    Save one sample alert email as an HTML file.
    Open in browser to see exactly what the engineer receives.
    """
    builder = AlertEmailBuilder()
    sample_alert = {
        'kpi': 'reflow_peak_temp_C',
        'value': 257.3,
        'sample_id': 107,
        'detector': 'Z-Score + Isolation Forest',
        'operator': 'Lee_H',
        'timestamp': datetime.now().isoformat()
    }
    html = builder.build_html(sample_alert, 'CRITICAL')
    with open('day4_sample_email.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("   ✅ Sample email saved: day4_sample_email.html")
    print("      → Open in browser to preview exactly what engineers receive")


# ─────────────────────────────────────────────
# 6. MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("🍎 Apple PQE — Alert Engine")
    print("   Day 4: Automated Email Alert Dispatcher")
    print("─" * 50)

    # Check database exists
    if not os.path.exists('apple_pqe_quality.db'):
        print("\n❌ Database not found!")
        print("   → Run day3_database_logger.py first")
        exit()

    print("\n[1/4] Initializing alert engine...")
    engine = AlertEngine(
        db_path='apple_pqe_quality.db',
        sender_email=None,   # ← Add your Gmail here to send real emails
        app_password=None    # ← Add your Gmail App Password here
    )

    print("\n[2/4] Running alert dispatcher...")
    log_df = engine.run(max_alerts=6)

    print("\n[3/4] Saving dispatch log...")
    engine.save_dispatch_log(log_df)
    engine.print_summary(log_df)

    print("\n[4/4] Generating sample email preview...")
    save_sample_email()

    print("\n✅ Day 4 complete! Files saved:")
    print("   • day4_dispatch_log.csv    (full alert dispatch history)")
    print("   • day4_sample_email.html   (open in browser to see the email!)")
    print("\n💡 To send REAL emails:")
    print("   1. Get a Gmail App Password (myaccount.google.com → Security)")
    print("   2. Add your email + password to AlertEngine() above")
    print("   3. Run again — alerts will land in real inboxes!")
