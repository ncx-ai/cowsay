import os

from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        database_url = os.environ["DATABASE_URL"]
        _pool = ConnectionPool(conninfo=database_url, min_size=1, max_size=5, open=True)
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def check_db() -> bool:
    try:
        with get_pool().connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001 -- any failure here means "unhealthy"
        return False


def ensure_schema() -> None:
    with get_pool().connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                body TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def insert_message(body: str) -> dict:
    with get_pool().connection() as conn:
        row = conn.execute(
            "INSERT INTO messages (body) VALUES (%s) RETURNING id, body",
            (body,),
        ).fetchone()
        return {"id": row[0], "say": row[1]}


def get_message_by_body(body: str) -> dict | None:
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT id, body FROM messages WHERE body = %s LIMIT 1", (body,)
        ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "say": row[1]}


def get_or_create_message(body: str) -> dict:
    # Not race-safe: concurrent identical POSTs can both
    # insert. Acceptable here — single replica, toy service.
    existing = get_message_by_body(body)
    if existing is not None:
        return existing
    return insert_message(body)


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


def get_message(message_id: int) -> dict | None:
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT id, body FROM messages WHERE id = %s", (message_id,)
        ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "say": row[1]}
