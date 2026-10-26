import uuid
from datetime import datetime

from pydantic import BaseModel

from app.auth import Role


class ProductOut(BaseModel):
    id: uuid.UUID
    name: str
    image_url: str
    created_at: datetime


class ProductPage(BaseModel):
    items: list[ProductOut]
    next_offset: int | None


class MeOut(BaseModel):
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    role: Role
