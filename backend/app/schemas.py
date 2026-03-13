from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MirrorCreate(BaseModel):
    source_url: str = Field(min_length=1, max_length=1024)


class MirrorResponse(BaseModel):
    id: int
    source_url: str
    status: str
    public_token: str
    expires_at: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SyncJobResponse(BaseModel):
    id: int
    mirror_id: int
    state: str
    error: str | None
    leak_report: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class CreateMirrorResponse(BaseModel):
    mirror: MirrorResponse
    job: SyncJobResponse


class RenewUrlResponse(BaseModel):
    mirror_id: int
    new_token: str
    expires_at: datetime


class MirrorPublicListing(BaseModel):
    path: str
    type: Literal["file", "dir"]


class PublicMirrorView(BaseModel):
    mirror_id: int
    expires_at: datetime
    entries: list[MirrorPublicListing]

