# Synora — Living Project Memory & State Log

> **Classification:** Project State Tracking & Architectural Decision Record (ADR)  
> **Document Version:** 1.6.0 (Step 4 Memory Graph & Vector RAG Assistant Completed)  
> **Last Updated:** 10 November 2026, 00:25 IST  
> **Hard Deadline:** 11 November 2026, 10:00 AM IST  
> **Rule:** This document must be updated immediately upon the completion of every implementation phase.

---

## 1. Current Project Status

- **Current Active Phase:** **Phase 8 (Task 4: Formal New-Joiner Handover Assignment & Verification) — COMPLETED & VERIFIED**
- **Next Phase:** **Phase 8 (Remaining Polish) & Phase 9 (Free-Tier Cloud Deployment & Live Signoff)**
- **System Health:**
  - Backend API: Fully connected with FastAPI, SQLAlchemy ORM, bcrypt password hashing, and pyjwt bearer tokens. Live Supabase PostgreSQL with pgvector v0.8.2 and Supabase Storage active.
  - Frontend UI: Functional on React 19 + Vite 8 + TypeScript 5.9 with zero build errors. Real server-driven authentication, manager assignment workflow with real-time UI updates, and zero layout disruptions.
  - Test Suite: **78/78 backend tests passing (`pytest`)** covering all core modules, 10 dedicated handover assignment tests, migration tests, and full regression.
  - Frontend Build: `tsc -b && vite build` clean with 0 errors, 0 warnings (dist built in 1.71s).
  - Agent Skills: 4 curated MIT skills active in `.agents/skills/`.

---

## 2. Architectural Decisions Log (ADR)

### ADR-001: Technology Stack Selection (React + Vite + TypeScript & FastAPI)
- **Status:** **APPROVED & IMPLEMENTED** (Phase 1)
- **Context:** The project requires a performant, modular foundation capable of real-time AI interactions, structured knowledge capture, and rapid local iteration.
- **Decision:** Use React 19 with Vite 8 and TypeScript 5.9 for the frontend, and FastAPI with Python 3.12 for the backend.
- **Consequences:** Provides fast Hot Module Replacement (HMR), strict type safety across client and server, native OpenAPI documentation generation, and high throughput.

### ADR-002: Cloud-First Persistence with Supabase PostgreSQL & SQLite Local Fallback
- **Status:** **APPROVED, IMPLEMENTED & VERIFIED** (Phase 3)
- **Context:** The production system requires persistent cloud storage with vector capabilities (`pgvector`) within free-tier limits, while enabling zero-setup local development and rapid test suite execution.
- **Decision:** Implement SQLAlchemy dialect abstraction in `app.core.database.py`. When `DATABASE_URL` points to Supabase PostgreSQL, enable connection pooling (`pool_pre_ping=True`, `pool_size=5`, `max_overflow=10`, `pool_recycle=300`). When `DATABASE_URL` points to SQLite or is omitted, fall back seamlessly to local SQLite (`sqlite:///./synora.db`).
- **Consequences:** Production deployments on Render/Vercel connect to persistent cloud Supabase PostgreSQL without data loss on container restarts; local development and automated CI tests run out-of-the-box with zero database setup.

### ADR-003: Strict Grounding, Source Citations & Uncertainty Protocol
- **Status:** **APPROVED & AUDITED** (Phase 2)
- **Context:** In institutional continuity, an incorrect or hallucinated technical instruction causes severe operational outages. Absolute claims such as "zero hallucination" are misleading and untestable.
- **Decision:** Replace absolute claims with an engineering protocol: enforce a minimum cosine similarity threshold ($\ge 0.65$), require structured source citation tags (`[Source: Doc, ChunkID]`), declare explicit uncertainty when evidence is missing, and require human review for critical records.
- **Consequences:** Builds trust with engineering leads; guarantees auditability; prevents fabricated operational steps.

### ADR-004: Windows PowerShell Command Execution Policy
- **Status:** **APPROVED & RECORDED** (Phase 1)
- **Context:** On Windows PowerShell environments, standard `npm` is a bash wrapper script, causing command execution failures.
- **Decision:** All automated and manual terminal commands on Windows must invoke `npm.cmd` explicitly instead of `npm`.
- **Consequences:** Flawless dependency installation and script execution across Windows shells.

