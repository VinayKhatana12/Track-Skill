"""Password hashing tests for app.core.security."""

from app.core.security import hash_password, verify_password


def test_hash_and_verify_roundtrip() -> None:
    hashed = hash_password("Track@123")
    assert hashed != "Track@123"
    assert hashed.startswith("$2")
    assert verify_password("Track@123", hashed)


def test_wrong_password_fails() -> None:
    hashed = hash_password("Track@123")
    assert not verify_password("wrong-password", hashed)


def test_unique_hashes_for_same_password() -> None:
    assert hash_password("Track@123") != hash_password("Track@123")
