# 🍎 PQE Quality Monitor
### Apple Product Quality Engineering — Intern Portfolio Project

> **Live Dashboard → [pqe-quality-monitor.netlify.app](https://pqe-quality-monitor.netlify.app)**

A complete, end-to-end **Quality Monitoring Alert System** built to mirror Apple's data-driven quality infrastructure at the Pohang SMT manufacturing facility in South Korea.

This project directly addresses the Apple PQE internship requirement:
> *"Use data to develop the quality monitoring system and implement the data-driven alert system."*

<img width="1888" height="865" alt="product quality monitor" src="https://github.com/user-attachments/assets/5e81b8ab-3df0-4aba-988a-e11cd504b9d7" />

<img width="1843" height="795" alt="img2" src="https://github.com/user-attachments/assets/96ca24b1-7cc7-486d-a9dc-7f1314ff4ef3" />

<img width="1826" height="687" alt="img3" src="https://github.com/user-attachments/assets/78cd79f3-6ee3-4c2f-8e5b-1fe678f02578" />

---

## 🎯 What This System Does

Monitors 3 critical KPIs on a Surface Mount Technology (SMT) production line in real-time:

| KPI | Target | Spec Limits | Detection Tool |
|-----|--------|-------------|----------------|
| Solder Paste Volume | 1000 μm³ | LSL 850 / USL 1150 | SPI Machine |
| Reflow Peak Temperature | 245°C | LSL 235 / USL 255 | Oven Profiler |
| Bond Pull Strength | 80 gf | LSL 50 / USL 110 | Bond Pull Tester |

When anomalies are detected → system automatically classifies severity → logs to database → dispatches email alerts to engineers on call.

---

## 🏗️ System Architecture

```
Sensor Data → SPC Engine → ML Anomaly Detector → SQLite Database → Email Alerts → Live Dashboard
     Day 1         Day 1           Day 2               Day 3           Day 4          Day 5
```

### Module Breakdown

| Module | File | What It Does |
|--------|------|-------------|
| Day 1 | `project3_day1_simulator.py` | Simulates 8hr shift data. SPC with Western Electric Rules + Cpk analysis |
| Day 2 | `day2_anomaly_detection.py` | Rolling Z-Score + Isolation Forest ML for multivariate anomaly detection |
| Day 3 | `day3_database_logger.py` | Logs 5 shifts to normalized SQLite DB. SQL analytics queries |
| Day 4 | `day4_alert_engine.py` | Reads DB alerts, dispatches emails via 3-tier escalation matrix |
| Day 5 | `index.html` | Live browser dashboard. Auto-refreshes every 3 seconds |

---

## 🤖 Detection Methods

### 1. SPC — Western Electric Rules
Fixed control limits (±3σ) calculated from baseline. Four rules detect different violation patterns — spikes, trends, shifts, and drift.

### 2. Rolling Z-Score
Adaptive detection using a sliding 20-sample window. Adjusts to slow drift while still catching sudden spikes.

### 3. Isolation Forest (ML)
Unsupervised anomaly detection across all 3 KPIs **simultaneously**. Catches multivariate anomalies that single-KPI rules miss — e.g., borderline reflow temp + borderline solder volume at the same time = cold joint risk.

<img width="1914" height="1016" alt="day1_control_charts" src="https://github.com/user-attachments/assets/3fb37f49-adf4-4576-8aa1-543edcede9bb" />

<img width="1899" height="1014" alt="day2_ML_anomaly_detection" src="https://github.com/user-attachments/assets/dbdf6354-9ea3-4443-963b-10a8e1df2f07" />

---

## 🚨 Alert Escalation Matrix

| Severity | Condition | Response SLA | Recipients |
|----------|-----------|-------------|------------|
| 🔴 CRITICAL | Out-of-spec OR both detectors flag | 15 minutes | PQE Engineer + Line Supervisor → Quality Manager |
| 🟡 WARNING | One detector flags, within spec | 60 minutes | PQE Engineer |
| 👀 WATCH | Borderline Z-score | 4 hours | Logged only |

<img width="820" height="1180" alt="email_alert1" src="https://github.com/user-attachments/assets/80038270-318d-4361-9339-ea8c4b567d53" />

<img width="820" height="1180" alt="email_alert2" src="https://github.com/user-attachments/assets/5c99929a-e958-4694-b881-7561a80fc460" />

---

## 🗄️ Database Schema

Normalized SQLite with 4 tables:
- **shifts** — Production shift metadata
- **samples** — Every sensor reading (1,200 across 5 shifts)
- **alerts** — Every violation with severity, detector, Z-score, IF score
- **summary** — Shift-level Cpk, mean, std, alert counts

<img width="1896" height="1020" alt="day3_database_analytics" src="https://github.com/user-attachments/assets/411b8cf2-c209-4f5b-884e-7775649cd897" />

---

## 📊 Key Findings

- **Reflow Temp Cpk: 0.781** — Process not capable, oven calibration drift detected after sample 140
- **Operator Analysis** — Lee_H had 50% more critical alerts than Kim_J → training intervention flagged
- **Alert Density** — Highest concentration in final 30 minutes of shift → end-of-shift fatigue pattern
- **Sample #107** — Most anomalous (IF score: −0.678). Reflow temp −3.02σ AND solder volume +2.75σ simultaneously — caught only by Isolation Forest

---

## 🛠️ Tech Stack

```
Python · NumPy · Pandas · Matplotlib · Scikit-learn
Flask · SQLite · smtplib · Chart.js · HTML/CSS
```

---

## 🚀 Run Locally

```bash
# Clone
git clone https://github.com/Shatakshi2204/pqe-quality-monitor
cd pqe-quality-monitor

# Install dependencies
pip install numpy pandas matplotlib scikit-learn flask

# Run Day 1 → generates shift data
python project3_day1_simulator.py

# Run Day 2 → ML anomaly detection
python day2_anomaly_detection.py

# Run Day 3 → database logging
python day3_database_logger.py

# Run Day 4 → email alerts (add Gmail credentials)
python day4_alert_engine.py

# Run Day 5 → local Flask dashboard
python day5_dashboard.py
# Open http://127.0.0.1:5000

# Or just open index.html in Chrome for the live standalone dashboard
```

---

## 🔬 Physical Tool Knowledge

Alert recommendations are mapped to real PQE inspection tools:

| Alert Type | Recommended Tool | Why |
|-----------|-----------------|-----|
| Solder volume violation | X-ray → SPI recalibration | Non-destructive check for voids |
| Reflow temp violation | Oven profiler + thermocouple check | Thermal drift identification |
| Bond pull violation | SEM fracture analysis + FTIR | Fracture mode + contamination check |

---

## 👩‍💻 About

Built by **Shatakshi** as part of a 15-day Apple PQE Intern preparation portfolio.

- 🎓 BTech CSE — Data Analytics & Finance
- 🇰🇷 Korean Language — Yonsei University (94%)
- 🇯🇵 Japanese Language Certified
- 🍎 Applying: Apple Product Quality Engineering Intern — Pohang, Korea

---

*Live Dashboard: [pqe-quality-monitor.netlify.app](https://pqe-quality-monitor.netlify.app)*
