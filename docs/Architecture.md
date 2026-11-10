# Synora — System Architecture & Technical Specification

> **Classification:** Technical Architecture Document  
> **Document Version:** 1.1.0 (Audited & Aligned with Original Proposal)  
> **Status:** Approved for Implementation  
> **Target Deployment:** Persistent Free-Tier Cloud Compatible (Supabase PostgreSQL + Render + Vercel)

---

## 1. System Architecture Overview

Synora is architected as a modular, decoupled full-stack platform consisting of a high-performance **FastAPI backend** (Python 3.12) and an enterprise-grade **React + Vite + TypeScript frontend**, backed by a cloud-persistent **Supabase PostgreSQL database** (with `pgvector` extension) and an optional local SQLite fallback.

### 1.1 High-Level Architecture Diagram

```mermaid
graph TB
    subgraph Client_Layer["Frontend Layer (React 19 + Vite 8 + TypeScript)"]
        UI_Dash[Executive Dashboard]
        UI_HO[Handover Engine Module 6]
        UI_Radar[Knowledge Loss Radar Module 5]
        UI_Sent[Synora Sentinel Module 7]
        UI_KG[Memory Graph Explorer Module 3]
        UI_RAG[AI Knowledge Assistant Module 4]
        UI_Rec[Environment Recreator Module 8]
        API_Client[Typed API Client Axios/Fetch]
        UI_Dash & UI_HO & UI_Radar & UI_Sent & UI_KG & UI_RAG & UI_Rec --> API_Client
    end

    subgraph API_Gateway["API Layer (FastAPI / Uvicorn)"]
        CORS[CORS Middleware]
        Auth_Sec[Auth & RBAC Handler]
        Router_V1[API v1 Router Aggregator]
        API_Client -->|HTTP/REST /api/v1| CORS
        CORS --> Auth_Sec --> Router_V1
    end

    subgraph Service_Layer["Eight Core Product Services"]
        S1[1. Ingestion Pipeline Service]
        S2[2. Knowledge Extraction & Verification Engine]
        S3[3. Organizational Memory Graph Service]
        S4[4. AI Knowledge Assistant & RAG Engine]
        S5[5. Knowledge Loss Radar Service]
        S6[6. Role-Based Handover Service]
        S7[7. Synora Sentinel Observer Service]
        S8[8. Environment Recreator Service]
    end

    Router_V1 --> S1
    Router_V1 --> S2
    Router_V1 --> S3
    Router_V1 --> S4
    Router_V1 --> S5
    Router_V1 --> S6
    Router_V1 --> S7
    Router_V1 --> S8

    subgraph Storage_Layer["Persistence & Infrastructure Layer (SQLAlchemy ORM)"]
        DB_Rel[(Supabase PostgreSQL Primary / SQLite Local Fallback)]
        Vector_Index[(pgvector / In-Memory Similarity Index)]
        Audit_Store[(Immutable Audit Logs Table)]
    end

    S1 & S2 & S3 & S5 & S6 & S7 & S8 --> DB_Rel
    S4 --> Vector_Index
    S2 & S6 --> Audit_Store
```

---

## 2. Frontend Architecture (React + TypeScript)

### 2.1 Technology Stack
- **Framework:** React 19 / Vite 8
- **Language:** TypeScript 5.9 with `verbatimModuleSyntax: true`
- **Styling:** Custom Enterprise Dark Design System (Vanilla CSS with CSS variables, zero runtime overhead)
- **Icons:** `lucide-react`
- **Build Target:** ES2022, strict type-checking via `tsc -b`

### 2.2 Component Hierarchy & State Flow

```mermaid
graph TD
    App[App.tsx - Platform Shell & State Controller]
    Nav[Navbar.tsx - Navigation & Backend Health Indicator]
    Dash[DashboardView.tsx - Continuity KPIs & Risk Summary]
    HO[HandoverView.tsx - Transition Dossiers & Creation Modal]
    Radar[RadarView.tsx - Knowledge Loss Radar & Gap Scanner]
    Sent[SentinelView.tsx - Bus Factor & SPOF Risk Alerts]
    KG[KnowledgeView.tsx - Memory Graph Explorer & RAG Assistant]
    Rec[RecreatorView.tsx - Dev Environment Specs & Quickstart]

    App --> Nav
    App --> Dash
    App --> HO
    App --> Radar
    App --> Sent
    App --> KG
    App --> Rec
```

