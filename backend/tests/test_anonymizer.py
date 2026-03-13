from pathlib import Path

from app.services.anonymizer import sanitize_tree


def test_sanitize_tree_replaces_sensitive_values(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    (source / "README.md").write_text(
        "Repo by Jane Doe at jane@example.com\nSource: https://github.com/acme/secret-repo",
        encoding="utf-8",
    )
    (source / ".git").mkdir()
    (source / ".git" / "config").write_text("sensitive", encoding="utf-8")

    result = sanitize_tree(
        source,
        output,
        sensitive_terms={"Jane Doe", "acme", "secret-repo", "https://github.com/acme/secret-repo"},
    )
    text = (output / "README.md").read_text(encoding="utf-8")

    assert "Jane Doe" not in text
    assert "jane@example.com" not in text
    assert "secret-repo" not in text
    assert result.replacements > 0
    assert result.unresolved_hits == 0
    assert not (output / ".git").exists()

