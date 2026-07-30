from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    postgres: str
    redis: str


class SayRequest(BaseModel):
    say: str


class MessageResponse(BaseModel):
    id: int
    say: str
    cowsay: str


class MessageListItem(BaseModel):
    id: int
    say: str
    created_at: datetime
