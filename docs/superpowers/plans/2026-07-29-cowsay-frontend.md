# Cowsay Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a no-build-step frontend to the cowsay service with a say input, an auto-refreshing recent list, and a paginated, clickable list of saved db entries — backed by three small API changes (dedup-on-persist, server-side pagination, recent-push on click-to-say).

**Architecture:** FastAPI serves static files (`app/static/index.html`, `app.js`, `style.css`) mounted at `/ui/` via `StaticFiles(html=True)`. Vanilla JS calls the existing (and three newly-modified) JSON endpoints with `fetch`. No new dependencies, no build tooling, no Docker/CI changes.

**Tech Stack:** FastAPI, psycopg (existing `ConnectionPool` in `app/db.py`), Redis (existing `app/redis_client.py`), vanilla HTML/CSS/JS.

## Global Constraints

- No build step for the frontend — plain HTML/CSS/JS only, served directly by FastAPI.
- Root `/` must keep returning `{"status": "alive"}` unchanged — it's the k8s liveness probe target (`k8s/base/deployment.yaml:38`).
- Dedup on `POST /messages` is exact match, case-sensitive.
- `GET /messages` pagination: default `limit=10`, max `limit=100`, default `offset=0`, ordered newest-first (`id DESC`).
- `POST /messages` and `GET /messages/{id}/cowsay` must each call `push_recent` exactly once per request — no double-pushes.

---

### Task 1: Dedup on `POST /messages` + return rendered art

**Files:**
- Modify: `app/db.py` (add `get_message_by_body`, `get_or_create_message`)
- Modify: `app/models.py:15-17` (`MessageResponse` gains `cowsay: str`)
- Modify: `app/main.py:71-80` (`create_message` uses `get_or_create_message`, returns art)
- Test: `tests/test_messages.py`

**Interfaces:**
- Consumes: `app.cowsay_util.render(text: str) -> str` (existing), `app.redis_client.push_recent(text: str) -> None` (existing)
- Produces: `app.db.get_or_create_message(body: str) -> dict` returning `{"id": int, "say": str}` — later tasks don't depend on this, but keep the shape identical to the existing `insert_message` return shape.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_messages.py`:

```python
def test_create_message_dedups_exact_match(client):
    # A second insert would receive a new SERIAL id, so an identical id proves
    # the existing row was reused. Deliberately does NOT read GET /messages —
    # that response shape changes in Task 2.
    first = client.post("/messages", json={"say": "dedup-marker-xyz"}).json()
    second = client.post("/messages", json={"say": "dedup-marker-xyz"}).json()
    assert first["id"] == second["id"]


def test_create_message_returns_cowsay_art(client):
    created = client.post("/messages", json={"say": "art-marker"}).json()
    assert "art-marker" in created["cowsay"]
    assert "^__^" in created["cowsay"]
```

Also update the existing test to match the new list response shape (this will fail until Task 2 lands too, so for now just add the assertion for the new field and leave the `/messages` GET call as-is — Task 2 finishes the shape migration):

```python
def test_create_and_list_messages(client):
    response = client.post("/messages", json={"say": "test message one"})
    assert response.status_code == 200
    created = response.json()
    assert created["say"] == "test message one"
    assert isinstance(created["id"], int)
    assert "^__^" in created["cowsay"]
```

