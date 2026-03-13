from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class MirrorStatus(str, Enum):
    pending = "pending"
    ready = "ready"
    failed = "failed"


class JobState(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class Mirror(Base):
    __tablename__ = "mirrors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=MirrorStatus.pending.value, nullable=False)
    public_token: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    jobs: Mapped[list["SyncJob"]] = relationship("SyncJob", back_populates="mirror")
    snapshot: Mapped["PublishedSnapshot"] = relationship(
        "PublishedSnapshot", back_populates="mirror", uselist=False
    )


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    mirror_id: Mapped[int] = mapped_column(ForeignKey("mirrors.id"), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(32), default=JobState.queued.value, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    leak_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    mirror: Mapped["Mirror"] = relationship("Mirror", back_populates="jobs")


class PublishedSnapshot(Base):
    __tablename__ = "published_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    mirror_id: Mapped[int] = mapped_column(ForeignKey("mirrors.id"), unique=True, nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    mirror: Mapped["Mirror"] = relationship("Mirror", back_populates="snapshot")

