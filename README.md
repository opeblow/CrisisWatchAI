<p align="center">
  <img src="https://img.shields.io/badge/Next.js-14-black?style=for-the-badge&logo=next.js" alt="Next.js"/>
  <img src="https://img.shields.io/badge/FastAPI-0.111-green?style=for-the-badge&logo=fastapi" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/XGBoost-2.0-orange?style=for-the-badge" alt="XGBoost"/>
  <img src="https://img.shields.io/badge/Prophet-1.1-blue?style=for-the-badge" alt="Prophet"/>
  <img src="https://img.shields.io/badge/PostGIS-3.4-purple?style=for-the-badge&logo=postgis" alt="PostGIS"/>
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="MIT License"/>
  <img src="https://img.shields.io/badge/PRs-Welcome-brightgreen?style=for-the-badge" alt="PRs Welcome"/>
  <img src="https://img.shields.io/badge/python-3.12-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12"/>
  <img src="https://img.shields.io/badge/TypeScript-5.5-blue?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript"/>
</p>

<h1 align="center">🌍 CrisisWatch AI</h1>

<p align="center">
  <strong>Real-Time Global Crisis Intelligence Platform</strong><br/>
  Aggregates earthquakes, floods, outbreaks, wildfires & conflict from 7+ public data sources,<br/>
  applies explainable ML, and delivers actionable intelligence for NGOs, governments & first responders.
</p>

<p align="center">
  <a href="#-quickstart">Quickstart</a> •
  <a href="#-features">Features</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-api-reference">API</a> •
  <a href="#-contributing">Contributing</a>
</p>

---

## ✨ Features

| Feature | Description | Tech |
|:--------|:------------|:-----|
| 🗺️ Live Crisis Map | Interactive dark-theme global map with severity-coded markers | React-Leaflet + CARTO |
| 📊 Real-Time Dashboard | Stats, trend charts, severity donut, top-affected countries | Recharts + TanStack Query |
| 🧠 Severity Classifier | Predicts 1–5 risk level with SHAP feature attribution | XGBoost |
| 📝 NLP Report Classifier | Classifies situation reports into 8 crisis categories | DistilBERT (keyword fallback) |
| 📈 Regional Forecasting | Time-series crisis frequency prediction with 95% confidence bands | Prophet (seasonal-naive fallback) |
| 🔍 Hotspot Clustering | Identifies emerging crisis zones by density + severity | HDBSCAN (DBSCAN fallback) |
| 🔔 Smart Alerts | Priority-ranked alerts auto-generated when severity crosses threshold | FastAPI + SQLAlchemy |
| 📄 Auto Reports | One-click impact reports with executive summaries + markdown export | ReportService |
| 🎯 Explainable AI | Every prediction shows *why* — top features, direction, plain-language reasoning | SHAP |

**Data Sources:** GDACS · USGS · NASA FIRMS · ReliefWeb · WHO · ACLED · Open-Meteo

---

## 📁 Project Structure

