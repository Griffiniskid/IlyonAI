"""
Database layer for AI Sentinel using async PostgreSQL (Supabase compatible).

Handles:
- User tracking and referrals
- Analysis history
- Click tracking for affiliate analytics
- Bot statistics

Uses asyncpg for async operations with SQLAlchemy for ORM.
"""

import logging
import secrets
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert

from src.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class User(Base):
    """
    User tracking for referral system and analytics.

    Tracks Telegram users, their referral codes, and activity metrics.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)

    # Referral system
    referral_code = Column(String(32), unique=True, index=True, nullable=False)
    referred_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Activity metrics
    analyses_count = Column(Integer, default=0)
    quick_buys_count = Column(Integer, default=0)
    shares_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Premium (future feature)
    premium_until = Column(DateTime, nullable=True)


class Analysis(Base):
    """
    Token analysis history.

    Stores all token analyses performed by users for analytics and caching.
    """
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Token info
    token_address = Column(String(64), index=True, nullable=False)
    token_symbol = Column(String(32), nullable=True)
    token_name = Column(String(128), nullable=True)

    # Analysis results
    overall_score = Column(Integer, nullable=True)
    grade = Column(String(2), nullable=True)
    mode = Column(String(16), nullable=True)  # quick/standard/full
    ai_verdict = Column(String(32), nullable=True)

    # Full result JSON for reference
    result_json = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class Referral(Base):
    """
    Referral tracking for viral growth.

    Records when one user refers another.
    """
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    referrer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    referred_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class QuickBuyClick(Base):
    """
    Affiliate click tracking.

    Records when users click Quick Buy to track affiliate performance.
    """
    __tablename__ = "quick_buy_clicks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_address = Column(String(64), index=True, nullable=False)
    token_symbol = Column(String(32), nullable=True)
    affiliate_bot = Column(String(32), default="trojan")
    clicked_at = Column(DateTime, default=datetime.utcnow)


class BotStats(Base):
    """
    Daily bot statistics.

    Aggregated daily metrics for dashboard and analytics.
    """
    __tablename__ = "bot_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, index=True, unique=True)

    users_total = Column(Integer, default=0)
    users_new = Column(Integer, default=0)
    analyses_total = Column(Integer, default=0)
    quick_buys = Column(Integer, default=0)
    referrals = Column(Integer, default=0)
    shares = Column(Integer, default=0)


# ═══════════════════════════════════════════════════════════════════════════════
# WALLET FORENSICS MODELS (Developer Wallet Tracking)
# ═══════════════════════════════════════════════════════════════════════════════

class WalletReputation(Base):
    """
    Track wallet reputation across token deployments.

    Part of the Developer Wallet Forensics Engine - tracks deployer
    wallets to identify serial scammers and protect the ecosystem.
    """
    __tablename__ = "wallet_reputations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_address = Column(String(64), unique=True, index=True, nullable=False)

    # Reputation metrics
    reputation_score = Column(Float, default=50.0)  # 0-100
    risk_level = Column(String(32), default="MEDIUM")  # CLEAN, LOW, MEDIUM, HIGH, CRITICAL, KNOWN_SCAMMER

    # Token deployment history
    tokens_deployed = Column(Integer, default=0)
    rugged_tokens = Column(Integer, default=0)
    active_tokens = Column(Integer, default=0)
    abandoned_tokens = Column(Integer, default=0)

    # Financial impact
    total_value_rugged_usd = Column(Float, default=0.0)
    avg_token_lifespan_hours = Column(Float, default=0.0)

    # Risk flags
    is_known_scammer = Column(Boolean, default=False)
    patterns_detected = Column(JSON, default=list)  # List of pattern names

    # Related wallets (JSON array of addresses)
    related_wallets = Column(JSON, default=list)
    funding_sources = Column(JSON, default=list)

    # Timestamps
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TokenDeployment(Base):
    """
    Track individual token deployments for pattern analysis.

    Records the lifecycle of tokens to build deployer reputation
    and detect scam patterns.
    """
    __tablename__ = "token_deployments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token_address = Column(String(64), unique=True, index=True, nullable=False)
    deployer_wallet = Column(String(64), index=True, nullable=False)

    # Token metadata
    token_symbol = Column(String(32), nullable=True)
    token_name = Column(String(128), nullable=True)

    # Token outcome
    status = Column(String(32), default="active")  # active, rugged, abandoned
    peak_liquidity_usd = Column(Float, default=0.0)
    final_liquidity_usd = Column(Float, default=0.0)
    liquidity_removal_pct = Column(Float, default=0.0)

    # Timeline
    deployed_at = Column(DateTime, default=datetime.utcnow)
    rugged_at = Column(DateTime, nullable=True)
    last_trade_at = Column(DateTime, nullable=True)
    lifespan_hours = Column(Float, default=0.0)

    # Analysis data
    final_score = Column(Integer, nullable=True)
    final_grade = Column(String(2), nullable=True)
    risk_factors = Column(JSON, default=list)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════════════════════
# SOLANA BLINKS MODELS (Shareable Security Links)
# ═══════════════════════════════════════════════════════════════════════════════

class Blink(Base):
    """
    Shareable Blink for token security analysis.

    Enables viral sharing of security reports via Twitter/X with
    interactive Solana Actions that allow instant verification.
    """
    __tablename__ = "blinks"

    id = Column(String(16), primary_key=True)
    token_address = Column(String(64), index=True, nullable=False)

    # Cached analysis snapshot
    token_symbol = Column(String(32))
    token_name = Column(String(128))
    overall_score = Column(Integer)
    grade = Column(String(2))
    ai_verdict = Column(String(32))
    ai_rug_probability = Column(Integer)
    liquidity_locked = Column(Boolean)

    # Full cached result (JSON)
    cached_result = Column(JSON)

    # Creator info
    created_by_telegram_id = Column(BigInteger, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Analytics
    views_count = Column(Integer, default=0)
    verifications_count = Column(Integer, default=0)
    last_verified_at = Column(DateTime)

    # Expiry
    expires_at = Column(DateTime)


class BlinkAnalytics(Base):
    """
    Analytics tracking for Blink interactions.

    Records views, verifications, and shares for viral metrics.
    """
    __tablename__ = "blink_analytics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    blink_id = Column(String(16), ForeignKey("blinks.id"), index=True)

    event_type = Column(String(32))  # 'view', 'verify', 'share'
    ip_hash = Column(String(64))     # Hashed IP for rate limiting
    user_agent = Column(Text)
    referrer = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

class Database:
    """
    Async database interface for AI Sentinel.

    Provides methods for user management, analysis tracking,
    referral system, and statistics.
    """

    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize database connection.

        Args:
            database_url: PostgreSQL connection string. If not provided,
                         uses settings.database_url
        """
        self.database_url = database_url or settings.database_url
        self.engine = None
        self.async_session = None
        self._initialized = False

    async def init(self):
        """
        Initialize database connection and create tables.

        Should be called once at startup.
        """
        if self._initialized:
            return

        if not self.database_url:
            logger.warning("DATABASE_URL not set - database features disabled")
            return

        try:
            # Convert postgres:// to postgresql+asyncpg://
            url = self.database_url
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

            self.engine = create_async_engine(url, echo=False, pool_pre_ping=True)
            self.async_session = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            # Create tables
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            self._initialized = True
            logger.info("✅ Database initialized successfully")

        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise

    async def close(self):
        """Close database connection"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connection closed")

    def _generate_referral_code(self, telegram_id: int) -> str:
        """Generate unique referral code for user"""
        return f"ai_{secrets.token_hex(4)}_{telegram_id % 10000}"

    # ═══════════════════════════════════════════════════════════════════════════
    # USER MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_or_create_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None
    ) -> Optional[User]:
        """
        Get existing user or create new one.

        Args:
            telegram_id: Telegram user ID
            username: Telegram username (optional)
            first_name: User's first name (optional)

        Returns:
            User object or None if database not available
        """
        if not self._initialized:
            return None

        async with self.async_session() as session:
            # Try to get existing user
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if user:
                # Update last active
                user.last_active = datetime.utcnow()
                if username:
                    user.username = username
                if first_name:
                    user.first_name = first_name
                await session.commit()
                return user

            # Create new user
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                referral_code=self._generate_referral_code(telegram_id)
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            logger.info(f"New user created: {telegram_id} (ref: {user.referral_code})")
            return user

    async def get_user(self, telegram_id: int) -> Optional[User]:
        """Get user by Telegram ID"""
        if not self._initialized:
            return None

        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()

    async def get_user_by_referral_code(self, referral_code: str) -> Optional[User]:
        """Get user by their referral code"""
        if not self._initialized:
            return None

        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(User.referral_code == referral_code)
            )
            return result.scalar_one_or_none()

    # ═══════════════════════════════════════════════════════════════════════════
    # REFERRAL SYSTEM
    # ═══════════════════════════════════════════════════════════════════════════

    async def track_referral(self, referrer_code: str, new_user_telegram_id: int) -> bool:
        """
        Track referral signup.

        Args:
            referrer_code: Referral code of the referrer
            new_user_telegram_id: Telegram ID of the new user

        Returns:
            True if referral tracked successfully
        """
        if not self._initialized:
            return False

        async with self.async_session() as session:
            # Get referrer
            referrer = await self.get_user_by_referral_code(referrer_code)
            if not referrer:
                logger.warning(f"Referral code not found: {referrer_code}")
                return False

            # Get new user
            new_user = await self.get_user(new_user_telegram_id)
            if not new_user:
                return False

            # Don't allow self-referral
            if referrer.telegram_id == new_user_telegram_id:
                return False

            # Check if already referred
            if new_user.referred_by_id:
                return False

            # Create referral record
            referral = Referral(
                referrer_id=referrer.id,
                referred_id=new_user.id
            )
            session.add(referral)

            # Update new user's referred_by
            await session.execute(
                update(User)
                .where(User.id == new_user.id)
                .values(referred_by_id=referrer.id)
            )

            await session.commit()
            logger.info(f"Referral tracked: {referrer.telegram_id} -> {new_user_telegram_id}")
            return True

    async def count_referrals(self, user_id: int) -> int:
        """Count number of users referred by this user"""
        if not self._initialized:
            return 0

        async with self.async_session() as session:
            result = await session.execute(
                select(func.count(Referral.id))
                .where(Referral.referrer_id == user_id)
            )
            return result.scalar() or 0

    async def get_referral_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top referrers leaderboard.

        Returns list of dicts with user info and referral count.
        """
        if not self._initialized:
            return []

        async with self.async_session() as session:
            # Count referrals per user
            result = await session.execute(
                select(
                    User.telegram_id,
                    User.username,
                    User.first_name,
                    func.count(Referral.id).label('referral_count')
                )
                .join(Referral, User.id == Referral.referrer_id)
                .group_by(User.id)
                .order_by(func.count(Referral.id).desc())
                .limit(limit)
            )

            return [
                {
                    "telegram_id": row.telegram_id,
                    "username": row.username,
                    "first_name": row.first_name,
                    "referral_count": row.referral_count
                }
                for row in result
            ]

    # ═══════════════════════════════════════════════════════════════════════════
    # ANALYSIS TRACKING
    # ═══════════════════════════════════════════════════════════════════════════

    async def track_analysis(
        self,
        user_telegram_id: int,
        token_address: str,
        token_symbol: Optional[str] = None,
        token_name: Optional[str] = None,
        overall_score: Optional[int] = None,
        grade: Optional[str] = None,
        mode: Optional[str] = None,
        ai_verdict: Optional[str] = None,
        result_json: Optional[Dict] = None
    ) -> bool:
        """
        Record token analysis in history.

        Also increments user's analyses_count.
        """
        if not self._initialized:
            return False

        async with self.async_session() as session:
            user = await self.get_user(user_telegram_id)
            if not user:
                return False

            # Create analysis record
            analysis = Analysis(
                user_id=user.id,
                token_address=token_address,
                token_symbol=token_symbol,
                token_name=token_name,
                overall_score=overall_score,
                grade=grade,
                mode=mode,
                ai_verdict=ai_verdict,
                result_json=result_json
            )
            session.add(analysis)

            # Increment user's analysis count
            await session.execute(
                update(User)
                .where(User.id == user.id)
                .values(analyses_count=User.analyses_count + 1)
            )

            await session.commit()
            return True

    async def track_quick_buy(
        self,
        user_telegram_id: int,
        token_address: str,
        token_symbol: Optional[str] = None
    ) -> bool:
        """Record Quick Buy click"""
        if not self._initialized:
            return False

        async with self.async_session() as session:
            user = await self.get_user(user_telegram_id)
            if not user:
                return False

            click = QuickBuyClick(
                user_id=user.id,
                token_address=token_address,
                token_symbol=token_symbol,
                affiliate_bot="trojan"
            )
            session.add(click)

            # Increment user's quick buy count
            await session.execute(
                update(User)
                .where(User.id == user.id)
                .values(quick_buys_count=User.quick_buys_count + 1)
            )

            await session.commit()
            return True

    # ═══════════════════════════════════════════════════════════════════════════
    # STATISTICS
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_stats(self) -> Dict[str, Any]:
        """Get overall bot statistics"""
        if not self._initialized:
            return {"database": "not configured"}

        async with self.async_session() as session:
            # Total users
            users_result = await session.execute(select(func.count(User.id)))
            total_users = users_result.scalar() or 0

            # Total analyses
            analyses_result = await session.execute(select(func.count(Analysis.id)))
            total_analyses = analyses_result.scalar() or 0

            # Total quick buys
            buys_result = await session.execute(select(func.count(QuickBuyClick.id)))
            total_quick_buys = buys_result.scalar() or 0

            # Total referrals
            refs_result = await session.execute(select(func.count(Referral.id)))
            total_referrals = refs_result.scalar() or 0

            return {
                "users_total": total_users,
                "analyses_total": total_analyses,
                "quick_buys_total": total_quick_buys,
                "referrals_total": total_referrals,
                "database": "connected"
            }

    # ═══════════════════════════════════════════════════════════════════════════
    # WALLET FORENSICS
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_wallet_reputation(self, wallet_address: str) -> Optional[WalletReputation]:
        """Get wallet reputation by address"""
        if not self._initialized:
            return None

        async with self.async_session() as session:
            result = await session.execute(
                select(WalletReputation).where(WalletReputation.wallet_address == wallet_address)
            )
            return result.scalar_one_or_none()

    async def upsert_wallet_reputation(
        self,
        wallet_address: str,
        reputation_score: float,
        risk_level: str,
        tokens_deployed: int = 0,
        rugged_tokens: int = 0,
        active_tokens: int = 0,
        total_value_rugged_usd: float = 0.0,
        patterns_detected: Optional[List[str]] = None,
        is_known_scammer: bool = False,
    ) -> bool:
        """
        Create or update wallet reputation.

        Args:
            wallet_address: Wallet address to track
            reputation_score: Calculated reputation score (0-100)
            risk_level: Risk classification
            tokens_deployed: Number of tokens deployed
            rugged_tokens: Number of tokens that were rugged
            active_tokens: Number of currently active tokens
            total_value_rugged_usd: Total USD value rugged
            patterns_detected: List of detected scam patterns
            is_known_scammer: Whether flagged as known scammer

        Returns:
            True if successful
        """
        if not self._initialized:
            return False

        async with self.async_session() as session:
            # Try upsert
            stmt = insert(WalletReputation).values(
                wallet_address=wallet_address,
                reputation_score=reputation_score,
                risk_level=risk_level,
                tokens_deployed=tokens_deployed,
                rugged_tokens=rugged_tokens,
                active_tokens=active_tokens,
                total_value_rugged_usd=total_value_rugged_usd,
                patterns_detected=patterns_detected or [],
                is_known_scammer=is_known_scammer,
                last_active=datetime.utcnow(),
            )

            # On conflict, update
            stmt = stmt.on_conflict_do_update(
                index_elements=['wallet_address'],
                set_={
                    'reputation_score': reputation_score,
                    'risk_level': risk_level,
                    'tokens_deployed': tokens_deployed,
                    'rugged_tokens': rugged_tokens,
                    'active_tokens': active_tokens,
                    'total_value_rugged_usd': total_value_rugged_usd,
                    'patterns_detected': patterns_detected or [],
                    'is_known_scammer': is_known_scammer,
                    'last_active': datetime.utcnow(),
                    'updated_at': datetime.utcnow(),
                }
            )

            await session.execute(stmt)
            await session.commit()
            return True

    async def flag_known_scammer(self, wallet_address: str) -> bool:
        """Flag a wallet as a known scammer"""
        if not self._initialized:
            return False

        async with self.async_session() as session:
            await session.execute(
                update(WalletReputation)
                .where(WalletReputation.wallet_address == wallet_address)
                .values(
                    is_known_scammer=True,
                    risk_level="KNOWN_SCAMMER",
                    reputation_score=0.0,
                    updated_at=datetime.utcnow(),
                )
            )
            await session.commit()
            return True

    async def get_known_scammers(self, limit: int = 100) -> List[str]:
        """Get list of known scammer wallet addresses"""
        if not self._initialized:
            return []

        async with self.async_session() as session:
            result = await session.execute(
                select(WalletReputation.wallet_address)
                .where(WalletReputation.is_known_scammer == True)
                .limit(limit)
            )
            return [row[0] for row in result.all()]

    async def track_token_deployment(
        self,
        token_address: str,
        deployer_wallet: str,
        token_symbol: Optional[str] = None,
        token_name: Optional[str] = None,
        peak_liquidity_usd: float = 0.0,
    ) -> bool:
        """
        Record a new token deployment.

        Args:
            token_address: Token mint address
            deployer_wallet: Wallet that deployed the token
            token_symbol: Token symbol
            token_name: Token name
            peak_liquidity_usd: Initial/peak liquidity

        Returns:
            True if successful
        """
        if not self._initialized:
            return False

        async with self.async_session() as session:
            stmt = insert(TokenDeployment).values(
                token_address=token_address,
                deployer_wallet=deployer_wallet,
                token_symbol=token_symbol,
                token_name=token_name,
                peak_liquidity_usd=peak_liquidity_usd,
                final_liquidity_usd=peak_liquidity_usd,
                status="active",
            )

            # On conflict, just update the liquidity if higher
            stmt = stmt.on_conflict_do_update(
                index_elements=['token_address'],
                set_={
                    'peak_liquidity_usd': func.greatest(
                        TokenDeployment.peak_liquidity_usd,
                        peak_liquidity_usd
                    ),
                    'last_trade_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow(),
                }
            )

            await session.execute(stmt)
            await session.commit()
            return True

    async def mark_token_rugged(
        self,
        token_address: str,
        final_liquidity_usd: float = 0.0,
        lifespan_hours: float = 0.0,
    ) -> bool:
        """Mark a token as rugged"""
        if not self._initialized:
            return False

        async with self.async_session() as session:
            # Get current token data
            result = await session.execute(
                select(TokenDeployment).where(TokenDeployment.token_address == token_address)
            )
            deployment = result.scalar_one_or_none()

            if not deployment:
                return False

            # Calculate LP removal percentage
            if deployment.peak_liquidity_usd > 0:
                removal_pct = ((deployment.peak_liquidity_usd - final_liquidity_usd)
                              / deployment.peak_liquidity_usd) * 100
            else:
                removal_pct = 100.0

            await session.execute(
                update(TokenDeployment)
                .where(TokenDeployment.token_address == token_address)
                .values(
                    status="rugged",
                    final_liquidity_usd=final_liquidity_usd,
                    liquidity_removal_pct=removal_pct,
                    rugged_at=datetime.utcnow(),
                    lifespan_hours=lifespan_hours,
                    updated_at=datetime.utcnow(),
                )
            )
            await session.commit()
            return True

    async def get_wallet_deployments(
        self,
        deployer_wallet: str,
        limit: int = 20,
    ) -> List[TokenDeployment]:
        """Get all token deployments by a wallet"""
        if not self._initialized:
            return []

        async with self.async_session() as session:
            result = await session.execute(
                select(TokenDeployment)
                .where(TokenDeployment.deployer_wallet == deployer_wallet)
                .order_by(TokenDeployment.deployed_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_deployer_stats(self, deployer_wallet: str) -> Dict[str, Any]:
        """Get aggregated stats for a deployer wallet"""
        if not self._initialized:
            return {}

        async with self.async_session() as session:
            # Count by status
            result = await session.execute(
                select(
                    TokenDeployment.status,
                    func.count(TokenDeployment.id).label('count'),
                    func.sum(TokenDeployment.peak_liquidity_usd).label('total_peak_liq'),
                )
                .where(TokenDeployment.deployer_wallet == deployer_wallet)
                .group_by(TokenDeployment.status)
            )

            stats = {
                "tokens_deployed": 0,
                "active": 0,
                "rugged": 0,
                "abandoned": 0,
                "total_peak_liquidity_usd": 0.0,
            }

            for row in result:
                stats[row.status] = row.count
                stats["tokens_deployed"] += row.count
                stats["total_peak_liquidity_usd"] += float(row.total_peak_liq or 0)

            return stats

    # ═══════════════════════════════════════════════════════════════════════════
    # SOLANA BLINKS
    # ═══════════════════════════════════════════════════════════════════════════

    async def create_blink(
        self,
        blink_id: str,
        token_address: str,
        token_symbol: Optional[str] = None,
        token_name: Optional[str] = None,
        overall_score: Optional[int] = None,
        grade: Optional[str] = None,
        ai_verdict: Optional[str] = None,
        ai_rug_probability: Optional[int] = None,
        liquidity_locked: Optional[bool] = None,
        cached_result: Optional[Dict] = None,
        created_by_telegram_id: Optional[int] = None,
        expires_at: Optional[datetime] = None,
    ) -> Optional[Blink]:
        """
        Create a new shareable Blink.

        Args:
            blink_id: Unique blink identifier
            token_address: Solana token address
            token_symbol: Token symbol
            token_name: Token name
            overall_score: Analysis score (0-100)
            grade: Letter grade (A-F)
            ai_verdict: AI verdict string
            ai_rug_probability: Rug probability percentage
            liquidity_locked: Whether LP is locked
            cached_result: Full analysis result JSON
            created_by_telegram_id: Creator's Telegram ID
            expires_at: Optional expiration datetime

        Returns:
            Created Blink object or None if database not available
        """
        if not self._initialized:
            return None

        async with self.async_session() as session:
            blink = Blink(
                id=blink_id,
                token_address=token_address,
                token_symbol=token_symbol,
                token_name=token_name,
                overall_score=overall_score,
                grade=grade,
                ai_verdict=ai_verdict,
                ai_rug_probability=ai_rug_probability,
                liquidity_locked=liquidity_locked,
                cached_result=cached_result,
                created_by_telegram_id=created_by_telegram_id,
                expires_at=expires_at,
            )
            session.add(blink)
            await session.commit()
            await session.refresh(blink)

            logger.info(f"Blink created: {blink_id} for token {token_address[:16]}...")
            return blink

    async def get_blink(self, blink_id: str) -> Optional[Blink]:
        """Get a Blink by ID"""
        if not self._initialized:
            return None

        async with self.async_session() as session:
            result = await session.execute(
                select(Blink).where(Blink.id == blink_id)
            )
            return result.scalar_one_or_none()

    async def get_blink_by_token(self, token_address: str) -> Optional[Blink]:
        """Get the most recent Blink for a token address"""
        if not self._initialized:
            return None

        async with self.async_session() as session:
            result = await session.execute(
                select(Blink)
                .where(Blink.token_address == token_address)
                .order_by(Blink.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def update_blink_result(
        self,
        blink_id: str,
        overall_score: int,
        grade: str,
        ai_verdict: str,
        ai_rug_probability: Optional[int] = None,
        liquidity_locked: Optional[bool] = None,
        cached_result: Optional[Dict] = None,
    ) -> bool:
        """Update a Blink with fresh analysis results"""
        if not self._initialized:
            return False

        async with self.async_session() as session:
            await session.execute(
                update(Blink)
                .where(Blink.id == blink_id)
                .values(
                    overall_score=overall_score,
                    grade=grade,
                    ai_verdict=ai_verdict,
                    ai_rug_probability=ai_rug_probability,
                    liquidity_locked=liquidity_locked,
                    cached_result=cached_result,
                    last_verified_at=datetime.utcnow(),
                )
            )
            await session.commit()
            return True

    async def increment_blink_views(self, blink_id: str) -> bool:
        """Increment view count for a Blink"""
        if not self._initialized:
            return False

        async with self.async_session() as session:
            await session.execute(
                update(Blink)
                .where(Blink.id == blink_id)
                .values(views_count=Blink.views_count + 1)
            )
            await session.commit()
            return True

    async def increment_blink_verifications(self, blink_id: str) -> bool:
        """Increment verification count for a Blink"""
        if not self._initialized:
            return False

        async with self.async_session() as session:
            await session.execute(
                update(Blink)
                .where(Blink.id == blink_id)
                .values(
                    verifications_count=Blink.verifications_count + 1,
                    last_verified_at=datetime.utcnow(),
                )
            )
            await session.commit()
            return True

    async def track_blink_event(
        self,
        blink_id: str,
        event_type: str,
        ip_hash: Optional[str] = None,
        user_agent: Optional[str] = None,
        referrer: Optional[str] = None,
    ) -> bool:
        """
        Track a Blink analytics event.

        Args:
            blink_id: Blink ID
            event_type: Event type ('view', 'verify', 'share')
            ip_hash: Hashed IP address for privacy
            user_agent: Request user agent
            referrer: Request referrer URL

        Returns:
            True if successful
        """
        if not self._initialized:
            return False

        async with self.async_session() as session:
            event = BlinkAnalytics(
                blink_id=blink_id,
                event_type=event_type,
                ip_hash=ip_hash,
                user_agent=user_agent,
                referrer=referrer,
            )
            session.add(event)
            await session.commit()
            return True

    async def get_blink_stats(self, blink_id: str) -> Dict[str, Any]:
        """Get analytics stats for a Blink"""
        if not self._initialized:
            return {}

        async with self.async_session() as session:
            # Get blink
            result = await session.execute(
                select(Blink).where(Blink.id == blink_id)
            )
            blink = result.scalar_one_or_none()

            if not blink:
                return {}

            return {
                "views": blink.views_count,
                "verifications": blink.verifications_count,
                "created_at": blink.created_at.isoformat() if blink.created_at else None,
                "last_verified_at": blink.last_verified_at.isoformat() if blink.last_verified_at else None,
            }


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL DATABASE INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

_db: Optional[Database] = None


async def get_database() -> Database:
    """Get or create global database instance"""
    global _db
    if _db is None:
        _db = Database()
        await _db.init()
    return _db


async def init_database():
    """Initialize database at startup"""
    db = await get_database()
    return db
