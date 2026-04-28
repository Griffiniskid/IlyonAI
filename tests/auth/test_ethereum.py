from src.auth.ethereum import verify_ethereum_signature


def test_invalid_signature_returns_false():
    assert verify_ethereum_signature("0xabc", "msg", "0xbad") is False


def test_valid_round_trip():
    from eth_account import Account
    from eth_account.messages import encode_defunct

    acct = Account.create()
    message = "Sign in to Ilyon AI"
    signed = acct.sign_message(encode_defunct(text=message))
    assert verify_ethereum_signature(
        acct.address, message, signed.signature.hex()
    ) is True
