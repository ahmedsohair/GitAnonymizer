from app.utils import expiration_from_now, generate_public_token, validate_github_public_url


def test_generate_public_token_is_long_and_unique() -> None:
    first = generate_public_token()
    second = generate_public_token()
    assert first != second
    assert len(first) >= 40


def test_validate_public_github_url() -> None:
    owner, repo = validate_github_public_url("https://github.com/openai/openai-python")
    assert owner == "openai"
    assert repo == "openai-python"


def test_expiration_from_now() -> None:
    expires = expiration_from_now(90)
    assert expires.year >= 2026

