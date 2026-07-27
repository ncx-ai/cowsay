from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse

from app.cowsay_util import render
from app.db import check_db, close_pool, get_pool
from app.models import HealthResponse, SayRequest
from app.redis_client import check_redis, close_redis, get_redis, push_recent


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_pool()
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
