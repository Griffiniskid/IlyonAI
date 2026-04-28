from src.auth.password import hash_password, verify_password


def test_hash_and_verify():
    h = hash_password("secret123")
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_hash_is_argon2():
    h = hash_password("test")
    assert h.startswith("$argon2")
