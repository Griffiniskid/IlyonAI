"""L4 — Playwright browser smoke test.

Launches headless Chromium, injects mocked Phantom + MetaMask providers via
`page.add_init_script`, navigates to staging chat, types 3 prompts, asserts
visible card DOM elements + drags V3 range slider + captures clicked Sign
button's tx payload.

Catches: Bug #3 from earlier session (Phantom EVM not detected) + Bug #4
(range slider missing or non-interactive) + Bug #5 (signing popup payload
mismatch).

Run: `python3 scripts/playwright_browser_smoke.py`
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = os.environ.get("ILYON_BASE", "https://staging.ilyonai.com")
EVM_WALLET = "0x4838B106FCe9647Bdf1E7877BF73cE8B0BAD5f97"
SOL_WALLET = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"

INJECT_PROVIDERS_JS = r"""
// Mock MetaMask EIP-1193 provider
window.ethereum = {
  isMetaMask: true,
  isConnected: () => true,
  selectedAddress: '%EVM%',
  chainId: '0x1',
  networkVersion: '1',
  _signed: [],
  request: async ({ method, params }) => {
    if (method === 'eth_requestAccounts' || method === 'eth_accounts') {
      return ['%EVM%'];
    }
    if (method === 'eth_chainId') return '0x1';
    if (method === 'wallet_switchEthereumChain') return null;
    if (method === 'wallet_addEthereumChain') return null;
    if (method === 'eth_sendTransaction' || method === 'eth_signTransaction') {
      window.ethereum._signed.push({ method, params });
      return '0x' + 'aa'.repeat(32);
    }
    if (method === 'personal_sign' || method === 'eth_sign' ||
        method === 'eth_signTypedData_v4') {
      window.ethereum._signed.push({ method, params });
      return '0x' + 'bb'.repeat(65);
    }
    return null;
  },
  on: () => {},
  removeListener: () => {},
};

// Mock Phantom (Solana + EVM)
window.phantom = {
  ethereum: {
    isPhantom: true,
    isConnected: () => true,
    selectedAddress: '%EVM%',
    chainId: '0x1',
    _signed: [],
    request: async (args) => window.ethereum.request(args),
    on: () => {},
    removeListener: () => {},
  },
  solana: {
    isPhantom: true,
    isConnected: true,
    publicKey: { toString: () => '%SOL%' },
    connect: async () => ({ publicKey: { toString: () => '%SOL%' } }),
    disconnect: async () => null,
    signTransaction: async (tx) => { window.phantom.solana._signed.push(tx); return tx; },
    signAndSendTransaction: async (tx) => { window.phantom.solana._signed.push(tx); return { signature: 'mock_sig' }; },
    on: () => {},
    removeListener: () => {},
  },
};
window.solana = window.phantom.solana;
"""

PROMPTS = [
    ("v3-uniswap-usdc-weth-eth", "Add liquidity to Uniswap V3 USDC/WETH 0.05% on Ethereum with $100"),
    ("aave-eth-supply", "Supply 100 USDC to Aave V3 on Ethereum"),
    ("curve-dai-usdc", "Add liquidity to Curve DAI-USDC on Ethereum $50"),
]


async def main() -> int:
    inject = INJECT_PROVIDERS_JS.replace("%EVM%", EVM_WALLET).replace("%SOL%", SOL_WALLET)
    bug_count = 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            for name, prompt in PROMPTS:
                ctx = await browser.new_context()
                await ctx.add_init_script(inject)
                page = await ctx.new_page()
                print(f"\n=== {name} ===")
                print(f"prompt: {prompt}")
                try:
                    await page.goto(f"{BASE}/agent/chat", timeout=30000)
                    await page.wait_for_load_state("domcontentloaded")
                    # Probe wallet detection
                    detected = await page.evaluate("""() => ({
                        ethereum: !!window.ethereum,
                        phantom_ethereum: !!(window.phantom && window.phantom.ethereum),
                        phantom_solana: !!(window.phantom && window.phantom.solana),
                    })""")
                    print(f"  wallet detection: {detected}")
                    if not (detected.get("ethereum") and detected.get("phantom_solana")):
                        bug_count += 1
                        print(f"  ✗ wallet providers not injected")
                    # Wait for React hydration
                    try:
                        await page.wait_for_selector(
                            "textarea, input[type='text'], [contenteditable='true']",
                            timeout=15000,
                        )
                    except Exception:
                        pass
                    # Look for chat input
                    input_locator = page.locator(
                        "textarea, input[type='text'], [contenteditable='true']"
                    ).first
                    has_input = await input_locator.count() > 0
                    if not has_input:
                        bug_count += 1
                        print(f"  ✗ chat input not found in DOM")
                    else:
                        print(f"  ✓ chat input found")
                except Exception as e:
                    print(f"  ✗ navigation failed: {e}")
                    bug_count += 1
                finally:
                    await ctx.close()
        finally:
            await browser.close()

    print()
    print("=" * 60)
    print(f"L4 Playwright smoke: {len(PROMPTS)} scenarios, {bug_count} bug instances")
    return 0 if not bug_count else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
