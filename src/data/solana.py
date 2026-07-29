"""
Solana RPC client for on-chain token data and holder analysis.

This module provides an async client for interacting with Solana RPC
to fetch token mint information, holder data, analyze wallet distribution,
and simulate transactions for honeypot detection.

NOTE: This is the core blockchain client for Ilyon AI.
Exclusively designed for Solana mainnet - no other chains supported.
"""

import logging
import base64
import asyncio
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import aiohttp
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Commitment
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

from src.analytics.anomaly_detector import BehavioralAnomalyDetector
from src.analytics.time_series import TimeSeriesDataPoint
from src.analytics.wallet_forensics import WalletForensicsEngine, get_token_deployer
from src.core.models import TokenInfo
from src.smart_money.models import CanonicalFlowEvent
from src.smart_money.normalizer import normalize_event

# Retry configuration for rate-limited RPC calls
MAX_RETRIES = 3
RETRY_DELAYS = [1.0, 2.0, 4.0]  # Exponential backoff delays in seconds


def _apply_helius_key_to_url(url: Optional[str], key: Optional[str]) -> Optional[str]:
    """Return ``url`` with its ``api-key=`` query value replaced by ``key``.

    Used so a rotated Helius key propagates to RPC endpoints that embed the key
    in the URL (e.g. ``https://mainnet.helius-rpc.com/?api-key=...``). Non-Helius
    or keyless URLs (the public mainnet-beta RPC) are returned unchanged.
    """
    if not url or not key or "api-key=" not in url:
        return url
    return re.sub(r"api-key=[^&]*", f"api-key={key}", url)


def to_canonical_flow_event(raw_event: Dict[str, Any]) -> CanonicalFlowEvent:
    canonical_raw = dict(raw_event)
    canonical_raw.setdefault("chain", "solana")
    return normalize_event(canonical_raw)


# SPL token-program addresses (both Token and Token-2022 emit identical
# AccountState layout — byte 108 of the 165-byte SPL token account is the
# state discriminant). Kept module-level so `check_account_frozen` doesn't
# allocate per call.
_SPL_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
_SPL_TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


async def check_account_frozen(
    mint: str,
    owner: str,
    rpc_url: str,
    *,
    session: Optional[aiohttp.ClientSession] = None,
    timeout_s: float = 8.0,
) -> bool:
    """V7-007 — Spec §13 row 5 frozen-account preflight.

    Returns True when `owner` holds an SPL token account for `mint` whose
    AccountState discriminant equals 2 (Frozen). The freeze authority on
    SPL-Token (and Token-2022) lets an issuer permanently disable transfers
    out of a holder's ATA — signing a swap/supply/stake on a frozen account
    burns gas and surfaces a confusing 0x11 (AccountFrozen) program error.
    Shield emits a FROZEN_ACCOUNT blocker so the user can route around it.

    Implementation:
      1. `getTokenAccountsByOwner({owner}, {mint, programId=Token})` — returns
         the user's token account(s) for that mint. We accept both legacy
         Token and Token-2022 (parallel JSON-RPC fan-out so a Token-2022 mint
         doesn't get false-negatived by the legacy programId filter).
      2. For each returned token account, decode the SPL token account data
         (Account layout, 165 bytes). Byte offset 108 is the AccountState
         u8: 0=Uninitialized, 1=Initialized, 2=Frozen. The RPC `jsonParsed`
         encoding hands us the state as `state: "frozen"` so we honor that
         path first, then fall back to raw base64 byte-decode.
      3. ANY token account in state=Frozen → return True. The caller treats
         the (mint, owner) pair as blocked.

    Fail-soft: network errors / malformed responses return False. The
    preflight's job is to surface a known-true blocker; it must never
    fabricate one from a transport flake.
    """
    if not mint or not owner or not rpc_url:
        return False

    owns_session = session is None
    if owns_session:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s))

    try:
        async def _accounts_for_program(program_id: str) -> List[Dict[str, Any]]:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    owner,
                    {"mint": mint, "programId": program_id},
                    {"encoding": "jsonParsed", "commitment": "confirmed"},
                ],
            }
            try:
                async with session.post(rpc_url, json=payload,
                                        timeout=aiohttp.ClientTimeout(total=timeout_s)) as resp:
                    if resp.status != 200:
                        return []
                    body = await resp.json()
            except Exception as exc:
                logger.debug("getTokenAccountsByOwner failed for %s/%s: %s",
                             mint[:8], owner[:8], exc)
                return []
            if not isinstance(body, dict) or body.get("error"):
                return []
            result = body.get("result") or {}
            value = result.get("value")
            return value if isinstance(value, list) else []

        # Fan out both SPL Token and Token-2022 programs in parallel so a
        # Token-2022 mint isn't missed by a legacy-only filter.
        legacy_accounts, token22_accounts = await asyncio.gather(
            _accounts_for_program(_SPL_TOKEN_PROGRAM),
            _accounts_for_program(_SPL_TOKEN_2022_PROGRAM),
            return_exceptions=False,
        )
        accounts = (legacy_accounts or []) + (token22_accounts or [])
        if not accounts:
            return False

        async def _account_is_frozen(entry: Dict[str, Any]) -> bool:
            # 1) jsonParsed fast-path. RPC hands us
            # {account: {data: {parsed: {info: {state: "frozen"|"initialized"|"uninitialized"}}}}}
            pubkey = entry.get("pubkey") or ""
            acct = entry.get("account") or {}
            data = acct.get("data")
            if isinstance(data, dict):
                parsed = data.get("parsed") or {}
                info = parsed.get("info") if isinstance(parsed, dict) else None
                if isinstance(info, dict):
                    state = str(info.get("state") or "").lower()
                    if state == "frozen":
                        return True
                    if state in {"initialized", "uninitialized"}:
                        return False

            # 2) Fallback — re-fetch with base64 encoding and byte-decode the
            # SPL token account. AccountState is at offset 108 (1 byte u8).
            if not pubkey:
                return False
            info_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": [pubkey, {"encoding": "base64", "commitment": "confirmed"}],
            }
            try:
                async with session.post(rpc_url, json=info_payload,
                                        timeout=aiohttp.ClientTimeout(total=timeout_s)) as ar:
                    if ar.status != 200:
                        return False
                    abody = await ar.json()
            except Exception as exc:
                logger.debug("getAccountInfo fallback failed for %s: %s",
                             pubkey[:8], exc)
                return False
            if not isinstance(abody, dict) or abody.get("error"):
                return False
            avalue = (abody.get("result") or {}).get("value") or {}
            adata = avalue.get("data")
            if isinstance(adata, list) and len(adata) >= 2 and adata[1] == "base64":
                try:
                    raw = base64.b64decode(adata[0])
                except Exception:
                    return False
                # SPL Account layout — state at offset 108.
                if len(raw) >= 109:
                    return raw[108] == 2
            return False

        flags = await asyncio.gather(
            *(_account_is_frozen(a) for a in accounts),
            return_exceptions=False,
        )
        return any(bool(f) for f in flags)
    finally:
        if owns_session and session is not None:
            await session.close()


@dataclass
class SimulationResult:
    """Result of transaction simulation."""
    success: bool
    error: Optional[str] = None
    error_code: Optional[int] = None
    logs: List[str] = field(default_factory=list)
    units_consumed: int = 0
    return_data: Optional[Dict] = None

logger = logging.getLogger(__name__)