### ADR-005: Preservation of the Eight Core Product Modules
- **Status:** **APPROVED & AUDITED** (Phase 2)
- **Context:** Initial documentation drafts inadvertently substituted infrastructure components (storage, document processing) for core product modules and omitted the Knowledge Loss Radar.
- **Decision:** Strictly align with the original Synora specification's eight core product modules:
  1. Knowledge Integration Pipeline
  2. Knowledge Extraction & Verification Engine
  3. Organizational Memory Graph
  4. AI Knowledge Assistant (RAG Engine)
  5. Knowledge Loss Radar
  6. Role-Based Handover Module
  7. Synora Sentinel
  8. Environment Recreator
  Storage (Supabase PostgreSQL + pgvector) and document processing are codified strictly as infrastructure.
- **Consequences:** Fully aligns the product scope with the proposal specification; establishes a clear boundary between platform features and supporting infrastructure.

### ADR-006: Provider-Independent AI Interface & Environment Variables
- **Status:** **APPROVED & AUDITED** (Phase 2)
- **Context:** Relying on hardcoded LLM endpoints introduces vendor lock-in and complicates testing.
- **Decision:** Abstract all LLM operations behind a provider-independent interface (`LLMProvider`) configured via environment variables (`LLM_PROVIDER`, `GEMINI_API_KEY`, `GEMINI_MODEL`, etc.), with support for Google Gemini, OpenAI-compatible APIs, and local mock providers for tests.
- **Consequences:** Seamless switching of AI providers without touching core business logic; offline testing viability.

### ADR-007: Declarative Schema Migrations via Alembic
- **Status:** **APPROVED, IMPLEMENTED & VERIFIED** (Phase 3)
- **Context:** Database schema evolution across multiple developer environments and cloud deployments requires deterministic, automated versioning.
- **Decision:** Use Alembic configured with dynamic database URL detection in `alembic/env.py`. Provide automated database initialization on startup via FastAPI lifespan hook.
- **Consequences:** Zero-touch table creation and seeding on first run; deterministic upgrade and rollback paths for cloud deployments.

### ADR-008: Handover Lifecycle State Machine & Review Protocols
- **Status:** **APPROVED, IMPLEMENTED & VERIFIED** (Step 1)
- **Context:** Handover processes often fail because tasks and blockers are unverified or fall into ambiguity without structured review checkpoints.
- **Decision:** Implement a deterministic 6-state finite state machine in `HandoverService`:
  `draft` $\rightarrow$ `submitted` $\rightarrow$ `under_review` $\rightarrow$ `changes_requested` / `verified` $\rightarrow$ `completed`.
  Invalid transitions are rejected with HTTP 400. Change requests require a reason that remains visible to the employee. Dynamic readiness scores (0-100%) evaluate completion, documentation, and blockers. Completed handovers lock against arbitrary mutations.
- **Consequences:** Eliminates incomplete handovers before employee departure; enforces engineering manager sign-off with audit logging. Role enforcement is currently simulated via client persona envelope until JWT/RBAC is integrated.

### ADR-009: Document Ingestion, Storage Abstraction & Chunking Protocol
- **Status:** **APPROVED, IMPLEMENTED & VERIFIED** (Step 2)
- **Context:** Technical knowledge exists across runbooks, architecture specs, and READMEs in varied formats (.pdf, .md, .txt). Ingestion must be secure against directory traversal and script execution, deduplicate redundant uploads, and preserve page/token metadata for grounded citations.
- **Decision:** Implement `StorageProvider` interface with `LocalStorageProvider` fallback (ready for Supabase Storage). Restrict uploads to `.pdf`, `.md`, `.txt` under 25 MB. Enforce SHA-256 deduplication per handover. Extract plain text (using `pypdf` for PDFs with page tracking) and generate sliding-window word chunks (350 words, 50-word overlap). Persist to `Document` and `DocumentChunk` with cascading deletion.
- **Consequences:** Provides persistent, structured text chunks ready for vector embeddings (Module 4) while isolating file system risks and preventing arbitrary code execution.

### ADR-010: Knowledge Extraction, Grounded Citations & Human Verification Engine
- **Status:** **APPROVED, IMPLEMENTED & VERIFIED** (Step 3 / Module 2)
- **Context:** Unsupervised LLM extractions can fabricate tasks, hallucinate ownership, or produce untraceable claims. Critical handover knowledge requires absolute factual grounding in source text, clear confidence metrics, and mandatory human review for low-confidence items.
- **Decision:** Build a provider-independent LLM architecture (`LLMProvider`) supporting Google Gemini API via REST and a deterministic rule-based mock provider (`MockLLMProvider`) for offline testing/CI. Extract 7 structured knowledge categories (tasks, architecture decisions, blockers, configs, modules, processes, tooling) strictly supported by chunk evidence. Enforce:
  1. Every extraction must link to `document_id`, `chunk_id`, and store a verbatim `source_quote`.
  2. Any extraction with confidence $< 0.65$ is automatically flagged (`is_flagged_for_review: true`, `verification_status: "unverified"`).
  3. No task marked complete without verbatim evidence; no owners assigned without explicit document attribution.
  4. Reprocessing documents performs idempotent cleanup of prior extractions.
  5. Manager review lifecycle (`verified`, `modified`, `rejected`) records immutable `VerificationRecord` and `AuditLog` entries.
