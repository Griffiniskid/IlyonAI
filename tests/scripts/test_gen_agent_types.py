import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_check_mode_passes():
    r = subprocess.run(
        ["python", "scripts/gen_agent_types.py", "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr


def test_generated_file_contains_expected_types():
    content = (ROOT / "web" / "types" / "agent.ts").read_text()
    for sym in [
        "ToolEnvelope", "AgentCard", "SentinelBlock", "ShieldBlock",
        "AllocationPayload", "SwapQuotePayload", "PoolPayload",
        "MarketOverviewPayload", "PairListPayload",
        "ThoughtFrame", "ToolFrame", "ObservationFrame",
        "CardFrame", "FinalFrame", "DoneFrame",
    ]:
        assert sym in content, f"missing {sym} in agent.ts"
