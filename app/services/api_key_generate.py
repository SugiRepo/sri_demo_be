import secrets

_API_KEY_PREFIX = "sk_"


def generate_api_key() -> str:
    """Return a new random API key string (no persistence or env updates)."""
    return f"{_API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
