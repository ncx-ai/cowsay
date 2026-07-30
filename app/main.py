from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

from app.cowsay_util import render
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
from app.redis_client import check_redis, close_redis, get_recent, get_redis, push_recent


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_pool()
    ensure_schema()
    get_redis()
    yield
    close_pool()
    close_redis()


app = FastAPI(
    title="cowsay",
    description="Toy example service demonstrating a full dev-to-prod deployment pipeline.",
    lifespan=lifespan,
)


@app.get("/", summary="Liveness check")
def root() -> dict:
    return {"status": "alive"}


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Readiness check",
    description="Checks connectivity to both Postgres and the Redis sidecar.",
)
def health() -> JSONResponse:
    postgres_ok = check_db()
    redis_ok = check_redis()
    body = HealthResponse(
        postgres="ok" if postgres_ok else "error",
        redis="ok" if redis_ok else "error",
    )
    status_code = 200 if (postgres_ok and redis_ok) else 503
    return JSONResponse(content=body.model_dump(), status_code=status_code)


@app.post(
    "/say",
    response_class=PlainTextResponse,
    summary="Say something",
    description="Returns cowsay ASCII art for the given text. Ephemeral — "
    "not persisted to Postgres, but pushed onto the Redis recent list.",
)
def say(request: SayRequest) -> str:
    push_recent(request.say)
    return render(request.say)


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


@app.get(
    "/recent",
    response_model=list[str],
    summary="Recently said things",
    description="Returns the 5 most recent things said via /say or /messages.",
)
def recent() -> list[str]:
    return get_recent()


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