- **Consequences:** Eliminates hallucinations in the institutional knowledge base; ensures all captured intelligence is verifiable against original uploaded documentation.

### ADR-011: Organizational Memory Graph & Grounded Vector RAG Assistant
- **Status:** **APPROVED, IMPLEMENTED & VERIFIED** (Step 4 / Modules 3 & 4)
- **Context:** Isolated documentation and extracted knowledge lack contextual interconnectivity, making cross-module dependencies and departure impacts opaque. Furthermore, conversational AI assistants frequently hallucinate answers or generate ungrounded claims when evidence is absent.
- **Decision:**
  1. Implement `GraphService` (`GET /api/v1/knowledge/graph`) constructing grounded directed entity graphs from `ExtractedKnowledge`, `Document`, and attested maintainers (`User`/`owner`). Connect nodes exclusively through real evidence: database `KnowledgeRelationship` rows, `document_id` foreign keys (`DOCUMENTED_IN`), and explicit maintainer attribution (`MAINTAINS`). Reject invented relationships.
  2. Implement `EmbeddingProvider` interface in `app.core.embeddings` supporting Google Gemini text embeddings (`text-embedding-004`) and a deterministic dense vectorizer for offline/local environments that produces unit-normalized vectors where dot product equals cosine similarity.
  3. Implement `RAGService` (`POST /api/v1/knowledge/query`) enforcing strict cross-project data isolation. Compute cosine similarity against project chunks; if max similarity is below threshold ($< 0.65$), refuse to speculate and declare honest uncertainty with 0 citations.
  4. When evidence exists ($\ge 0.65$), synthesize answers via `LLMProvider` grounded strictly in retrieved context with inspectable citations (`document_name`, `chunk_id`, `page_number`, `similarity_score`, `verification_status`).
- **Consequences:** Delivers an auditable knowledge network and conversational assistant that engineers can trust; prevents cross-project leakage and eliminates unsubstantiated operational claims.

### ADR-012: Google Gemini v1beta Model Alignment & Multimodal Provider Verification
- **Status:** **APPROVED, IMPLEMENTED & VERIFIED**
- **Context:** Newly provisioned Google AI Studio API keys on the `v1beta` registry deprecate legacy models like `gemini-2.5-flash` with a 404 response. Embeddings similarly require models present in the current Google AI Studio model registry.
- **Decision:**
  1. Standardize default live Gemini generation model to `gemini-flash-lite-latest` in `backend/.env`.
  2. Standardize default live Gemini embedding model to `gemini-embedding-001` (producing 3072-dimensional normalized vectors).
  3. Ensure absolute `.env` path resolution in `backend/app/core/config.py` using `Path(__file__).resolve().parent.parent.parent / ".env"`.
  4. Never print, log, or leak API keys in test logs, terminal outputs, or API responses.
- **Consequences:** Google Gemini API is verified genuinely active for live queries and extractions, with sub-second latency and zero credential leaks.

### ADR-013: Knowledge Loss Radar Engine & Transparent Coverage Scoring
- **Status:** **APPROVED, IMPLEMENTED & VERIFIED** (Step 5 / Module 5)
- **Context:** Departing employees, architectural drift, and single-maintainer dependencies frequently cause silent knowledge loss before anyone notices. Teams need continuous, proactive detection of documentation voids with clear, auditable remediation workflows.
- **Decision:**
  1. Implement `RadarService` (`backend/app/services/radar.py`) with 4 deterministic detectors:
     - `ADR_MISSING`: Architectural and configuration components lacking linked Architecture Decision Records.
     - `SECONDARY_OWNER_MISSING`: Modules maintained solely by a single engineer without designated backup maintainers, flagging Single Points of Failure (SPOFs).
     - `STALE_DOCUMENTATION`: Technical documents uploaded $>30$ days ago without periodic re-verification.
     - `UNDOCUMENTED_DEPENDENCY`: External dependencies declared in employee handovers that lack integration runbooks or recovery documentation.
  2. Ground all detected risks with verbatim source references (document name, chunk index, handover role, confidence). Reject fabricated risks or owners.
  3. Compute transparent, project-specific 0-100 Knowledge Coverage Score:
     $$\text{Raw Score} = \text{Documentation}[35] + \text{Decisions}[30] + \text{Ownership}[20] + \text{Verification}[15]$$
     $$\text{Penalties} = (\text{Critical} \times 15) + (\text{High} \times 8) + (\text{Medium} \times 4) + (\text{Low} \times 2)$$
     $$\text{Coverage Score} = \max(0, \min(100, \text{Raw Score} - \text{Penalties}))$$
  4. Expose REST endpoints: `GET /radar/overview`, `GET /radar/risks`, `POST /radar/scan`, `PATCH /radar/risks/{risk_id}` with audit logging and immediate score recalculation.
  5. Build dedicated frontend `RadarView.tsx` with coverage health gauges, severity spectrum heatmap, search/filtering toolbar, remediation modal, and formula transparency modal.
