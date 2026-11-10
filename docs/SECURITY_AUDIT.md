# Synora Platform Security Audit Report

**Date:** 10 November 2026  
**Auditor:** Autonomous Verification Engine  
**Target Environment:** Supabase Cloud PostgreSQL (pgvector v0.8.2) + Supabase Cloud Storage (`synora-documents`)  
**Scope:** Multi-Tenant Isolation, API Router Authentication, RBAC Role Enforcement, Health Endpoint Redaction, Document & Storage Security, Cryptographic Credentials.

---

## Executive Summary

A comprehensive, adversarial security audit and end-to-end multi-tenant validation was executed across all backend API routers and database models in the Synora platform.

All identified vulnerabilities—including multi-tenant handover scoping, anonymous endpoint exposure, health check credential and topology leakage, and foreign key isolation gaps—were remediated, verified with live database migrations, regression-tested with automated test suites, and validated against the live cloud Supabase environment.

| Total Security Checks Executed | Passed | Failed | Unresolved Vulnerabilities |
| :--- | :--- | :--- | :--- |
| **41 Live Adversarial Checks** | **41** | **0** | **0** |
| **86 Pytest Backend Unit & Integration Tests** | **86** | **0** | **0** |
| **7 Supabase Storage Integration Checks** | **7** | **0** | **0** |
| **6 Live Supabase Assignment Checks** | **6** | **0** | **0** |
| **Frontend Production TypeScript Build** | **Success (0 errors)** | **0** | **0** |

---

## Vulnerability Findings, Classifications & Remediations

### 1. [HIGH] Multi-Tenant Handover Isolation Gap for Unlinked Dossiers
- **Category:** Broken Object Level Authorization (BOLA) / Multi-Tenancy Boundary Failure
- **Finding:** Handovers created without a linked `project_id` lacked an explicit `organization_id` column. Cross-organization managers and employees were able to retrieve and enumerate dossiers created by external organizations.
- **Remediation:**
  1. Added `organization_id` foreign key (`organizations.id`) with index on the `Handover` model.
  2. Implemented and applied Alembic migration `a3cfb3a89578_add_handover_organization_id.py` with safe backfill:
     - Derives `organization_id` from linked project where present.
     - Derives `organization_id` from creator's verified organization membership for unlinked dossiers.
     - Preserves unresolvable legacy records without guessing or data loss.
  3. Enforced organization scoping in `verify_handover_organization_access()`: users outside the organization receive strict `HTTP 403 Forbidden`.
  4. Updated `list_handovers()` to restrict results to the caller's organization memberships, assigned dossiers, or self-created dossiers.

### 2. [HIGH] Anonymous Access to Handover Dossiers
- **Category:** Missing Authentication
- **Finding:** `GET /api/v1/handovers/` and `GET /api/v1/handovers/{id}` utilized `get_current_user_optional`, allowing unauthenticated actors to read confidential corporate handover dossiers.
- **Remediation:**
  1. Replaced `get_current_user_optional` with strict `get_current_user` dependency across `GET /api/v1/handovers/`, `GET /api/v1/handovers/{id}`, and `GET /api/v1/handovers/{id}/export`.
  2. Anonymous requests fail closed with `HTTP 401 Unauthorized` and `WWW-Authenticate: Bearer` challenge.

### 3. [MEDIUM] Public Health Endpoint Infrastructure & Topology Leakage
- **Category:** Security Misconfiguration / Information Disclosure
- **Finding:** The public `/api/v1/health` endpoint previously exposed partial database connection targets (including Supabase hostnames, cloud regions, and driver schemes) and connection pool metrics (`checked_in`, `checked_out`, `size`).
- **Remediation:**
  1. Fully sanitized public `/api/v1/health`:
     - `database_target` replaced with abstract string (`"managed-cloud"` or `"local"`).
     - Removed all database URLs, pooler ports, regions, and pool statistics.
     - Redacted all raw driver exception strings on connectivity failures to prevent connection string leakage.
  2. Created an authenticated diagnostics endpoint `GET /api/v1/health/diagnostics` restricted to authenticated operators (`get_current_user`).

### 4. [HIGH] Premature State Validation in Handover Assignment
- **Category:** Improper Authorization Ordering
- **Finding:** When a manager attempted to assign a handover dossier, state validation (`draft` status check) occurred prior to verifying if the manager belonged to the same organization as the dossier, leaking state information via `HTTP 400` instead of rejecting with `HTTP 403`.
- **Remediation:**
  1. Placed `verify_handover_organization_access()` at the entry point of `/api/v1/handovers/{handover_id}/assign`.
  2. Cross-organization assignment attempts are immediately rejected with `HTTP 403 Forbidden` before state or payload inspection.

### 5. [MEDIUM] Organization Isolation for Repository Blueprint & Environment Exports
- **Category:** Broken Access Control
- **Finding:** `GET /api/v1/recreator/export/env`, `GET /api/v1/recreator/export/docker`, and `GET /api/v1/recreator/blueprint` lacked project-level organization isolation.
- **Remediation:**
  1. Added `verify_project_organization_access()` checks to all Recreator blueprint, checklist, and export endpoints.

---

## Router-by-Router Security Audit Matrix

