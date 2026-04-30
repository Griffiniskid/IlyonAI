from src.optimizer.daemon import OptimizerDaemon
from src.optimizer.plan_synth import move_to_plan
from src.optimizer.safety import OptimizerPreferences, can_propose_rebalance, should_throttle
from src.optimizer.snapshot import PortfolioPosition, PortfolioSnapshot


def test_optimizer_requires_all_opt_in_gates():
    prefs = OptimizerPreferences(
        auto_rebalance_opt_in=True,
        risk_budget="balanced",
        preferred_chains=["arbitrum"],
        gas_cap_usd=25,
        rebalance_auth_signature="0xsigned",
    )

    assert can_propose_rebalance(prefs) is True
    assert can_propose_rebalance(prefs.model_copy(update={"rebalance_auth_signature": None})) is False


def test_move_to_plan_reuses_execution_plan_shape():
    plan = move_to_plan(
        {
            "from_token": "USDC",
            "to_protocol": "aave-v3",
            "to_chain_id": 42161,
            "usd_value": 2_000,
            "estimated_gas_usd": 8,
        }
    )

    assert plan.card_type == "execution_plan_v2"
    assert plan.payload.risk_gate in {"clear", "soft_warn"}


def test_daemon_records_no_change_for_optimal_portfolio():
    daemon = OptimizerDaemon()
    snapshot = PortfolioSnapshot(
        user_id=1,
        positions=[PortfolioPosition(protocol="aave-v3", token="USDC", chain="arbitrum", usd_value=2_000, apy=4.8, sentinel=88)],
    )

    run = daemon.propose(user_id=1, snapshot=snapshot, target_positions=snapshot.positions)

    assert run.outcome == "no_change"
    assert run.plan is None


def test_safety_throttle_blocks_second_daily_proposal():
    assert should_throttle(last_proposed_at=100.0, now=100.0 + 60 * 60, force=False) is True
    assert should_throttle(last_proposed_at=100.0, now=100.0 + 60 * 60, force=True) is False
