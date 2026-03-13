from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..config import settings
from ..utils import EMAIL_RE


@dataclass
class AnonymizeResult:
    replacements: int
    unresolved_hits: int
    findings: list[str]


def is_binary(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:1024]
    except OSError:
        return True
    if not chunk:
        return False
    return b"\x00" in chunk


def _compile_patterns(sensitive_terms: set[str]) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for term in sorted([t for t in sensitive_terms if t], key=len, reverse=True):
        patterns.append(re.compile(re.escape(term), re.IGNORECASE))
    return patterns


def sanitize_tree(source_root: Path, output_root: Path, sensitive_terms: set[str]) -> AnonymizeResult:
    output_root.mkdir(parents=True, exist_ok=True)
    replacements = 0
    findings: list[str] = []

    patterns = _compile_patterns(sensitive_terms)

    for src in source_root.rglob("*"):
        rel = src.relative_to(source_root)
        if rel.parts and rel.parts[0] == ".git":
            continue

        dst = output_root / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)

        if src.stat().st_size > settings.max_file_size_bytes or is_binary(src):
            dst.write_bytes(src.read_bytes())
            continue

        text = src.read_text(encoding="utf-8", errors="ignore")
        original_text = text

        text, email_hits = EMAIL_RE.subn("[REDACTED_EMAIL]", text)
        if email_hits:
            findings.append(f"{rel}: replaced {email_hits} email value(s)")
            replacements += email_hits

        for pattern in patterns:
            text, count = pattern.subn("[REDACTED]", text)
            if count:
                findings.append(f"{rel}: replaced {count} instance(s) of sensitive token")
                replacements += count

        dst.write_text(text, encoding="utf-8")
        if text == original_text:
            continue

    unresolved_hits = scan_for_sensitive_hits(output_root, sensitive_terms)
    return AnonymizeResult(
        replacements=replacements,
        unresolved_hits=unresolved_hits,
        findings=findings,
    )


def scan_for_sensitive_hits(root: Path, sensitive_terms: set[str]) -> int:
    patterns = _compile_patterns(sensitive_terms)
    unresolved = 0
    for path in root.rglob("*"):
        if not path.is_file() or is_binary(path) or path.stat().st_size > settings.max_file_size_bytes:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if EMAIL_RE.search(text):
            unresolved += 1
            continue
        for pattern in patterns:
            if pattern.search(text):
                unresolved += 1
                break
    return unresolved