| Router | Path | Auth Required | Role Required | Org Scoped | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Auth** | `POST /api/v1/auth/register` | None (Public) | None | N/A | **PASSED** (bcrypt rounds=12, email regex, 8+ char pw) |
| **Auth** | `POST /api/v1/auth/login` | None (Public) | None | N/A | **PASSED** (generic timing-safe 401 error) |
| **Auth** | `GET /api/v1/auth/me` | Bearer JWT | Any active | Self | **PASSED** (passwords omitted from schema) |
| **Health** | `GET /api/v1/health` | None (Public) | None | Public | **PASSED** (abstract target, no hostnames or secrets) |
| **Health** | `GET /api/v1/health/diagnostics`| Bearer JWT | Any active | Caller | **PASSED** (authenticated only, credentials redacted) |
| **Handover** | `GET /api/v1/handovers/` | Bearer JWT | Any active | Org-only | **PASSED** (unauthenticated 401, multi-tenant filtered) |
| **Handover** | `GET /api/v1/handovers/{id}` | Bearer JWT | Any active | Org-only | **PASSED** (cross-org 403, employee boundary enforced) |
| **Handover** | `POST /api/v1/handovers/` | Bearer JWT | Any active | Org-only | **PASSED** (auto-populates organization_id) |
| **Handover** | `POST /api/v1/handovers/{id}/submit`| Bearer JWT | Employee/Owner| Org-only | **PASSED** |
| **Handover** | `POST /api/v1/handovers/{id}/start-review`| Bearer JWT | Manager | Org-only | **PASSED** (employee 403) |
| **Handover** | `POST /api/v1/handovers/{id}/approve`| Bearer JWT | Manager | Org-only | **PASSED** (employee 403) |
| **Handover** | `POST /api/v1/handovers/{id}/assign`| Bearer JWT | Manager | Org-only | **PASSED** (cross-org 403, employee 403) |
| **Handover** | `GET /api/v1/handovers/assignees` | Bearer JWT | Manager | Org-only | **PASSED** (scoped to manager's org members) |
| **Documents** | `POST /api/v1/documents/upload` | Bearer JWT | Any active | Org-only | **PASSED** (MIME validation, size limit, SHA-256 dedup) |
| **Documents** | `GET /api/v1/documents/` | Bearer JWT | Any active | Org-only | **PASSED** (scoped by project org) |
| **Documents** | `GET /api/v1/documents/{id}/download` | Bearer JWT | Any active | Org-only | **PASSED** (signed URLs, service-role keys never exposed) |
| **Documents** | `DELETE /api/v1/documents/{id}` | Bearer JWT | Any active | Org-only | **PASSED** (cross-org deletion blocked 403) |
| **Knowledge** | `GET /api/v1/knowledge/graph` | Bearer JWT | Any active | Org-only | **PASSED** (scoped to project org) |
| **Knowledge** | `POST /api/v1/knowledge/query` | Bearer JWT | Any active | Org-only | **PASSED** (RAG retrieval scoped to project chunks) |
| **Knowledge** | `PATCH /api/v1/knowledge/nodes/{id}/verify`| Bearer JWT| Manager | Org-only | **PASSED** (employee 403, cross-org 403) |
| **Radar** | `GET /api/v1/radar/overview` | Bearer JWT | Any active | Org-only | **PASSED** (project scoped) |
| **Radar** | `PATCH /api/v1/radar/risks/{id}` | Bearer JWT | Manager | Org-only | **PASSED** (employee 403) |
| **Sentinel** | `GET /api/v1/sentinel/overview` | Bearer JWT | Any active | Org-only | **PASSED** (project scoped) |
| **Sentinel** | `PATCH /api/v1/sentinel/risks/{id}`| Bearer JWT | Manager | Org-only | **PASSED** (employee 403) |
| **Recreator** | `GET /api/v1/recreator/export/env` | Bearer JWT | Any active | Org-only | **PASSED** (project org check enforced) |

---

## Verification Evidence

1. **Alembic Database Migration Parity:**
   - Head Revision: `a3cfb3a89578` (`add_handover_organization_id`)
   - Applied cleanly on Supabase Cloud PostgreSQL.
   - Upgrade and downgrade tests passed without orphaned schema state.

2. **Live Adversarial Test Output (`verify_security_audit.py`):**
   - 41/41 live HTTP checks passed against running Supabase backend.
   - Anonymous access to handovers rejected (`401`).
   - Cross-organization read and assignment attempts rejected (`403`).
   - Health check reveals zero secrets, credentials, or internal topology.

3. **Backend Regression Test Suite:**
   - 86 test cases executed to completion with **0 failures**.

4. **Frontend Production Build:**
   - Command: `tsc -b && vite build`
   - Exit Code: **0**
   - Bundle: `dist/assets/index-Cnql9SzW.js` (424.16 kB)

---

## Unresolved Risks & Operational Recommendations

1. **JWT Expiration Strategy:**
   - Current access token expiry is configured for 24 hours (`ACCESS_TOKEN_EXPIRE_MINUTES = 1440`).
   - *Recommendation:* Introduce short-lived access tokens (15-60 min) with refresh tokens stored in HTTP-only, Secure cookies for production enterprise hardening.
2. **Rate Limiting:**
   - Authentication endpoints (`/auth/login`, `/auth/register`) do not currently enforce IP-level rate limiting in application middleware.
   - *Recommendation:* Configure cloud edge rate limiting (via Render / Cloudflare / reverse proxy) to mitigate brute-force attempts on `/auth/login`.