```
CrisisWatchAI/
├── .github/
│   └── workflows/
│       ├── ci.yml                    # Lint, type-check, test (backend + frontend)
│       └── deploy.yml                # Build & push Docker images
├── backend/
│   ├── main.py                       # FastAPI app entrypoint
│   ├── requirements.txt              # Python dependencies
│   ├── Dockerfile                    # Backend container
│   ├── seed_demo.py                  # Idempotent demo data seeder (259 events, 176 alerts)
│   ├── smoke_test.py                 # In-process ASGI endpoint verifier
│   ├── db/
│   │   ├── database.py               # Async SQLAlchemy engine + session factory
│   │   └── models.py                 # ORM models (CrisisEvent, CrisisAlert, Prediction, Forecast, Report)
│   ├── data/
│   │   ├── http.py                   # Async HTTP client wrapper
│   │   ├── schema.py                 # Unified CrisisEvent dataclass + EVENT_TYPES
│   │   ├── ingestion.py              # Multi-source ingestion orchestrator
│   │   ├── preprocessing.py          # Normalisation & severity scoring
│   │   ├── utils.py                  # Data helpers
│   │   └── sources/
│   │       ├── base.py               # Abstract source adapter
│   │       ├── acled.py              # Armed Conflict Location & Event Data
│   │       ├── gdacs.py              # Global Disaster Alerting Coordination System
│   │       ├── nasa_firms.py         # NASA FIRMS active fire data
│   │       ├── open_meteo.py         # Open-Meteo weather API
│   │       ├── reliefweb.py          # ReliefWeb reports
│   │       ├── usgs.py               # USGS earthquake data
│   │       └── who.py                # WHO disease outbreak data
│   ├── ml/
│   │   ├── classifier.py             # XGBoost severity model (1–5)
│   │   ├── nlp_classifier.py         # DistilBERT text classifier (8 crisis types)
│   │   ├── forecaster.py             # Prophet / seasonal-naive time-series forecaster
│   │   ├── clustering.py             # HDBSCAN / DBSCAN spatial hotspot clustering
│   │   ├── explainability.py         # SHAP explanations + local occlusion fallback
│   │   └── models/
│   │       └── crisis_classifier.joblib   # Pre-trained XGBoost artifact
│   ├── routers/
│   │   ├── crises.py                 # GET /api/crises, /map, /stats, /regions
│   │   ├── predictions.py            # POST /predict/severity, /classify, GET /forecast, /clusters
│   │   ├── alerts.py                 # GET/POST /api/alerts, PATCH /{id}/read
│   │   └── reports.py               # POST /api/reports/generate, GET /api/reports
│   └── services/
│       ├── alert_service.py          # Alert severity mapping + message generation
│       └── report_service.py         # Markdown report builder
├── frontend/
│   ├── package.json                  # Next.js 14 + React 18 dependencies
│   ├── next.config.js                # API rewrites → localhost:8000
│   ├── tailwind.config.ts            # Dark navy theme + custom colours
│   ├── Dockerfile                    # Multi-stage frontend container
│   ├── app/
│   │   ├── layout.tsx                # Root layout: dark theme, sidebar, providers
│   │   ├── globals.css               # Tailwind + leaflet overrides + markdown styles
│   │   ├── page.tsx                  # Landing page (hero, stats, feature grid)
│   │   ├── dashboard/page.tsx        # Map + charts + stat cards
│   │   ├── predictions/page.tsx      # Classifier, NLP, forecast, clustering
│   │   ├── alerts/page.tsx           # Alert feed with mark-read
│   │   └── reports/page.tsx          # Generate + archive + export
│   ├── components/
│   │   ├── AppShell.tsx              # Client wrapper (sidebar only on non-landing)
│   │   ├── Sidebar.tsx               # Navigation sidebar with live status
│   │   ├── Providers.tsx             # TanStack Query provider
│   │   ├── CrisisMap.tsx             # React-Leaflet dark-theme map
│   │   ├── SeverityGauge.tsx         # Circular SVG severity gauge
│   │   ├── TrendChart.tsx            # Area, Donut, Bar, Forecast charts
│   │   ├── CrisisCard.tsx            # Event summary card
│   │   ├── StatsOverview.tsx         # 4-stat overview cards
│   │   └── ui/
│   │       ├── Card.tsx
│   │       ├── Badge.tsx
│   │       ├── Button.tsx
│   │       ├── Select.tsx
│   │       └── Skeleton.tsx
│   └── lib/
│       ├── api.ts                    # API client (fetch wrapper)
│       ├── types.ts                  # TypeScript interfaces
│       └── utils.ts                  # Severity colours, labels, formatters
├── docker-compose.yml                # Full-stack: PostGIS + Redis + Backend + Frontend
├── .env.example                      # Environment variable template
├── .gitignore
├── LICENSE                           # MIT
├── README.md                         # This file
├── SECURITY.md
├── CONTRIBUTING.md
└── CODE_OF_CONDUCT.md
```

---

## 🚀 Quickstart

### Prerequisites

- Python 3.12+
- Node.js 18+
- Docker & Docker Compose *(optional)*

### Local Development

**1 — Backend**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Use SQLite for local dev (no Postgres needed)
export DATABASE_URL=sqlite+aiosqlite:///./crisiswatch.db
# Windows PowerShell: $env:DATABASE_URL = "sqlite+aiosqlite:///./crisiswatch.db"