### 2.3 State Management & Network Strategy
- **State Pattern:** Root component state with custom React hooks for polling and synchronization (`useHealth`, `usePlatformData`).
- **Resilience:** Graceful offline degradation. If the backend is unreachable, the frontend displays an offline status indicator without crashing, enabling cached view navigation.
- **Local Proxy:** `frontend/vite.config.ts` includes a reverse proxy mapping `/api` requests to `http://127.0.0.1:8000`, preventing CORS friction during local development.

---

## 3. Backend Architecture (FastAPI & Python 3.12)

### 3.1 Layered Architecture
The backend strictly isolates concerns into four distinct layers:

```
backend/
├── app/
│   ├── api/             # Transport Layer: Route definitions, request validation, HTTP status codes
│   ├── core/            # Foundation Layer: Settings, database session, security, LLM provider config
│   ├── models/          # Persistence Layer: SQLAlchemy declarative ORM models
│   ├── schemas/         # Data Contract Layer: Pydantic v2 validation models
│   └── services/        # Business Logic Layer: The 8 product module engines
```

### 3.2 Key Backend Conventions
- **Pydantic v2:** Used for all input validation and output serialization. Strict typing, default factories with timezone-aware datetimes (`datetime.now(timezone.utc)`).
- **Dependency Injection:** FastAPI `Depends()` pattern used for database sessions and authentication.
- **Asynchronous Execution:** Async route handlers where I/O operations occur, with sync handlers for CPU-bound extraction tasks.

---

## 4. Database Architecture & Data Entities

The persistence layer uses **SQLAlchemy ORM** configured with an engine dialect abstraction. The **primary production database is Supabase PostgreSQL** (free-tier cloud instance with `pgvector`), while **SQLite is provided strictly as an optional zero-setup local development fallback** when `DATABASE_URL` is omitted.

### 4.1 Database Configuration Strategy

```python
# app/core/database.py dialect abstraction
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./synora.db")

# Automatically configure connection parameters based on dialect
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # Supabase / PostgreSQL configuration
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
```

### 4.2 Entity Relationship Diagram (ERD)

```mermaid
erDiagram
    USERS ||--o{ HANDOVERS : "initiates"
    USERS ||--o{ AUDIT_LOGS : "triggers"
    PROJECTS ||--o{ HANDOVERS : "associated_with"
    PROJECTS ||--o{ RISK_ALERTS : "has_risks"
    PROJECTS ||--o{ KNOWLEDGE_GAPS : "has_gaps"
    PROJECTS ||--o{ KNOWLEDGE_NODES : "contains"
    KNOWLEDGE_NODES ||--o{ KNOWLEDGE_EDGES : "source_node"
    KNOWLEDGE_NODES ||--o{ KNOWLEDGE_EDGES : "target_node"
    DOCUMENTS ||--o{ DOCUMENT_CHUNKS : "chunked_into"
    HANDOVERS ||--o{ AUDIT_LOGS : "logs_change"

    USERS {
        string id PK
        string email
        string full_name
        string role
        string hashed_password
        datetime created_at
    }

    PROJECTS {
        string id PK
        string name
        string description
        string repository_url
        float bus_factor
        float knowledge_coverage_score
        datetime created_at
    }

    HANDOVERS {
        string id PK
        string employee_name
        string role
        string department
        string transition_type
        string status
        float readiness_score
        json key_responsibilities
        json critical_dependencies
        json unresolved_blockers
        string project_id FK
        datetime created_at
        datetime updated_at
    }

    RISK_ALERTS {
        string id PK
        string project_name
        string risk_level
        string category
        string description
        string recommended_action
        boolean is_resolved
        datetime detected_at
    }

    KNOWLEDGE_GAPS {
        string id PK
        string project_id FK
        string module_name
        string gap_type
        string severity
        text description
        string recommended_remediation
        boolean is_resolved
        datetime detected_at
    }

    KNOWLEDGE_NODES {
        string id PK
        string label
        string category
        text details
        string owner
        float confidence_score
        string verification_status
        string project_id FK
        datetime created_at
    }

    KNOWLEDGE_EDGES {
        string id PK
        string source_id FK
        string target_id FK
        string relation_type
        float confidence
    }

    DOCUMENTS {
        string id PK
        string filename
        string content_type
        int file_size
        text raw_text
        string uploaded_by FK
        datetime uploaded_at
    }

    DOCUMENT_CHUNKS {
        string id PK
        string document_id FK
        text chunk_text
        int chunk_index
        json metadata_tags
    }

    AUDIT_LOGS {
        string id PK
        string user_id FK
        string action
        string entity_type
        string entity_id
        json details
        datetime timestamp
    }
```

