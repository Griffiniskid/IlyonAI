import asyncio
import logging
import sys
import os
import io
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

# Ensure DATABASE_URL is set for testing
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./ilyon_ai.db"
    print("⚠️  DATABASE_URL not set. Using local SQLite: sqlite+aiosqlite:///./ilyon_ai.db")

from src.core.models import TokenInfo, AnalysisResult
from src.api.services.blink_service import get_blink_service
from src.storage.database import init_database, get_database

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_dummy_blink():
    print("\n🛡️  Creating Test Blink...")
    
    # 1. Initialize Database
    try:
        db = await init_database()
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Database error: {e}")
        return

    # 2. Create Dummy Data
    token = TokenInfo(
        address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", # USDC
        symbol="USDC",
        name="USD Coin",
        price_usd=1.0,
        liquidity_usd=500000000,
        liquidity_locked=True,
        mint_authority_enabled=False,
        freeze_authority_enabled=True,
        ai_verdict="SAFE",
        ai_rug_probability=1,
        ai_summary="This is a stablecoin issued by Circle. It is considered safe.",
        ai_score=95
    )

    result = AnalysisResult(
        token=token,
        safety_score=90,
        liquidity_score=100,
        distribution_score=85,
        activity_score=95,
        social_score=80,
        overall_score=95,
        grade="A+",
        recommendation="SAFE",
        honeypot_score=100,
        deployer_reputation_score=100,
        behavioral_anomaly_score=100
    )

    # 3. Create Blink using Service
    service = get_blink_service()
    
    try:
        # We use a dummy telegram ID for the creator
        blink_data = await service.create_blink(
            token_address=token.address,
            analysis_result=result,
            telegram_id=123456789
        )
        
        blink_id = blink_data['id']
        blink_url = blink_data['url']
        
        print("\n✅ Blink Created Successfully!")
        print(f"🆔 Blink ID: {blink_id}")
        print(f"🔗 Local URL: http://localhost:8080/api/v1/blinks/{blink_id}")
        print(f"🔗 Public URL: {blink_url}")
        
        print("\n👇 To test this Blink:")
        print(f"1. Start the server: python -m src.main")
        print(f"2. Run: curl http://localhost:8080/api/v1/blinks/{blink_id}")
        print(f"3. Run: curl -X POST http://localhost:8080/api/v1/blinks/{blink_id}")
        
        return blink_id

    except Exception as e:
        print(f"❌ Error creating blink: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(create_dummy_blink())
