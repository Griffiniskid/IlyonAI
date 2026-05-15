"""Spec §6g — 20-row receipt-verification table.

Each row maps a protocol-family receipt kind to (a) the RPC read the
assistant must perform within the 60-second post-broadcast window,
(b) the success criterion ("balance delta ≥ expected × (1 − slippage)"
/ "position has liquidity > 0" / "ticks match plan"), and (c) any
optional sanity check (e.g. Curve's get_virtual_price peg drift).

This module ships the table as data. Live RPC reads are implemented
in src/defi/verification/verifiers.py — each kind has a verifier
function with the signature:

    async def verify(
        web3,                # AsyncWeb3 or solana AsyncClient
        user: str,           # EOA / pubkey
        tx_hash: str,
        expected: dict,      # { amount, lp_token, position_id, ... }
    ) -> ReceiptVerificationResult
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class ReceiptKind(str, Enum):
    LP_ERC20 = "LP_ERC20"                           # Uniswap V2 + 8 forks, Curve, Balancer V2/V3 (BPT also fits)
    BPT = "BPT"                                     # Balancer V2/V3 specifically (with Vault.getPoolTokenInfo sanity)
    V3_NFT = "V3_NFT"                               # Uniswap V3, PancakeSwap V3, Slipstream, Velodrome CL
    V4_NFT = "V4_NFT"                               # Uniswap V4 PositionManager
    ATOKEN = "ATOKEN"                               # Aave V3
    ERC4626_SHARE = "ERC4626_SHARE"                 # Yearn V3, Beefy, Reaper, Spark, Sky, Renzo, Ether.fi
    KTOKEN = "KTOKEN"                               # Kamino Vaults strategy share
    POSITION_PDA = "POSITION_PDA"                   # Meteora DLMM (no NFT — PDA only)
    POSITION_PDA_WITH_NFT = "POSITION_PDA_WITH_NFT" # Orca Whirlpools, Raydium CLMM (PDA + NFT)
    LP_MINT_SPL = "LP_MINT_SPL"                     # Raydium AMM v4 + CPMM, Orca v1, Meteora DAMM v2
    JLP = "JLP"                                     # Jupiter Perps LP (SPL token + program state)
    MSOL = "MSOL"                                   # Marinade Liquid Staking
    JITOSOL = "JITOSOL"                             # Jito Stake Pool
    INF = "INF"                                     # Sanctum Infinity
    LST_ERC20 = "LST_ERC20"                         # Lido, Rocket Pool, Frax, Stader, Mantle, ether.fi
    LRT_ERC20 = "LRT_ERC20"                         # Renzo ezETH, Kelp rsETH, Swell rswETH, Puffer pufETH, EigenLayer
    OBLIGATION_STATE = "OBLIGATION_STATE"           # Kamino Lend klend (no SPL — obligation account read)
    CTOKEN = "CTOKEN"                               # Compound V3 cBaseToken
    PENDLE_PT_YT = "PENDLE_PT_YT"                   # Pendle V2 (PT + YT or LP)
    STARGATE_SHARE = "STARGATE_SHARE"               # Stargate V2 S*USDC etc.


@dataclass
class ReceiptVerifierSpec:
    """Describes what to verify for a given receipt kind."""

    kind: ReceiptKind
    chain_family: str                # "evm" | "solana"
    rpc_method: str                  # one-line description of the RPC read
    success_predicate: str           # one-line description of the success criterion
    sanity_check: str | None = None  # optional secondary check
    note: str | None = None          # gotchas (e.g. "AMM v4 LP not Jupiter-tradable")


RECEIPT_TABLE: dict[ReceiptKind, ReceiptVerifierSpec] = {
    ReceiptKind.LP_ERC20: ReceiptVerifierSpec(
        kind=ReceiptKind.LP_ERC20,
        chain_family="evm",
        rpc_method="balanceOf(user, lpToken) before/after",
        success_predicate="delta >= expected_lp_amount * (1 - slippage)",
    ),
    ReceiptKind.BPT: ReceiptVerifierSpec(
        kind=ReceiptKind.BPT,
        chain_family="evm",
        rpc_method="balanceOf(user, bpt) before/after",
        success_predicate="delta > 0 AND matches plan within slippage",
        sanity_check="Vault.getPoolTokenInfo(poolId) ratio sanity",
        note="Balancer V2 (legacy Vault) and V3 (new singleton Vault) share BPT shape; verifier reads from the right Vault per protocol_version.",
    ),
    ReceiptKind.V3_NFT: ReceiptVerifierSpec(
        kind=ReceiptKind.V3_NFT,
        chain_family="evm",
        rpc_method="NFPM.positions(tokenId)",
        success_predicate="liquidity > 0 AND tickLower/Upper match plan",
        note="Read NFPM Transfer(0x0, user, tokenId) from receipt logs to discover tokenId.",
    ),
    ReceiptKind.V4_NFT: ReceiptVerifierSpec(
        kind=ReceiptKind.V4_NFT,
        chain_family="evm",
        rpc_method="PoolManager.getPositionInfo(poolId, owner, salt)",
        success_predicate="liquidity > 0",
        note="V4 has no per-pool contract; identity is (poolId, owner, salt) hash.",
    ),
    ReceiptKind.ATOKEN: ReceiptVerifierSpec(
        kind=ReceiptKind.ATOKEN,
        chain_family="evm",
        rpc_method="balanceOf(user, aToken) before/after",
        success_predicate="delta >= supply_amount",
        sanity_check="getReserveConfiguration isolated-mode flag matches user expectation",
    ),
    ReceiptKind.ERC4626_SHARE: ReceiptVerifierSpec(
        kind=ReceiptKind.ERC4626_SHARE,
        chain_family="evm",
        rpc_method="convertToAssets(balanceOf(user))",
        success_predicate="convertToAssets(balanceOf) >= deposit_amount * (1 - slippage)",
    ),
    ReceiptKind.KTOKEN: ReceiptVerifierSpec(
        kind=ReceiptKind.KTOKEN,
        chain_family="solana",
        rpc_method="getTokenAccountBalance(user_kToken_ata)",
        success_predicate="ATA balance delta > 0 within expected range",
    ),
    ReceiptKind.POSITION_PDA: ReceiptVerifierSpec(
        kind=ReceiptKind.POSITION_PDA,
        chain_family="solana",
        rpc_method="getAccountInfo(position_pda) + parse owner+liquidity+bin_distribution",
        success_predicate="owner == user AND liquidity > 0 AND bin distribution matches strategy",
        note="Meteora DLMM positions live as PDA accounts (no NFT mint).",
    ),
    ReceiptKind.POSITION_PDA_WITH_NFT: ReceiptVerifierSpec(
        kind=ReceiptKind.POSITION_PDA_WITH_NFT,
        chain_family="solana",
        rpc_method="getAccountInfo(position_pda) + getTokenAccountInfo(position_mint_ata)",
        success_predicate="position_pda exists with liquidity > 0 AND user holds the position-NFT (Metaplex metadata)",
        note="Whirlpool + Raydium CLMM both mint a Metaplex NFT alongside the PDA.",
    ),
    ReceiptKind.LP_MINT_SPL: ReceiptVerifierSpec(
        kind=ReceiptKind.LP_MINT_SPL,
        chain_family="solana",
        rpc_method="getTokenAccountBalance(user_lp_ata) before/after",
        success_predicate="LP ATA delta >= expected_lp_amount",
        note="Raydium AMM v4 LP NOT Jupiter-tradable — redemption goes through Raydium's program.",
    ),
    ReceiptKind.JLP: ReceiptVerifierSpec(
        kind=ReceiptKind.JLP,
        chain_family="solana",
        rpc_method="getTokenAccountBalance(user_JLP_ata) + Jupiter Perps program-state confirm",
        success_predicate="JLP ATA delta > 0 AND program-state LP supply increased",
        note="Withdrawal lockup 1 hour — surface in Preview.",
    ),
    ReceiptKind.MSOL: ReceiptVerifierSpec(
        kind=ReceiptKind.MSOL,
        chain_family="solana",
        rpc_method="getTokenAccountBalance(user_mSOL_ata)",
        success_predicate="ATA delta * marinade_exchange_rate ≈ input SOL",
        sanity_check="Marinade state.msol_supply increased; oracle exchange rate matches on-chain rate",
    ),
    ReceiptKind.JITOSOL: ReceiptVerifierSpec(
        kind=ReceiptKind.JITOSOL,
        chain_family="solana",
        rpc_method="getTokenAccountBalance(user_JitoSOL_ata)",
        success_predicate="ATA delta > 0 AND SPL Stake Pool state.totalLamports increased",
    ),
    ReceiptKind.INF: ReceiptVerifierSpec(
        kind=ReceiptKind.INF,
        chain_family="solana",
        rpc_method="getTokenAccountBalance(user_INF_ata)",
        success_predicate="ATA delta > 0 AND Sanctum router state matches deposit",
    ),
    ReceiptKind.LST_ERC20: ReceiptVerifierSpec(
        kind=ReceiptKind.LST_ERC20,
        chain_family="evm",
        rpc_method="balanceOf(user, lst_token)",
        success_predicate="balance delta >= input_amount * exchange_rate * (1 - slippage)",
        sanity_check="For Lido: getPooledEthByShares(balanceOf) ≈ input ETH",
    ),
    ReceiptKind.LRT_ERC20: ReceiptVerifierSpec(
        kind=ReceiptKind.LRT_ERC20,
        chain_family="evm",
        rpc_method="balanceOf(user, lrt_token)",
        success_predicate="balance delta > 0",
        sanity_check="Restaking state confirms queued portion (Renzo, Kelp, Swell stake state read)",
    ),
    ReceiptKind.OBLIGATION_STATE: ReceiptVerifierSpec(
        kind=ReceiptKind.OBLIGATION_STATE,
        chain_family="solana",
        rpc_method="getAccountInfo(obligation_pda) → deposits[reserve].amount",
        success_predicate="obligation.deposits[reserve].amount delta ≈ supply_amount",
        note="No SPL receipt; obligation account state is the source of truth.",
    ),
    ReceiptKind.CTOKEN: ReceiptVerifierSpec(
        kind=ReceiptKind.CTOKEN,
        chain_family="evm",
        rpc_method="Comet.balanceOf(user) (cBaseToken)",
        success_predicate="balance delta >= supply_amount",
        note="Compound V3 Comet — single base asset + multi-collateral mode.",
    ),
    ReceiptKind.PENDLE_PT_YT: ReceiptVerifierSpec(
        kind=ReceiptKind.PENDLE_PT_YT,
        chain_family="evm",
        rpc_method="balanceOf(user, PT) + balanceOf(user, YT) OR balanceOf(user, LP)",
        success_predicate="(mintPY: PT delta > 0 AND YT delta > 0) OR (addLiquidity: LP delta > 0)",
        note="Three entry modes — verify which the user's plan executed.",
    ),
    ReceiptKind.STARGATE_SHARE: ReceiptVerifierSpec(
        kind=ReceiptKind.STARGATE_SHARE,
        chain_family="evm",
        rpc_method="balanceOf(user, S*USDC|S*USDT)",
        success_predicate="balance delta >= deposit * (1 - slippage)",
        note="Stargate V2 share follows ERC-4626 shape but uses its own router.",
    ),
}


def verifier_for(kind: ReceiptKind | str) -> ReceiptVerifierSpec | None:
    if isinstance(kind, str):
        try:
            kind = ReceiptKind(kind)
        except ValueError:
            return None
    return RECEIPT_TABLE.get(kind)


def list_receipt_kinds() -> list[str]:
    return [k.value for k in ReceiptKind]