---

## 5. Provider-Independent AI & RAG Architecture

Synora implements a provider-independent AI interface that decouples application business logic from specific LLM vendors. Integration with Google Gemini, Anthropic Claude, OpenAI, or local models (Ollama) is managed via environment variables and an extensible adapter interface:

```mermaid
graph TD
    Query[User Query / Extraction Task] --> Adapter[LLM Provider Adapter Interface]
    Adapter -->|LLM_PROVIDER=gemini| Gemini[Gemini 1.5 / 2.0 Flash via Google GenAI SDK]
    Adapter -->|LLM_PROVIDER=openai| OpenAI[OpenAI API / Compatible Gateway]
    Adapter -->|LLM_PROVIDER=mock| Mock[Deterministic Test/Dev Mock Provider]
    Adapter --> Output[Grounded Output Envelope]
```

### 5.1 Environment Configuration
```ini
# AI / LLM Provider Configuration
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash
EMBEDDING_PROVIDER=local_or_gemini
EMBEDDING_MODEL=all-MiniLM-L6-v2

# Database Configuration (Supabase PostgreSQL primary, SQLite local fallback)
DATABASE_URL=postgresql+psycopg2://postgres:password@db.supabase.co:5432/postgres
# Local Fallback: DATABASE_URL=sqlite:///./synora.db
```

### 5.2 RAG Grounding, Source Citations & Uncertainty Handling
- **Grounding Protocol:** The assistant answers queries exclusively using retrieved context chunks from the persistent store and relations from the Memory Graph.
- **Mandatory Source Citations:** Every statement generated in an answer must include a structured source citation object referencing:
  - `document_name`: Originating document title or code file
  - `chunk_id`: Specific chunk identifier
  - `author`: Historical contributor
  - `timestamp`: Creation or commit timestamp
- **Uncertainty Management:**
  - Similarity Threshold: Minimum cosine similarity of $0.65$.
  - When similarity is below threshold or documentation is absent, the system does not guess. It responds with an explicit declaration:
    *"No verified institutional knowledge found for this query."*
- **Human Verification:** Knowledge extracted from documents is tagged `unverified` until explicitly reviewed and approved by a human lead in the UI.

---

## 6. The Eight Product Module Engines

### 6.1 Module 1: Knowledge Integration Pipeline (`IngestionService`)
- Parses incoming documents (`.md`, `.txt`, `.pdf`, `.json`) and simulated VCS/ticket payloads.
- Normalizes text, splits into 500-token chunks with 50-token overlap.
- Records document hash, author, and timestamp for immutable source tracking.

### 6.2 Module 2: Knowledge Extraction & Verification Engine (`ExtractionService`)
- Uses schema-constrained LLM generation to extract structured entities: Decisions, Responsibilities, Dependencies, Blockers.
- Assigns confidence scores ($0.0 - 1.0$) to each extracted item.
- Exposes human approval endpoints transitioning items from `unverified` to `verified`.

### 6.3 Module 3: Organizational Memory Graph Engine (`GraphService`)
- Builds and maintains the relational graph in PostgreSQL via `knowledge_nodes` and `knowledge_edges`.
- Traverses directed dependency chains to analyze transition impact when employees depart.
- Computes connected subgraphs for specific projects and roles.

### 6.4 Module 4: AI Knowledge Assistant - RAG Engine (`RAGService`)
- Indexes chunk embeddings using `pgvector` or in-memory vector store.
- Executes hybrid vector and keyword search.
- Generates grounded Q&A responses containing inspectable source citation pills.

### 6.5 Module 5: Knowledge Loss Radar Engine (`RadarService`)
- Continuously assesses organizational knowledge health across projects.
- Detects missing architecture records (`ADR_MISSING`), orphaned modules without secondary maintainers (`SECONDARY_OWNER_MISSING`), and stale documentation.
- Computes the project **Knowledge Coverage Score** ($0\% - 100\%$) and serves the Risk Dashboard.

### 6.6 Module 6: Role-Based Handover Module (`HandoverService`)
- Generates structured transition dossiers using role-specific templates.
- Manages complete handover lifecycle: `draft` $\rightarrow$ `in_progress` $\rightarrow$ `verified` $\rightarrow$ `completed`.
- Calculates dynamic **Readiness Assessment Score** based on resolved blockers and verified dependencies.
- Formats and exports dossiers to Markdown and printable HTML.

