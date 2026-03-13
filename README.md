# VeilMirror Platform

Web platform that ingests a public GitHub repository, creates an anonymized hosted mirror at a unique URL, and supports manual resync while blocking publication when leak checks fail.

This repository includes two runtimes:
- Core runtime (FastAPI + React) at `http://localhost:5173`
- Advanced runtime (full VeilMirror feature set) at `http://localhost:5000`

## Stack

- Backend: FastAPI + SQLAlchemy + RQ worker
- Frontend: React (Vite)
- Data: PostgreSQL + Redis
- Deployment: Docker Compose (single VM profile)

## Features implemented

- Create mirror from a public GitHub URL (`https://github.com/{owner}/{repo}`)
- Generate high-entropy public mirror URL token
- Manual sync job queue (RQ + Redis)
- Anonymization pipeline:
  - strips `.git` metadata from published artifact
  - replaces sensitive tokens (owner/repo/URL/author names-emails) in text files
  - replaces all detected emails with `[REDACTED_EMAIL]`
  - blocks publish if unresolved sensitive hits remain
- Public mirror access:
  - JSON listing: `GET /m/{token}`
  - Browsable HTML with file tree + preview panel: `GET /m/{token}/browse?path=...`
  - Raw files: `GET /m/{token}/raw/{path}`
  - Alias routes (v2-style): `GET /r/{token}`, `/r/{token}/browse`, `/r/{token}/raw/{path}`
- URL expiry with default 90-day TTL and manual renewal (`POST /mirrors/{id}/renew-url`)
- Latest snapshot only (old snapshot is overwritten)
- v2 frontend UX and operations flow (home + anonymize + dashboard)

## Run with Docker

```bash
docker compose up --build
```

Services:

- API: `http://localhost:8000`
- UI: `http://localhost:5173`

## Run Advanced Feature Set (all missing parity features)

The `advanced/` directory contains the VeilMirror advanced stack (GitHub OAuth, private repos, pull request anonymization, conferences, admin panel, quotas, webview routes, claim flow, and queue/admin operations).
It has been productized as **VeilMirror** (custom branding/UI and one-click platform OAuth login, with optional custom OAuth support) while preserving feature parity.

Start advanced services:

```bash
docker compose --profile advanced up --build -d advanced-app advanced-streamer advanced-redis advanced-mongodb
```

Open:

- Advanced app: `http://localhost:5000`

Optional setup:

1. Set `ADVANCED_GITHUB_CLIENT_ID` and `ADVANCED_GITHUB_CLIENT_SECRET` in a root `.env` file (see `.env.example`) for platform-managed one-click login.
2. Start advanced services and click `Login with GitHub` (no per-user client ID/secret entry required).
3. Optional: copy `advanced/.env.example` to `advanced/.env` only when running `advanced/docker-compose.yml` directly.
4. For custom OAuth apps, set callback URL to `http://localhost:5000/github/auth`.

## Deploy Advanced Runtime on Railway

Create separate Railway services from this same repository:

1. `advanced-app`: root directory `advanced`, Dockerfile `advanced/Dockerfile`, default start command.
2. `advanced-streamer`: same build as above, start command:
   - `node --require ./opentelemetry.js ./build/streamer/index.js`
3. Redis service (Railway Redis plugin or service exposing `REDIS_URL`).
4. MongoDB service (Railway Mongo plugin or service exposing `MONGODB_URI`).

Set these variables on both `advanced-app` and `advanced-streamer`:

- `CLIENT_ID` and `CLIENT_SECRET` (GitHub OAuth app credentials)
- `SESSION_SECRET` (long random secret)
- `APP_BASE_URL=https://<your-railway-domain>`
- `AUTH_CALLBACK=https://<your-railway-domain>/github/auth`
- `APP_HOSTNAME=<your-railway-domain-without-https>`
- `REDIS_URL=<railway-redis-url>`
- `MONGODB_URI=<railway-mongodb-uri>`
- `TRUST_PROXY=1`
- `STREAMER_ENTRYPOINT=http://<private-streamer-domain>:<port>/`

GitHub OAuth app settings must match:

- Homepage URL: `https://<your-railway-domain>`
- Authorization callback URL: `https://<your-railway-domain>/github/auth`

## Key API endpoints

- `POST /mirrors` body: `{ "source_url": "https://github.com/org/repo" }`
- `GET /mirrors`
- `GET /mirrors/{id}`
- `GET /mirrors/{id}/jobs`
- `POST /mirrors/{id}/sync`
- `POST /mirrors/{id}/renew-url`
- `GET /stats`

## Local backend test run

```bash
cd backend
pip install -r requirements.txt
pytest
```

## Notes

- V1 currently supports public GitHub sources only.
- Sync is manual-only in this implementation.
- Binaries are included as-is and are not metadata-scrubbed.
- Existing core features are preserved; advanced features are added side-by-side in `advanced/`.