- **Consequences:** Proactively safeguards institutional continuity with auditable evidence; provides engineering leaders with an actionable, transparent metric for technical debt and turnover risk.

### ADR-014: Synora Sentinel Handover Integrity & Verification Engine
- **Status:** **APPROVED, IMPLEMENTED & VERIFIED** (Step 6 / Module 7)
- **Context:** Project handovers submitted by transitioning engineers frequently contain uncorroborated completion claims, contradictory status flags (e.g. marking deliverables complete while listing them as unresolved blockers), empty sections, broken technical links, and missing environment setup guides. These voids result in immediate post-departure engineering outages.
- **Decision:**
  1. Implement `SentinelService` (`backend/app/services/sentinel.py`) as an automated continuous verification engine executing 7 deterministic audit checks:
     - `MISSING_DOCUMENTATION`: 0 attached architectural runbooks or specifications.
     - `INCOMPLETE_HANDOVER_SECTION`: Missing mandatory responsibilities or dependencies.
     - `BROKEN_OR_MISSING_REFERENCE`: Placeholder technical references (`TODO`, `TBD`, `localhost`) or empty links.
     - `UNSUPPORTED_COMPLETION_CLAIM`: Completed tasks lacking verifiable keyword corroboration in attached documentation.
     - `CONTRADICTORY_HANDOVER_INFO`: Deliverables marked completed that simultaneously appear in pending tasks or blockers.
     - `MISSING_ENVIRONMENT_SETUP`: Absences of reproducible local or containerized setup instructions.
     - `SPOF_RISK`: Single Point of Failure concentration when Bus Factor $\le 1.0$ without completed transition dossiers.
  2. Clearly classify findings into:
     - `Verified Fact`: Confirmed by attached documentation or system assets.
     - `Unverified Claim`: Claimed complete by departing employee without evidence.
     - `Suspected Inconsistency`: Conflicting statements between sections or documentation.
  3. Compute transparent Handover Integrity Score:
     $$\text{Base Score} = \text{Sections}[30] + \text{Documents}[30] + \text{SupportedTasks}[25] + \text{EnvSetup}[15]$$
     $$\text{Penalties} = (\text{Critical} \times 20) + (\text{High} \times 10) + (\text{Medium} \times 5) + (\text{Low} \times 2)$$
     $$\text{Handover Integrity Score} = \max(0, \min(100, \text{Base Score} - \text{Penalties}))$$
  4. Expose REST endpoints: `GET /sentinel/overview`, `GET /sentinel/risks`, `POST /sentinel/scan`, `PATCH /sentinel/risks/{risk_id}` supporting both resolution and `request_changes` transitions on associated handovers.
  5. Build dedicated `SentinelView.tsx` with repository integrity matrix, severity pills, findings stream, and revision request modal.
- **Consequences:** Eliminates subjective handover reviews; ensures no employee transition dossier is approved without factually grounded evidence and reproducible environment runbooks.

---

## 3. Completed Work Log