(Remove the old `listing = client.get("/messages")` lines from this test — pagination-shape coverage moves to Task 2's tests.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose up -d postgres redis && pytest tests/test_messages.py -v`
Expected: `test_create_message_dedups_exact_match` FAILS (two inserts → two different ids) and `test_create_message_returns_cowsay_art` FAILS (`KeyError: 'cowsay'`). `test_create_and_list_messages` FAILs on the `assert "^__^" in created["cowsay"]` line.

- [ ] **Step 3: Implement `get_or_create_message` in `app/db.py`**

Add after the existing `insert_message` function (`app/db.py:45-51`):

```python
def get_message_by_body(body: str) -> dict | None:
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT id, body FROM messages WHERE body = %s LIMIT 1", (body,)
        ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "say": row[1]}


def get_or_create_message(body: str) -> dict:
    existing = get_message_by_body(body)
    if existing is not None:
        return existing
    return insert_message(body)
```

- [ ] **Step 4: Update `MessageResponse` in `app/models.py`**

Change `app/models.py:15-17` from:

```python
class MessageResponse(BaseModel):
    id: int
    say: str
```

to:

```python
class MessageResponse(BaseModel):
    id: int
    say: str
    cowsay: str
```

- [ ] **Step 5: Update `create_message` in `app/main.py`**

Change the import line `app/main.py:7-15` to add `get_or_create_message` and drop the now-unused `insert_message`:

```python
from app.db import (
    check_db,
    close_pool,
    ensure_schema,
    get_message,
    get_or_create_message,
    get_pool,
    list_messages,
)
```

Change `create_message` (`app/main.py:71-80`) from:

```python
@app.post(
    "/messages",
    response_model=MessageResponse,
    summary="Save a message",
    description="Persists the said text to Postgres and pushes it onto the Redis recent list.",
)
def create_message(request: SayRequest) -> MessageResponse:
    row = insert_message(request.say)
    push_recent(request.say)
    return MessageResponse(**row)
```

to:

```python
@app.post(
    "/messages",
    response_model=MessageResponse,
    summary="Save a message",
    description="Persists the said text to Postgres (reusing an exact-match row if "
    "one exists), pushes it onto the Redis recent list, and returns the rendered "
    "cowsay art.",
)
def create_message(request: SayRequest) -> MessageResponse:
    row = get_or_create_message(request.say)
    push_recent(request.say)
    return MessageResponse(id=row["id"], say=row["say"], cowsay=render(row["say"]))
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_messages.py -v`
Expected: PASS (note `test_create_and_list_messages`'s old pagination assertions were already removed in Step 1, so this file is self-consistent even though Task 2 hasn't landed yet)

- [ ] **Step 7: Commit**

```bash
git add app/db.py app/models.py app/main.py tests/test_messages.py
git commit -m "feat: dedup POST /messages on exact match, return rendered art"
```

---

### Task 2: Paginate `GET /messages`

**Files:**
- Modify: `app/db.py` (update `list_messages` signature, add `count_messages`)
- Modify: `app/models.py` (add `MessagePage`)
- Modify: `app/main.py:83-89` (`get_messages` accepts `limit`/`offset`, returns `MessagePage`)
- Test: `tests/test_messages.py`

**Interfaces:**
- Consumes: `MessageListItem` (existing, `app/models.py:20-23`)
- Produces: `app.db.list_messages(limit: int, offset: int) -> list[dict]` (same row shape as before: `{"id", "say", "created_at"}`), `app.db.count_messages() -> int`, `MessagePage` model with fields `items: list[MessageListItem]`, `total: int`, `limit: int`, `offset: int`. Task 3 and the frontend tasks both depend on this exact `MessagePage` shape and on `GET /messages?limit=&offset=`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_messages.py`:

```python
def test_messages_pagination_shape_and_bounds(client):
    # Unique per run: POST /messages dedups on exact match (Task 1), so fixed
    # text would insert nothing on a re-run and make ordering assertions flaky.
    import uuid

    run = uuid.uuid4().hex[:8]
    for i in range(3):
        client.post("/messages", json={"say": f"page-marker-{run}-{i}"})

    page = client.get("/messages", params={"limit": 2, "offset": 0}).json()
    assert len(page["items"]) == 2
    assert page["limit"] == 2
    assert page["offset"] == 0
    assert page["total"] >= 3

    # newest-first: the two most recent inserts are this run's -2 and -1
    says = [m["say"] for m in page["items"]]
    assert says == [f"page-marker-{run}-2", f"page-marker-{run}-1"]

    # and the second page continues the descending sequence
    page2 = client.get("/messages", params={"limit": 2, "offset": 2}).json()
    assert page2["offset"] == 2
    assert page2["items"][0]["say"] == f"page-marker-{run}-0"


def test_messages_default_pagination(client):
    page = client.get("/messages").json()
    assert page["limit"] == 10
    assert page["offset"] == 0
    assert len(page["items"]) <= 10


def test_messages_limit_is_capped(client):
    page = client.get("/messages", params={"limit": 1000}).json()
    assert page["limit"] == 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_messages.py -v`
Expected: FAIL — `GET /messages` currently returns a bare list, so `.json()["items"]` raises `TypeError`.

- [ ] **Step 3: Update `list_messages` and add `count_messages` in `app/db.py`**

Change `list_messages` (`app/db.py:54-59`) from:

```python
def list_messages() -> list[dict]:
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT id, body, created_at FROM messages ORDER BY id"
        ).fetchall()
        return [{"id": r[0], "say": r[1], "created_at": r[2]} for r in rows]
