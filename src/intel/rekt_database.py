"""
REKT Database and Audit Database for the Intelligence Platform.

Data is sourced from public incident trackers and audit repositories
(DeFiLlama hacks, Rekt.news, public audit databases), supplemented
by our own curated records.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# Curated seed data for major incidents (will be supplemented by live API data)
KNOWN_REKT_INCIDENTS = [
    {
        "id": "ronin-2022",
        "name": "Ronin Bridge",
        "date": "2022-03-23",
        "amount_usd": 625_000_000,
        "protocol": "Ronin / Axie Infinity",
        "chains": ["Ethereum"],
        "attack_type": "Private Key Compromise",
        "description": "Attackers compromised 5/9 Ronin validator private keys (4 Sky Mavis + 1 Axie DAO) and drained 173,600 ETH and 25.5M USDC from the bridge.",
        "post_mortem_url": "https://roninblockchain.substack.com/p/back-to-basics-ronin-network-hack",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "poly-2021",
        "name": "Poly Network",
        "date": "2021-08-10",
        "amount_usd": 611_000_000,
        "protocol": "Poly Network",
        "chains": ["Ethereum", "BSC", "Polygon"],
        "attack_type": "Smart Contract Logic Flaw",
        "description": "Attacker exploited a cross-chain contract keeper privilege escalation to drain assets across three chains. Funds were returned by the attacker.",
        "post_mortem_url": "https://medium.com/poly-network-blog/poly-network-hacker-returned-all-remaining-user-funds-ad176e4cf7db",
        "funds_recovered": True,
        "severity": "CRITICAL",
    },
    {
        "id": "bnb-bridge-2022",
        "name": "BNB Bridge",
        "date": "2022-10-06",
        "amount_usd": 568_000_000,
        "protocol": "BNB Chain Bridge",
        "chains": ["BSC"],
        "attack_type": "Cryptographic Proof Forgery",
        "description": "Attacker forged Merkle proofs to mint 2M BNB from the BSC bridge. BSC validators paused the chain to contain the damage.",
        "post_mortem_url": "https://www.bnbchain.org/en/blog/bnb-chain-ecosystem-update",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "wormhole-2022",
        "name": "Wormhole Bridge",
        "date": "2022-02-02",
        "amount_usd": 320_000_000,
        "protocol": "Wormhole",
        "chains": ["Solana", "Ethereum"],
        "attack_type": "Signature Verification Bypass",
        "description": "Attacker bypassed signature verification in the Solana Wormhole contract to mint 120,000 wETH without collateral.",
        "post_mortem_url": "https://wormhole.com/news/wormhole-vulnerability-postmortem",
        "funds_recovered": True,
        "severity": "CRITICAL",
    },
    {
        "id": "nomad-2022",
        "name": "Nomad Bridge",
        "date": "2022-08-01",
        "amount_usd": 190_000_000,
        "protocol": "Nomad",
        "chains": ["Ethereum"],
        "attack_type": "Initialization Bug / Free-for-all Exploit",
        "description": "A routine upgrade incorrectly set the trusted root to 0x00, allowing anyone to drain funds. The exploit went viral as copy-cat transactions flooded the chain.",
        "post_mortem_url": "https://medium.com/nomad-xyz-blog/nomad-bridge-hack-root-cause-analysis-875ad2e5aacd",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "beanstalk-2022",
        "name": "Beanstalk Farms",
        "date": "2022-04-17",
        "amount_usd": 182_000_000,
        "protocol": "Beanstalk",
        "chains": ["Ethereum"],
        "attack_type": "Flash Loan Governance Attack",
        "description": "Attacker used a flash loan to acquire a supermajority of governance tokens and pass a malicious proposal draining the treasury in a single transaction.",
        "post_mortem_url": "https://bean.money/blog/beanstalk-security-incident-recap",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "euler-2023",
        "name": "Euler Finance",
        "date": "2023-03-13",
        "amount_usd": 197_000_000,
        "protocol": "Euler Finance",
        "chains": ["Ethereum"],
        "attack_type": "Flash Loan / Donation Attack",
        "description": "A flaw in Euler's donate() function allowed attackers to manipulate health factor accounting and drain lending pools across multiple transactions.",
        "post_mortem_url": "https://medium.com/@euler_mab/on-euler-finances-hack-192-million-in-3-days-and-its-return-9f51da83c2e5",
        "funds_recovered": True,
        "severity": "CRITICAL",
    },
    {
        "id": "mango-2022",
        "name": "Mango Markets",
        "date": "2022-10-11",
        "amount_usd": 114_000_000,
        "protocol": "Mango Markets",
        "chains": ["Solana"],
        "attack_type": "Oracle Price Manipulation",
        "description": "Attacker manipulated MNGO spot price using their own accounts to inflate collateral value, then borrowed against it and drained the treasury.",
        "post_mortem_url": "https://osec.io/blog/reports/2022-10-11-mango-market-exploit",
        "funds_recovered": False,
        "severity": "HIGH",
    },
    {
        "id": "curve-2023",
        "name": "Curve Finance",
        "date": "2023-07-30",
        "amount_usd": 73_500_000,
        "protocol": "Curve Finance",
        "chains": ["Ethereum"],
        "attack_type": "Reentrancy / Vyper Compiler Bug",
        "description": "Multiple Curve pools were drained after a Vyper compiler reentrancy bug affected pools including alETH/ETH, msETH/ETH, and pETH/ETH. The incident also triggered broader DeFi contagion concerns around Curve-linked lending positions.",
        "post_mortem_url": "https://www.llamarisk.com/research/curve-vyper-exploit-july-2023",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "ftx-2022",
        "name": "FTX Exchange",
        "date": "2022-11-11",
        "amount_usd": 477_000_000,
        "protocol": "FTX",
        "chains": ["Ethereum", "Solana", "BSC"],
        "attack_type": "Unauthorized Access / Key Compromise",
        "description": "Following FTX's bankruptcy filing, approximately $477M was drained from FTX wallets in what appeared to be unauthorized access to exchange wallets.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "multichain-2023",
        "name": "Multichain Bridge",
        "date": "2023-07-06",
        "amount_usd": 126_000_000,
        "protocol": "Multichain",
        "chains": ["Ethereum", "Fantom"],
        "attack_type": "Key Compromise / Insider",
        "description": "Assets were unexpectedly moved from Multichain bridge contracts after the CEO was reportedly detained, suggesting compromised admin keys.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "harmony-2022",
        "name": "Harmony Horizon Bridge",
        "date": "2022-06-23",
        "amount_usd": 100_000_000,
        "protocol": "Harmony",
        "chains": ["Ethereum"],
        "attack_type": "Private Key Compromise",
        "description": "Attackers compromised 2/5 multi-sig keys on the Horizon bridge to drain ~$100M in various tokens.",
        "post_mortem_url": "https://medium.com/harmony-one/harmonys-horizon-bridge-hack-1e8d283b6d66",
        "funds_recovered": False,
        "severity": "HIGH",
    },
    {
        "id": "wintermute-2022",
        "name": "Wintermute",
        "date": "2022-09-20",
        "amount_usd": 160_000_000,
        "protocol": "Wintermute",
        "chains": ["Ethereum"],
        "attack_type": "Vanity Address Exploit",
        "description": "DeFi operations wallet compromised through a Profanity vanity address generator vulnerability, allowing attacker to derive the private key.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "cream-2021",
        "name": "Cream Finance",
        "date": "2021-10-27",
        "amount_usd": 130_000_000,
        "protocol": "Cream Finance",
        "chains": ["Ethereum"],
        "attack_type": "Flash Loan / Oracle Manipulation",
        "description": "Third exploit of Cream Finance using flash loans to manipulate price oracle and drain lending pools.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "badger-2021",
        "name": "BadgerDAO",
        "date": "2021-12-02",
        "amount_usd": 120_000_000,
        "protocol": "BadgerDAO",
        "chains": ["Ethereum"],
        "attack_type": "Frontend / Supply Chain Attack",
        "description": "Attacker injected malicious scripts via a compromised Cloudflare API key, tricking users into approving token transfers.",
        "post_mortem_url": "https://badger.com/blog/technical-post-mortem",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "vulcan-2023",
        "name": "Vulcan Forged",
        "date": "2021-12-13",
        "amount_usd": 140_000_000,
        "protocol": "Vulcan Forged",
        "chains": ["Ethereum", "Polygon"],
        "attack_type": "Private Key Compromise",
        "description": "Attacker obtained private keys of 96 wallets from the platform's key management system and drained PYR tokens.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "cashio-2022",
        "name": "Cashio",
        "date": "2022-03-23",
        "amount_usd": 52_000_000,
        "protocol": "Cashio",
        "chains": ["Solana"],
        "attack_type": "Infinite Mint / Validation Bug",
        "description": "Attacker exploited missing collateral validation to mint unlimited CASH stablecoin and drain liquidity pools.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "HIGH",
    },
    {
        "id": "parity-2017",
        "name": "Parity Wallet",
        "date": "2017-11-06",
        "amount_usd": 280_000_000,
        "protocol": "Parity Technologies",
        "chains": ["Ethereum"],
        "attack_type": "Self-Destruct / Library Bug",
        "description": "A user accidentally triggered selfdestruct on the shared Parity multi-sig library contract, permanently freezing ~$280M in ETH across 587 wallets.",
        "post_mortem_url": "https://www.parity.io/blog/a-postmortem-on-the-parity-multi-sig-library-self-destruct",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "dao-2016",
        "name": "The DAO",
        "date": "2016-06-17",
        "amount_usd": 60_000_000,
        "protocol": "The DAO",
        "chains": ["Ethereum"],
        "attack_type": "Reentrancy",
        "description": "The original reentrancy exploit that drained ~$60M from The DAO's investment fund, leading to the Ethereum hard fork.",
        "post_mortem_url": "",
        "funds_recovered": True,
        "severity": "HIGH",
    },
    {
        "id": "kyberswap-2023",
        "name": "KyberSwap Elastic",
        "date": "2023-11-22",
        "amount_usd": 48_800_000,
        "protocol": "KyberSwap",
        "chains": ["Ethereum", "Arbitrum", "Optimism", "Polygon", "Base", "Avalanche", "BSC"],
        "attack_type": "Tick Manipulation / Precision Exploit",
        "description": "Attacker exploited a precision rounding issue in KyberSwap Elastic's concentrated liquidity math to drain pools across 7 chains simultaneously.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "HIGH",
    },
    {
        "id": "atomic-wallet-2023",
        "name": "Atomic Wallet",
        "date": "2023-06-03",
        "amount_usd": 100_000_000,
        "protocol": "Atomic Wallet",
        "chains": ["Ethereum", "Bitcoin", "BSC"],
        "attack_type": "Key Compromise / Supply Chain",
        "description": "Users' private keys were compromised, likely through a dependency vulnerability or server-side key storage breach, draining wallets across multiple chains.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "HIGH",
    },
    {
        "id": "level-finance-2023",
        "name": "Level Finance",
        "date": "2023-05-02",
        "amount_usd": 1_100_000,
        "protocol": "Level Finance",
        "chains": ["BSC"],
        "attack_type": "Referral Logic Bug",
        "description": "Attacker exploited a bug in the referral reward claiming function to repeatedly claim LVL token rewards.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "MEDIUM",
    },
    {
        "id": "platypus-2023",
        "name": "Platypus Finance",
        "date": "2023-02-16",
        "amount_usd": 8_500_000,
        "protocol": "Platypus Finance",
        "chains": ["Avalanche"],
        "attack_type": "Flash Loan / Logic Bug",
        "description": "Attacker used flash loans to exploit a solvency check flaw in the stablecoin USP minting mechanism.",
        "post_mortem_url": "",
        "funds_recovered": True,
        "severity": "MEDIUM",
    },
    {
        "id": "radiant-2024",
        "name": "Radiant Capital",
        "date": "2024-10-16",
        "amount_usd": 50_000_000,
        "protocol": "Radiant Capital",
        "chains": ["Arbitrum", "BSC"],
        "attack_type": "Multi-sig Compromise",
        "description": "Attackers compromised 3/11 multi-sig signers through malware and used the access to drain lending pools on two chains.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "HIGH",
    },
]

# Curated seed audit records
KNOWN_AUDITS = [
    {
        "id": "uniswap-v3-trail-of-bits",
        "protocol": "Uniswap V3",
        "auditor": "Trail of Bits",
        "date": "2021-03-01",
        "report_url": "https://github.com/Uniswap/v3-core/blob/main/audits/tob/audit.pdf",
        "severity_findings": {"critical": 0, "high": 0, "medium": 2, "low": 5, "informational": 7},
        "verdict": "PASS",
        "chains": ["Ethereum"],
    },
    {
        "id": "aave-v3-peckshield",
        "protocol": "Aave V3",
        "auditor": "PeckShield",
        "date": "2022-01-10",
        "report_url": "https://github.com/aave/aave-v3-core/blob/master/audits/27-01-2022_PeckShield_AaveV3.pdf",
        "severity_findings": {"critical": 0, "high": 0, "medium": 1, "low": 4, "informational": 6},
        "verdict": "PASS",
        "chains": ["Ethereum", "Polygon", "Arbitrum", "Optimism", "Avalanche"],
    },
    {
        "id": "compound-v3-openzeppelin",
        "protocol": "Compound V3",
        "auditor": "OpenZeppelin",
        "date": "2022-08-15",
        "report_url": "https://blog.openzeppelin.com/compound-comet-audit",
        "severity_findings": {"critical": 0, "high": 1, "medium": 3, "low": 8, "informational": 12},
        "verdict": "PASS",
        "chains": ["Ethereum"],
    },
    {
        "id": "curve-finance-chainsecurity",
        "protocol": "Curve Finance",
        "auditor": "ChainSecurity",
        "date": "2020-11-30",
        "report_url": "https://chainsecurity.com/wp-content/uploads/2021/04/ChainSecurity_Curve_Finance_audit.pdf",
        "severity_findings": {"critical": 0, "high": 0, "medium": 1, "low": 3, "informational": 8},
        "verdict": "PASS",
        "chains": ["Ethereum"],
    },
]


class RektDatabase:
    """
    Database of DeFi security incidents (hacks, exploits, rug pulls).

    Combines curated seed data with live data from DefiLlama hacks API.
    """

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._live_cache: Optional[List[Dict[str, Any]]] = None
        self._cache_ts: float = 0

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self._session

    async def _fetch_llama_hacks(self) -> List[Dict[str, Any]]:
        """Fetch live hacks data from DefiLlama."""
        import time
        now = time.time()
        # Cache for 1 hour
        if self._live_cache is not None and (now - self._cache_ts) < 3600:
            return self._live_cache

        try:
            session = await self._get_session()
            async with session.get("https://api.llama.fi/v2/hacks") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._live_cache = data if isinstance(data, list) else []
                    self._cache_ts = now
                    return self._live_cache
        except Exception as e:
            logger.warning(f"Failed to fetch DefiLlama hacks: {e}")

        return []

    def _normalize_llama_hack(self, hack: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a DefiLlama hack entry to our schema."""
        amount = hack.get("amount") or 0
        return {
            "id": f"llama-{hack.get('name', '').lower().replace(' ', '-')}",
            "name": hack.get("name", "Unknown"),
            "date": hack.get("date", ""),
            "amount_usd": amount,
            "protocol": hack.get("name", ""),
            "chains": hack.get("chains") or [],
            "attack_type": hack.get("category", "Unknown"),
            "description": hack.get("description") or "",
            "post_mortem_url": hack.get("sourceUrl") or "",
            "funds_recovered": (hack.get("returnedFunds") or 0) > 0,
            "severity": (
                "CRITICAL" if amount > 100_000_000
                else "HIGH" if amount > 10_000_000
                else "MEDIUM" if amount > 1_000_000
                else "LOW"
            ),
            "source": "DefiLlama",
        }

    async def get_incidents(
        self,
        chain: Optional[str] = None,
        attack_type: Optional[str] = None,
        min_amount: float = 0,
        search: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Query REKT incidents with optional filters.
        """
        # Start with curated seed data
        incidents: List[Dict[str, Any]] = [dict(i) for i in KNOWN_REKT_INCIDENTS]

        # Supplement with live DefiLlama data
        live = await self._fetch_llama_hacks()
        for hack in live:
            normalized = self._normalize_llama_hack(hack)
            # Avoid duplicates with seed data (by name similarity)
            seed_names = {i["name"].lower() for i in incidents}
            if normalized["name"].lower() not in seed_names:
                incidents.append(normalized)

        # Apply filters
        if chain:
            incidents = [
                i for i in incidents
                if any(chain.lower() in c.lower() for c in (i.get("chains") or []))
            ]
        if attack_type:
            incidents = [
                i for i in incidents
                if attack_type.lower() in (i.get("attack_type") or "").lower()
            ]
        if min_amount > 0:
            incidents = [i for i in incidents if (i.get("amount_usd") or 0) >= min_amount]
        if search:
            s = search.lower()
            incidents = [
                i for i in incidents
                if s in (i.get("name") or "").lower()
                or s in (i.get("protocol") or "").lower()
                or s in (i.get("description") or "").lower()
                or s in (i.get("attack_type") or "").lower()
            ]

        # Sort by amount descending
        incidents.sort(key=lambda i: i.get("amount_usd") or 0, reverse=True)
        return incidents[:limit]

    async def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Get a single incident by ID."""
        all_incidents = await self.get_incidents(limit=10000)
        for i in all_incidents:
            if i.get("id") == incident_id:
                return i
        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class AuditDatabase:
    """
    Database of smart contract security audits.

    Combines curated seed data with live data from DefiLlama protocols endpoint.
    """

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._live_cache: Optional[List[Dict[str, Any]]] = None
        self._cache_ts: float = 0

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self._session

    async def _fetch_defillama_audits(self) -> List[Dict[str, Any]]:
        """Fetch protocol audit metadata from DefiLlama."""
        import time
        now = time.time()
        if self._live_cache is not None and (now - self._cache_ts) < 3600:
            return self._live_cache

        try:
            session = await self._get_session()
            async with session.get("https://api.llama.fi/protocols") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    audited = []
                    if isinstance(data, list):
                        for proto in data:
                            audit_links = proto.get("audit_links") or []
                            audits_count = proto.get("audits")
                            if not audit_links and not audits_count:
                                continue
                            auditor = "Unknown"
                            audit_note = proto.get("audit_note") or ""
                            if audit_note:
                                for firm in ["Trail of Bits", "OpenZeppelin", "PeckShield",
                                             "ChainSecurity", "Quantstamp", "CertiK", "Halborn",
                                             "Consensys Diligence", "Sherlock", "Code4rena",
                                             "Spearbit", "Cyfrin", "MixBytes"]:
                                    if firm.lower() in audit_note.lower():
                                        auditor = firm
                                        break
                            audited.append({
                                "id": f"llama-{proto.get('name', '').lower().replace(' ', '-')}",
                                "protocol": proto.get("name", "Unknown"),
                                "auditor": auditor,
                                "date": "",
                                "report_url": audit_links[0] if audit_links else "",
                                "severity_findings": {},
                                "verdict": "PASS" if audits_count and str(audits_count) != "0" else "UNKNOWN",
                                "chains": proto.get("chains") or [],
                                "source": "DefiLlama",
                            })
                    self._live_cache = audited
                    self._cache_ts = now
                    return self._live_cache
        except Exception as e:
            logger.warning(f"Failed to fetch DefiLlama audit data: {e}")

        return []

    async def get_audits(
        self,
        protocol: Optional[str] = None,
        auditor: Optional[str] = None,
        chain: Optional[str] = None,
        verdict: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query audit records with optional filters."""
        audits: List[Dict[str, Any]] = [dict(a) for a in KNOWN_AUDITS]

        # Supplement with live DefiLlama data
        live = await self._fetch_defillama_audits()
        seed_protocols = {a["protocol"].lower() for a in audits}
        for audit in live:
            if audit["protocol"].lower() not in seed_protocols:
                audits.append(audit)

        if protocol:
            audits = [
                a for a in audits
                if protocol.lower() in (a.get("protocol") or "").lower()
            ]
        if auditor:
            audits = [
                a for a in audits
                if auditor.lower() in (a.get("auditor") or "").lower()
            ]
        if chain:
            audits = [
                a for a in audits
                if any(chain.lower() in c.lower() for c in (a.get("chains") or []))
            ]
        if verdict:
            audits = [
                a for a in audits
                if (a.get("verdict") or "").upper() == verdict.upper()
            ]

        audits.sort(key=lambda a: a.get("date") or "", reverse=True)
        return audits[:limit]

    async def get_audit(self, audit_id: str) -> Optional[Dict[str, Any]]:
        """Get a single audit record by ID."""
        all_audits = await self.get_audits(limit=10000)
        for a in all_audits:
            if a.get("id") == audit_id:
                return a
        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
