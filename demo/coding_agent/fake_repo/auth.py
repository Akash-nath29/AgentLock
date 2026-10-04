"""Tiny auth module the demo coding agent works on."""

import hashlib
import time

USERS = {
    "alice": hashlib.sha256(b"wonderland").hexdigest(),
    "guest": hashlib.sha256(b"guest-pass").hexdigest(),
}


def check_password(username: str, password: str) -> bool:
    """True if `password` matches the stored hash for `username`."""
    if not password:
        return False
    stored = USERS.get(username)
    return stored is not None and hashlib.sha256(password.encode()).hexdigest() == stored


def is_token_expired(token: dict, now: float | None = None) -> bool:
    """A token is expired once the current time reaches its `expires_at`."""
    now = time.time() if now is None else now
    return token["expires_at"] > now