| Phase | Milestone | Timestamp | Deliverables & Verification |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Baseline Setup & Scaffold | 09 Nov 2026, 18:45 IST | React + Vite + TypeScript frontend initialized with `npm.cmd`; FastAPI backend configured in Python 3.12 virtual environment; 5/5 Pytest test cases passing; frontend production build verified; live server communication verified. |
| **Phase 2** | Documentation Suite & Consistency Audit | 09 Nov 2026, 21:15 IST | Authored and audited all 6 authoritative project documents in `/docs`: `PRD.md`, `Architecture.md`, `Rules.md`, `Phases.md`, `Design.md`, and `Memory.md`. Corrected the 8 product module definitions, established Supabase PostgreSQL as primary database, enforced provider-independent AI, removed absolute claims, and established clear prototype acceptance criteria. |
| **Skills** | Agent Skills Workspace Enhancement | 09 Nov 2026, 21:35 IST | Curated and installed 4 compatible MIT agent skills in `.agents/skills/`: `ui-ux-pro-max`, `react-best-practices`, `supabase-postgres-best-practices`, and `api-and-interface-design`. |
| **Phase 3** | Persistent Database Layer & Schema Migrations | 09 Nov 2026, 21:55 IST | Implemented SQLAlchemy ORM with Supabase PostgreSQL dialect abstraction & SQLite fallback; configured Alembic migrations (`0ab674b0c6fe_initial_schema_all_models.py`); created 15 entity models; built enterprise seeder; refactored endpoints with database sessions; verified with 16 passing backend tests. |
| **Step 1** | Handover Lifecycle & Review Workflow | 09 Nov 2026, 22:45 IST | Implemented complete 6-state handover lifecycle FSM, 8 REST endpoints, manager approval and change request workflow, dynamic readiness score calculation, Markdown report export, dual-persona frontend (Employee/Manager), and verified with 17 passing backend tests and clean frontend build. |
| **Step 2** | Knowledge Integration Pipeline & Document Processing | 09 Nov 2026, 23:20 IST | Implemented secure document upload (`.pdf`, `.md`, `.txt`), storage provider abstraction, SHA-256 deduplication, sliding-window chunker with page-number tracking, 4 REST endpoints (`upload`, `list`, `get`, `chunks`, `delete`), attached document UI & inspector in Employee/Manager drawer, and verified with 25 passing backend tests and clean frontend build. |
| **Step 3** | Knowledge Extraction & Verification Engine (Module 2) | 09 Nov 2026, 23:55 IST | Implemented provider-independent LLM service with Google Gemini API & deterministic mock engine, structured chunk-level knowledge extraction, verbatim source grounding, $<0.65$ confidence flagging, manager verification/modification/rejection workflows, Alembic migration `5033ca3bd58a`, and verified with 30 passing backend tests and clean frontend build. |
| **Step 4** | Memory Graph & AI Knowledge Assistant (Modules 3 & 4) | 10 Nov 2026, 00:25 IST | Implemented grounded graph constructor (`/knowledge/graph`), dense vector embedding provider, cosine similarity retrieval with honest uncertainty bounds, RAG Q&A endpoint (`/knowledge/query`) with inspectable citations, interactive SVG graph explorer, and verified with 38 passing backend tests and clean frontend build. |
| **Step 5** | Knowledge Loss Radar (Module 5) | 10 Nov 2026, 00:55 IST | Implemented `RadarService` with detectors for `ADR_MISSING`, `SECONDARY_OWNER_MISSING`, `STALE_DOCUMENTATION`, and `UNDOCUMENTED_DEPENDENCY`; transparent 0-100 coverage scoring formula; 5 REST endpoints (`overview`, `risks`, `scan`, `remediate`, `coverage`); dedicated frontend `RadarView.tsx` with risk heatmap, remediation modal, and formula inspector; verified with 44 passing backend tests and clean frontend build. |
| **Step 6** | Synora Sentinel (Module 7) | 10 Nov 2026, 01:25 IST | Implemented `SentinelService` with 7 audit detectors (missing docs, incomplete sections, broken links, unsupported claims, contradictory tasks, missing env setup, SPOF); transparent 0-100 integrity scoring formula; 4 REST endpoints (`overview`, `risks`/`findings`, `scan`, `remediate`); dedicated frontend `SentinelView.tsx` with project integrity matrix and change request workflow; verified with 51 passing backend tests and clean frontend build. |
| **Step 7** | Environment Recreator (Module 8) | 10 Nov 2026, 02:00 IST | Implemented `RecreatorService` with live disk manifest inspection (`requirements.txt`, `package.json`, `.env.example`, `Dockerfile`), deterministic Windows PowerShell (`.cmd` aware) & POSIX Bash quickstarts, self-contained `docker-compose.yml` with health check probes, strict regex-based secret redaction, 7-step interactive onboarding checklist with persistent step attribution, 8 REST endpoints, dedicated frontend `RecreatorView.tsx`; verified with 59 passing backend tests and clean frontend build. |

---

## 4. Pending Work Log (Implementation Roadmap)

| Phase | Target Window | Scope of Work | Priority |
| :--- | :--- | :--- | :--- |
| **Step 8** | 10 Nov 02:30 – 10 Nov 06:00 IST | End-to-end integration test suite, UI responsiveness polish, toast notifications, navigation flows across all 8 modules. | **HIGH** |
| **Step 9** | 10 Nov 06:00 – 11 Nov 10:00 IST | Cloud deployment (Render + Vercel + Supabase), live domain verification, smoke test signoff. | **CRITICAL** |

