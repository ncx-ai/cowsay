# Cowsay Frontend — Design

## Overview

Add a simple, no-build-step frontend to the cowsay service covering three
features: a say input, a recent-list view, and a paginated, clickable list of
saved db entries. The frontend is served by FastAPI itself as static files;
supporting backend changes add dedup-on-persist, pagination, and a couple of
small response/behavior tweaks.

## Architecture

- New `app/static/` directory: `index.html`, `app.js`, `style.css`. Plain
  HTML/CSS/vanilla JS — no build step, no new dependencies, no Docker/CI
  changes.
- Mounted via `app.mount("/ui", StaticFiles(directory=..., html=True), name="ui")`
  in `app/main.py`, so the page is served at `/ui/`.
- Root `/` is left untouched (it's the k8s liveness probe target — see
  `k8s/base/deployment.yaml`); the UI lives at a separate path.

## Backend changes

### `app/db.py`

- Add `get_or_create_message(body: str) -> dict`: looks up a message by exact
  (case-sensitive) `body` match; returns the existing row if found, otherwise
  inserts a new one. Replaces the direct `insert_message` call in the create
  endpoint.
- `list_messages` gains `limit` and `offset` params, orders `id DESC`
  (newest first — a change from the current ascending order), and the
  endpoint layer also needs a total count (`count_messages()` or equivalent)
  for pagination metadata.

### `app/models.py`

- `MessageResponse` gains a `cowsay: str` field containing the rendered
  ASCII art, so the say-input flow gets art back in a single request.
- New `MessagePage` model: `{items: list[MessageListItem], total: int,
  limit: int, offset: int}`.

### `app/main.py`

- `POST /messages`: use `get_or_create_message`, still calls `push_recent`
  exactly once, and returns the rendered `cowsay` art in the response body.
- `GET /messages`: accepts `limit` (default 10, max 100) and `offset`
  (default 0) query params; returns `MessagePage` instead of a bare list.
  This is a breaking response-shape change.
- `GET /messages/{message_id}/cowsay`: now also calls `push_recent` after
  rendering, so re-saying an old message surfaces it in the recent list.

## Frontend behavior (`app/static/`)

Single page, three panels, vanilla JS with `fetch`, no framework:

1. **Say form** — text input + submit button. `POST /messages` with
   `{say: text}`; renders the returned `cowsay` field into a shared output
   `<pre>` block. Button disables while in-flight; inline error message on
   failure (network error or non-2xx response).
2. **Recent list** — `GET /recent`, rendered as a simple list. Loads once on
   page load, and re-fetches after every successful "say" action (from
   either the say form or a paginated-list click). Empty state: "nothing
   said yet."
3. **Paginated db list** — table showing id / text / created_at, with
   Prev/Next buttons and a page indicator ("Page N of M"), fixed page size
   10 (matches backend default). Prev disabled on the first page, Next
   disabled on the last. Clicking a row calls
   `GET /messages/{id}/cowsay`, renders the art into the same shared output
   `<pre>` as the say form, and triggers a recent-list refresh. Empty
   state: "no messages yet."

## Error handling

- Say form: client-side guard against empty submission; server errors shown
  inline near the form, don't clear existing output.
- Pagination: out-of-range offset (e.g. after messages are deleted
  elsewhere) degrades to an empty page with Prev still usable, rather than
  erroring.
- Recent/list fetch failures show an inline "couldn't load" message in that
  panel without breaking the rest of the page.

## Testing

- **Backend**: update `tests/test_messages.py` for the new `MessagePage`
  response shape from `GET /messages`. Add cases for:
  - dedup — posting the same `say` text twice returns the same `id` and
    does not create a second row
  - pagination bounds — `limit`/`offset` behavior, `total` correctness,
    default page size
  - `GET /messages/{id}/cowsay` pushes to the Redis recent list
- **Frontend**: no automated tests for a build-step-free vanilla JS page.
  Manual verification of the golden path in a browser via the dev server
  before calling the work done: say → art renders in output panel; db list
  paginates correctly; clicking a row re-says it and updates the recent
  list.

## Open decision flagged during design

- `GET /messages` pagination order was set to newest-first (`id DESC`),
  changing from the current ascending order. If ascending is actually
  preferred, this is a one-line change in the plan.
