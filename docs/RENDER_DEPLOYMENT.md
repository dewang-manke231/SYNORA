# Render Backend Deployment Guide

This document outlines the deployment configuration for hosting the **Synora Backend** service on Render.

---

## 1. Service Overview

- **Service Type:** Web Service
- **Runtime:** Python 3.12 (or Docker using `backend/Dockerfile`)
- **Root Directory:** `backend`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python run.py` (or `uvicorn app.main:app --host 0.0.0.0 --port $PORT`)
- **Health Check Path:** `/api/v1/health`

---

## 2. Infrastructure & Networking

1. **Port Handling:**
   - Render automatically injects the `$PORT` environment variable (default 10000).
   - `run.py` and `Dockerfile` are configured to bind to `0.0.0.0` and respect `$PORT`.

2. **CORS Configuration:**
   - Configure `CORS_ORIGINS` to include your Vercel frontend domain:
     ```
     CORS_ORIGINS=["https://synora.vercel.app","http://localhost:5173"]
     ```

3. **Database Connectivity:**
   - Direct encrypted SSL connection to Supabase PostgreSQL:
     ```
     DATABASE_URL=postgresql+psycopg2://postgres.[PROJECT_REF]:[PASSWORD]@aws-1-[REGION].pooler.supabase.com:5432/postgres?sslmode=require
     ```
   - Pool pinging (`pool_pre_ping=True`) is active in SQLAlchemy to prevent connection dropouts on Render free-tier idle wakeups.

---

## 3. Required Environment Variables

| Variable Name | Required | Description | Example / Recommended Value |
| :--- | :---: | :--- | :--- |
| `DATABASE_URL` | **Yes** | Supabase PostgreSQL Connection URI | `postgresql+psycopg2://postgres...` |
| `JWT_SECRET_KEY` | **Yes** | 32+ character cryptographically random secret | Generate via `openssl rand -hex 32` |
| `STORAGE_PROVIDER` | **Yes** | Persistent document storage backend | `supabase` |
| `SUPABASE_URL` | **Yes** | Supabase project API URL | `https://[PROJECT_REF].supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | **Yes** | Supabase service-role secret key (backend only) | `sb_secret_...` |
| `SUPABASE_STORAGE_BUCKET` | **Yes** | Storage bucket for private documents | `synora-documents` |
| `GEMINI_API_KEY` | **Yes** | Google Gemini API key for extraction & RAG | `AIzaSy...` |
| `GEMINI_MODEL` | No | Gemini model variant | `gemini-1.5-flash` |
| `EMBEDDING_PROVIDER` | No | Vector embeddings provider | `local` (or `gemini`) |
| `CORS_ORIGINS` | **Yes** | Permitted frontend origins (JSON list or comma-separated) | `["https://synora.vercel.app"]` |
| `PORT` | Auto | Render-injected web service listener port | `10000` |

---

## 4. Pre-Deployment Verification Checklist

- [x] Alembic migration head applied to Supabase PostgreSQL (`a3cfb3a89578`).
- [x] pgvector extension active in Supabase (`v0.8.2`).
- [x] Private Supabase Storage bucket `synora-documents` exists.
- [x] Public `/api/v1/health` verified (returns sanitized `200 OK` without leaking credentials).
- [x] Automated regression suite passing (86/86 tests).

