from __future__ import annotations

import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import JobState, Mirror, MirrorStatus, PublishedSnapshot, SyncJob
from ..utils import dump_json, normalize_repo_url, sha256_directory, utcnow, validate_github_public_url
from .anonymizer import sanitize_tree


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({' '.join(cmd)}): {result.stderr.strip()}")
    return result.stdout


def _collect_sensitive_terms(source_url: str, clone_dir: Path) -> set[str]:
    owner, repo = validate_github_public_url(source_url)
    terms = {
        owner,
        repo,
        f"{owner}/{repo}",
        f"github.com/{owner}/{repo}",
        f"https://github.com/{owner}/{repo}",
        f"https://github.com/{owner}/{repo}.git",
    }

    try:
        raw = _run(["git", "log", "--format=%an|%ae"], cwd=clone_dir)
        for line in raw.splitlines():
            if not line.strip():
                continue
            name, _, email = line.partition("|")
            if name.strip():
                terms.add(name.strip())
            if email.strip():
                terms.add(email.strip())
    except RuntimeError:
        # Repo might have unusual history access; continue with URL-driven terms.
        pass

    return terms


def _publish_snapshot(db: Session, mirror: Mirror, staging_dir: Path) -> str:
    mirror_root = Path(settings.mirror_storage_root) / str(mirror.id)
    current_dir = mirror_root / "current"
    if current_dir.exists():
        shutil.rmtree(current_dir)
    current_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(staging_dir, current_dir)
    digest = sha256_directory(current_dir)

    snapshot = db.query(PublishedSnapshot).filter(PublishedSnapshot.mirror_id == mirror.id).one_or_none()
    if snapshot is None:
        snapshot = PublishedSnapshot(mirror_id=mirror.id, artifact_path=str(current_dir), content_hash=digest)
        db.add(snapshot)
    else:
        snapshot.artifact_path = str(current_dir)
        snapshot.content_hash = digest
        snapshot.published_at = utcnow()
    return digest


def execute_sync_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.query(SyncJob).filter(SyncJob.id == job_id).one_or_none()
        if job is None:
            return
        mirror = db.query(Mirror).filter(Mirror.id == job.mirror_id).one()

        job.state = JobState.running.value
        job.started_at = utcnow()
        job.error = None
        db.commit()

        with tempfile.TemporaryDirectory(dir=settings.temp_root) as temp_dir:
            work_dir = Path(temp_dir)
            clone_dir = work_dir / "source"
            output_dir = work_dir / "sanitized"
            normalized_url = normalize_repo_url(mirror.source_url)

            _run(["git", "clone", "--depth=1", normalized_url, str(clone_dir)])
            sensitive_terms = _collect_sensitive_terms(mirror.source_url, clone_dir)
            result = sanitize_tree(clone_dir, output_dir, sensitive_terms)

            report = {
                "timestamp_utc": datetime.utcnow().isoformat(),
                "replacements": result.replacements,
                "unresolved_hits": result.unresolved_hits,
                "findings": result.findings[:500],
            }
            job.leak_report = dump_json(report)

            if result.unresolved_hits > 0:
                raise RuntimeError("Leak detection failed: unresolved sensitive identifiers remain after redaction")

            _publish_snapshot(db, mirror, output_dir)
            mirror.status = MirrorStatus.ready.value
            mirror.updated_at = utcnow()
            job.state = JobState.succeeded.value
            job.finished_at = utcnow()
            db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job = db.query(SyncJob).filter(SyncJob.id == job_id).one_or_none()
        if job:
            mirror = db.query(Mirror).filter(Mirror.id == job.mirror_id).one_or_none()
            if mirror:
                mirror.status = MirrorStatus.failed.value
                mirror.updated_at = utcnow()
            job.state = JobState.failed.value
            job.error = str(exc)
            job.finished_at = utcnow()
            db.commit()
    finally:
        db.close()