---

## 5. Architectural Decision Records (ADRs)

### ADR-015: Environment Recreator & Deterministic Onboarding Engine (10 Nov 2026)
- **Context:** Departing engineers often leave behind partial, outdated, or platform-specific setup instructions. Incoming developers waste days debugging version incompatibilities, missing environment variables, or PowerShell execution policies.
- **Decision:** Build an evidence-driven `RecreatorService` that inspects live repository manifests on disk (`requirements.txt`, `package.json`, `.env.example`, `Dockerfile`). Generate deterministic Windows PowerShell (`.cmd` wrapper aware) and POSIX Bash setup sequences. Redact all database passwords and API tokens using regex and replacement rules (`your_gemini_api_key_here`, `postgresql://user:[REDACTED_PASSWORD]@host/db`). Persist an interactive 7-step onboarding checklist within `EnvironmentSnapshot.blueprint_spec` using SQLAlchemy `flag_modified` to track step completion timestamps and actor attribution.
- **Consequences:** Incoming engineers ramp up in minutes with zero guesswork. No credentials or secrets are ever exposed in export artifacts or API payloads. All 8 original product modules are now fully implemented and verified.

### ADR-016: Comprehensive Phase 8 Hardening, Live Gemini Verification & Deployment Readiness (10 Nov 2026)
- **Context:** Prior to final production deployment and presentation, the complete multi-module pipeline needed exhaustive end-to-end integration testing, live Google Gemini API verification, frontend error containment, and production container definitions.
- **Decision:** Implemented `test_e2e_workflow.py` validating the full 8-module lifecycle in an automated test. Verified live Gemini generation (`gemini-flash-lite-latest`, 1.74s latency) and live Gemini embedding (`gemini-embedding-001`, 3072 dimensions, 0.80s latency). Added React `ErrorBoundary` and unified `ToastProvider` to prevent white-screen crashes. Created multi-stage `Dockerfile` (backend and frontend), `docker-compose.yml`, `render.yaml`, and `vercel.json` for deployment readiness.
- **Consequences:** 60/60 backend tests pass without mock illusions. System is proven capable of running against live Gemini cloud APIs with seamless fallback resilience. Frontend gracefully catches component errors and alerts users. Deployment assets are verified.

### ADR-017: Production-Grade Server-Side Authentication & Role-Based Authorization (RBAC) (10 Nov 2026)
- **Context:** Previous phases utilized client-side persona switching for UX testing. In an enterprise handover platform, sensitive operations (approving handovers, requesting revisions, verifying knowledge nodes, resolving risk alerts) must be strictly enforced on the server, passwords must be securely hashed with bcrypt, and multi-tenant organizations must be isolated against unauthorized cross-organization leakage.
- **Decision:**
  1. Implemented secure password hashing via `bcrypt` (salt rounds=12) and JWT token creation/decoding via `pyjwt` in `backend/app/core/security.py`. Plaintext passwords are never stored or logged.
  2. Implemented REST endpoints: `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, and `GET /api/v1/auth/me`.
  3. Enforced server-side `require_role('manager')` dependency on all sensitive mutation endpoints:
     - `POST /api/v1/handovers/{id}/approve`
     - `POST /api/v1/handovers/{id}/request-changes`
     - `POST /api/v1/handovers/{id}/start-review`
     - `POST /api/v1/handovers/{id}/complete`
     - `PATCH /api/v1/sentinel/risks/{risk_id}`
     - `PATCH /api/v1/radar/risks/{risk_id}`
     - `PATCH /api/v1/knowledge/nodes/{node_id}/verify`
  4. Enforced strict organization and project data isolation (`verify_project_organization_access`, `verify_handover_organization_access`), failing closed with HTTP 403 Forbidden or HTTP 404 Not Found on cross-tenant access attempts.
  5. Built full frontend authentication suite with `AuthModal.tsx`, server-issued JWT role badge display in `Navbar.tsx`, session expiration handling with global toast notifications, and automatic Bearer token injection via `authFetch()` across all API requests.
- **Consequences:** Client-side persona toggles cannot bypass server authorization. Complete test suite expanded to 68/68 passing tests, with 8 dedicated security tests verifying 401s, 403s, cross-org isolation, and bcrypt validation. Clean production build verified.

### ADR-018: Supabase PostgreSQL Integration & Dual-Dialect Vector Resilience (10 Nov 2026)
- **Context:** Phase 8 Task 2 required connecting Synora to real Supabase PostgreSQL instances while preserving local development/testing offline fallback with SQLite, ensuring zero credential leaks in logs/APIs, and supporting pgvector without breaking SQLite CI runs.
- **Decision:**
  1. Followed `.agents/skills/supabase-postgres-best-practices/SKILL.md`: implemented `pool_pre_ping=True`, `pool_size=5`, `max_overflow=5`, `pool_recycle=300`, `pool_timeout=30`, and `connect_args={"sslmode": "require", "connect_timeout": 15}`.
  2. Created `normalize_db_url()` to dynamically convert standard Supabase connection strings (`postgres://` or `postgresql://`) into SQLAlchemy 2.0 compatible `postgresql+psycopg2://`.
  3. Created `mask_database_url()` to strip passwords and redact Supabase project reference IDs (`db.***.supabase.co`) from logs, telemetry, and health responses.
  4. Dual-column vector compatibility: Added `embedding_vector = Column(Vector(), nullable=True)` to `DocumentChunk` alongside `embedding_json`. `pgvector` extension is enabled idempotently (`CREATE EXTENSION IF NOT EXISTS vector;`) during Alembic upgrade.
  5. Expanded `GET /api/v1/health` and frontend `Navbar.tsx` status pill with live database dialect, masked target, connection latency, table count, and `pgvector_installed` status.
  6. Created end-to-end 7-step test script `backend/scripts/verify_supabase_postgres.py` testing connection, pgvector, migrations, tables, CRUD across all 15 models, session persistence, and tenant isolation.