```

to:

```python
def list_messages(limit: int, offset: int) -> list[dict]:
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT id, body, created_at FROM messages "
            "ORDER BY id DESC LIMIT %s OFFSET %s",
            (limit, offset),
        ).fetchall()
        return [{"id": r[0], "say": r[1], "created_at": r[2]} for r in rows]


def count_messages() -> int:
    with get_pool().connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
        return row[0]
```

- [ ] **Step 4: Add `MessagePage` to `app/models.py`**

Append to `app/models.py`:

```python
class MessagePage(BaseModel):
    items: list[MessageListItem]
    total: int
    limit: int
    offset: int
```

- [ ] **Step 5: Update `get_messages` in `app/main.py`**

Add `count_messages` and `MessagePage` to the imports (extend the `app.db` import block from Task 1 and the `app.models` import on `app/main.py:16`):

```python
from app.db import (
    check_db,
    close_pool,
    count_messages,
    ensure_schema,
    get_message,
    get_or_create_message,
    get_pool,
    list_messages,
)
from app.models import HealthResponse, MessageListItem, MessagePage, MessageResponse, SayRequest
```

Change `get_messages` (`app/main.py:83-89`) from:

```python
@app.get(
    "/messages",
    response_model=list[MessageListItem],
    summary="List saved messages",
)
def get_messages() -> list[MessageListItem]:
    return [MessageListItem(**row) for row in list_messages()]