class SolanaClient:
    """
    Async client for Solana RPC operations.

    Handles on-chain token data fetching including mint authority,
    freeze authority, token supply, and top holder analysis.
    """

    # Solana program addresses
    TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

    # Well-known token mints for whale detection
    WSOL_MINT = "So11111111111111111111111111111111111111112"
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
    STABLECOIN_MINTS = {USDC_MINT, USDT_MINT}
    # All payment-side mints (not the traded asset)
    PAYMENT_MINTS = {WSOL_MINT, USDC_MINT, USDT_MINT}

    # Known addresses to exclude from holder analysis
    KNOWN_ADDRESSES = {
        '5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1',  # Raydium Authority V4
        'So11111111111111111111111111111111111111112',   # Wrapped SOL
        '1nc1nerator11111111111111111111111111111111',   # Burn address
        '11111111111111111111111111111111',              # System program
    }

    def __init__(self, rpc_url: str, helius_api_key: Optional[str] = None):
        """
        Initialize Solana RPC client.

        Args:
            rpc_url: Solana RPC endpoint URL
            helius_api_key: Optional Helius API key for enhanced holder data
        """
        # Resolve the live Helius key from the shared failover pool so every
        # SolanaClient (whale poller, portfolio scan, token analysis) rotates
        # together. The explicit ``helius_api_key`` arg is a fallback used when
        # the pool is empty (tests / single-key setups with no env configured).
        from src.data.helius_keys import get_active_helius_key

        self.helius_api_key = get_active_helius_key() or helius_api_key
        # If the RPC URL embeds a Helius key, swap in the live one so the RPC
        # endpoint rotates together with the enhanced-API key.
        self.rpc_url = _apply_helius_key_to_url(rpc_url, self.helius_api_key) or rpc_url
        self._client: Optional[AsyncClient] = None
        self._anomaly_detector = BehavioralAnomalyDetector()
        self._wallet_forensics = WalletForensicsEngine(solana_rpc_url=self.rpc_url)

    def _rotate_helius_key(self, failed_key: Optional[str] = None, transient: bool = False) -> bool:
        """Mark the failed Helius key exhausted and switch to the next one.

        Updates ``self.helius_api_key`` and ``self.rpc_url`` in place and drops
        the native RPC client so it reconnects with the new key. Returns True
        when a *different* key is now active than the one the caller used (i.e.
        it's worth retrying); False for single-key setups with nothing to fail
        over to.

        ``failed_key`` is the key the caller actually sent the failing request
        with. When several concurrent requests (e.g. the whale poller's parallel
        DEX-program fetches) all 429 on the same key, only the first should park
        it — the rest find ``failed_key`` no longer current and simply adopt the
        already-rotated key instead of wrongly parking the healthy one.

        ``transient`` marks a per-second rate-limit 429 (key healthy, recovers in
        seconds → short cooldown) versus a monthly-cap 429 (key dead until reset
        → long cooldown). Misclassifying a rate limit as a cap would strand a
        healthy key for 30 min, so callers pass the result of ``is_cap_exhaustion``.
        """
        from src.data.helius_keys import (
            mark_helius_key_exhausted,
            RATE_LIMIT_COOLDOWN_S,
            DEFAULT_COOLDOWN_S,
        )

        current = self.helius_api_key
        if failed_key is not None and failed_key != current:
            # Another concurrent caller already rotated past the failed key;
            # the current key is different, so retrying is worthwhile.
            return True
        cooldown = RATE_LIMIT_COOLDOWN_S if transient else DEFAULT_COOLDOWN_S
        nxt = mark_helius_key_exhausted(current, cooldown)
        if nxt and nxt != current:
            self.helius_api_key = nxt
            self.rpc_url = _apply_helius_key_to_url(self.rpc_url, nxt) or self.rpc_url
            # Force a reconnect so native RPC calls use the rotated key/URL.
            self._client = None
            return True
        return False

    async def _handle_helius_429(self, resp, used_key: Optional[str]) -> bool:
        """Read a 429 response body, classify cap-vs-rate-limit, and rotate.

        Returns True when a different key is now active (worth retrying). Reading
        the body is what lets us tell a transient per-second rate limit (empty
        body) from a monthly-cap 429 (``max usage reached``) and pick the right
        cooldown.
        """
        from src.data.helius_keys import is_cap_exhaustion

        try:
            body_text = await resp.text()
        except Exception:
            body_text = ""
        transient = not is_cap_exhaustion(getattr(resp, "status", 429), body_text)
        return self._rotate_helius_key(used_key, transient=transient)

    async def _ensure_connected(self):
        """Ensure RPC client is connected"""
        if not self._client:
            self._client = AsyncClient(self.rpc_url, commitment=Commitment("confirmed"))
            logger.info("✅ Solana RPC connected")

    async def close(self):
        """Close the RPC client connection"""
        if self._client:
            await self._client.close()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def _get_holders_via_helius(self, address: str, limit: int = 20) -> List[Dict]:
        """Fetch token holders via Helius RPC + DAS fallback.

        Strategy:
          1. getTokenLargestAccounts (fast, returns top 20 with UI amounts).
          2. On transient overload (-32603), retry up to 2x with backoff.
          3. On 'too many accounts' (-32600), fall back to public Solana RPC
             which still serves getTokenLargestAccounts for big mints.
        """
        if not self.helius_api_key:
            return []

        helius_url = f"https://mainnet.helius-rpc.com/?api-key={self.helius_api_key}"
        public_url = self.rpc_url or "https://api.mainnet-beta.solana.com"

        async def _largest(session, url):
            payload = {"jsonrpc": "2.0", "id": 1, "method": "getTokenLargestAccounts", "params": [address]}
            try:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status != 200:
                        return ("status", r.status, None)
                    return ("ok", None, await r.json())
            except Exception as exc:
                return ("exc", str(exc), None)

        def _parse_largest(body):
            if not isinstance(body, dict):
                return None
            if 'error' in body:
                return None
            value = (body.get('result') or {}).get('value') or []
            holders = []
            for account in value[:limit]:
                amount = 0.0
                if account.get('uiAmount') is not None:
                    amount = float(account['uiAmount'])
                elif account.get('ui_amount') is not None:
                    amount = float(account['ui_amount'])
                elif account.get('uiAmountString'):
                    try: amount = float(account['uiAmountString'])
                    except Exception: amount = 0.0
                elif 'amount' in account:
                    raw = account.get('amount', 0)
                    dec = int(account.get('decimals', 9))
                    if isinstance(raw, str):
                        try: raw = int(raw)
                        except Exception: raw = 0
                    amount = raw / (10 ** dec) if dec else float(raw)
                holders.append({'address': account.get('address', ''), 'amount': amount})
            return holders

        try:
            async with aiohttp.ClientSession() as session:
                # 1. Try Helius getTokenLargestAccounts with retry on -32603.
                body = None
                err_code = None
                err_msg = ''
                for attempt in range(3):
                    kind, info, b = await _largest(session, helius_url)
                    if kind == "ok" and isinstance(b, dict):
                        body = b
                        err = b.get('error') if isinstance(b.get('error'), dict) else None
                        err_code = err.get('code') if err else None
                        err_msg = err.get('message', '') if err else ''
                        if err_code == -32603 and attempt < 2:
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        break
                    if kind == "status" and info in (429, 503) and attempt < 2:
                        # 429 → fail over to the next Helius key before retrying.
                        # No body captured here, so treat as transient (short
                        # cooldown); the whale/token paths long-park a real cap.
                        if info == 429 and self._rotate_helius_key(transient=True):
                            helius_url = f"https://mainnet.helius-rpc.com/?api-key={self.helius_api_key}"
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    break

                # 2. Success path: parse and return.
                if body is not None and 'error' not in body:
                    holders = _parse_largest(body) or []
                    if holders:
                        logger.info(f"✅ Helius: Found {len(holders)} holders for {address[:8]}")
                    return holders

                if err_code or err_msg:
                    logger.warning(f"Helius API error after retries: code={err_code} msg={err_msg}")

                # 3. Fall back to public Solana RPC for getTokenLargestAccounts.
                kind, info, b = await _largest(session, public_url)
                if kind == "ok" and isinstance(b, dict) and 'error' not in b:
                    holders = _parse_largest(b) or []
                    if holders:
                        logger.info(f"✅ Public RPC fallback: {len(holders)} holders for {address[:8]}")
                        return holders

                # 4. Final fallback — Helius DAS getTokenAccounts paged scan.
                #    Pull up to 5 pages (5000 accounts), sort by raw amount,
                #    then return top N. Won't capture every whale on 5M-holder
                #    mints but yields a representative top-N for most tokens.
                decimals = 0
                try:
                    mint_payload = {"jsonrpc": "2.0", "id": 1, "method": "getAsset", "params": {"id": address}}
                    async with session.post(helius_url, json=mint_payload, timeout=aiohttp.ClientTimeout(total=10)) as mr:
                        if mr.status == 200:
                            mr_data = await mr.json()
                            token_info = ((mr_data.get('result') or {}).get('token_info') or {})
                            decimals = int(token_info.get('decimals') or 0)
                except Exception:
                    decimals = 0
                divisor = (10 ** decimals) if decimals else 1
                all_accounts: List[Dict] = []
                cursor = None
                for _ in range(5):
                    das_params = {
                        "mint": address,
                        "limit": 1000,
                        "options": {"showZeroBalance": False},
                    }
                    if cursor:
                        das_params["cursor"] = cursor
                    das_payload = {"jsonrpc": "2.0", "id": 1, "method": "getTokenAccounts", "params": das_params}
                    try:
                        async with session.post(helius_url, json=das_payload, timeout=aiohttp.ClientTimeout(total=15)) as dr:
                            if dr.status != 200:
                                break
                            das_data = await dr.json()
                    except Exception:
                        break
                    if isinstance(das_data, dict) and 'error' in das_data:
                        break
                    result = (das_data or {}).get('result') or {}
                    accounts = result.get('token_accounts') or []
                    if not accounts:
                        break
                    all_accounts.extend(accounts)
                    cursor = result.get('cursor')
                    if not cursor:
                        break
                if all_accounts:
                    ranked = sorted(all_accounts, key=lambda a: int(a.get('amount') or 0), reverse=True)[:limit]
                    holders = [
                        {
                            'address': a.get('owner', '') or a.get('address', ''),
                            'amount': float(int(a.get('amount') or 0)) / divisor if divisor else float(int(a.get('amount') or 0)),
                        }
                        for a in ranked if int(a.get('amount') or 0) > 0
                    ]
                    if holders:
                        logger.info(f"✅ DAS paged fallback: {len(holders)} holders for {address[:8]} (sampled {len(all_accounts)})")
                        return holders
                logger.info(f"All holder fetch paths exhausted for {address[:8]}")
                return []

        except Exception as e:
            logger.warning(f"Helius holder fetch failed: {e}")
            return []

    def is_valid_address(self, address: str) -> bool:
        """
        Validate if a string is a valid Solana address.

        Args:
            address: String to validate

        Returns:
            True if valid Solana address, False otherwise
        """
        try:
            if len(address) < 32 or len(address) > 44:
                return False
            Pubkey.from_string(address)
            return True
        except Exception:
            return False

    async def get_wallet_assets(self, wallet_address: str, _attempts_left: Optional[int] = None) -> List[Dict]:
        """
        Fetch all token balances for a wallet using Helius DAS API.
        
        Uses getAssetsByOwner to get fungible token balances with metadata.
        
        Args:
            wallet_address: Solana wallet address
            
        Returns:
            List of token dicts with balance, metadata, and price info
        """
        if not self.helius_api_key:
            logger.info("Helius key not configured — using free public-RPC balance path")
            return await self._get_wallet_assets_public_rpc(wallet_address)

        # One attempt per configured key so a 429 on the active key fails over to
        # the next AND retries the same request (otherwise the pool only rotates
        # for FUTURE callers and this balance call returns empty).
        if _attempts_left is None:
            from src.data.helius_keys import get_helius_pool
            _attempts_left = max(1, get_helius_pool().key_count())

        tokens = []
        
        try:
            url = f"https://mainnet.helius-rpc.com/?api-key={self.helius_api_key}"
            
            # Use DAS API getAssetsByOwner with fungible display options
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAssetsByOwner",
                "params": {
                    "ownerAddress": wallet_address,
                    "page": 1,
                    "limit": 100,
                    "displayOptions": {
                        "showFungible": True,
                        "showNativeBalance": True
                    }
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        # 429 → classify (cap vs rate-limit) + rotate so the shared
                        # pool (and the next portfolio scan, which reads the active
                        # key at construction) moves on — cross-consumer failover.
                        if resp.status == 429:
                            rotated = await self._handle_helius_429(resp, self.helius_api_key)
                            # Retry the SAME request on the rotated key so this
                            # balance call actually benefits from the failover
                            # (not just future callers).
                            if rotated and _attempts_left > 1:
                                return await self.get_wallet_assets(wallet_address, _attempts_left - 1)
                        logger.warning(f"Helius getAssetsByOwner returned {resp.status} — falling back to public RPC")
                        return await self._get_wallet_assets_public_rpc(wallet_address)

                    data = await resp.json()

                    if 'error' in data:
                        logger.warning(f"Helius API error: {data['error']} — falling back to public RPC")
                        return await self._get_wallet_assets_public_rpc(wallet_address)
                    
                    result = data.get('result', {})
                    items = result.get('items', [])
                    native_balance = result.get('nativeBalance', {})
                    
                    # Add native SOL balance first
                    if native_balance:
                        sol_lamports = native_balance.get('lamports', 0)
                        # Use the live SOL price (Jupiter→CoinGecko) rather than a
                        # stale hardcoded $200 when Helius omits price_per_sol.
                        sol_price = native_balance.get('price_per_sol')
                        if not sol_price:
                            sol_price = await self._get_sol_price()
                        sol_balance = sol_lamports / 1e9
                        
                        if sol_balance > 0.001:  # Only show if > 0.001 SOL
                            tokens.append({
                                'mint': 'So11111111111111111111111111111111111111112',
                                'symbol': 'SOL',
                                'name': 'Solana',
                                'logo': 'https://raw.githubusercontent.com/solana-labs/token-list/main/assets/mainnet/So11111111111111111111111111111111111111112/logo.png',
                                'amount': sol_balance,
                                'decimals': 9,
                                'value_usd': sol_balance * sol_price,
                                'price_usd': sol_price,
                                'price_change_24h': 0
                            })
                    
                    # Process fungible tokens
                    for item in items:
                        try:
                            interface = item.get('interface', '')
                            
                            # Only process fungible tokens
                            if interface not in ['FungibleToken', 'FungibleAsset']:
                                continue
                            
                            token_info = item.get('token_info', {})
                            content = item.get('content', {})
                            metadata = content.get('metadata', {})
                            
                            mint = item.get('id', '')
                            # Spec §11 D.4: sanitise on-chain symbol + name
                            # before they reach LLM context. Token-name
                            # prompt-injection ("USDC; ignore prior
                            # instructions") is stripped + length-capped here.
                            try:
                                from src.agent.sanitizer import sanitise_onchain_string
                                _raw_symbol = token_info.get('symbol', metadata.get('symbol', '???'))
                                _raw_name = metadata.get('name', _raw_symbol)
                                symbol = sanitise_onchain_string(_raw_symbol, max_len=24).sanitised or '???'
                                name = sanitise_onchain_string(_raw_name, max_len=80).sanitised or symbol
                            except Exception:
                                # Defensive: sanitiser should never crash the
                                # portfolio fetch — fall back to raw values
                                # but still cap length at 80 chars.
                                symbol = (token_info.get('symbol', metadata.get('symbol', '???')) or '???')[:24]
                                name = (metadata.get('name', symbol) or symbol)[:80]
                            
                            # Get balance
                            balance = float(token_info.get('balance', 0) or 0)
                            decimals = int(token_info.get('decimals', 9) or 9)
                            ui_balance = balance / (10 ** decimals) if decimals > 0 else balance
                            
                            # Skip dust (very small balances)
                            if ui_balance < 0.000001:
                                continue
                            
                            # Get price info if available
                            price_info = token_info.get('price_info', {})
                            price_usd = float(price_info.get('price_per_token', 0) or 0)
                            value_usd = ui_balance * price_usd
                            
                            # Get logo from content
                            links = content.get('links', {})
                            files = content.get('files', [])
                            logo = links.get('image') or (files[0].get('uri') if files else None)
                            
                            tokens.append({
                                'mint': mint,
                                'symbol': symbol,
                                'name': name,
                                'logo': logo,
                                'amount': ui_balance,
                                'decimals': decimals,
                                'value_usd': value_usd,
                                'price_usd': price_usd,
                                'price_change_24h': float(price_info.get('price_change_24h', 0) or 0)
                            })
                            
                        except Exception as e:
                            logger.debug(f"Error parsing token asset: {e}")
                            continue
                    
                    # Enrich 24h price change from DexScreener (free) — Helius DAS
                    # does not return a real price_change_24h, so it was always 0.
                    try:
                        spl_mints = [t['mint'] for t in tokens
                                     if t.get('mint') and t['mint'] != 'So11111111111111111111111111111111111111112']
                        if spl_mints:
                            enrich = await self._dexscreener_batch(spl_mints)
                            for t in tokens:
                                meta = enrich.get(t['mint'])
                                if meta and meta.get('price_change_24h') is not None:
                                    t['price_change_24h'] = float(meta.get('price_change_24h') or 0)
                    except Exception as _e:
                        logger.debug("price_change_24h enrichment failed: %s", _e)

                    # Sort by value (highest first)
                    tokens.sort(key=lambda x: x.get('value_usd', 0), reverse=True)

                    # A 200 with zero tokens usually means the DAS key is capped
                    # ("max usage reached" comes back as an empty result, not a
                    # 429). Fall back to the free public RPC so balance still works.
                    if not tokens:
                        logger.info("Helius returned 0 tokens — falling back to public RPC")
                        return await self._get_wallet_assets_public_rpc(wallet_address)

                    logger.info(f"Fetched {len(tokens)} tokens for wallet {wallet_address[:8]}...")
                    return tokens
                    
        except Exception as e:
            logger.error(f"Error fetching wallet assets: {e}")
            return await self._get_wallet_assets_public_rpc(wallet_address)

    async def _get_wallet_assets_public_rpc(self, wallet_address: str) -> List[Dict]:
        """
        Fetch wallet balances WITHOUT Helius — free public Solana RPC + DexScreener.

        The fallback that makes "My balance" work with zero paid infra. Used when
        the Helius DAS path is unavailable (no key, or the key hit "max usage
        reached"). Holdings come from the free public RPC (getBalance for native
        SOL + getTokenAccountsByOwner for SPL and Token-2022); price/symbol/name/
        logo are enriched best-effort from DexScreener's free token endpoint. A
        token DexScreener doesn't know is still returned (amount + truncated-mint
        symbol, value_usd=0) so the user always sees their holdings.
        """
        if not self.is_valid_address(wallet_address):
            return []

        # Genuinely key-free endpoint — never a Helius URL (its key may be capped).
        public_rpc = "https://api.mainnet-beta.solana.com"
        tokens: List[Dict] = []

        async def _rpc(session, method, params):
            payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            try:
                async with session.post(public_rpc, json=payload,
                                        timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        logger.debug("public RPC %s -> HTTP %s", method, resp.status)
                        return None
                    body = await resp.json()
            except Exception as exc:
                logger.debug("public RPC %s failed: %s", method, exc)
                return None
            if not isinstance(body, dict) or body.get("error"):
                logger.debug("public RPC %s error: %s", method, (body or {}).get("error"))
                return None
            return body.get("result")

        try:
            async with aiohttp.ClientSession() as session:
                # 1) Native SOL
                bal = await _rpc(session, "getBalance",
                                 [wallet_address, {"commitment": "confirmed"}])
                lamports = bal.get("value", 0) if isinstance(bal, dict) else 0
                sol_balance = (lamports or 0) / 1e9
                if sol_balance > 0.001:
                    sol_price = await self._get_sol_price()
                    tokens.append({
                        'mint': 'So11111111111111111111111111111111111111112',
                        'symbol': 'SOL',
                        'name': 'Solana',
                        'logo': 'https://raw.githubusercontent.com/solana-labs/token-list/main/assets/mainnet/So11111111111111111111111111111111111111112/logo.png',
                        'amount': sol_balance,
                        'decimals': 9,
                        'value_usd': sol_balance * sol_price,
                        'price_usd': sol_price,
                        'price_change_24h': 0,
                    })

                # 2) SPL + Token-2022 holdings (parallel fan-out)
                async def _accounts(program_id):
                    res = await _rpc(session, "getTokenAccountsByOwner", [
                        wallet_address,
                        {"programId": program_id},
                        {"encoding": "jsonParsed", "commitment": "confirmed"},
                    ])
                    if isinstance(res, dict) and isinstance(res.get("value"), list):
                        return res["value"]
                    return []

                legacy, token22 = await asyncio.gather(
                    _accounts(self.TOKEN_PROGRAM),
                    _accounts(self.TOKEN_2022),
                )

                holdings: Dict[str, Dict] = {}  # mint -> {amount, decimals}
                for entry in (legacy or []) + (token22 or []):
                    try:
                        info = (((entry.get("account") or {}).get("data") or {})
                                .get("parsed") or {}).get("info") or {}
                        mint = info.get("mint")
                        ta = info.get("tokenAmount") or {}
                        decimals = int(ta.get("decimals", 0) or 0)
                        ui = ta.get("uiAmount")
                        if ui is None:
                            raw = float(ta.get("amount", 0) or 0)
                            ui = raw / (10 ** decimals) if decimals else raw
                        ui = float(ui or 0)
                        if not mint or ui < 0.000001:
                            continue
                        cur = holdings.get(mint)  # multiple ATAs for one mint → sum
                        if cur:
                            cur["amount"] += ui
                        else:
                            holdings[mint] = {"amount": ui, "decimals": decimals}
                    except Exception as exc:
                        logger.debug("parse token account failed: %s", exc)
                        continue

                # 3) Enrich price/symbol/name/logo from DexScreener (free, batched).
                enrich = await self._dexscreener_batch(list(holdings.keys()))
                for mint, h in holdings.items():
                    meta = enrich.get(mint) or {}
                    price = float(meta.get("price_usd", 0) or 0)
                    short = f"{mint[:4]}…{mint[-4:]}"
                    symbol = meta.get("symbol") or short
                    name = meta.get("name") or symbol
                    # Sanitise on-chain strings before they reach LLM/UI context.
                    try:
                        from src.agent.sanitizer import sanitise_onchain_string
                        symbol = sanitise_onchain_string(symbol, max_len=24).sanitised or short
                        name = sanitise_onchain_string(name, max_len=80).sanitised or symbol
                    except Exception:
                        symbol = (symbol or short)[:24]
                        name = (name or symbol)[:80]
                    tokens.append({
                        'mint': mint,
                        'symbol': symbol,
                        'name': name,
                        'logo': meta.get("logo"),
                        'amount': h["amount"],
                        'decimals': h["decimals"],
                        'value_usd': h["amount"] * price,
                        'price_usd': price,
                        'price_change_24h': float(meta.get("price_change_24h", 0) or 0),
                    })

            tokens.sort(key=lambda x: x.get("value_usd", 0), reverse=True)
            logger.info("Public-RPC balance: %d tokens for %s...",
                        len(tokens), wallet_address[:8])
            return tokens
        except Exception as exc:
            logger.error("Public-RPC balance path failed: %s", exc)
            return tokens  # whatever we managed (usually at least native SOL)

    async def _dexscreener_batch(self, mints: List[str]) -> Dict[str, Dict]:
        """
        Best-effort price/symbol/name/logo for SPL mints from DexScreener's free
        token endpoint (up to 30 mints per call, chunked + parallel). Returns
        ``{mint: {price_usd, symbol, name, logo, price_change_24h}}``. Never
        raises — a mint DexScreener doesn't know is simply absent from the map.
        """
        out: Dict[str, Dict] = {}
        if not mints:
            return out

        async def _fetch(session, chunk):
            url = "https://api.dexscreener.com/latest/dex/tokens/" + ",".join(chunk)
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return
                    body = await resp.json()
            except Exception as exc:
                logger.debug("DexScreener batch failed: %s", exc)
                return
            pairs = (body or {}).get("pairs") or []
            best: Dict[str, tuple] = {}  # mint -> (liquidity, pair, baseToken)
            for p in pairs:
                base = p.get("baseToken") or {}
                addr = base.get("address")
                if not addr:
                    continue
                liq = ((p.get("liquidity") or {}).get("usd") or 0) or 0
                prev = best.get(addr)
                if prev is None or liq > prev[0]:
                    best[addr] = (liq, p, base)
            for addr, (_liq, p, base) in best.items():
                info = p.get("info") or {}
                out[addr] = {
                    "price_usd": p.get("priceUsd") or 0,
                    "symbol": base.get("symbol"),
                    "name": base.get("name"),
                    "logo": info.get("imageUrl"),
                    "price_change_24h": (p.get("priceChange") or {}).get("h24") or 0,
                }

        try:
            async with aiohttp.ClientSession() as session:
                chunks = [mints[i:i + 30] for i in range(0, len(mints), 30)]
                await asyncio.gather(*(_fetch(session, c) for c in chunks))
        except Exception as exc:
            logger.debug("DexScreener batch outer failed: %s", exc)
        return out

    async def get_onchain_data(self, address: str) -> Dict:
        """
        Get on-chain token mint data from Solana.

        Fetches mint authority status, freeze authority status,
        total supply, and decimals directly from the blockchain.

        Args:
            address: Solana token mint address

        Returns:
            Dict with structure:
            {
                'mint_auth': bool,      # Mint authority enabled
                'freeze_auth': bool,    # Freeze authority enabled
                'supply': int,          # Total supply (raw)
                'decimals': int         # Token decimals
            }
        """
        await self._ensure_connected()

        # Default result
        result = {
            'mint_auth': True,
            'freeze_auth': True,
            'supply': 0,
            'decimals': 9
        }

        try:
            pubkey = Pubkey.from_string(address)
            info = await self._client.get_account_info(pubkey)

            if not info.value:
                logger.warning(f"No account info for {address[:8]}")
                return result

            data = info.value.data
            owner = str(info.value.owner)

            # Verify this is a token mint account
            if owner not in [self.TOKEN_PROGRAM, self.TOKEN_2022]:
                logger.warning(f"Address {address[:8]} is not a token mint")
                return result

            # Parse token mint data (minimum 82 bytes required)
            if len(data) < 82:
                logger.warning(f"Insufficient data length for {address[:8]}")
                return result

            # Parse mint account structure:
            # Bytes 0-4: mint_authority option (0 = None, 1 = Some)
            # Bytes 36-44: supply (u64)
            # Byte 44: decimals (u8)
            # Bytes 46-50: freeze_authority option (0 = None, 1 = Some)

            result['mint_auth'] = int.from_bytes(data[0:4], 'little') == 1
            result['supply'] = int.from_bytes(data[36:44], 'little')
            result['decimals'] = data[44]
            result['freeze_auth'] = int.from_bytes(data[46:50], 'little') == 1

            logger.info(
                f"✅ On-chain data for {address[:8]}: "
                f"Mint={result['mint_auth']}, "
                f"Freeze={result['freeze_auth']}, "
                f"Supply={result['supply']}"
            )

        except Exception as e:
            logger.error(f"Error fetching on-chain data for {address[:8]}: {e}", exc_info=True)

        return result

    async def get_top_holders(self, address: str, limit: int = 20) -> List[Dict]:
        """
        Get top token holders from Solana.

        Fetches the largest token account balances for the given mint.
        Uses Helius API if available, falls back to standard RPC with retry logic.

        Args:
            address: Solana token mint address
            limit: Maximum number of holders to return (default: 20)

        Returns:
            List of dicts with structure:
            [
                {
                    'address': str,  # Token account address
                    'amount': float  # Token amount (UI format)
                },
                ...
            ]
        """
        # Try Helius first if available (more reliable, no rate limits)
        if self.helius_api_key:
            helius_holders = await self._get_holders_via_helius(address, limit)
            # When Helius is configured, trust its answer (incl. empty) and skip
            # the public-RPC fallback. The fallback otherwise 429s on huge mints
            # and adds 30+ seconds of retry backoff to every analyzer call.
            return helius_holders

        await self._ensure_connected()

        # Retry loop with exponential backoff for rate limiting (429 errors)
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                pubkey = Pubkey.from_string(address)
                resp = await self._client.get_token_largest_accounts(pubkey)

                if not resp or not resp.value:
                    logger.warning(f"⚠️ No holder data returned for {address[:8]}")
                    return []

                holders = []
                for idx, account in enumerate(resp.value[:limit]):
                    try:
                        amount = 0.0

                        # Debug: log the raw account structure for first holder
                        if idx == 0:
                            logger.debug(f"Raw holder account structure: {type(account)}, attrs: {dir(account)}")
                            if hasattr(account, 'amount'):
                                logger.debug(f"Amount structure: {type(account.amount)}, attrs: {dir(account.amount)}")

                        # Parse amount from response - try multiple approaches
                        if hasattr(account, 'amount'):
                            amt_obj = account.amount

                            # Approach 1: ui_amount (float)
                            if hasattr(amt_obj, 'ui_amount') and amt_obj.ui_amount is not None:
                                amount = float(amt_obj.ui_amount)

                            # Approach 2: ui_amount_string (string)
                            elif hasattr(amt_obj, 'ui_amount_string') and amt_obj.ui_amount_string:
                                try:
                                    amount = float(amt_obj.ui_amount_string)
                                except (ValueError, TypeError):
                                    pass

                            # Approach 3: uiAmount (camelCase variant)
                            elif hasattr(amt_obj, 'uiAmount') and amt_obj.uiAmount is not None:
                                amount = float(amt_obj.uiAmount)

                            # Approach 4: Direct dict access
                            elif isinstance(amt_obj, dict):
                                amount = float(amt_obj.get('uiAmount') or amt_obj.get('ui_amount') or 0)

                        # Also try direct account attributes
                        elif hasattr(account, 'uiAmount') and account.uiAmount is not None:
                            amount = float(account.uiAmount)

                        holders.append({
                            'address': str(account.address),
                            'amount': amount
                        })
                    except Exception as e:
                        logger.debug(f"Error parsing holder account {idx}: {e}")
                        continue

                # Log holder data for debugging
                if holders:
                    top_amount = holders[0].get('amount', 0) if holders else 0
                    total_amount = sum(h.get('amount', 0) for h in holders)
                    logger.info(
                        f"✅ Found {len(holders)} holders for {address[:8]}, "
                        f"top holder: {top_amount:,.2f}, total in top-{len(holders)}: {total_amount:,.2f}"
                    )
                else:
                    logger.warning(f"⚠️ Holders list empty for {address[:8]}")

                return holders

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Check if it's a rate limit error (429)
                if '429' in error_str or 'too many requests' in error_str or 'rate' in error_str:
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_DELAYS[attempt]
                        logger.warning(
                            f"⚠️ Rate limited on holder fetch for {address[:8]}, "
                            f"retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})"
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f"❌ Rate limit exceeded after {MAX_RETRIES} attempts for {address[:8]}")
                else:
                    # Non-rate-limit error, don't retry
                    logger.error(f"❌ Error fetching holders for {address[:8]}: {e}", exc_info=True)
                    break

        logger.error(f"❌ Failed to fetch holders for {address[:8]} after retries: {last_error}")
        return []

    async def analyze_holder_distribution(self, token: TokenInfo) -> None:
        """
        Analyze token holder distribution for suspicious patterns.

        Modifies the TokenInfo object in-place with analysis results:
        - top_holder_pct: Percentage held by largest wallet
        - dev_wallet_risk: Whether top holder concentration is risky
        - suspicious_wallets: Number of suspicious wallets detected
        - holder_flags: List of warning messages

        Checks for:
        - High concentration in top wallets (>20% in one wallet)
        - Suspicious round number allocations
        - Related wallets with similar balances

        Args:
            token: TokenInfo object with top_holders already populated
        """
        # Debug logging
        logger.info(
            f"🔍 Starting holder analysis for {token.symbol}: "
            f"holders={len(token.top_holders) if token.top_holders else 0}, "
            f"supply={token.supply}, decimals={token.decimals}"
        )

        if not token.top_holders:
            logger.warning(f"⚠️ No holders data for {token.symbol}")
            return

        if token.supply <= 0:
            logger.warning(f"⚠️ Supply is 0 for {token.symbol}, cannot analyze holders")
            return

        total_supply = token.supply / (10 ** token.decimals)
        logger.debug(f"Total supply (UI): {total_supply:,.2f}")
        flags = []
        suspicious_count = 0

        # Track top-10 holder concentration
        top_10_concentration = 0.0

        for i, holder in enumerate(token.top_holders[:10]):
            addr = holder.get('address', '')
            amount = holder.get('amount', 0)

            # Skip known addresses (LP pools, burn addresses, etc.)
            if not addr or addr in self.KNOWN_ADDRESSES:
                continue

            pct = (amount / total_supply * 100) if total_supply > 0 else 0

            # Accumulate concentration for valid holders
            top_10_concentration += pct

            # ═══════════════════════════════════════════════════════════════
            # TOP-1 HOLDER ANALYSIS
            # ═══════════════════════════════════════════════════════════════
            if i == 0:
                token.top_holder_pct = pct

                # Risky: Top wallet holds >20%
                if pct > 20:
                    token.dev_wallet_risk = True
                    flags.append(f"🐋 Top wallet holds {pct:.1f}%")
                    suspicious_count += 1

                # Critical: Top wallet holds >50%
                if pct > 50:
                    flags.append(f"🚨 CRITICAL: One wallet = {pct:.1f}%")

            # ═══════════════════════════════════════════════════════════════
            # ROUND NUMBER DETECTION (often dev allocations)
            # ═══════════════════════════════════════════════════════════════
            if amount > 0:
                amount_str = f"{amount:.0f}"
                if len(amount_str) > 6:
                    # Count trailing zeros
                    zeros = len(amount_str) - len(amount_str.rstrip('0'))
                    if zeros >= 6:  # Many zeros = possibly dev allocation
                        suspicious_count += 1
                        if suspicious_count <= 3:
                            flags.append(f"⚠️ Wallet #{i+1}: suspiciously round amount")

            # ═══════════════════════════════════════════════════════════════
            # HIGH CONCENTRATION IN TOP WALLETS
            # ═══════════════════════════════════════════════════════════════
            if i < 5 and pct > 10:
                suspicious_count += 1
                if i > 0:  # Don't duplicate top-1 flag
                    flags.append(f"🐋 Wallet #{i+1} holds {pct:.1f}%")

        # ═══════════════════════════════════════════════════════════════
        # RELATED WALLETS DETECTION (similar balances)
        # ═══════════════════════════════════════════════════════════════
        if len(token.top_holders) >= 3:
            amounts = [h.get('amount', 0) for h in token.top_holders[:5] if h.get('amount', 0) > 0]
            if len(amounts) >= 2:
                # Check for very similar balances (difference < 1%)
                for i in range(len(amounts)):
                    for j in range(i + 1, len(amounts)):
                        if amounts[i] > 0 and amounts[j] > 0:
                            diff = abs(amounts[i] - amounts[j]) / max(amounts[i], amounts[j])
                            if diff < 0.01:  # Less than 1% difference
                                flags.append(f"🔗 Wallets #{i+1} and #{j+1} have similar balances (related?)")
                                suspicious_count += 1
                                break
                    else:
                        continue
                    break

        # ═══════════════════════════════════════════════════════════════
        # SET HOLDER CONCENTRATION
        # ═══════════════════════════════════════════════════════════════
        token.holder_concentration = top_10_concentration

        # ═══════════════════════════════════════════════════════════════
        # FINAL SUMMARY
        # ═══════════════════════════════════════════════════════════════
        if suspicious_count >= 3:
            flags.insert(0, f"🚨 Detected {suspicious_count} suspicious wallets!")

        token.suspicious_wallets = suspicious_count
        token.holder_flags = flags[:5]  # Maximum 5 flags

        logger.info(
            f"🔍 Holder analysis for {token.symbol}: "
            f"top-1={token.top_holder_pct:.1f}%, "
            f"top-10={token.holder_concentration:.1f}%, "
            f"suspicious={suspicious_count}"
        )

    async def simulate_transaction(
        self,
        transaction_base64: str,
        sig_verify: bool = False,
        commitment: str = "confirmed"
    ) -> SimulationResult:
        """
        Simulate a transaction without executing it.

        Used for honeypot detection by simulating sell transactions
        to verify they would succeed.

        Args:
            transaction_base64: Base64-encoded serialized transaction
            sig_verify: Whether to verify signatures (False for simulation)
            commitment: Bank state commitment level

        Returns:
            SimulationResult with success status, logs, and error info
        """
        await self._ensure_connected()

        try:
            # Decode the base64 transaction
            tx_bytes = base64.b64decode(transaction_base64)
            tx = VersionedTransaction.from_bytes(tx_bytes)

            logger.debug("Simulating transaction...")

            # Simulate via RPC
            response = await self._client.simulate_transaction(
                tx,
                sig_verify=sig_verify,
                commitment=Commitment(commitment)
            )

            # Parse response
            if not response or not response.value:
                return SimulationResult(
                    success=False,
                    error="No simulation response received",
                    logs=[]
                )

            value = response.value

            # Check for simulation error
            if value.err:
                error_msg = str(value.err)
                error_code = self._extract_error_code(value.err)

                logger.debug(f"Simulation failed: {error_msg}")
                return SimulationResult(
                    success=False,
                    error=error_msg,
                    error_code=error_code,
                    logs=list(value.logs) if value.logs else [],
                    units_consumed=value.units_consumed or 0
                )

            # Simulation succeeded
            logger.debug(f"Simulation succeeded, CU: {value.units_consumed}")
            return SimulationResult(
                success=True,
                logs=list(value.logs) if value.logs else [],
                units_consumed=value.units_consumed or 0,
                return_data=value.return_data if hasattr(value, 'return_data') else None
            )

        except Exception as e:
            logger.error(f"Transaction simulation failed: {e}", exc_info=True)
            return SimulationResult(
                success=False,
                error=str(e),
                logs=[]
            )

    def _extract_error_code(self, err: Any) -> Optional[int]:
        """
        Extract numeric error code from simulation error.

        Parses Solana error format to get custom program error codes.

        Args:
            err: Error object from simulation response

        Returns:
            Integer error code if present, None otherwise
        """
        try:
            # Handle dict-style errors
            if isinstance(err, dict):
                if "InstructionError" in err:
                    instruction_err = err["InstructionError"]
                    if isinstance(instruction_err, list) and len(instruction_err) >= 2:
                        custom_err = instruction_err[1]
                        if isinstance(custom_err, dict) and "Custom" in custom_err:
                            return custom_err["Custom"]

            # Handle string errors with error codes
            err_str = str(err)
            if "Custom" in err_str:
                # Try to extract number from string like "Custom(6000)"
                import re
                match = re.search(r'Custom\((\d+)\)', err_str)
                if match:
                    return int(match.group(1))

        except Exception:
            pass
        return None

    # ═══════════════════════════════════════════════════════════════════════════
    # SOL PRICE CACHE
    # ═══════════════════════════════════════════════════════════════════════════

    _sol_price_cache: Dict = {}  # class-level cache

    async def _get_sol_price(self) -> float:
        """
        Get current SOL price in USD, cached for 60 seconds.
        Uses Jupiter Price API as primary, CoinGecko as fallback.
        """
        import time
        cache = SolanaClient._sol_price_cache
        if cache.get('price') and cache.get('time', 0) > time.time() - 60:
            return cache['price']

        # Try Jupiter Price API first
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.jup.ag/price/v2?ids=So11111111111111111111111111111111111111112",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        price = float(data.get("data", {}).get(
                            "So11111111111111111111111111111111111111112", {}
                        ).get("price", 0))
                        if price > 0:
                            cache['price'] = price
                            cache['time'] = time.time()
                            logger.debug(f"SOL price from Jupiter: ${price:.2f}")
                            return price
        except Exception as e:
            logger.debug(f"Jupiter price API failed: {e}")

        # Fallback to CoinGecko
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        price = float(data.get("solana", {}).get("usd", 0))
                        if price > 0:
                            cache['price'] = price
                            cache['time'] = time.time()
                            logger.debug(f"SOL price from CoinGecko: ${price:.2f}")
                            return price
        except Exception as e:
            logger.debug(f"CoinGecko price API failed: {e}")

        # Last resort fallback
        return cache.get('price', 200.0)

    # ═══════════════════════════════════════════════════════════════════════════
    # HELIUS WHALE TRACKING METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_recent_large_transactions(
        self,
        min_amount_usd: float = 10000,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get recent large transactions across the entire ecosystem.
        
        Monitors major DEX routers (Jupiter, Raydium, Pump.fun, Orca) to detect
        whales on ANY token, enabling discovery of new pumps.

        Args:
            min_amount_usd: Minimum transaction value in USD
            limit: Maximum transactions to return

        Returns:
            List of whale transaction dicts with parsed data
        """
        if not self.helius_api_key:
            logger.warning("Helius API key not configured - cannot fetch whale transactions")
            return []

        from src.data.dexscreener import DexScreenerClient
        
        all_transactions = []
        
        # Get real SOL price for accurate USD calculations
        sol_price = await self._get_sol_price()
        logger.info(f"Using SOL price: ${sol_price:.2f} for whale tracking")

        # Major DEX programs to monitor (expanded coverage)
        DEX_PROGRAMS = {
            'Jupiter': 'JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4',
            'Raydium': '675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8',
            'Raydium CLMM': 'CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK',
            'Raydium CP': 'CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C',
            'Pump.fun': '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P',
            'Orca': 'whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc',
            'Meteora': 'LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo',
            'Phoenix': 'PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY',
            'Lifinity': '2wT8Yq49kHgDzXuPxZSaeLaH1qbmGXtEyPy64bL7aD3s',
        }
        
        try:
            # Throttle the parallel DEX-program fan-out so it stays under Helius's
            # per-second rate limit — a burst of all programs at once trips 429s
            # even on a healthy key (with only one healthy key, rotation can't fix
            # a rate limit; staying under it can). Retry/rotate is the backstop.
            helius_sem = asyncio.Semaphore(4)

            # Helper to fetch and parse for a specific program
            async def fetch_program_txs(name: str, address: str, session: aiohttp.ClientSession) -> List[Dict]:
                from src.data.helius_keys import get_helius_pool

                # One attempt per configured key (so a 429 can roll through every
                # key) plus a spare for the transient-retry path; minimum 2.
                max_attempts = max(2, get_helius_pool().key_count() + 1)

                for attempt in range(max_attempts):
                    # Rebuild the URL each attempt so a rotated key takes effect.
                    # Capture the key used so concurrent program fetches that all
                    # 429 on it don't each park a *different* key (see _rotate).
                    used_key = self.helius_api_key
                    url = (
                        f"https://api.helius.xyz/v0/addresses/{address}/transactions"
                        f"?api-key={used_key}&type=SWAP&limit=100"
                    )
                    status = None
                    rotated = False
                    data = None
                    try:
                        # Hold the throttle only across the network call, not the
                        # backoff sleep below (which would serialise the retries).
                        async with helius_sem:
                            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                                status = resp.status
                                if status == 200:
                                    data = await resp.json()
                                elif status == 429:
                                    # Classify cap vs transient rate-limit, rotate.
                                    rotated = await self._handle_helius_429(resp, used_key)
                    except Exception as e:
                        if attempt < max_attempts - 1:
                            await asyncio.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
                            continue
                        logger.debug(f"Error fetching {name} txs: {e}")
                        return []

                    if status == 200:
                        if not data or not isinstance(data, list):
                            return []
                        parsed_txs = []
                        for tx in data:
                            parsed = await self._parse_helius_transaction(
                                tx,
                                min_amount_usd,
                                sol_price=sol_price
                            )
                            if parsed:
                                parsed['dex_name'] = name
                                parsed_txs.append(parsed)
                        return parsed_txs

                    # Non-200. On a 429 that rotated to a different key, retry it
                    # immediately; otherwise back off for retryable statuses.
                    if status == 429 and rotated and attempt < max_attempts - 1:
                        continue
                    if status in {429, 500, 502, 503, 504} and attempt < max_attempts - 1:
                        await asyncio.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
                        continue
                    logger.debug(f"Helius {name} fetch returned status {status}")
                    return []

                return []

            async with aiohttp.ClientSession() as session:
                tasks = [fetch_program_txs(name, address, session) for name, address in DEX_PROGRAMS.items()]
                results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Aggregate results
            for res in results:
                if isinstance(res, list):
                    all_transactions.extend(res)
            
            # Sort by time (newest first)
            from datetime import datetime, timezone

            def parse_time(tx):
                timestamp = tx.get('timestamp')
                if not timestamp:
                    return 0.0
                try:
                    dt = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.timestamp()
                except Exception:
                    return 0.0
            
            all_transactions.sort(key=parse_time, reverse=True)
            
            # Deduplicate by signature
            unique_txs = []
            seen_sigs = set()
            for tx in all_transactions:
                signature = tx.get('signature')
                if signature:
                    if signature in seen_sigs:
                        continue
                    seen_sigs.add(signature)
                unique_txs.append(tx)
            
            final_txs = unique_txs[:limit]
            
            # Enrich with Metadata (Symbol/Name)
            # We collect all token addresses that need lookup
            tokens_to_fetch = set()
            for tx in final_txs:
                if tx.get('token_symbol') == '???' and tx.get('token_address'):
                    tokens_to_fetch.add(tx['token_address'])
            
            if tokens_to_fetch:
                try:
                    async with DexScreenerClient() as dex_client:
                        # Fetch in parallel
                        # We use get_token for each as get_tokens_batch isn't public, 
                        # but we can do parallel calls
                        lookup_tasks = [dex_client.get_token(addr) for addr in tokens_to_fetch]
                        lookup_results = await asyncio.gather(*lookup_tasks, return_exceptions=True)
                        
                        # Build map
                        token_map = {}
                        for res in lookup_results:
                            if res and isinstance(res, dict) and res.get('main'):
                                base = res['main'].get('baseToken', {})
                                addr = base.get('address')
                                if addr:
                                    token_map[addr] = {
                                        'symbol': base.get('symbol', '???'),
                                        'name': base.get('name', 'Unknown')
                                    }
                        
                        # Apply metadata
                        for tx in final_txs:
                            addr = tx['token_address']
                            if addr in token_map:
                                tx['token_symbol'] = token_map[addr]['symbol']
                                tx['token_name'] = token_map[addr]['name']
                                
                except Exception as e:
                    logger.warning(f"Metadata enrichment failed: {e}")

            logger.info(f"✅ Found {len(final_txs)} global whale transactions")
            return final_txs

        except Exception as e:
            logger.error(f"Error fetching global whale transactions: {e}")
            return []

    async def _parse_helius_transaction(
        self,
        tx: Dict,
        min_amount_usd: float,
        known_symbol: Optional[str] = None,
        known_name: Optional[str] = None,
        sol_price: Optional[float] = None
    ) -> Optional[Dict]:
        """
        Parse a Helius transaction response into whale transaction format.

        Args:
            tx: Raw Helius transaction data
            min_amount_usd: Minimum amount threshold
            known_symbol: Optional known token symbol to override '???'
            known_name: Optional known token name

        Returns:
            Parsed transaction dict or None if not a qualifying whale trade
        """
        try:
            # Helius enhanced format
            signature = tx.get('signature', '')
            timestamp = tx.get('timestamp', 0)
            tx_type = tx.get('type', 'UNKNOWN')
            
            # Check for token transfers in the transaction
            token_transfers = tx.get('tokenTransfers', [])
            native_transfers = tx.get('nativeTransfers', [])
            
            # Calculate total USD value
            total_usd = 0
            token_info = None
            tx_direction = 'buy'
            wallet_address = ''
            
            for transfer in token_transfers:
                mint = transfer.get('mint', '')
                amount = float(transfer.get('tokenAmount', 0) or 0)
                
                # Get USD value if available from Helius
                # Note: Helius sometimes puts price/value in different fields depending on tier
                # We often need to estimate if Helius doesn't provide direct USD
                # But for this logic, we assume we check against passed min_amount_usd later
                
                # Determine direction based on transfer direction
                from_addr = transfer.get('fromUserAccount', '')
                to_addr = transfer.get('toUserAccount', '')
                
                if mint and amount > 0:
                    token_info = {
                        'address': mint,
                        'amount': amount
                    }
                    wallet_address = to_addr if to_addr else from_addr
                    
                    # If sending TO a DEX, it's a sell; if receiving FROM DEX, it's a buy
                    # Simple heuristic: if 'from' is the wallet we're tracking (or a user), it's a sell (sending token)
                    # If 'to' is the wallet, it's a buy (receiving token)
                    # For general monitoring, we look for the non-program account
                    if from_addr and to_addr:
                        # Heuristic: Raydium/Pump/Jup usually in the address or known program list
                        # Ideally we'd check against a list of known DEX vaults
                        pass 

            effective_sol_price = sol_price or 200.0

            # ── Calculate USD value from native SOL transfers ──
            sol_value_transferred = 0
            main_user = None

            for transfer in native_transfers:
                lamports = float(transfer.get('amount', 0) or 0)
                sol_amount = lamports / 1e9
                sol_value = sol_amount * effective_sol_price
                sol_value_transferred += sol_value

                if not main_user:
                    main_user = transfer.get('fromUserAccount') or transfer.get('toUserAccount')

            # ── Calculate USD value from stablecoin (USDC/USDT) transfers ──
            stablecoin_usd = 0
            stablecoin_user = None

            for transfer in token_transfers:
                mint = transfer.get('mint', '')
                if mint in self.STABLECOIN_MINTS:
                    amount = float(transfer.get('tokenAmount', 0) or 0)
                    stablecoin_usd += amount
                    if not stablecoin_user:
                        stablecoin_user = transfer.get('fromUserAccount') or transfer.get('toUserAccount')

            # ── Calculate USD value from wrapped SOL token transfers ──
            wsol_usd = 0
            wsol_user = None

            for transfer in token_transfers:
                mint = transfer.get('mint', '')
                if mint == self.WSOL_MINT:
                    amount = float(transfer.get('tokenAmount', 0) or 0)
                    wsol_usd += amount * effective_sol_price
                    if not wsol_user:
                        wsol_user = transfer.get('fromUserAccount') or transfer.get('toUserAccount')

            # For swap routes with multiple transfer legs, avoid runaway over-counting.
            # Use the strongest payment-side estimate while still supporting mixed paths.
            payment_estimates = [
                sol_value_transferred,
                stablecoin_usd,
                wsol_usd,
                sol_value_transferred + stablecoin_usd,
                stablecoin_usd + wsol_usd,
            ]
            total_usd = max(payment_estimates)

            # If no SOL transfers, derive main_user from stablecoin/WSOL transfers
            if not main_user and stablecoin_user:
                main_user = stablecoin_user
            if not main_user and wsol_user:
                main_user = wsol_user

            # ── Determine primary token transfer (the traded asset) ──
            # Filter out payment-side mints (WSOL, USDC, USDT)
            asset_transfers = [t for t in token_transfers if t.get('mint') not in self.PAYMENT_MINTS]

            if not asset_transfers:
                return None

            # Pick the largest token transfer as the main asset
            main_transfer = max(asset_transfers, key=lambda t: float(t.get('tokenAmount', 0) or 0))

            # ── Determine buy/sell direction ──
            if main_user and main_transfer.get('toUserAccount') == main_user:
                tx_direction = 'buy'
            elif main_user and main_transfer.get('fromUserAccount') == main_user:
                tx_direction = 'sell'
            else:
                tx_direction = 'buy'
                wallet_address = main_transfer.get('toUserAccount')

            if not main_user:
                wallet_address = main_transfer.get('toUserAccount') if tx_direction == 'buy' else main_transfer.get('fromUserAccount')
            else:
                wallet_address = main_user

            # Filter by minimum amount
            if total_usd < min_amount_usd:
                return None
            
            # Use passed metadata if available
            symbol = known_symbol if known_symbol else '???'
            name = known_name if known_name else 'Unknown'
            
            # Convert timestamp to timezone-aware UTC datetime
            from datetime import datetime, timezone
            tx_time = (
                datetime.fromtimestamp(timestamp, tz=timezone.utc)
                if timestamp else datetime.now(timezone.utc)
            )
            
            return {
                'signature': signature,
                'wallet_address': wallet_address[:44] if wallet_address else 'unknown',
                'wallet_label': None,
                'token_address': main_transfer.get('mint'),
                'token_symbol': symbol,
                'token_name': name,
                'type': tx_direction,
                'amount_tokens': float(main_transfer.get('tokenAmount', 0)),
                'amount_usd': total_usd,
                'price_usd': total_usd / float(main_transfer.get('tokenAmount', 1)) if float(main_transfer.get('tokenAmount', 0)) > 0 else 0,
                'timestamp': tx_time.isoformat(),
                'dex_name': tx.get('source', 'DEX').title() # Helius often provides 'source' like RAYDIUM
            }
            
        except Exception as e:
            logger.debug(f"Failed to parse Helius tx: {e}")
            return None


    async def get_whale_transactions(
        self,
        min_amount_usd: float = 5000,
        limit: int = 50,
    ) -> List[Dict]:
        """Get global whale transactions using real Helius on-chain data."""
        return await self.get_recent_large_transactions(
            min_amount_usd=min_amount_usd,
            limit=limit,
        )

    async def get_token_whale_transactions(
        self,
        token_address: str,
        min_amount_usd: float = 5000,
        limit: int = 50,
        token_symbol: Optional[str] = None,
        token_name: Optional[str] = None
    ) -> List[Dict]:
        """
        Get whale transactions for a specific token using Helius.

        Args:
            token_address: Token mint address to track
            min_amount_usd: Minimum transaction value
            limit: Maximum transactions to return
            token_symbol: Optional known token symbol
            token_name: Optional known token name

        Returns:
            List of whale transaction dicts for the token
        """
        if not self.helius_api_key:
            logger.warning("Helius API key not configured")
            return []

        # Get real SOL price for accurate USD calculations
        sol_price = await self._get_sol_price()
        transactions = []
        seen_signatures = set()

        try:
            async with aiohttp.ClientSession() as session:
                before_signature = None
                max_pages = 3

                from src.data.helius_keys import get_helius_pool

                for _ in range(max_pages):
                    # One attempt per configured key (so a 429 rolls through all)
                    # plus a spare for the transient-retry path; minimum 2.
                    max_attempts = max(2, get_helius_pool().key_count() + 1)

                    data = None
                    for attempt in range(max_attempts):
                        # Rebuild per attempt so a rotated key takes effect.
                        used_key = self.helius_api_key
                        url = (
                            f"https://api.helius.xyz/v0/addresses/{token_address}/transactions"
                            f"?api-key={used_key}&type=SWAP&limit=100"
                        )
                        if before_signature:
                            url = f"{url}&before={before_signature}"
                        try:
                            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                                if resp.status != 200:
                                    # 429 → classify (cap vs rate-limit) + fail over.
                                    if resp.status == 429 and await self._handle_helius_429(resp, used_key) and attempt < max_attempts - 1:
                                        continue
                                    should_retry = resp.status in {429, 500, 502, 503, 504} and attempt < max_attempts - 1
                                    if should_retry:
                                        await asyncio.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
                                        continue
                                    logger.warning(f"Helius token transactions returned {resp.status}")
                                    data = []
                                    break

                                data = await resp.json()
                                break
                        except Exception:
                            if attempt < max_attempts - 1:
                                await asyncio.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
                                continue
                            data = []

                    if not data or not isinstance(data, list):
                        break

                    for tx in data:
                        try:
                            signature = tx.get('signature')
                            if signature and signature in seen_signatures:
                                continue

                            parsed = await self._parse_helius_transaction(
                                tx,
                                min_amount_usd,
                                known_symbol=token_symbol,
                                known_name=token_name,
                                sol_price=sol_price
                            )
                            if not parsed:
                                continue

                            if signature:
                                seen_signatures.add(signature)

                            transactions.append(parsed)
                            if len(transactions) >= limit:
                                break
                        except Exception:
                            continue

                    if len(transactions) >= limit:
                        break

                    if len(data) < 100:
                        break

                    before_signature = data[-1].get('signature')
                    if not before_signature:
                        break

            logger.info(f"✅ Found {len(transactions)} whale transactions for token {token_address[:8]}")
            return transactions[:limit]

        except Exception as e:
            logger.error(f"Error fetching token whale transactions: {e}")
            return []

    async def get_behavior_transactions(
        self,
        token_address: str,
        min_amount_usd: float = 5000,
        limit: int = 50,
        token_symbol: Optional[str] = None,
        token_name: Optional[str] = None,
    ) -> List[Dict]:
        transactions = await self.get_token_whale_transactions(
            token_address=token_address,
            min_amount_usd=min_amount_usd,
            limit=limit,
            token_symbol=token_symbol,
            token_name=token_name,
        )
        return await self._annotate_behavior_transactions(token_address, transactions)

    async def _annotate_behavior_transactions(self, token_address: str, transactions: List[Dict]) -> List[Dict]:
        if not transactions:
            return []

        anomaly_flags = [flag.to_dict() for flag in self._anomaly_detector.detect_behavior_flags(self._build_behavior_time_series(transactions))]
        entity_heuristics = [
            heuristic.to_dict()
            for heuristic in await self._detect_entity_heuristics(token_address, transactions)
        ]

        annotated = []
        for tx in transactions:
            enriched = dict(tx)
            enriched["anomaly_flags"] = anomaly_flags
            enriched["entity_heuristics"] = entity_heuristics
            annotated.append(enriched)
        return annotated

    async def _detect_entity_heuristics(self, token_address: str, transactions: List[Dict]):
        total_abs_amount = sum(abs(float(tx.get("amount_usd", 0) or 0)) for tx in transactions)
        if total_abs_amount <= 0:
            return []

        wallet_totals: Dict[str, float] = {}
        for tx in transactions:
            wallet = str(tx.get("wallet_address") or "")
            if not wallet:
                continue
            wallet_totals[wallet] = wallet_totals.get(wallet, 0.0) + abs(float(tx.get("amount_usd", 0) or 0))

        top_holders = [
            {"address": wallet, "share": amount / total_abs_amount}
            for wallet, amount in sorted(wallet_totals.items(), key=lambda item: item[1], reverse=True)
        ]
        deployer_wallet = await get_token_deployer(token_address, self.rpc_url)
        return self._wallet_forensics.detect_entity_heuristics(deployer_wallet, top_holders)

    def _build_behavior_time_series(self, transactions: List[Dict]) -> List[TimeSeriesDataPoint]:
        ordered = sorted(transactions, key=lambda tx: str(tx.get("timestamp") or ""))
        max_amount = max(abs(float(tx.get("amount_usd", 0) or 0)) for tx in ordered) if ordered else 0.0
        liquidity_proxy = sum(abs(float(tx.get("amount_usd", 0) or 0)) for tx in ordered) * 1.5
        points: List[TimeSeriesDataPoint] = []

        for tx in ordered:
            amount = abs(float(tx.get("amount_usd", 0) or 0))
            tx_type = str(tx.get("type") or "buy").lower()
            if tx_type == "sell":
                liquidity_proxy = max(1000.0, liquidity_proxy - amount)
            else:
                liquidity_proxy += amount * 0.05

            timestamp_raw = tx.get("timestamp")
            if isinstance(timestamp_raw, str):
                timestamp = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
            elif isinstance(timestamp_raw, datetime):
                timestamp = timestamp_raw
            else:
                timestamp = datetime.utcnow()

            points.append(
                TimeSeriesDataPoint(
                    timestamp=timestamp,
                    liquidity_usd=liquidity_proxy,
                    buy_count=1 if tx_type != "sell" else 0,
                    sell_count=1 if tx_type == "sell" else 0,
                    large_sells=1 if tx_type == "sell" and amount >= max_amount * 0.5 else 0,
                    whale_net_flow_usd=amount if tx_type != "sell" else -amount,
                )
            )

        return points