- **Consequences:** Backend seamlessly auto-detects either Supabase PostgreSQL or SQLite without code changes. All 68 backend tests pass, frontend production build is clean, and the application is production-ready for live Supabase deployment.

### ADR-019: Supabase Storage Integration & Hierarchical Multi-Tenant Object Persistence (10 Nov 2026)
- **Context:** Phase 8 Task 3 required implementing persistent cloud document storage in Supabase Storage without losing local development support, ensuring private bucket isolation, organizing documents hierarchically, and generating signed URLs without leaking service-role credentials to clients.
- **Decision:**
  1. Provisioned a private storage bucket named `synora-documents` (`public=false`) in Supabase.
  2. Created provider abstraction `StorageProvider` in `backend/app/services/storage.py` with `SupabaseStorageProvider` (REST API client, connection pooling, and signed URL generation) and `LocalStorageProvider` (safe local filesystem fallback).
  3. Established strict hierarchical object organization: `{organization_id}/{project_id}/{document_id}/{filename}` in `IngestionService.process_and_store_document()`.
  4. Enforced organization-level isolation on all storage operations via `verify_document_organization_access()`, failing closed with HTTP 403 Forbidden on unauthorized cross-tenant requests.
  5. Implemented secure download mechanisms: `GET /api/v1/documents/{id}/download` generates short-lived signed URLs without exposing backend `service_role` keys, and `GET /api/v1/documents/{id}/stream` streams binary data for authorized users.
  6. Preserved SHA-256 duplicate detection and metadata in PostgreSQL, and authored `backend/scripts/migrate_local_to_supabase_storage.py` for safe migration.
  7. Authored `backend/scripts/verify_supabase_storage.py` testing private bucket configuration, PDF binary upload, presence checks, SHA-256 bit-for-bit checksum match, signed URL creation, cross-org denial, and clean deletion.
- **Consequences:** Synora documents are securely stored in Supabase Storage with cryptographic checksum verification and zero credential exposure. Test suite passes 68/68, frontend build is clean.

### ADR-020: Formal New-Joiner Handover Assignment & Access Boundary Enforcement (10 Nov 2026)
- **Context:** While a manager could approve a handover, formal assignment of a handover to a specific incoming engineer was previously unverified in the database and API. Assignment must be restricted to managers, enforce organization boundary checks, prohibit premature assignments in `draft` status, and enforce access restrictions so that third-party employees cannot access another engineer's assigned handover.
- **Decision:**
  1. Evolved `Handover` model with indexed foreign key `assigned_to` referencing `users.id` and timestamp `assigned_at`.
  2. Created Alembic migration `8b9f01bc34de_add_handover_assigned_to.py` with explicit named constraint `fk_handovers_assigned_to` ensuring cross-dialect SQLite batch and PostgreSQL compatibility. Applied at head on Supabase.
  3. Implemented `POST /api/v1/handovers/{id}/assign` guarded by `require_role('manager')`, validating target user existence and organization membership, and rejecting `draft` state handovers with HTTP 400 Bad Request.
  4. Implemented `GET /api/v1/handovers/assignees` to list eligible teammates within the manager's organization.
  5. Enforced assignment access boundaries in `verify_handover_organization_access()`: assigned employees and authors can view the handover, while unassigned third-party employees receive HTTP 403 Forbidden.
  6. Emitted `assign_handover` and `reassign_handover` audit events in `AuditLog`.
  7. Integrated assignment modal, status tags, and "Assigned to Me" query filter in `HandoverView.tsx` without changing the visual theme or component layout.
