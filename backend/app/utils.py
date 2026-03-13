import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse


GITHUB_RE = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[A-Za-z]{2,}\b")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def validate_github_public_url(source_url: str) -> tuple[str, str]:
    match = GITHUB_RE.match(source_url.strip())
    if not match:
        raise ValueError("Only public GitHub repository URLs are supported, e.g. https://github.com/org/repo")
    owner = match.group(1)
    repo = match.group(2)
    return owner, repo


def normalize_repo_url(source_url: str) -> str:
    parsed = urlparse(source_url.strip())
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return f"https://github.com{path}.git"


def generate_public_token() -> str:
    return secrets.token_urlsafe(48)


def expiration_from_now(days: int) -> datetime:
    return utcnow() + timedelta(days=days)


def sha256_directory(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted([p for p in root.rglob("*") if p.is_file()]):
        digest.update(str(path.relative_to(root)).encode("utf-8", errors="ignore"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def dump_json(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True)