```

to:

```python
@app.get(
    "/messages",
    response_model=MessagePage,
    summary="List saved messages",
    description="Paginated, newest-first. `limit` defaults to 10 and caps at 100.",
)
def get_messages(limit: int = 10, offset: int = 0) -> MessagePage:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    rows = list_messages(limit=limit, offset=offset)
    return MessagePage(
        items=[MessageListItem(**row) for row in rows],
        total=count_messages(),
        limit=limit,
        offset=offset,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_messages.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/db.py app/models.py app/main.py tests/test_messages.py
git commit -m "feat: paginate GET /messages, newest-first"
```

---

### Task 3: `GET /messages/{id}/cowsay` pushes to Redis recent

**Files:**
- Modify: `app/main.py:102-111`
- Test: `tests/test_messages.py`

**Interfaces:**
- Consumes: `app.redis_client.push_recent(text: str) -> None` (existing), `app.db.get_message(message_id: int) -> dict | None` (existing, unchanged)
- Produces: no new interface — this only changes a side effect of the existing endpoint.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_messages.py`:

```python
def test_cowsay_by_id_pushes_to_recent(client):
    from app.redis_client import RECENT_KEY, get_redis

    created = client.post("/messages", json={"say": "cowsay-recent-marker"}).json()
    client.post("/messages", json={"say": "other-marker-noise"})

    client.get(f"/messages/{created['id']}/cowsay")
    recent = get_redis().lrange(RECENT_KEY, 0, 4)
    assert recent[0] == "cowsay-recent-marker"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_messages.py::test_cowsay_by_id_pushes_to_recent -v`
Expected: FAIL — `recent[0]` is `"other-marker-noise"`, not `"cowsay-recent-marker"`.

- [ ] **Step 3: Implement**

Change `cowsay_message` (`app/main.py:102-111`) from:

```python
@app.get(
    "/messages/{message_id}/cowsay",
    response_class=PlainTextResponse,
    summary="Cowsay a saved message",
)
def cowsay_message(message_id: int) -> str:
    row = get_message(message_id)
    if row is None:
        raise HTTPException(status_code=404, detail="message not found")
    return render(row["say"])
```

to:

```python
@app.get(
    "/messages/{message_id}/cowsay",
    response_class=PlainTextResponse,
    summary="Cowsay a saved message",
    description="Renders the saved message and pushes it onto the Redis recent list.",
)
def cowsay_message(message_id: int) -> str:
    row = get_message(message_id)
    if row is None:
        raise HTTPException(status_code=404, detail="message not found")
    push_recent(row["say"])
    return render(row["say"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_messages.py -v`
Expected: PASS (full file, all tests including Tasks 1-2's)

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_messages.py
git commit -m "feat: push to recent list when re-saying a message by id"
```

---

### Task 4: Serve the frontend (say form, recent list, paginated list)

**Files:**
- Create: `app/static/index.html`
- Create: `app/static/style.css`
- Create: `app/static/app.js`
- Modify: `app/main.py` (mount `/ui`)

**Interfaces:**
- Consumes: `POST /messages` → `{id, say, cowsay}` (Task 1), `GET /messages?limit=&offset=` → `{items: [{id, say, created_at}], total, limit, offset}` (Task 2), `GET /messages/{id}/cowsay` → plain text art (Task 3), `GET /recent` → `list[str]` (existing, `app/main.py:92-99`).
- Produces: nothing consumed by other tasks — this is the last code task.

- [ ] **Step 1: Mount static files in `app/main.py`**

Add these imports near the top of `app/main.py` (after the existing `from contextlib import asynccontextmanager`):

```python
from pathlib import Path

from fastapi.staticfiles import StaticFiles
```

Add this line right after `app = FastAPI(...)` (`app/main.py:30-34`):

```python
app.mount(
    "/ui", StaticFiles(directory=str(Path(__file__).parent / "static"), html=True), name="ui"
)
```

- [ ] **Step 2: Create `app/static/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>cowsay</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <h1>cowsay</h1>

  <section id="say-panel">
    <h2>Say something</h2>
    <form id="say-form">
      <input type="text" id="say-input" placeholder="What should the cow say?" required />
      <button type="submit">Say</button>
    </form>
    <p id="say-error" class="error hidden"></p>
    <pre id="output">Say something to see it here.</pre>
  </section>

  <section id="recent-panel">
    <h2>Recently said</h2>
    <ul id="recent-list"></ul>
  </section>

  <section id="messages-panel">
    <h2>Saved messages</h2>
    <table id="messages-table">
      <thead>
        <tr><th>ID</th><th>Text</th><th>Created</th></tr>
      </thead>
      <tbody id="messages-body"></tbody>
    </table>
    <div id="pagination">
      <button id="prev-page" type="button">Prev</button>
      <span id="page-indicator"></span>
      <button id="next-page" type="button">Next</button>
    </div>
  </section>

  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 3: Create `app/static/style.css`**

```css
body {
  font-family: system-ui, sans-serif;
  max-width: 720px;
  margin: 2rem auto;
  padding: 0 1rem;
  color: #222;
}

section {
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #ddd;
}

#output {
  background: #f5f5f5;
  padding: 1rem;
  border-radius: 4px;
  white-space: pre;
  overflow-x: auto;
  min-height: 3rem;
}

.error {
  color: #b00020;
}

.hidden {
  display: none;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th, td {
  text-align: left;
  padding: 0.4rem 0.6rem;
  border-bottom: 1px solid #eee;
}

.message-row {
  cursor: pointer;
}

.message-row:hover {
  background: #f0f0f0;
}

#pagination {
  margin-top: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
```

- [ ] **Step 4: Create `app/static/app.js`**

```js
const PAGE_SIZE = 10;
let currentOffset = 0;

const sayForm = document.getElementById("say-form");
const sayInput = document.getElementById("say-input");
const sayError = document.getElementById("say-error");
const output = document.getElementById("output");
const recentList = document.getElementById("recent-list");
const messagesBody = document.getElementById("messages-body");
const prevPageBtn = document.getElementById("prev-page");
const nextPageBtn = document.getElementById("next-page");
const pageIndicator = document.getElementById("page-indicator");

function showError(text) {
  sayError.textContent = text;
  sayError.classList.remove("hidden");
}

function clearError() {
  sayError.textContent = "";
  sayError.classList.add("hidden");
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

async function loadRecent() {
  recentList.innerHTML = "<li>Loading...</li>";
  try {
    const response = await fetch("/recent");
    if (!response.ok) throw new Error(`status ${response.status}`);
    const items = await response.json();
    if (items.length === 0) {
      recentList.innerHTML = "<li>nothing said yet</li>";
      return;
    }
    recentList.innerHTML = "";
    for (const item of items) {
      const li = document.createElement("li");
      li.textContent = item;
      recentList.appendChild(li);
    }
  } catch (err) {
    recentList.innerHTML = '<li class="error">couldn\'t load recent list</li>';
  }
}

async function loadMessages(offset) {
  messagesBody.innerHTML = '<tr><td colspan="3">Loading...</td></tr>';
  try {
    const response = await fetch(`/messages?limit=${PAGE_SIZE}&offset=${offset}`);
    if (!response.ok) throw new Error(`status ${response.status}`);
    const page = await response.json();
    currentOffset = page.offset;

    if (page.items.length === 0) {
      messagesBody.innerHTML = '<tr><td colspan="3">no messages yet</td></tr>';
    } else {
      messagesBody.innerHTML = "";
      for (const item of page.items) {
        const tr = document.createElement("tr");
        tr.classList.add("message-row");
        const created = new Date(item.created_at).toLocaleString();
        tr.innerHTML = `<td>${item.id}</td><td>${escapeHtml(item.say)}</td><td>${created}</td>`;
        tr.addEventListener("click", () => sayMessage(item.id));
        messagesBody.appendChild(tr);
      }
    }

    const totalPages = Math.max(1, Math.ceil(page.total / page.limit));
    const currentPage = Math.floor(page.offset / page.limit) + 1;
    pageIndicator.textContent = `Page ${currentPage} of ${totalPages}`;
    prevPageBtn.disabled = page.offset <= 0;
    nextPageBtn.disabled = page.offset + page.limit >= page.total;
  } catch (err) {
    messagesBody.innerHTML = '<tr><td colspan="3" class="error">couldn\'t load messages</td></tr>';
  }
}

async function sayMessage(id) {
  try {
    const response = await fetch(`/messages/${id}/cowsay`);
    if (!response.ok) throw new Error(`status ${response.status}`);
    const art = await response.text();
    output.textContent = art;
    await loadRecent();
  } catch (err) {
    showError("couldn't say that message");
  }
}

sayForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = sayInput.value.trim();
  if (!text) {
    showError("say something first");
    return;
  }
  clearError();
  const submitButton = sayForm.querySelector("button");
  submitButton.disabled = true;
  try {
    const response = await fetch("/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ say: text }),
    });
    if (!response.ok) throw new Error(`status ${response.status}`);
    const created = await response.json();
    output.textContent = created.cowsay;
    sayInput.value = "";
    await loadRecent();
  } catch (err) {
    showError("failed to say that — try again");
  } finally {
    submitButton.disabled = false;
  }
});

prevPageBtn.addEventListener("click", () => {
  loadMessages(Math.max(0, currentOffset - PAGE_SIZE));
});

nextPageBtn.addEventListener("click", () => {
  loadMessages(currentOffset + PAGE_SIZE);
});

loadRecent();
loadMessages(0);
```

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/static/index.html app/static/style.css app/static/app.js
git commit -m "feat: add static frontend (say form, recent list, paginated messages)"
```

---

### Task 5: Manual browser verification

**Files:** none (verification only)

**Interfaces:** none

- [ ] **Step 1: Start the local stack**

```bash
docker compose up -d postgres redis
uvicorn app.main:app --reload --env-file .env
```

- [ ] **Step 2: Open the UI**

Open `http://localhost:8000/ui/` in a browser.

- [ ] **Step 3: Test the say flow**

Type a new, never-before-said phrase into the say input and submit. Confirm:
- The cowsay art appears in the output panel immediately.
- The recent list updates to show the new phrase at the top, without a manual refresh.

- [ ] **Step 4: Test dedup**

Submit the exact same phrase again. Confirm the app still works (no error), and check `GET /messages?limit=100` in a new tab shows only one row with that text.

- [ ] **Step 5: Test the paginated list**

Confirm the saved-messages table shows up to 10 rows, newest first, with working Prev/Next buttons and a correct "Page N of M" indicator. Prev should be disabled on page 1; Next disabled on the last page.

- [ ] **Step 6: Test click-to-say**

Click an older row in the table (ideally on page 2, if there are enough rows — say a few more phrases from Step 3 if needed to get a second page). Confirm:
- The output panel shows that row's cowsay art.
- The recent list updates to show that row's text at the top.

- [ ] **Step 7: Confirm root and health endpoints are unaffected**

```bash
curl -s http://localhost:8000/ | python3 -m json.tool
curl -s http://localhost:8000/health | python3 -m json.tool
```

Expected: `/` still returns `{"status": "alive"}`; `/health` still returns `postgres`/`redis` status.

No commit for this task — it's verification only. If any step fails, fix the relevant earlier task and re-run affected `pytest` tests before re-verifying.
