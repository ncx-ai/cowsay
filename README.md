# cowsay

Toy example FastAPI service demonstrating a full dev-to-prod deployment
pipeline: cowsay ASCII art, message persistence in Postgres, and a Redis
sidecar tracking recently-said things.

## Running the whole stack in Docker

```bash
make up              # builds the image, starts postgres + redis + app, opens the UI
make down            # stops everything
make up PORT=8100    # if port 8000 is already taken
```

## Local development

Run the app on the host against containerised postgres and redis:

```bash
cp .env.example .env
docker compose up -d postgres redis
pip install -r requirements-dev.txt
make dev             # or: uvicorn app.main:app --reload --env-file .env
```

Interactive API docs: http://localhost:8000/docs

## Web UI

A plain HTML/CSS/vanilla-JS frontend (no build step) is served at `/ui/`:

```bash
make up              # full Docker stack, then opens the browser
make ui              # local server only (starts it if needed), then opens the browser
```

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