### 6.7 Module 7: Synora Sentinel Observer Engine (`SentinelService`)
- Scans codebase author histories and project activity metrics.
- Calculates repository Bus Factor:
  $$\text{Bus Factor} = \min \left\{ |S| : S \subset \text{Authors}, \, \sum_{a \in S} \text{Ownership}(a) \ge 0.5 \right\}$$
- Generates proactive `RiskAlert` records when Bus Factor is 1 or a single engineer owns $>75\%$ of contributions.

### 6.8 Module 8: Environment Recreator Engine (`RecreatorService`)
- Inspects repository manifests (`package.json`, `requirements.txt`, `pyproject.toml`, `Dockerfile`, `.env.example`).
- Synthesizes deterministic, executable local launch sequences (PowerShell, Bash) and container blueprints (`docker-compose.yml`).
- Generates interactive onboarding checklists for incoming team members.

---

## 7. API Specifications (RESTful API v1)

All endpoints reside under the `/api/v1` namespace.

| Method | Endpoint | Module | Description | Request Body | Response Model |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health` | Core | Service health & version metadata | None | `HealthStatus` |
| `POST` | `/documents/upload` | Module 1 | Ingest project documentation | Form-data file | `DocumentUploadResult` |
| `GET` | `/documents/` | Module 1 | List ingested documents | None | `List[DocumentItem]` |
| `POST` | `/documents/{id}/extract` | Module 2 | Extract entities from document | None | `ExtractionResult` |
| `PATCH` | `/knowledge/nodes/{id}/verify` | Module 2 | Human verification of extracted node | `VerifyNodeRequest` | `KnowledgeNode` |
| `GET` | `/knowledge/graph` | Module 3 | Retrieve nodes and edges for visualization | Project filter | `GraphData` |
| `GET` | `/knowledge/nodes` | Module 3 | List institutional knowledge nodes | Category filter | `List[KnowledgeNode]` |
| `POST` | `/knowledge/query` | Module 4 | RAG query with source citations | `KnowledgeQuery` | `QueryResponse` |
| `GET` | `/radar/gaps` | Module 5 | List detected knowledge gaps | Project filter | `List[KnowledgeGap]` |
| `GET` | `/radar/coverage` | Module 5 | Get project Knowledge Coverage Scores | None | `List[ProjectCoverage]` |
| `GET` | `/handovers/` | Module 6 | List all handover dossiers | Query filters (`status`, `dept`) | `List[HandoverItem]` |
| `POST` | `/handovers/` | Module 6 | Create a new handover dossier | `HandoverCreate` | `HandoverItem` |
| `GET` | `/handovers/{id}` | Module 6 | Retrieve specific handover dossier | None | `HandoverItem` |
| `PATCH` | `/handovers/{id}` | Module 6 | Update handover status/blockers | `HandoverUpdate` | `HandoverItem` |
| `GET` | `/handovers/{id}/export` | Module 6 | Export dossier as formatted Markdown | None | `HandoverExport` |
| `GET` | `/sentinel/risks` | Module 7 | List detected continuity risks | Severity filter | `List[RiskAlert]` |
| `POST` | `/sentinel/scan` | Module 7 | Trigger on-demand continuity scan | `ScanRequest` | `ScanResult` |
| `GET` | `/recreator/spec` | Module 8 | Get dev environment recreate spec | Project query | `RecreatorSpec` |

---

## 8. Project Directory Structure

```
synora/
├── docs/                             # Complete project documentation
│   ├── PRD.md                        # Product Requirements Document
│   ├── Architecture.md               # Technical Architecture (this file)
│   ├── Rules.md                      # Development Rules & Coding Standards
│   ├── Phases.md                     # Sequential Implementation Roadmap
│   ├── Design.md                     # Visual Identity & UI Design System
│   └── Memory.md                     # Living Project State & Decision Log
│
├── backend/                          # FastAPI Backend Application
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                   # App initialization & CORS middleware
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py             # Settings, environment variables, LLM configs
│   │   │   ├── database.py           # Supabase PostgreSQL / SQLite session factory
│   │   │   ├── llm.py                # Provider-independent LLM adapter interface
│   │   │   └── seed.py               # Enterprise database seeder
│   │   ├── models/                   # SQLAlchemy ORM entity models
│   │   │   ├── __init__.py
│   │   │   ├── handover.py           # Module 6
│   │   │   ├── risk.py               # Module 7
│   │   │   ├── radar.py              # Module 5
│   │   │   ├── knowledge.py          # Module 3
│   │   │   ├── document.py           # Module 1 & 4
│   │   │   └── audit.py              # Audit logging infrastructure
│   │   ├── schemas/                  # Pydantic v2 validation contracts
│   │   │   ├── __init__.py
│   │   │   ├── common.py
│   │   │   ├── handover.py
│   │   │   ├── risk.py
│   │   │   ├── radar.py
│   │   │   └── knowledge.py
│   │   ├── services/                 # Eight Core Product Services
│   │   │   ├── __init__.py
│   │   │   ├── ingestion.py          # Module 1
│   │   │   ├── extraction.py         # Module 2
│   │   │   ├── graph.py              # Module 3
│   │   │   ├── rag.py                # Module 4
│   │   │   ├── radar.py              # Module 5
│   │   │   ├── handover.py           # Module 6
│   │   │   ├── sentinel.py           # Module 7
│   │   │   └── recreator.py          # Module 8
│   │   └── api/
│   │       ├── __init__.py
│   │       └── v1/
│   │           ├── __init__.py
│   │           ├── api.py            # Unified router aggregator
│   │           └── endpoints/
│   │               ├── health.py
│   │               ├── documents.py
│   │               ├── knowledge.py
│   │               ├── radar.py
│   │               ├── handover.py
│   │               ├── sentinel.py
│   │               └── recreator.py
│   ├── tests/                        # Automated backend tests
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_health.py
│   │   └── test_modules.py
│   ├── requirements.txt              # Production & dev dependencies
│   ├── run.py                        # Uvicorn entry point
│   └── .venv/                        # Virtual environment
│
├── frontend/                         # React + Vite + TypeScript Frontend
│   ├── src/
│   │   ├── assets/                   # Static icons & branding assets
│   │   ├── components/               # UI Views & modular components
│   │   │   ├── Navbar.tsx            # Header & live backend status pill
│   │   │   ├── DashboardView.tsx     # Executive KPIs & overview
│   │   │   ├── HandoverView.tsx      # Module 6: Transition dossiers & modal form
│   │   │   ├── RadarView.tsx         # Module 5: Knowledge Loss Radar & Gaps
│   │   │   ├── SentinelView.tsx      # Module 7: Risk & SPOF alert monitoring
│   │   │   ├── KnowledgeView.tsx     # Module 3 & 4: Memory graph & RAG assistant
│   │   │   └── RecreatorView.tsx     # Module 8: Environment Recreator quickstart
│   │   ├── services/
│   │   │   └── api.ts                # Typed client API integration
│   │   ├── types.ts                  # TypeScript interfaces & types
│   │   ├── App.tsx                   # Main platform view controller
│   │   ├── App.css                   # Enterprise dark-mode design system
│   │   ├── index.css                 # Typography & theme variables
│   │   └── main.tsx                  # React DOM entry point
│   ├── index.html                    # Root HTML template
│   ├── vite.config.ts                # Vite config with backend proxy
│   ├── tsconfig.json                 # TypeScript compiler options
│   └── package.json                  # NPM dependencies & scripts
│
├── .gitignore                        # Git exclusion rules
└── README.md                         # Project overview & quickstart
```

---

## 9. Deployment Architecture (Persistent Cloud Free-Tier)

To satisfy the deadline and persistent free-tier prototype requirements:

```mermaid
graph LR
    User[Web Browser] -->|HTTPS| Vercel[Frontend on Vercel / Render Static]
    Vercel -->|API Calls /api/v1| Render[FastAPI on Render Free Web Service]
    Render --> Supabase[(Persistent Supabase PostgreSQL + pgvector)]
```

- **Frontend Hosting:** Vercel (Free tier, automated deployment from GitHub, global edge CDN).
- **Backend Hosting:** Render Web Service (Free tier, Python 3.12, Uvicorn ASGI server).
- **Database:** Supabase PostgreSQL instance (Free tier, persistent cloud storage, `pgvector` enabled, reachable via standard `DATABASE_URL`).
- **Environment Management:** Environment variables configured in Render and Vercel dashboards (`DATABASE_URL`, `LLM_PROVIDER`, `GEMINI_API_KEY`, `VITE_API_URL`, `CORS_ORIGINS`).