python seed_demo.py              # Seed 259 demo events + 176 alerts
uvicorn main:app --reload --port 8000
```

API docs → http://localhost:8000/docs

**2 — Frontend**

```bash
cd frontend
npm install
npm run dev
```

App → http://localhost:3000

> Next.js rewrites `/api/*` → `http://localhost:8000/api/*` automatically — no CORS config needed.

### Docker

```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

---

## 🧪 Verification

### Backend smoke test (no server required)

```bash
cd backend
export DATABASE_URL=sqlite+aiosqlite:///./crisiswatch.db
python smoke_test.py
```

Exercises all endpoints in-process via ASGI transport against a seeded SQLite DB.

### Frontend build + typecheck

```bash
cd frontend
npm run build
```

---

## 📡 API Reference

| Method | Endpoint | Description |
|:------:|:---------|:------------|
| `GET` | `/api/crises` | Paginated/filterable crisis events |
| `GET` | `/api/crises/map` | GeoJSON boundary payload |
| `GET` | `/api/crises/stats` | Global stats (by type, severity, top countries) |
| `GET` | `/api/crises/regions` | Region summary list |
| `GET` | `/api/alerts` | Priority-ranked alerts + unread count |
| `POST` | `/api/alerts` | Synthesize alerts from recent events |
| `PATCH` | `/api/alerts/{id}/read` | Mark alert as read |
| `POST` | `/api/predict/severity` | XGBoost severity + SHAP + explanation |
| `POST` | `/api/predict/classify` | NLP crisis-type classification |
| `GET` | `/api/forecast` | Time-series forecast with confidence bands |
| `GET` | `/api/clusters` | Hotspot clusters with risk scores |
| `POST` | `/api/reports/generate` | Generate impact report (markdown) |
| `GET` | `/api/reports` | List generated reports |
| `GET` | `/api/reports/{id}` | Get a single report |

---

## 🏗️ Architecture

```
┌──────────────┐     /api/*      ┌──────────────┐     async     ┌────────────┐
│   Next.js    │ ──── rewrite ──▶│   FastAPI     │ ────────────▶│ PostgreSQL │
│   Frontend   │                 │   Backend     │              │ + PostGIS  │
│  (port 3000) │                 │  (port 8000)  │              └────────────┘
└──────────────┘                 └──────┬───────┘
                                        │
                               ┌────────┼────────┐
                               ▼        ▼        ▼
                          ┌────────┐ ┌──────┐ ┌────────┐
                          │ XGBoost│ │Prophet│ │HDBSCAN │
                          │ + SHAP │ │      │ │+ DBSCAN│
                          └────────┘ └──────┘ └────────┘
                                        │
                               ┌────────┼────────┐
                               ▼        ▼        ▼
                          ┌────────┐ ┌──────┐ ┌────────┐
                          │  GDACS │ │ USGS │ │  NASA  │ ...7+ sources
                          └────────┘ └──────┘ └────────┘
```

**Graceful fallbacks** — every ML component runs without optional dependencies:

| Model | Full | Fallback |
|:------|:-----|:---------|
| Forecaster | Prophet | Seasonal-naive median |
| Clustering | HDBSCAN | DBSCAN (40km eps) |
| NLP | DistilBERT | Keyword-based rules |
| Explainability | SHAP | Local occlusion |

---

## 🔧 Tech Stack

**Frontend:** Next.js 14 · React 18 · TypeScript · Tailwind CSS · Recharts · React-Leaflet · Framer Motion · TanStack Query

**Backend:** Python 3.12 · FastAPI · SQLAlchemy (async) · Pydantic v2 · httpx

**ML/Data:** XGBoost · scikit-learn · Prophet · HDBSCAN · SHAP · DistilBERT · pandas · NumPy

**Infra:** PostgreSQL + PostGIS · Redis · Docker Compose · GitHub Actions

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines.

Quick start:
```bash
git clone https://github.com/YOUR_USERNAME/CrisisWatchAI.git
cd CrisisWatchAI
# Follow the Quickstart above
```

---

## 📄 License

This project is licensed under the MIT License — see [LICENSE](LICENSE).

---

## 🔒 Security

For vulnerability reports, see [SECURITY.md](SECURITY.md).

---

## 🙏 Data Attribution

All crisis data comes from publicly available sources. This project is for educational and demonstration purposes and is **not** a certified disaster-response system.

| Source | Data | License |
|:-------|:-----|:--------|
| [GDACS](https://www.gdacs.org) | Disaster alerts | Public API |
| [USGS](https://earthquake.usgs.gov) | Earthquakes | Public domain |
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov) | Active fires | Public |
| [ReliefWeb](https://reliefweb.int) | Humanitarian reports | OCHA |
| [WHO](https://www.who.int) | Disease outbreaks | Public |
| [ACLED](https://acleddata.com) | Conflict events | ACLED Terms |
| [Open-Meteo](https://open-meteo.com) | Weather data | Free API |
