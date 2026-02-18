# Docker Deployment (PostgreSQL + ELA App)

## Goal

Run the project in containers with stable service boundaries:
- `postgres` for persistence
- `app` for inference/training utilities
- `frontend` for production React UI (served by Nginx)

## Files

- `Dockerfile`
- `docker-compose.yml`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `.env.example`
- `requirements-docker-cpu.txt` (container-only deps, CPU profile)

## 1) Prepare environment

```bash
cp .env.example .env
```

Adjust `.env` values for production secrets, host port mapping, and media thresholds if needed.
Frontend host port is configurable via `FRONTEND_PORT` (default `8080`).

Compose CLI requirement:
- use Docker Compose v2 (`docker compose ...`).
- legacy `docker-compose` v1 is deprecated and is not supported in this setup.

CPU-only container profile:
- Docker image installs `torch` from CPU index (`download.pytorch.org/whl/cpu`).
- This prevents pulling NVIDIA CUDA wheel stacks during `docker compose build`.
- Torch version is configurable via `.env`: `TORCH_VERSION=2.5.1`.

Media limits (default profile):
- `MEDIA_MAX_DURATION_MIN=15`
- `MEDIA_MAX_SIZE_LOCAL_MB=250` (targeting ~15 min medium-quality source files)
- `MEDIA_MAX_SIZE_BACKEND_MB=2048` (hard cap for backend async path)

Runtime policy mode:
- `ELA_RUNTIME_MODE=online` (default)
- available values: `online` | `offline`
- in `offline` mode runtime blocks backend-dependent features and phonetic enrichment.

Deployment + phonetic license gate:
- `ELA_DEPLOYMENT_MODE=local|backend|distributed`
- `ELA_PHONETIC_POLICY=enabled|disabled|backend_only`
- Example safe setup for distributed delivery:
  - `ELA_DEPLOYMENT_MODE=distributed`
  - `ELA_PHONETIC_POLICY=disabled` (or keep `backend_only` and run phonetic only on backend deployment)

Offline user-facing limitations:
- phonetic enrichment is unavailable,
- DB persistence and backend async jobs are unavailable,
- large media above local limits is rejected (no backend fallback in offline mode).

Temporary media retention policy:
- `MEDIA_TEMP_DIR=artifacts/media_tmp`
- `MEDIA_RETENTION_TTL_HOURS=24`
- run cleanup periodically:
  - `.venv/bin/python -m ela_pipeline.runtime.cleanup_media_tmp --dry-run`
  - `.venv/bin/python -m ela_pipeline.runtime.cleanup_media_tmp`

Minimal identity policy:
- `ELA_PHONE_HASH_SALT` must be set (strong secret value).
- backend stores only `phone_hash` in DB (table `backend_accounts`).
- raw phone number must not be persisted.

## 2) Build and start

```bash
docker compose up -d --build
```

`app` waits for healthy Postgres and then applies migrations automatically:

```bash
python -m ela_pipeline.db.migrate
```

## 3) Check services

```bash
docker compose ps
docker compose logs postgres --tail=100
docker compose logs app --tail=100
docker compose logs frontend --tail=100
```

## 4) Open frontend

Open:
- `http://localhost:${FRONTEND_PORT}` (default `http://localhost:8080`)

Runtime API is exposed behind frontend Nginx proxy:
- `GET /api/ui-state`
- `GET /api/projects`
- `POST /api/projects`
- `GET /api/selected-project`
- `POST /api/selected-project`
- `POST /api/upload` (multipart file upload)
- `POST /api/submit-media`
- `GET /api/backend-jobs`
- `GET /api/backend-job-status?job_id=...`
- `POST /api/retry-backend-job`
- `POST /api/resume-backend-jobs`
- `POST /api/sync-backend-result`
- `GET /api/files`
- `GET /api/visualizer-payload?document_id=...`
- `POST /api/apply-edit`

## 5) Run inference inside container

```bash
docker compose exec app python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --persist-db
```

## 6) Inspect database

```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT sentence_key, source_text, language_pair FROM sentences ORDER BY updated_at DESC LIMIT 10;"
```

## Notes for production

- Replace default credentials in `.env` before deployment.
- Keep volumes persistent (`pgdata`, `artifacts_data`, `inference_results`, `hf_cache`).
- Add reverse-proxy/API service later if you expose inference to external clients.
- Media extraction pipeline in current runtime API:
  - `text`: native extraction
  - `pdf`: `pypdf`
  - `audio/video`: transcript sidecar fallback (`<media>.<ext>.txt`) until ASR is integrated
