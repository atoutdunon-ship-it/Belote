"""Authentification : code PIN hache en Argon2id et jeton JWT."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from .config import get_settings

_hasher = PasswordHasher()
PIN_PATTERN = re.compile(r"^\d{4}$")
ALGORITHM = "HS256"


class AuthError(ValueError):
    pass


def validate_pin(pin: str) -> str:
    if not PIN_PATTERN.match(pin or ""):
        raise AuthError("Le code PIN doit comporter exactement 4 chiffres.")
    return pin


def hash_pin(pin: str) -> str:
    return _hasher.hash(validate_pin(pin))


def validate_password(password: str) -> str:
    if len(password or "") < 6:
        raise AuthError("Le mot de passe doit comporter au moins 6 caracteres.")
    return password


def hash_password(password: str) -> str:
    return _hasher.hash(validate_password(password))


def verify_pin(pin: str, pin_hash: str) -> bool:
    try:
        return _hasher.verify(pin_hash, pin or "")
    except (VerifyMismatchError, VerificationError):
        return False


def verify_password(password: str, password_hash: str) -> bool:
    return verify_pin(password, password_hash)


def needs_rehash(pin_hash: str) -> bool:
    return _hasher.check_needs_rehash(pin_hash)


def create_token(player_id: int, numero: int, is_admin: bool) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(player_id),
        "num": numero,
        "adm": is_admin,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.token_ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AuthError("Session expiree ou jeton invalide.") from exc
