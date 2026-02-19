"""Simple password hash verification test."""

import os
from passlib.context import CryptContext

# Using a pure-python hashing scheme avoids external dependencies
PWD_CONTEXT = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def test_password_verification() -> None:
    """Ensure a generated hash verifies against the original password."""
    hashed = PWD_CONTEXT.hash("password")
    assert PWD_CONTEXT.verify("password", hashed)
