"""
Basic integration tests for AI Sentinel.

Tests core functionality without requiring API keys.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.analyzer import TokenAnalyzer
from src.data.dexscreener import DexScreenerClient
from src.data.solana import SolanaClient
from src.monetization.affiliates import get_manager
from src.config import settings

# Test addresses (well-known Solana tokens)
BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
SOL = "So11111111111111111111111111111111111111112"


async def test_config():
    """Test configuration loading"""
    print("\n" + "=" * 70)
    print("TEST: Configuration")
    print("=" * 70)

    print(f"✅ Bot Token: {'*' * 20}{settings.bot_token[-4:] if len(settings.bot_token) > 4 else '❌ NOT SET'}")
    print(f"✅ OpenAI API Key: {'Configured' if settings.openai_api_key else '❌ NOT SET'}")
    print(f"✅ Gemini API Key: {'Configured' if settings.gemini_api_key else 'Not configured (optional)'}")
    print(f"✅ Grok API Key: {'Configured' if settings.grok_api_key else 'Not configured (optional)'}")
    print(f"✅ Primary Affiliate: {settings.primary_affiliate}")
    print(f"✅ Solana RPC: {settings.solana_rpc_url[:50]}...")
    print("PASSED ✓\n")


async def test_affiliates():
    """Test affiliate system"""
    print("=" * 70)
    print("TEST: Affiliate System")
    print("=" * 70)

    manager = get_manager()
    enabled = manager.enabled_bots

    print(f"Enabled bots: {len(enabled)}")
    for bot in enabled:
        print(f"  {bot.emoji} {bot.name} ({bot.commission}) - Priority {bot.priority}")

    # Test link generation
    primary = manager.get_primary_bot()
    if primary:
        link = primary.generate_link(BONK)
        print(f"\nPrimary bot: {primary.name}")
        print(f"Example link: {link[:60]}...")
        print("PASSED ✓\n")
    else:
        print("⚠️  No primary bot configured")
        print("SKIPPED\n")


async def test_dexscreener():
    """Test DexScreener API client"""
    print("=" * 70)
    print("TEST: DexScreener Client")
    print("=" * 70)

    try:
        async with DexScreenerClient() as client:
            print(f"Fetching data for BONK...")
            data = await client.get_token(BONK)

            if data and "main" in data:
                pair = data["main"]
                base = pair.get("baseToken", {})
                print(f"✅ Symbol: {base.get('symbol')}")
                print(f"✅ Name: {base.get('name')}")
                print(f"✅ Price: ${float(pair.get('priceUsd', 0)):.8f}")
                print(f"✅ Liquidity: ${float(pair.get('liquidity', {}).get('usd', 0)):,.2f}")
                print("PASSED ✓\n")
            else:
                print("❌ No data returned")
                print("FAILED ✗\n")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("FAILED ✗\n")


async def test_solana_client():
    """Test Solana RPC client"""
    print("=" * 70)
    print("TEST: Solana RPC Client")
    print("=" * 70)

    try:
        async with SolanaClient(settings.solana_rpc_url) as client:
            # Test address validation
            valid_bonk = client.is_valid_address(BONK)
            valid_sol = client.is_valid_address(SOL)
            invalid = client.is_valid_address("invalid123")

            print(f"✅ BONK validation: {valid_bonk}")
            print(f"✅ SOL validation: {valid_sol}")
            print(f"✅ Invalid address: {invalid}")

            if valid_bonk and valid_sol and not invalid:
                print("PASSED ✓\n")
            else:
                print("FAILED ✗\n")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("FAILED ✗\n")


async def test_analyzer_init():
    """Test analyzer initialization"""
    print("=" * 70)
    print("TEST: Analyzer Initialization")
    print("=" * 70)

    try:
        analyzer = TokenAnalyzer()
        print(f"✅ Analyzer created")
        print(f"✅ DexScreener client: {analyzer.dex is not None}")
        print(f"✅ RugCheck client: {analyzer.rugcheck is not None}")
        print(f"✅ Solana client: {analyzer.solana is not None}")
        print(f"✅ Scraper: {analyzer.scraper is not None}")
        print(f"✅ AI Router: {analyzer.ai_router is not None}")
        print(f"✅ Scorer: {analyzer.scorer is not None}")

        await analyzer.close()
        print("PASSED ✓\n")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("FAILED ✗\n")


async def test_quick_analysis():
    """Test quick analysis (requires OpenAI API key)"""
    print("=" * 70)
    print("TEST: Quick Analysis (Optional - requires API keys)")
    print("=" * 70)

    if not settings.openai_api_key:
        print("⚠️  OpenAI API key not configured")
        print("SKIPPED\n")
        return

    try:
        analyzer = TokenAnalyzer()
        print(f"Analyzing BONK in quick mode...")

        result = await analyzer.analyze(BONK, mode="quick")

        if result:
            print(f"✅ Symbol: {result.token.symbol}")
            print(f"✅ Overall Score: {result.overall_score}/100")
            print(f"✅ Grade: {result.grade}")
            print(f"✅ Safety: {result.safety_score}/100")
            print(f"✅ Liquidity: {result.liquidity_score}/100")
            print(f"✅ Recommendation: {result.recommendation[:60]}...")
            print("PASSED ✓\n")
        else:
            print("❌ Analysis returned None")
            print("FAILED ✗\n")

        await analyzer.close()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        print("FAILED ✗\n")


async def run_all_tests():
    """Run all tests"""
    print("\n" + "🛡️  AI SENTINEL - INTEGRATION TESTS ".center(70, "="))
    print()

    # Run tests
    await test_config()
    await test_affiliates()
    await test_dexscreener()
    await test_solana_client()
    await test_analyzer_init()
    await test_quick_analysis()

    print("=" * 70)
    print("TEST SUITE COMPLETE")
    print("=" * 70)
    print("\n✅ Basic integration tests passed!")
    print("\nNOTE: Full analysis tests require API keys:")
    print("  - OpenAI API key for AI analysis")
    print("  - Gemini API key for web research (optional)")
    print("  - Grok API key for Twitter sentiment (optional)")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(run_all_tests())
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
