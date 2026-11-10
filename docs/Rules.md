# Synora — Development Rules & Engineering Standards

> **Classification:** Engineering Governance & Code Quality Standards  
> **Document Version:** 1.1.0 (Audited & Aligned with Original Proposal)  
> **Applicability:** All contributors, subagents, and automated code generation pipelines

---

## 1. Core Engineering Principles

1. **Maintain Architectural Integrity:** Never add ad-hoc scripts, global variables, or orphan files. Every code change must map directly to one of the eight core product modules or defined infrastructure layers.
2. **Preserve Documentation & Comments:** Preserve all existing docstrings, type annotations, and contextual comments.
3. **Fail Explicitly & Gracefully:** Never swallow exceptions or hide failures behind generic catch-alls. Return structured error models with descriptive remediation advice.
4. **Strict Grounding, Citations & Uncertainty Handling:** Absolute claims such as "zero hallucination" are prohibited. Every AI-generated output (knowledge extraction, RAG Q&A, handover synthesis) must cite verifiable source records, enforce similarity thresholds ($\ge 0.65$), and declare uncertainty explicitly when grounding data is absent.
5. **Human-in-the-Loop Authority:** Automated extractions are advisory (`unverified`) until formally reviewed, edited, and approved by a human lead or manager.
6. **Provider-Independent AI:** AI capabilities must be abstracted behind a provider-independent adapter interface, configurable via environment variables (`LLM_PROVIDER`, `GEMINI_API_KEY`, etc.). Direct vendor lock-in in business logic is prohibited.
7. **Cloud-First Persistence with Local Fallback:** The primary production target is persistent Supabase PostgreSQL. SQLite is strictly an optional zero-setup local development fallback. All ORM schemas must be 100% compatible with both PostgreSQL and SQLite.

---

## 2. Coding Standards

### 2.1 Frontend (React + Vite + TypeScript)
- **Strict Typing:** No implicit `any`. All props, state variables, API payloads, and event handlers must be strictly typed.
- **Type-Only Imports:** TypeScript is configured with `verbatimModuleSyntax: true`. You **must** import types using the `import type { ... } from '...'` syntax.
- **Component Modularity:**
  - One primary component per file.
  - Functional components with React hooks exclusively (no class components).
  - Component files must be named in `PascalCase.tsx`.
- **Styling Architecture:**
  - Leverage the centralized design tokens defined in `frontend/src/index.css` via CSS variables (`var(--bg-primary)`, `var(--text-primary)`, `var(--primary)`, etc.).
  - Avoid inline styles for structural layouts; write semantic classes in `frontend/src/App.css`.
- **Zero Console Errors:** The build must pass `tsc -b && vite build` with zero warnings and zero errors.

### 2.2 Backend (FastAPI + Python 3.12)
- **Type Annotations:** Full type hinting across all functions, arguments, and return types (`typing` / Python 3.12 syntax).
- **Pydantic v2 Standard:**
  - Use `pydantic.BaseModel` with strict field definitions.
  - Use `SettingsConfigDict` for configuration classes (`class Config:` is strictly prohibited).
  - Use timezone-aware UTC timestamps: `datetime.now(timezone.utc)`. Never use deprecated `datetime.utcnow()`.
- **Route Organization:**
  - All endpoints must declare a `response_model` or explicit status code.
  - Routers must be grouped by domain under `app/api/v1/endpoints/`.
  - Transport logic (FastAPI routers) must never contain raw database queries; call into `app/services/` or `app/models/`.

---

## 3. Naming Conventions

| Entity | Convention | Example |
| :--- | :--- | :--- |
| **Frontend Components** | PascalCase | `HandoverView.tsx`, `RadarView.tsx`, `Navbar.tsx` |
| **Frontend Types & Interfaces** | PascalCase | `HandoverItem`, `RiskAlert`, `KnowledgeGap` |
| **Frontend Utility Functions** | camelCase | `fetchHandovers()`, `formatDate()` |
| **Frontend CSS Classes** | kebab-case | `.card-handover`, `.status-pill`, `.radar-card` |
| **Backend Modules & Files** | snake_case | `handover.py`, `scanner.py`, `radar.py` |
| **Backend Classes** | PascalCase | `HandoverService`, `RadarService`, `RiskAlert` |
| **Backend Functions & Methods** | snake_case | `list_handovers()`, `compute_bus_factor()` |
| **Backend Constants** | UPPER_SNAKE_CASE | `API_V1_STR`, `CORS_ORIGINS`, `DEFAULT_SIMILARITY_THRESHOLD` |
| **Database Tables** | snake_case (plural) | `handovers`, `knowledge_nodes`, `risk_alerts`, `knowledge_gaps` |
| **Database Columns** | snake_case | `employee_name`, `created_at`, `is_resolved` |
| **REST Endpoints** | kebab-case (plural resources) | `/api/v1/handovers/`, `/api/v1/sentinel/risks`, `/api/v1/radar/gaps` |