- **Consequences:** 10/10 dedicated assignment tests pass, migration tests pass, live Supabase PostgreSQL persistence verified across 6 checks, full regression suite passes 78/78, and frontend builds with 0 errors.

### ADR-021: Multi-Tenant Handover Scoping, Anonymous Access Elimination & Health Redaction (10 Nov 2026)
- **Context:** Security audit revealed three critical boundary vulnerabilities: (1) unlinked handovers without `project_id` lacked an explicit `organization_id`, allowing cross-organization read exposure; (2) `GET /api/v1/handovers/` and `GET /api/v1/handovers/{id}` allowed anonymous unauthenticated access; (3) public `/api/v1/health` exposed database driver scheme, partial hostnames, and connection pool statistics.
- **Decision:**
  1. Added `organization_id` foreign key (`organizations.id`) with index on `Handover`.
  2. Implemented Alembic migration `a3cfb3a89578_add_handover_organization_id.py` with safe backfill: derives `organization_id` from linked project where present, resolves from creator organization membership for unlinked dossiers, and preserves unresolved records without guessing. Applied at head on Supabase.
  3. Removed anonymous access across all sensitive handover routes: `GET /api/v1/handovers/`, `GET /api/v1/handovers/{id}`, and `GET /api/v1/handovers/{id}/export` now require `get_current_user` and return `HTTP 401 Unauthorized` when unauthenticated.
  4. Enforced organization scoping in `verify_handover_organization_access()`: users outside the organization receive strict `HTTP 403 Forbidden`. Handover listings are strictly filtered by caller organization.
  5. Handover creation paths automatically populate `organization_id` from project or user organization.
  6. Completely sanitized public `/api/v1/health`: replaced hostnames and connection strings with abstract `database_target` (`"managed-cloud"` or `"local"`), removed all pool statistics, and redacted driver exception strings. Added authenticated `GET /api/v1/health/diagnostics`.
  7. Updated `run.py` to bind to `os.environ.get("PORT", 8000)` for Render compatibility.
- **Consequences:** All 41 live security audit checks pass (`verify_security_audit.py`), 86 backend tests pass, frontend production build compiles cleanly in 1.7s, and documentation (`SECURITY_AUDIT.md`, `RENDER_DEPLOYMENT.md`, `VERCEL_DEPLOYMENT.md`) is complete.

---

## 6. Known Issues & Workarounds

1. **Issue:** Windows Standard Sandbox Environment Variable Token Limit (`CreateProcessSecurityEnvironment: The filename or extension is too long`).  
   - **Workaround:** Terminal commands execute using standard PowerShell execution within the sanctioned environment.
2. **Issue:** Node wrapper on Windows PowerShell requires `.cmd` extension.  
   - **Workaround:** Always invoke `npm.cmd` explicitly in all scripts and documentation.
3. **Issue:** Background daemon servers in testing environments.  
   - **Workaround:** Bound backend Uvicorn server and Vite frontend server to `0.0.0.0` to guarantee reachability from localhost, 127.0.0.1, and external browser tabs.
4. **Issue:** SQLite does not natively support Postgres `vector` type.  
   - **Workaround:** Implemented dual embedding persistence: `embedding_json` column (JSON array) for SQLite local fallback and compatibility, alongside `pgvector` compatibility when connected to Supabase PostgreSQL.
5. **Issue:** SQLAlchemy nested mutable JSON changes (`EnvironmentSnapshot.blueprint_spec`).  
   - **Workaround:** Explicitly invoke `flag_modified(snapshot, "blueprint_spec")` from `sqlalchemy.orm.attributes` to trigger ORM change tracking on deep dictionaries/lists.

---

## 7. Next Steps (Immediate Action Items for Step 8: End-to-End Polish & Verification)

1. Conduct end-to-end user workflow walk-through: Leaving Employee handover submission → Document ingestion & extraction → Manager Sentinel audit & approval → Memory Graph Q&A → Radar gap discovery → Environment recreation.
2. Verify responsive layout, keyboard accessibility, and navigation toast feedback across all 8 modules.
3. Prepare production deployment configurations for Render backend, Vercel frontend, and Supabase PostgreSQL.
