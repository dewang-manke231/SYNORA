# Synora

> **Where Organizational Knowledge Becomes Lasting Team Intelligence**

Synora is an AI-powered Knowledge Continuity and Project Protection Platform designed to prevent institutional knowledge loss caused by employee turnover, resignations, and team transitions.

---

## Architecture Overview

```
synora/
├── backend/                       # FastAPI Backend (Python 3.12.6)
│   ├── alembic/                   # Alembic database migrations
│   │   ├── versions/              # Migration revision scripts
│   │   └── env.py                 # Dynamic DB connection & auto-generation
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── endpoints/
│   │   │       │   ├── health.py     # System health check & database status
│   │   │       │   ├── handover.py   # Transition dossiers & handovers (Module 6)
│   │   │       │   ├── radar.py      # Knowledge Loss Radar & coverage (Module 5)
│   │   │       │   ├── sentinel.py   # Continuous SPOF & risk observer (Module 7)
│   │   │       │   └── knowledge.py  # Institutional knowledge graph (Module 3 & 4)
│   │   │       └── api.py            # API v1 router aggregator
│   │   ├── core/
│   │   │   ├── config.py             # Settings, CORS, & environment config
│   │   │   ├── database.py           # SQLAlchemy dialect abstraction (PostgreSQL / SQLite)
│   │   │   └── seed.py               # Enterprise database initializer & seeder
│   │   ├── models/                   # 15 SQLAlchemy declarative ORM models
│   │   │   └── __init__.py           # Users, Orgs, Projects, Handovers, Risks, etc.
│   │   ├── schemas/
│   │   │   └── common.py             # Pydantic v2 data contracts
│   │   └── main.py                   # FastAPI application factory with lifespan DB init
│   ├── tests/                        # Automated Pytest suite (16 tests)
│   │   ├── conftest.py               # Test fixtures & database isolation
│   │   ├── test_health.py            # Health & baseline endpoint tests
│   │   ├── test_database_models.py   # Model relationship & cascading tests
│   │   ├── test_api_persistence.py   # API CRUD & database persistence tests
│   │   └── test_migrations.py       # Alembic schema migration tests
│   ├── alembic.ini                   # Alembic migration configuration
│   ├── requirements.txt              # Production & dev dependencies
│   └── run.py                        # Uvicorn entry point
│
├── frontend/                      # React 19 + Vite 8 + TypeScript Frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── Navbar.tsx            # Header navigation & live status pill
│   │   │   ├── DashboardView.tsx     # Executive KPIs & continuity metrics
│   │   │   ├── HandoverView.tsx      # Role transition dossiers & creation form
│   │   │   ├── SentinelView.tsx      # Continuous risk & SPOF observer
│   │   │   ├── KnowledgeView.tsx     # Institutional knowledge graph explorer
│   │   │   └── RecreatorView.tsx     # Environment Recreator quickstart
│   │   ├── services/
│   │   │   └── api.ts                # Typed client API integration
│   │   ├── types.ts                  # TypeScript interface contracts
│   │   ├── App.tsx                   # Main platform view controller
│   │   ├── App.css                   # Enterprise dark-mode design system
│   │   └── index.css                 # Typography & theme variables
│   ├── vite.config.ts                # Vite config with backend API proxy
│   └── package.json
│
├── docs/                          # Authoritative project documentation
│   ├── PRD.md                        # Product Requirements Document
│   ├── Architecture.md               # Technical Architecture Specification
│   ├── Rules.md                      # Development Rules & Engineering Standards
│   ├── Phases.md                     # Sequential Implementation Roadmap
│   ├── Design.md                     # Visual Identity & UI Design System
│   ├── Memory.md                     # Living Project State & Decision Log
│   └── IMPLEMENTATION_STATUS.md      # Live phase progress tracker
│
└── .agents/skills/                # Curated Agent Skills
    ├── ui-ux-pro-max/                # Design intelligence & accessibility
    ├── react-best-practices/         # React 19 rendering & performance rules
    ├── supabase-postgres-best-practices/ # Production Postgres schema & pooling
    └── api-and-interface-design/     # Typed interface contracts & API standards
```

---

## Quickstart

### Prerequisites
- **Node.js**: v26.13.0+
- **Python**: 3.12.6+
- On Windows PowerShell, use `npm.cmd` instead of `npm`.

### 1. Database Configuration
Synora supports persistent cloud **Supabase PostgreSQL** as primary and local **SQLite** as an optional fallback.

Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```

To use Supabase PostgreSQL:
```ini
DATABASE_URL=postgresql+psycopg2://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres
```

To use SQLite local fallback (default when `DATABASE_URL` is omitted):
```ini
DATABASE_URL=sqlite:///./synora.db
```

### 2. Run Database Migrations & Start Backend

```powershell
cd backend

# Create virtual environment (if not already created)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt

# Run Alembic migrations up to head
alembic upgrade head

# Start backend server (runs on http://127.0.0.1:8000)
python run.py
```

- Interactive OpenAPI Swagger Docs: [http://127.0.0.1:8000/api/v1/docs](http://127.0.0.1:8000/api/v1/docs)
- Health check: [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)

### 3. Start Frontend Application

In a new PowerShell terminal:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```
Runs locally at [http://localhost:5173](http://localhost:5173).

---

## Verification & Testing

### Backend Test Suite
Run pytest in the `backend` directory:
```powershell
cd backend
.venv\Scripts\pytest -v
```

### Frontend Typecheck & Build
```powershell
cd frontend
npm.cmd run build
```
