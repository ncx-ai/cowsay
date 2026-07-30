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

## Web UI

A plain HTML/CSS/vanilla-JS frontend (no build step) is served at `/ui/`:

- Locally: http://localhost:8000/ui/
- In-cluster, via `kubectl port-forward svc/cowsay -n cowsay 8080:80`: http://localhost:8080/ui/

It has three panels: a say input, an auto-refreshing "recently said" list, and a
paginated, clickable list of saved Postgres messages.

The page fetches `/recent` and `/messages` as origin-absolute paths, so it works
at origin root but would need adjusting behind an ingress that adds a path
prefix. No ingress exists today.

## Running tests

```bash
docker compose up -d postgres redis
pytest
```

## API changes

`GET /messages` now returns a paginated envelope instead of a bare list:
`{"items": [...], "total": N, "limit": N, "offset": N}`, newest-first. `limit`
defaults to 10 and caps at 100. `POST /messages` responses gained a required
`cowsay` field with the rendered art. No in-repo consumers were found, so
nothing breaks today, but note it here since CI has no test step and the dev
environment auto-syncs on merge.
