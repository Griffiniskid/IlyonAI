from src.defi.search.models import OpportunityCandidate
from src.defi.search.ranking import _diversify_by_protocol


def _c(proto, sym):
    return OpportunityCandidate(protocol=proto, chain="bsc", symbol=sym, apy=1.0, tvl_usd=1e6, risk_level="MEDIUM")


def test_caps_per_protocol_so_list_is_varied():
    # 10 pancakeswap pools ranked first (reliable bonus), then others.
    ordered = [_c("pancakeswap-amm", f"P{i}") for i in range(10)]
    ordered += [_c("wombat", "W1"), _c("mdex", "M1"), _c("uniswap-v3", "U1"), _c("lista", "L1"), _c("biswap", "B1")]
    shown = _diversify_by_protocol(ordered, limit=8, per_cap=3)
    protos = [c.protocol_slug for c in shown]
    assert protos.count("pancakeswap-amm") <= 3, protos
    assert len(set(protos)) >= 4, protos  # multiple protocols surface
    assert len(shown) == 8


def test_backfills_when_few_protocols():
    # Only one protocol available → must still fill the limit (no starvation).
    ordered = [_c("pancakeswap-amm", f"P{i}") for i in range(8)]
    shown = _diversify_by_protocol(ordered, limit=8, per_cap=3)
    assert len(shown) == 8


def test_preserves_rank_order_within_cap():
    ordered = [_c("a", "1"), _c("a", "2"), _c("b", "3"), _c("a", "4")]
    shown = _diversify_by_protocol(ordered, limit=4, per_cap=3)
    assert [c.symbol for c in shown][:3] == ["1", "2", "3"]
