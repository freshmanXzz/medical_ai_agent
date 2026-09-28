"""Argon2id password hashing and verification."""

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from argon2.low_level import Type


_hasher = PasswordHasher(type=Type.ID)


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password must not be empty")
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, VerifyMismatchError):
        return False
