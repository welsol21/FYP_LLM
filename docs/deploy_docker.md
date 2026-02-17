# Docker Deployment (PostgreSQL + ELA App)

## Goal

Run the project in containers with stable service boundaries:
- `postgres` for persistence
- `app` for inference/training utilities

## Files

- `Dockerfile`
- `docker-compose.yml`
- `.env.example`

## 1) Prepare environment

```bash
cp .env.example .env
```

Adjust `.env` values for production secrets and host port mapping.

Compose CLI requirement:
- use Docker Compose v2 (`docker compose ...`).
- legacy `docker-compose` v1 is deprecated and is not supported in this setup.

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
```

## 4) Run inference inside container

```bash
docker compose exec app python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --persist-db
```

## 5) Inspect database

```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT sentence_key, source_text, language_pair FROM sentences ORDER BY updated_at DESC LIMIT 10;"
```

## Notes for production

- Replace default credentials in `.env` before deployment.
- Keep volumes persistent (`pgdata`, `artifacts_data`, `inference_results`, `hf_cache`).
- Add reverse-proxy/API service later if you expose inference to external clients.
