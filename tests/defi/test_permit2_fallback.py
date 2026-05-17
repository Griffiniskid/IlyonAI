"""Pin tests for V7-038 Permit2 fallback module."""

from src.defi.permit2_fallback import (
    PERMIT2_ADDRESS,
    fallback_approve_calldata,
    supports_permit2,
)


def test_supports_permit2_true_when_chain_advertises_support() -> None:
    caps = {"0x1": {"permit2": {"supported": True}}}
    assert supports_permit2(caps) is True


def test_supports_permit2_false_for_empty_dict() -> None:
    assert supports_permit2({}) is False


def test_supports_permit2_false_when_supported_flag_is_false() -> None:
    caps = {"0x1": {"permit2": {"supported": False}}}
    assert supports_permit2(caps) is False


def test_supports_permit2_false_for_none_or_non_dict() -> None:
    assert supports_permit2(None) is False  # type: ignore[arg-type]
    assert supports_permit2("not-a-dict") is False  # type: ignore[arg-type]


def test_supports_permit2_true_when_any_chain_supports() -> None:
    caps = {
        "0x1": {"permit2": {"supported": False}},
        "0x2105": {"permit2": {"supported": True}},
    }
    assert supports_permit2(caps) is True


def test_fallback_approve_calldata_returns_required_keys() -> None:
    out = fallback_approve_calldata(
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
        "0x000000000022D473030F116dDEE9F6B43aC78BA3",  # Permit2
        1_000_000,
    )
    assert set(out.keys()) == {"to", "data", "value"}
    assert out["to"] == "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    assert out["value"] == "0x0"


def test_fallback_approve_calldata_selector_is_approve() -> None:
    out = fallback_approve_calldata(
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        1,
    )
    assert out["data"].startswith("0x095ea7b3")


def test_fallback_approve_calldata_padded_lengths_correct() -> None:
    out = fallback_approve_calldata(
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        1_000_000,
    )
    data = out["data"]
    # 0x + 8-char selector + 64-char spender + 64-char amount = 138 chars total
    assert len(data) == 2 + 8 + 64 + 64
    selector = data[2:10]
    padded_spender = data[10:74]
    padded_amount = data[74:138]
    assert selector == "095ea7b3"
    assert len(padded_spender) == 64
    assert len(padded_amount) == 64
    # Spender padded to 32 bytes (address right-aligned, zero-prefixed)
    assert padded_spender == "000000000000000000000000" + "000000000022d473030f116ddee9f6b43ac78ba3"
    # Amount 1_000_000 = 0xf4240
    assert padded_amount.endswith("f4240")
    assert padded_amount.lstrip("0") == "f4240"


def test_permit2_address_constant() -> None:
    assert PERMIT2_ADDRESS == "0x000000000022D473030F116dDEE9F6B43aC78BA3"
