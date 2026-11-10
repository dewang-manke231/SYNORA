# Vercel Frontend Deployment Guide

This document outlines the deployment configuration for hosting the **Synora Frontend** application on Vercel.

---

## 1. Project Settings

- **Framework Preset:** Vite
- **Root Directory:** `frontend`
- **Build Command:** `npm run build`
- **Output Directory:** `dist`
- **Install Command:** `npm install`

---

## 2. SPA Routing Configuration (`vercel.json`)

Vercel requires single-page application (SPA) rewrite rules so that client-side routes (such as `/`, `/handovers`, `/documents`, `/radar`) resolve to `index.html`.

This is pre-configured in `frontend/vercel.json`:
```json
{
  "framework": "vite",
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "rewrites": [
    {
      "source": "/(.*)",
      "destination": "/index.html"
    }
  ]
}
```

---

## 3. Environment Variables

| Variable Name | Required | Description | Example / Recommended Value |
| :--- | :---: | :--- | :--- |
| `VITE_API_URL` | **Yes** | Public URL of the deployed Render backend | `https://synora-backend.onrender.com` |

> **IMPORTANT SECURITY NOTE:**  
> Never define `SUPABASE_SERVICE_ROLE_KEY`, `JWT_SECRET_KEY`, or database credentials in Vercel environment variables or frontend code. The frontend interacts strictly with the Synora API via JWT Bearer authentication.

---

## 4. Build Verification

Before triggering a production deployment on Vercel, verify locally:
```bash
cd frontend
npm run build
```
- Expected Result: Type check and bundle compile cleanly (`dist/assets/index-*.js`, 0 errors).

