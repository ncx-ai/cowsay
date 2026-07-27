# cowsay

Toy example FastAPI service demonstrating a full dev-to-prod deployment
pipeline: cowsay ASCII art, message persistence in Postgres, and a Redis
sidecar tracking recently-said things.

## Local development

```bash
cp .env.example .env
docker compose up -d postgres redis
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --env-file .env
```

Interactive API docs: http://localhost:8000/docs

## Running tests

```bash
docker compose up -d postgres redis
pytest
```