---

## 4. API Standards & Data Contracts

### 4.1 RESTful Conventions
- Use standard HTTP methods:
  - `GET` for retrieval (must be idempotent and side-effect free).
  - `POST` for resource creation (returns `HTTP 201 Created` with resource).
  - `PUT` for complete resource replacement.
  - `PATCH` for partial resource updates.
  - `DELETE` for resource removal (`HTTP 204 No Content` or `200 OK`).

### 4.2 Error Handling Contract
All API errors must return a consistent JSON envelope:

```json
{
  "detail": {
    "error_code": "RESOURCE_NOT_FOUND",
    "message": "Handover report with ID 'ho-999' was not found.",
    "timestamp": "2026-11-09T18:30:00Z",
    "path": "/api/v1/handovers/ho-999"
  }
}
```

- Always use FastAPI's native `HTTPException` with explicit status codes (`400`, `401`, `403`, `404`, `422`, `500`).

---

## 5. Security & Environment Variables

1. **Zero Secret Hardcoding:**
   - Database credentials, JWT secret keys, LLM API keys (`GEMINI_API_KEY`), and deployment URLs must be loaded exclusively through `app.core.config.settings` via environment variables.
   - A `.env.example` file must be maintained with sanitized placeholders for every required variable.
2. **CORS Configuration:**
   - Never use `allow_origins=["*"]` in production.
   - In development, allow explicitly: `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`.
3. **Role-Based Access Control (RBAC):**
   - Protected endpoints must enforce user roles (`Admin`, `Manager`, `Employee`).
   - Handover approval and risk dismissal endpoints require `Manager` or `Admin` privileges.
4. **Input Sanitization:**
   - All text inputs must be validated for length and content to prevent injection attacks and memory exhaustion.
   - File uploads must validate MIME types (`text/markdown`, `text/plain`, `application/pdf`, `application/json`) and enforce a 10MB maximum file size limit.

---

## 6. Responsible AI & Attribution Standards

To guarantee enterprise compliance and trust:

```mermaid
flowchart TD
    Prompt[User / Assistant Query] --> Search[Retrieve Chunks & Graph Relations]
    Search --> Check{Cosine Similarity >= 0.65?}
    Check -->|No| Uncertain[Flag Uncertainty: Explicit 'No verified knowledge found']
    Check -->|Yes| Grounded[Synthesize Answer with Source Citations]
    Grounded --> Citations[Attach [Source: Doc, Chunk ID, Timestamp]]
```

1. **Mandatory Source Citations:**
   - Every AI-generated statement must include a verifiable citation pointing to the originating document, chunk ID, or Git commit hash.
   - The UI must render citations as clickable badges displaying the source title and author.
2. **Uncertainty Declaration:**
   - If a user asks about an undocumented system or unrecorded decision, the system must declare:  
     *"No verified institutional documentation exists for this query."*
   - Never fabricate, extrapolate, or guess operational facts.
3. **Human Verification Workflow:**
   - Extracted handover items are tagged with status `unverified` until a designated Tech Lead or Manager reviews and transitions them to `verified`.
   - All verification actions must produce an immutable entry in the `audit_logs` table.

---

## 7. Prohibited Practices

The following actions are strictly forbidden:

> [!CAUTION]
> 1. **No Application Feature Implementation During Documentation:** Do not write or modify application business code until all six documentation deliverables are complete and aligned.
> 2. **No Invented Requirements or Module Renaming:** Preserve the exact eight original product modules:
>    - Knowledge Integration Pipeline
>    - Knowledge Extraction & Verification Engine
>    - Organizational Memory Graph
>    - AI Knowledge Assistant (RAG Engine)
>    - Knowledge Loss Radar
>    - Role-Based Handover Module
>    - Synora Sentinel
>    - Environment Recreator
> 3. **No Substituting Infrastructure for Product Modules:** Storage (PostgreSQL/SQLite) and document processing are infrastructure components, not product modules.
> 4. **No Absolute AI Claims:** Never claim "zero hallucinations"; specify source citations, uncertainty handling, and human verification instead.
> 5. **No SQLite Assumption for Production:** SQLite is strictly a local dev fallback; cloud deployment must support persistent Supabase PostgreSQL.
> 6. **No Breaking Sandbox Boundaries:** Never bypass permission boundaries, disable security checks, or execute unverified shell commands.
