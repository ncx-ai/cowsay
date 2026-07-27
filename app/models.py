from pydantic import BaseModel


class HealthResponse(BaseModel):
    postgres: str
    redis: str
