"""V4 multi-turn runner.

Fires one chain end-to-end against staging. Dumps raw SSE per turn to
/tmp/v3-deep/v4/<chain_id>/turn_N.txt. Prints per-turn assertion hints to
remind the validator what to read for by hand.

NO mechanical pass/fail. NO ✓/✗ summary. Just curl + dump + hints. The
validator (you) reads every byte and writes verdict prose to _log.md.

Usage:
    python -m tests.harness.v4_runner <chain_id>                # fire one chain
    python -m tests.harness.v4_runner --category A              # fire one category
    python -m tests.harness.v4_runner --all                     # fire all 120 chains
    python -m tests.harness.v4_runner --list                    # list chain IDs
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from tests.harness.v4_matrix import (
    ALL_CHAINS,
    Chain,
    chains_by_category,
    get_chain,
)


STAGING = os.environ.get("STAGING_URL", "https://staging.ilyonai.com")
EVM_WALLET = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SOL_WALLET = "5MgZcXp2qmH3jH8b4dZ7BoFvg9YjQRzL3Wb74Vfy839L"
_DEFAULT_OUT = Path(__file__).resolve().parents[2] / "docs" / "matrix-runs" / "passA-wave1"
OUT_ROOT = Path(os.environ.get("MATRIX_OUT_ROOT", str(_DEFAULT_OUT)))


def fire_turn(chain: Chain, turn_idx: int, sse_path: Path, timeout: int = 90) -> int:
    turn = chain.turns[turn_idx]
    payload = {
        "message": turn.user_message,
        "session_id": chain.session_id,
        "evm_wallet": EVM_WALLET,
        "solana_wallet": SOL_WALLET,
    }
    cmd = [
        "curl", "-sS", "-N", "-m", str(timeout),
        "-X", "POST",
        f"{STAGING}/api/v1/agent",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload),
    ]
    sse_path.parent.mkdir(parents=True, exist_ok=True)
    with sse_path.open("wb") as fh:
        rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, timeout=timeout + 10).returncode
    return rc


def print_hints(chain: Chain, turn_idx: int) -> None:
    turn = chain.turns[turn_idx]
    print(f"  hints turn {turn_idx + 1}:")
    if turn.expect_card:
        print(f"    expect card_type={turn.expect_card}")
    if turn.expect_status:
        print(f"    expect status={turn.expect_status}")
    if turn.expect_action:
        print(f"    expect step.action={turn.expect_action}")
    if turn.expect_blockers:
        print(f"    expect any blocker in {turn.expect_blockers}")
    if turn.expect_selectors:
        print(f"    expect selectors in tx.data: {turn.expect_selectors}")
    if turn.expect_fields:
        for k, v in turn.expect_fields.items():
            print(f"    expect field {k} == {v}")


def run_chain(chain: Chain, *, delay_between_turns: float = 1.5, force: bool = False) -> None:
    out_dir = OUT_ROOT / chain.id
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Chain {chain.id} ({chain.category}) — {chain.notes}")
    print(f"  session_id: {chain.session_id}")
    print(f"  turns: {len(chain.turns)}")
    print(f"  out: {out_dir}/")

    for i, _ in enumerate(chain.turns):
        sse_path = out_dir / f"turn_{i + 1}.txt"
        if sse_path.exists() and sse_path.stat().st_size > 100 and not force:
            print(f"  turn {i + 1}: SKIPPED (already captured, use --force to overwrite)")
            continue
        t0 = time.time()
        rc = fire_turn(chain, i, sse_path)
        dt = time.time() - t0
        size = sse_path.stat().st_size if sse_path.exists() else 0
        print(f"  turn {i + 1}: rc={rc} {dt:.1f}s {size}B → {sse_path.name}")
        print_hints(chain, i)
        if delay_between_turns:
            time.sleep(delay_between_turns)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("chain_id", nargs="?", help="single chain ID to run")
    ap.add_argument("--category", help="run all chains in category (A/B/C/D/E/F/G/H/I)")
    ap.add_argument("--all", action="store_true", help="run every chain")
    ap.add_argument("--list", action="store_true", help="list all chain IDs")
    ap.add_argument("--force", action="store_true", help="overwrite existing captures")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between turns")
    ap.add_argument("--start-from", help="skip all chains before this chain_id (alphabetical)")
    ap.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="run N chains concurrently (wave 8 infra: BUG-M01 singleton "
        "fix makes parallel runs stable. Recommended: 6-9. 1 = sequential.)",
    )
    args = ap.parse_args()

    if args.list:
        for ch in ALL_CHAINS:
            print(f"{ch.id:30s}  [{ch.category}]  {len(ch.turns)} turns  — {ch.notes}")
        return 0

    chains: list[Chain]
    if args.all:
        chains = ALL_CHAINS
    elif args.category:
        chains = chains_by_category(args.category.upper())
    elif args.chain_id:
        chains = [get_chain(args.chain_id)]
    else:
        ap.print_help()
        return 1

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    if args.start_from:
        chains = [c for c in chains if c.id >= args.start_from]

    if args.parallel <= 1:
        for ch in chains:
            run_chain(ch, delay_between_turns=args.delay, force=args.force)
    else:
        # Wave 8 — parallel matrix fire. Each worker runs N chains
        # sequentially in its own thread to preserve per-chain session_id
        # ordering. BUG-M01 (singleton aiohttp ClientSession) fix in wave 5
        # makes concurrent requests stable.
        from concurrent.futures import ThreadPoolExecutor, as_completed
        chunk_size = max(1, len(chains) // args.parallel)
        chunks = [chains[i:i + chunk_size] for i in range(0, len(chains), chunk_size)]
        print(f"\n=== Parallel run: {len(chunks)} workers × ~{chunk_size} chains each\n")
        def worker(chunk):
            for ch in chunk:
                run_chain(ch, delay_between_turns=args.delay, force=args.force)
            return len(chunk)
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            futures = [pool.submit(worker, chunk) for chunk in chunks]
            for f in as_completed(futures):
                _ = f.result()
        print(f"\n=== Parallel run complete: {sum(len(c) for c in chunks)} chains\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
