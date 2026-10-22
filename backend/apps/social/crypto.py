"""Encryption at rest for platform credentials (access/refresh tokens).

Tokens are encrypted with Fernet (AES-128-CBC + HMAC). ``SOCIAL_TOKEN_ENCRYPTION_KEYS``
holds one or more keys; the first encrypts, all decrypt, which allows rotation.
Tokens are never logged, serialized to the API, or sent to the browser.
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings


@lru_cache(maxsize=1)
def _fernet() -> MultiFernet:
    keys: list[str] = settings.SOCIAL_TOKEN_ENCRYPTION_KEYS
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt(value: str | None) -> str:
    if not value:
        return ""
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None


def rotate(value: str) -> str:
    """Re-encrypt with the current first key. Raises InvalidToken if no key decrypts it."""
    if not value:
        return ""
    return _fernet().rotate(value.encode()).decode()


def reset_cache() -> None:
    _fernet.cache_clear()
