from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, engine, get_db
from .models import Mirror, MirrorStatus, PublishedSnapshot, SyncJob
from .queue import get_queue
from .schemas import (
    CreateMirrorResponse,
    MirrorCreate,
    MirrorPublicListing,
    MirrorResponse,
    PublicMirrorView,
    RenewUrlResponse,
    SyncJobResponse,
)
from .utils import expiration_from_now, generate_public_token, utcnow, validate_github_public_url

app = FastAPI(title="VeilMirror Core Platform", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    Path(settings.mirror_storage_root).mkdir(parents=True, exist_ok=True)
    Path(settings.temp_root).mkdir(parents=True, exist_ok=True)


def _require_mirror(db: Session, mirror_id: int) -> Mirror:
    mirror = db.query(Mirror).filter(Mirror.id == mirror_id).one_or_none()
    if mirror is None:
        raise HTTPException(status_code=404, detail="Mirror not found")
    return mirror


def _latest_snapshot(db: Session, mirror_id: int) -> PublishedSnapshot:
    snapshot = db.query(PublishedSnapshot).filter(PublishedSnapshot.mirror_id == mirror_id).one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not available")
    return snapshot


def _queue_sync_job(db: Session, mirror: Mirror) -> SyncJob:
    job = SyncJob(mirror_id=mirror.id, state="queued")
    db.add(job)
    db.commit()
    db.refresh(job)

    queue = get_queue()
    queue.enqueue("app.services.sync_worker.execute_sync_job", job.id)
    return job


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stats")
def stats(db: Session = Depends(get_db)) -> dict[str, int]:
    mirrors = db.query(Mirror).all()
    total = len(mirrors)
    ready = sum(1 for m in mirrors if m.status == MirrorStatus.ready.value)
    failed = sum(1 for m in mirrors if m.status == MirrorStatus.failed.value)
    queued_jobs = db.query(SyncJob).filter(SyncJob.state == "queued").count()
    running_jobs = db.query(SyncJob).filter(SyncJob.state == "running").count()
    return {
        "mirrors_total": total,
        "mirrors_ready": ready,
        "mirrors_failed": failed,
        "jobs_queued": queued_jobs,
        "jobs_running": running_jobs,
    }


@app.get("/mirrors", response_model=list[MirrorResponse])
def list_mirrors(db: Session = Depends(get_db)) -> list[Mirror]:
    return db.query(Mirror).order_by(Mirror.created_at.desc()).all()


@app.post("/mirrors", response_model=CreateMirrorResponse)
def create_mirror(payload: MirrorCreate, db: Session = Depends(get_db)) -> CreateMirrorResponse:
    try:
        validate_github_public_url(payload.source_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    mirror = Mirror(
        source_url=payload.source_url.strip(),
        status=MirrorStatus.pending.value,
        public_token=generate_public_token(),
        expires_at=expiration_from_now(settings.default_url_ttl_days),
    )
    db.add(mirror)
    db.commit()
    db.refresh(mirror)

    sync_job = _queue_sync_job(db, mirror)
    return CreateMirrorResponse(mirror=mirror, job=sync_job)


@app.get("/mirrors/{mirror_id}", response_model=MirrorResponse)
def get_mirror(mirror_id: int, db: Session = Depends(get_db)) -> Mirror:
    return _require_mirror(db, mirror_id)


@app.get("/mirrors/{mirror_id}/jobs", response_model=list[SyncJobResponse])
def get_mirror_jobs(mirror_id: int, db: Session = Depends(get_db)) -> list[SyncJob]:
    _require_mirror(db, mirror_id)
    return db.query(SyncJob).filter(SyncJob.mirror_id == mirror_id).order_by(SyncJob.created_at.desc()).all()


@app.post("/mirrors/{mirror_id}/sync", response_model=SyncJobResponse)
def trigger_sync(mirror_id: int, db: Session = Depends(get_db)) -> SyncJob:
    mirror = _require_mirror(db, mirror_id)
    return _queue_sync_job(db, mirror)


@app.post("/mirrors/{mirror_id}/renew-url", response_model=RenewUrlResponse)
def renew_url(mirror_id: int, db: Session = Depends(get_db)) -> RenewUrlResponse:
    mirror = _require_mirror(db, mirror_id)
    mirror.public_token = generate_public_token()
    mirror.expires_at = expiration_from_now(settings.default_url_ttl_days)
    mirror.updated_at = utcnow()
    db.commit()
    db.refresh(mirror)
    return RenewUrlResponse(mirror_id=mirror.id, new_token=mirror.public_token, expires_at=mirror.expires_at)


def _mirror_from_token(token: str, db: Session) -> tuple[Mirror, Path]:
    mirror = db.query(Mirror).filter(Mirror.public_token == token).one_or_none()
    if mirror is None:
        raise HTTPException(status_code=404, detail="Mirror URL not found")
    if mirror.expires_at < utcnow():
        raise HTTPException(status_code=410, detail="Mirror URL expired")
    snapshot = _latest_snapshot(db, mirror.id)
    root = Path(snapshot.artifact_path)
    if not root.exists():
        raise HTTPException(status_code=404, detail="Snapshot artifact missing")
    return mirror, root


def _list_entries(root: Path) -> list[MirrorPublicListing]:
    entries: list[MirrorPublicListing] = []
    for path in sorted(root.iterdir(), key=lambda p: (p.is_file(), str(p).lower())):
        entries.append(MirrorPublicListing(path=path.name, type="dir" if path.is_dir() else "file"))
    return entries


def _get_public_mirror(token: str, db: Session) -> PublicMirrorView:
    mirror, root = _mirror_from_token(token, db)
    entries = _list_entries(root)
    return PublicMirrorView(mirror_id=mirror.id, expires_at=mirror.expires_at, entries=entries)


@app.get("/m/{token}", response_model=PublicMirrorView)
def get_public_mirror(token: str, db: Session = Depends(get_db)) -> PublicMirrorView:
    return _get_public_mirror(token, db)


@app.get("/r/{token}", response_model=PublicMirrorView)
def get_public_repo_style(token: str, db: Session = Depends(get_db)) -> PublicMirrorView:
    return _get_public_mirror(token, db)


def _normalize_target_path(path: str) -> str:
    parts = [part for part in path.strip().split("/") if part not in {"", ".", ".."}]
    return "/".join(parts)


def _resolve_target(root: Path, path: str) -> Path:
    normalized = _normalize_target_path(path)
    target = (root / normalized).resolve()
    root_resolved = root.resolve()
    if root_resolved not in target.parents and target != root_resolved:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    return target


def _is_binary_file(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:2048]
    except OSError:
        return True
    if not sample:
        return False
    return b"\x00" in sample


def _build_tree(root: Path) -> list[dict]:
    def walk(current: Path) -> list[dict]:
        nodes: list[dict] = []
        children = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        for child in children:
            rel = child.relative_to(root).as_posix()
            if child.is_dir():
                nodes.append({"type": "dir", "name": child.name, "path": rel, "children": walk(child)})
            else:
                nodes.append({"type": "file", "name": child.name, "path": rel})
        return nodes

    return walk(root)


def _render_tree_html(tree: list[dict], current_path: str, prefix: str, token: str) -> str:
    if not tree:
        return "<p class='empty'>Empty repository</p>"

    def render_nodes(nodes: list[dict]) -> str:
        parts = ["<ul class='tree'>"]
        for node in nodes:
            node_path = node["path"]
            is_active = current_path == node_path
            is_open = current_path.startswith(f"{node_path}/") or is_active
            classes = [node["type"]]
            if is_active:
                classes.append("active")
            if is_open:
                classes.append("open")
            href = f"/{prefix}/{token}/browse?path={quote(node_path, safe='/')}"
            icon = "📁" if node["type"] == "dir" else "📄"
            parts.append(
                f"<li class='{' '.join(classes)}'>"
                f"<a href='{href}'><span class='icon'>{icon}</span>{escape(node['name'])}</a>"
            )
            if node["type"] == "dir" and node.get("children"):
                parts.append(render_nodes(node["children"]))
            parts.append("</li>")
        parts.append("</ul>")
        return "".join(parts)

    return render_nodes(tree)


def _render_breadcrumb(current_path: str, prefix: str, token: str) -> str:
    if not current_path:
        return "<a class='crumb active' href='#'>root</a>"
    crumbs: list[str] = [f"<a class='crumb' href='/{prefix}/{token}/browse'>root</a>"]
    accumulated = []
    for piece in current_path.split("/"):
        accumulated.append(piece)
        rel = "/".join(accumulated)
        href = f"/{prefix}/{token}/browse?path={quote(rel, safe='/')}"
        active_class = " active" if rel == current_path else ""
        crumbs.append(f"<span class='sep'>/</span><a class='crumb{active_class}' href='{href}'>{escape(piece)}</a>")
    return "".join(crumbs)


def _render_directory_listing(target: Path, root: Path, prefix: str, token: str) -> str:
    rows = []
    for child in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        rel = child.relative_to(root).as_posix()
        href = f"/{prefix}/{token}/browse?path={quote(rel, safe='/')}"
        type_label = "dir" if child.is_dir() else "file"
        size = "-" if child.is_dir() else f"{child.stat().st_size:,}"
        rows.append(
            "<tr>"
            f"<td><a href='{href}'>{escape(child.name)}</a></td>"
            f"<td>{type_label}</td>"
            f"<td>{size}</td>"
            "</tr>"
        )
    if not rows:
        return "<p class='empty'>This directory is empty.</p>"
    return (
        "<table class='listing'><thead><tr><th>Name</th><th>Type</th><th>Size (bytes)</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _render_file_preview(target: Path, relative_path: str, prefix: str, token: str) -> str:
    raw_url = f"/{prefix}/{token}/raw/{quote(relative_path, safe='/')}"
    ext = target.suffix.lower()
    image_ext = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
    if ext in image_ext:
        return (
            "<div class='preview-tools'>"
            f"<a class='btn' href='{raw_url}' target='_blank' rel='noreferrer'>Open raw</a>"
            f"<a class='btn' href='{raw_url}' download>Download</a>"
            "</div>"
            f"<img class='image-preview' src='{raw_url}' alt='{escape(relative_path)}' />"
        )
    if ext == ".pdf":
        return (
            "<div class='preview-tools'>"
            f"<a class='btn' href='{raw_url}' target='_blank' rel='noreferrer'>Open raw</a>"
            f"<a class='btn' href='{raw_url}' download>Download</a>"
            "</div>"
            f"<iframe class='pdf-preview' src='{raw_url}' title='PDF preview'></iframe>"
        )
    if _is_binary_file(target):
        return (
            "<p class='empty'>Binary file preview is unavailable.</p>"
            f"<a class='btn' href='{raw_url}' download>Download file</a>"
        )

    text = target.read_text(encoding="utf-8", errors="ignore")
    return (
        "<div class='preview-tools'>"
        f"<a class='btn' href='{raw_url}' target='_blank' rel='noreferrer'>Open raw</a>"
        f"<a class='btn' href='{raw_url}' download>Download</a>"
        "</div>"
        f"<pre class='code'><code>{escape(text)}</code></pre>"
    )


def _browse_public_mirror(token: str, path: str, prefix: str, db: Session) -> str:
    mirror, root = _mirror_from_token(token, db)
    normalized_path = _normalize_target_path(path)
    target = _resolve_target(root, normalized_path)
    tree_html = _render_tree_html(_build_tree(root), normalized_path, prefix, token)
    breadcrumb = _render_breadcrumb(normalized_path, prefix, token)

    if target.is_dir():
        content_title = f"Directory: /{normalized_path}" if normalized_path else "Directory: /"
        content_html = _render_directory_listing(target, root, prefix, token)
    else:
        rel = target.relative_to(root).as_posix()
        content_title = f"File: /{rel}"
        content_html = _render_file_preview(target, rel, prefix, token)

    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Anonymized Repository</title>
  <style>
    :root {{
      --bg: #f2f5fb;
      --panel: #ffffff;
      --line: #d6deea;
      --ink: #1f2937;
      --muted: #63748b;
      --dark: #111827;
      --brand: #0e7490;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }}
    .topbar {{
      background: var(--dark);
      color: #fff;
      padding: 0.8rem 1rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 0.8rem;
      flex-wrap: wrap;
    }}
    .brand {{ font-weight: 700; letter-spacing: 0.2px; }}
    .meta {{ color: #c9d7f4; font-size: 0.88rem; }}
    .layout {{
      display: grid;
      grid-template-columns: 300px 1fr;
      gap: 0.9rem;
      padding: 0.9rem;
      min-height: calc(100vh - 64px);
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 10px;
      overflow: hidden;
    }}
    .panel h3 {{
      margin: 0;
      padding: 0.7rem 0.8rem;
      border-bottom: 1px solid var(--line);
      font-size: 0.96rem;
    }}
    .tree-wrap {{ padding: 0.45rem 0.55rem 0.8rem; overflow: auto; max-height: calc(100vh - 140px); }}
    .tree, .tree ul {{ list-style: none; margin: 0; padding-left: 0.8rem; }}
    .tree > li, .tree ul > li {{ margin: 0.2rem 0; }}
    .tree a {{
      color: #243446;
      text-decoration: none;
      display: inline-flex;
      gap: 0.35rem;
      align-items: center;
      border-radius: 6px;
      padding: 0.16rem 0.32rem;
    }}
    .tree li.active > a {{ background: #e6effd; color: #0c4a6e; font-weight: 700; }}
    .tree a:hover {{ background: #eef3fb; }}
    .icon {{ width: 1.2em; text-align: center; }}
    .content {{ display: flex; flex-direction: column; min-width: 0; }}
    .crumbs {{
      padding: 0.7rem 0.8rem;
      border-bottom: 1px solid var(--line);
      font-size: 0.9rem;
      overflow-wrap: anywhere;
    }}
    .crumb {{ color: #1f4a7a; text-decoration: none; }}
    .crumb.active {{ font-weight: 700; }}
    .sep {{ color: var(--muted); margin: 0 0.25rem; }}
    .content-head {{
      padding: 0.7rem 0.8rem;
      border-bottom: 1px solid var(--line);
      font-weight: 700;
      overflow-wrap: anywhere;
    }}
    .content-body {{ padding: 0.85rem; overflow: auto; }}
    .listing {{ width: 100%; border-collapse: collapse; }}
    .listing th, .listing td {{
      text-align: left;
      padding: 0.45rem 0.3rem;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    .listing a {{ color: #0d5581; text-decoration: none; }}
    .listing a:hover {{ text-decoration: underline; }}
    .code {{
      margin: 0;
      background: #0f172a;
      color: #d1e5ff;
      padding: 0.9rem;
      border-radius: 8px;
      overflow: auto;
      max-height: calc(100vh - 280px);
      white-space: pre;
    }}
    .preview-tools {{
      margin-bottom: 0.65rem;
      display: flex;
      gap: 0.45rem;
      flex-wrap: wrap;
    }}
    .btn {{
      display: inline-block;
      border: 1px solid #b9c8df;
      background: #eef3fc;
      color: #1f3348;
      text-decoration: none;
      border-radius: 7px;
      padding: 0.38rem 0.62rem;
      font-size: 0.86rem;
      font-weight: 600;
    }}
    .btn:hover {{ background: #e5edf9; }}
    .image-preview {{
      max-width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }}
    .pdf-preview {{
      width: 100%;
      min-height: calc(100vh - 320px);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .empty {{ color: var(--muted); }}
    @media (max-width: 940px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .tree-wrap {{ max-height: 280px; }}
      .code {{ max-height: 460px; }}
      .pdf-preview {{ min-height: 420px; }}
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand">VeilMirror Mirror Explorer</div>
    <div class="meta">
      r/{escape(token)} | mirror #{mirror.id} | expires {escape(mirror.expires_at.isoformat())}
    </div>
  </header>
  <main class="layout">
    <aside class="panel">
      <h3>Repository Tree</h3>
      <div class="tree-wrap">{tree_html}</div>
    </aside>
    <section class="panel content">
      <div class="crumbs">{breadcrumb}</div>
      <div class="content-head">{escape(content_title)}</div>
      <div class="content-body">{content_html}</div>
    </section>
  </main>
</body>
</html>
"""


@app.get("/m/{token}/browse", response_class=HTMLResponse)
def browse_public_mirror(token: str, path: str = "", db: Session = Depends(get_db)) -> str:
    return _browse_public_mirror(token, path, "m", db)


@app.get("/r/{token}/browse", response_class=HTMLResponse)
def browse_public_repo_style(token: str, path: str = "", db: Session = Depends(get_db)) -> str:
    return _browse_public_mirror(token, path, "r", db)


@app.get("/m/{token}/raw/{file_path:path}")
def raw_file(token: str, file_path: str, db: Session = Depends(get_db)) -> FileResponse:
    _, root = _mirror_from_token(token, db)
    target = (root / file_path).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise HTTPException(status_code=400, detail="Invalid path")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=target)


@app.get("/r/{token}/raw/{file_path:path}")
def raw_file_repo_style(token: str, file_path: str, db: Session = Depends(get_db)) -> FileResponse:
    return raw_file(token, file_path, db)

