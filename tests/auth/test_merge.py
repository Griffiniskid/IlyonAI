import hashlib


def test_sentinel_wallet_length():
    email = "user@example.com"
    sentinel = "email:" + hashlib.sha256(email.encode()).hexdigest()[:36]
    assert len(sentinel) == 42


def test_sentinel_is_deterministic():
    email = "alice@example.com"
    s1 = "email:" + hashlib.sha256(email.encode()).hexdigest()[:36]
    s2 = "email:" + hashlib.sha256(email.encode()).hexdigest()[:36]
    assert s1 == s2


def test_different_emails_different_sentinels():
    s1 = "email:" + hashlib.sha256(b"a@b.com").hexdigest()[:36]
    s2 = "email:" + hashlib.sha256(b"c@d.com").hexdigest()[:36]
    assert s1 != s2
