from app.core.security import (
    create_access_token,
    decode_access_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    verify_password,
)


def test_hash_password_produces_different_hash_than_input():
    hashed = hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"


def test_verify_password_accepts_correct_password():
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("wrong-password", hashed) is False


def test_hash_password_is_salted():
    # Duas chamadas para a mesma senha devem gerar hashes diferentes (salt aleatório).
    assert hash_password("same-password") != hash_password("same-password")


def test_encrypt_decrypt_roundtrip():
    secret = "gho_supersecrettoken123"
    encrypted = encrypt_secret(secret)

    assert encrypted != secret
    assert decrypt_secret(encrypted) == secret


def test_access_token_roundtrip():
    token = create_access_token("user-123", extra_claims={"username": "octocat"})
    payload = decode_access_token(token)

    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["username"] == "octocat"


def test_decode_invalid_token_returns_none():
    assert decode_access_token("not-a-valid-token") is None
