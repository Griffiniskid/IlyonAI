"""
Database layer for Ilyon AI using async PostgreSQL (Supabase compatible).

Handles:
- User tracking and referrals
- Analysis history
- Click tracking for affiliate analytics
- Bot statistics

Uses asyncpg for async operations with SQLAlchemy for ORM.
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, DateTime, ForeignKey, JSON, Text, UniqueConstraint
from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

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


class StatsSnapshot(Base):
    """
    Periodic stats snapshots for calculating change metrics.

    Stores dashboard statistics at regular intervals to enable
    calculation of daily changes (e.g., +10% volume change).
    """
    __tablename__ = "stats_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, index=True, default=datetime.utcnow)

    # Dashboard metrics at snapshot time
    total_volume_24h = Column(Float, default=0.0)
    active_tokens = Column(Integer, default=0)
    safe_tokens = Column(Integer, default=0)
    scams_detected = Column(Integer, default=0)
    tokens_analyzed = Column(Integer, default=0)
    total_liquidity = Column(Float, default=0.0)


class WebAnalysis(Base):
    """
    Web-based token analysis tracking.

    Tracks analyses performed via the web dashboard (not just Telegram).
    Used for accurate tokens_analyzed_today counts.
    """
    __tablename__ = "web_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token_address = Column(String(64), index=True, nullable=False)
    token_symbol = Column(String(32), nullable=True)
    token_name = Column(String(128), nullable=True)
    overall_score = Column(Integer, nullable=True)
    grade = Column(String(2), nullable=True)
    source = Column(String(32), default="web")  # web, api, telegram
    analyzed_at = Column(DateTime, default=datetime.utcnow, index=True)


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


class AlertAuditRecord(Base):
    """Persistent audit records for alert rule mutations."""

    __tablename__ = "alert_audit_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(64), nullable=False, index=True)
    actor_id = Column(String(128), nullable=False, index=True)
    trace_id = Column(String(128), nullable=False, index=True)
    payload = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class AlertRuleRow(Base):
    """Persistent alert rules."""
    __tablename__ = "alert_rules"

    id = Column(String(32), primary_key=True)
    name = Column(String(256), nullable=False)
    severity = Column(JSON, nullable=False, default=list)  # list of severity strings
    user_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AlertRecordRow(Base):
    """Persistent alert records."""
    __tablename__ = "alert_records"

    id = Column(String(64), primary_key=True)
    state = Column(String(32), nullable=False, default="new")
    severity = Column(String(32), nullable=False)
    title = Column(String(512), nullable=False)
    user_id = Column(String(64), nullable=True, index=True)
    rule_id = Column(String(32), nullable=True, index=True)
    subject_id = Column(String(128), nullable=True)
    kind = Column(String(64), nullable=True)
    snoozed_until = Column(String(64), nullable=True)
    resolved_at = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ContractScanCache(Base):
    """Cached contract scan results."""
    __tablename__ = "contract_scan_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chain = Column(String(32), nullable=False)
    address = Column(String(64), nullable=False, index=True)
    result_json = Column(JSON, nullable=False)
    scanned_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint('chain', 'address', name='uq_contract_scan_chain_address'),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# WEB AUTHENTICATION MODELS (Wallet-based auth for web frontend)
# ═══════════════════════════════════════════════════════════════════════════════

class WebUser(Base):
    """
    Web user authenticated via wallet signature.
    
    Separate from Telegram users - these are wallet-based web dashboard users.
    """
    __tablename__ = "web_users"

    wallet_address = Column(String(44), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, default=datetime.utcnow)
    
    # Activity metrics
    analyses_count = Column(Integer, default=0)
    tracked_wallets_count = Column(Integer, default=0)
    alerts_count = Column(Integer, default=0)
    
    # Premium (future feature)
    premium_until = Column(DateTime, nullable=True)


class UserSession(Base):
    """
    Session storage for web authentication.
    
    Used as fallback when Redis is unavailable.
    """
    __tablename__ = "user_sessions"

    token = Column(String(64), primary_key=True)
    wallet_address = Column(String(44), ForeignKey("web_users.wallet_address"), nullable=False, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)
    last_used = Column(DateTime, default=datetime.utcnow)


class TrackedWallet(Base):
    """
    Wallets tracked by authenticated users.
    
    Allows users to save and monitor multiple wallet addresses.
    """
    __tablename__ = "tracked_wallets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_wallet = Column(String(44), ForeignKey("web_users.wallet_address"), nullable=False, index=True)
    tracked_address = Column(String(44), nullable=False)
    label = Column(String(100), nullable=True)
    
    added_at = Column(DateTime, default=datetime.utcnow)
    last_synced = Column(DateTime, nullable=True)
    token_count = Column(Integer, default=0)
    total_value_usd = Column(Float, default=0.0)

    # Unique constraint: one user can't track the same wallet twice
    __table_args__ = (
        # Using a unique constraint instead of Index for composite uniqueness
        {'sqlite_autoincrement': True},
    )


class WhaleTransaction(Base):
    """Persisted whale transactions for the 24h rolling Smart Money feed."""
    __tablename__ = "whale_transactions"

    signature = Column(String(128), primary_key=True)
    wallet_address = Column(String(44), nullable=False, index=True)
    wallet_label = Column(String(128), nullable=True)
    token_address = Column(String(44), nullable=False)
    token_symbol = Column(String(32), nullable=False)
    token_name = Column(String(128), nullable=False)
    direction = Column(String(8), nullable=False, index=True)
    amount_usd = Column(Float, nullable=False)
    amount_tokens = Column(Float, nullable=False)
    price_usd = Column(Float, nullable=False)
    dex_name = Column(String(64), nullable=False)
    tx_timestamp = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class TransactionCache(Base):
    """Cached parsed transaction history per wallet. TTL-based to reduce Helius calls."""
    __tablename__ = "transaction_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_address = Column(String(64), index=True, nullable=False)
    chain = Column(String(16), nullable=False, default="solana")
    transactions_json = Column(JSON, nullable=False, default=list)
    fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

class Database:
    """
    Async database interface for Ilyon AI.

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

        Tries PostgreSQL first, falls back to local SQLite for development.
        Should be called once at startup.
        """
        if self._initialized:
            return

        # Try PostgreSQL first
        if self.database_url:
            try:
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

                # Test connection and create tables
                async with self.engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)

                self._initialized = True
                logger.info("✅ Database initialized (PostgreSQL)")
                return

            except Exception as e:
                logger.warning(f"PostgreSQL unavailable ({e}), falling back to SQLite")
                if self.engine:
                    await self.engine.dispose()
                    self.engine = None

        # Fallback to local SQLite
        try:
            import os
            db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
            os.makedirs(db_dir, exist_ok=True)
            sqlite_path = os.path.join(db_dir, "sentinel.db")

            self.engine = create_async_engine(
                f"sqlite+aiosqlite:///{sqlite_path}",
                echo=False,
            )
            self.async_session = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            self._initialized = True
            logger.info(f"✅ Database initialized (SQLite: {sqlite_path})")

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
    # WEB ANALYSIS TRACKING (for dashboard stats)
    # ═══════════════════════════════════════════════════════════════════════════

    async def track_web_analysis(
        self,
        token_address: str,
        token_symbol: Optional[str] = None,
        token_name: Optional[str] = None,
        overall_score: Optional[int] = None,
        grade: Optional[str] = None,
        source: str = "web"
    ) -> bool:
        """
        Record a web-based token analysis.

        Args:
            token_address: Token address analyzed
            token_symbol: Token symbol
            token_name: Token name
            overall_score: Analysis score
            grade: Letter grade
            source: Source of analysis (web, api, telegram)

        Returns:
            True if successful
        """
        if not self._initialized:
            return False

        try:
            async with self.async_session() as session:
                analysis = WebAnalysis(
                    token_address=token_address,
                    token_symbol=token_symbol,
                    token_name=token_name,
                    overall_score=overall_score,
                    grade=grade,
                    source=source
                )
                session.add(analysis)
                await session.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to track web analysis: {e}")
            return False

    async def count_analyses_last_24h(self) -> int:
        """Count total analyses performed in the last 24 hours (all sources)."""
        if not self._initialized:
            return 0

        try:
            async with self.async_session() as session:
                cutoff = datetime.utcnow() - timedelta(hours=24)

                # Count from both Analysis (Telegram) and WebAnalysis tables
                telegram_result = await session.execute(
                    select(func.count(Analysis.id))
                    .where(Analysis.created_at >= cutoff)
                )
                telegram_count = telegram_result.scalar() or 0

                web_result = await session.execute(
                    select(func.count(WebAnalysis.id))
                    .where(WebAnalysis.analyzed_at >= cutoff)
                )
                web_count = web_result.scalar() or 0

                return telegram_count + web_count
        except Exception as e:
            logger.error(f"Failed to count analyses: {e}")
            return 0

    async def count_total_analyses(self) -> int:
        """Count total analyses performed all time."""
        if not self._initialized:
            return 0

        try:
            async with self.async_session() as session:
                telegram_result = await session.execute(select(func.count(Analysis.id)))
                telegram_count = telegram_result.scalar() or 0

                web_result = await session.execute(select(func.count(WebAnalysis.id)))
                web_count = web_result.scalar() or 0

                return telegram_count + web_count
        except Exception as e:
            logger.error(f"Failed to count total analyses: {e}")
            return 0

    async def get_grade_distribution(self) -> Dict[str, int]:
        """Get distribution of analysis grades from real analyzed tokens."""
        if not self._initialized:
            return {}

        try:
            async with self.async_session() as session:
                result: Dict[str, int] = {}

                # From Telegram analyses
                tg_rows = await session.execute(
                    select(Analysis.grade, func.count(Analysis.id))
                    .where(Analysis.grade.isnot(None))
                    .group_by(Analysis.grade)
                )
                for grade, count in tg_rows:
                    result[grade] = result.get(grade, 0) + count

                # From Web analyses
                web_rows = await session.execute(
                    select(WebAnalysis.grade, func.count(WebAnalysis.id))
                    .where(WebAnalysis.grade.isnot(None))
                    .group_by(WebAnalysis.grade)
                )
                for grade, count in web_rows:
                    result[grade] = result.get(grade, 0) + count

                return result
        except Exception as e:
            logger.error(f"Failed to get grade distribution: {e}")
            return {}

    # ═══════════════════════════════════════════════════════════════════════════
    # STATS SNAPSHOTS (for change metrics)
    # ═══════════════════════════════════════════════════════════════════════════

    async def save_stats_snapshot(
        self,
        total_volume_24h: float = 0.0,
        active_tokens: int = 0,
        safe_tokens: int = 0,
        scams_detected: int = 0,
        tokens_analyzed: int = 0,
        total_liquidity: float = 0.0
    ) -> bool:
        """
        Save a stats snapshot for historical tracking.

        Should be called periodically (e.g., hourly) to enable
        calculation of change metrics.
        """
        if not self._initialized:
            return False

        try:
            async with self.async_session() as session:
                snapshot = StatsSnapshot(
                    total_volume_24h=total_volume_24h,
                    active_tokens=active_tokens,
                    safe_tokens=safe_tokens,
                    scams_detected=scams_detected,
                    tokens_analyzed=tokens_analyzed,
                    total_liquidity=total_liquidity
                )
                session.add(snapshot)
                await session.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to save stats snapshot: {e}")
            return False

    async def get_stats_snapshot_24h_ago(self) -> Optional[Dict[str, Any]]:
        """
        Get stats snapshot from approximately 24 hours ago.

        Returns the closest snapshot to 24h ago for calculating changes.
        """
        if not self._initialized:
            return None

        try:
            async with self.async_session() as session:
                target_time = datetime.utcnow() - timedelta(hours=24)
                
                # Get the snapshot closest to 24h ago
                result = await session.execute(
                    select(StatsSnapshot)
                    .where(StatsSnapshot.timestamp <= target_time)
                    .order_by(StatsSnapshot.timestamp.desc())
                    .limit(1)
                )
                snapshot = result.scalar_one_or_none()
                
                if snapshot:
                    return {
                        "total_volume_24h": snapshot.total_volume_24h,
                        "active_tokens": snapshot.active_tokens,
                        "safe_tokens": snapshot.safe_tokens,
                        "scams_detected": snapshot.scams_detected,
                        "tokens_analyzed": snapshot.tokens_analyzed,
                        "total_liquidity": snapshot.total_liquidity,
                        "timestamp": snapshot.timestamp
                    }
                return None
        except Exception as e:
            logger.error(f"Failed to get stats snapshot: {e}")
            return None

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
            stmt = pg_insert(WalletReputation).values(
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
            stmt = pg_insert(TokenDeployment).values(
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

    async def write_alert_audit_record(
        self,
        event_type: str,
        actor_id: str,
        trace_id: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Write an alert audit record to persistent storage."""
        if not self._initialized:
            return False

        async with self.async_session() as session:
            record = AlertAuditRecord(
                event_type=event_type,
                actor_id=actor_id,
                trace_id=trace_id,
                payload=payload or {},
            )
            session.add(record)
            await session.commit()
            return True

    async def fetch_latest_alert_audit_record(self, event_type: str) -> Optional[Dict[str, Any]]:
        """Fetch the latest alert audit record for the event type."""
        if not self._initialized:
            return None

        async with self.async_session() as session:
            result = await session.execute(
                select(AlertAuditRecord)
                .where(AlertAuditRecord.event_type == event_type)
                .order_by(AlertAuditRecord.created_at.desc())
                .limit(1)
            )
            record = result.scalar_one_or_none()
            if record is None:
                return None
            return {
                "event_type": record.event_type,
                "actor_id": record.actor_id,
                "trace_id": record.trace_id,
                "payload": record.payload or {},
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }

    # ═══════════════════════════════════════════════════════════════════════════
    # WEB USER MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_or_create_web_user(self, wallet_address: str) -> Optional[WebUser]:
        """
        Get or create a web user by wallet address.
        
        Args:
            wallet_address: Solana wallet address
            
        Returns:
            WebUser object or None if database not available
        """
        if not self._initialized:
            return None

        async with self.async_session() as session:
            result = await session.execute(
                select(WebUser).where(WebUser.wallet_address == wallet_address)
            )
            user = result.scalar_one_or_none()

            if user:
                user.last_login = datetime.utcnow()
                await session.commit()
                return user

            # Create new user
            user = WebUser(
                wallet_address=wallet_address,
                last_login=datetime.utcnow()
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            logger.info(f"New web user created: {wallet_address[:8]}...")
            return user

    async def get_web_user(self, wallet_address: str) -> Optional[WebUser]:
        """Get web user by wallet address."""
        if not self._initialized:
            return None

        async with self.async_session() as session:
            result = await session.execute(
                select(WebUser).where(WebUser.wallet_address == wallet_address)
            )
            return result.scalar_one_or_none()

    async def increment_web_user_analyses(self, wallet_address: str) -> bool:
        """Increment analyses count for web user."""
        if not self._initialized:
            return False

        async with self.async_session() as session:
            await session.execute(
                update(WebUser)
                .where(WebUser.wallet_address == wallet_address)
                .values(analyses_count=WebUser.analyses_count + 1)
            )
            await session.commit()
            return True

    # ═══════════════════════════════════════════════════════════════════════════
    # SESSION MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    async def create_user_session(
        self,
        token: str,
        wallet_address: str,
        expires_at: datetime
    ) -> Optional[UserSession]:
        """
        Create a new user session.
        
        Args:
            token: Session token
            wallet_address: User's wallet address
            expires_at: Session expiration datetime
            
        Returns:
            Created UserSession or None
        """
        if not self._initialized:
            return None

        # Ensure user exists
        await self.get_or_create_web_user(wallet_address)

        async with self.async_session() as session:
            user_session = UserSession(
                token=token,
                wallet_address=wallet_address,
                expires_at=expires_at
            )
            session.add(user_session)
            await session.commit()
            await session.refresh(user_session)
            return user_session

    async def get_user_session(self, token: str) -> Optional[UserSession]:
        """Get session by token."""
        if not self._initialized:
            return None

        async with self.async_session() as session:
            result = await session.execute(
                select(UserSession).where(UserSession.token == token)
            )
            return result.scalar_one_or_none()

    async def update_session_last_used(self, token: str) -> bool:
        """Update session last_used timestamp."""
        if not self._initialized:
            return False

        async with self.async_session() as session:
            await session.execute(
                update(UserSession)
                .where(UserSession.token == token)
                .values(last_used=datetime.utcnow())
            )
            await session.commit()
            return True

    async def extend_user_session(self, token: str, new_expires_at: datetime) -> bool:
        """Extend session expiration."""
        if not self._initialized:
            return False

        async with self.async_session() as session:
            await session.execute(
                update(UserSession)
                .where(UserSession.token == token)
                .values(
                    expires_at=new_expires_at,
                    last_used=datetime.utcnow()
                )
            )
            await session.commit()
            return True

    async def delete_user_session(self, token: str) -> bool:
        """Delete a session."""
        if not self._initialized:
            return False

        async with self.async_session() as session:
            await session.execute(
                select(UserSession).where(UserSession.token == token)
            )
            # Delete using raw SQL since we need to delete by token
            from sqlalchemy import delete
            await session.execute(
                delete(UserSession).where(UserSession.token == token)
            )
            await session.commit()
            return True

    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions."""
        if not self._initialized:
            return 0

        async with self.async_session() as session:
            from sqlalchemy import delete
            result = await session.execute(
                delete(UserSession).where(UserSession.expires_at < datetime.utcnow())
            )
            await session.commit()
            return result.rowcount or 0

    # ═══════════════════════════════════════════════════════════════════════════
    # TRACKED WALLETS
    # ═══════════════════════════════════════════════════════════════════════════

    async def add_tracked_wallet(
        self,
        owner_wallet: str,
        tracked_address: str,
        label: Optional[str] = None
    ) -> Optional[TrackedWallet]:
        """
        Add a wallet to track for a user.
        
        Args:
            owner_wallet: User's wallet address
            tracked_address: Wallet address to track
            label: Optional label for the wallet
            
        Returns:
            Created TrackedWallet or None
        """
        if not self._initialized:
            return None

        # Ensure user exists
        await self.get_or_create_web_user(owner_wallet)

        async with self.async_session() as session:
            # Check if already tracking
            result = await session.execute(
                select(TrackedWallet).where(
                    TrackedWallet.owner_wallet == owner_wallet,
                    TrackedWallet.tracked_address == tracked_address
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                # Update label if provided
                if label:
                    existing.label = label
                    await session.commit()
                return existing

            # Create new tracked wallet
            tracked = TrackedWallet(
                owner_wallet=owner_wallet,
                tracked_address=tracked_address,
                label=label
            )
            session.add(tracked)

            # Update user's tracked wallet count
            await session.execute(
                update(WebUser)
                .where(WebUser.wallet_address == owner_wallet)
                .values(tracked_wallets_count=WebUser.tracked_wallets_count + 1)
            )

            await session.commit()
            await session.refresh(tracked)
            return tracked

    async def get_tracked_wallets(self, owner_wallet: str) -> List[TrackedWallet]:
        """Get all wallets tracked by a user."""
        if not self._initialized:
            return []

        async with self.async_session() as session:
            result = await session.execute(
                select(TrackedWallet)
                .where(TrackedWallet.owner_wallet == owner_wallet)
                .order_by(TrackedWallet.added_at.desc())
            )
            return list(result.scalars().all())

    async def remove_tracked_wallet(self, owner_wallet: str, tracked_address: str) -> bool:
        """Remove a tracked wallet."""
        if not self._initialized:
            return False

        async with self.async_session() as session:
            from sqlalchemy import delete
            result = await session.execute(
                delete(TrackedWallet).where(
                    TrackedWallet.owner_wallet == owner_wallet,
                    TrackedWallet.tracked_address == tracked_address
                )
            )
            
            if result.rowcount and result.rowcount > 0:
                # Update user's tracked wallet count
                await session.execute(
                    update(WebUser)
                    .where(WebUser.wallet_address == owner_wallet)
                    .values(tracked_wallets_count=WebUser.tracked_wallets_count - 1)
                )
            
            await session.commit()
            return (result.rowcount or 0) > 0

    async def update_tracked_wallet_stats(
        self,
        owner_wallet: str,
        tracked_address: str,
        token_count: int,
        total_value_usd: float
    ) -> bool:
        """Update tracked wallet statistics."""
        if not self._initialized:
            return False

        async with self.async_session() as session:
            await session.execute(
                update(TrackedWallet)
                .where(
                    TrackedWallet.owner_wallet == owner_wallet,
                    TrackedWallet.tracked_address == tracked_address
                )
                .values(
                    token_count=token_count,
                    total_value_usd=total_value_usd,
                    last_synced=datetime.utcnow()
                )
            )
            await session.commit()
            return True

    # ── Whale Transaction Methods ─────────────────────────────────────────────

    async def insert_whale_transactions(self, transactions: list) -> list:
        """Insert whale transactions, skipping duplicates. Returns list of new signatures."""
        if not self._initialized:
            return []
        new_signatures = []
        is_pg = str(self.engine.url).startswith("postgresql")
        async with self.async_session() as session:
            for tx in transactions:
                try:
                    ts = tx.get("timestamp")
                    if isinstance(ts, datetime):
                        tx_timestamp = ts
                    elif isinstance(ts, (int, float)):
                        tx_timestamp = datetime.utcfromtimestamp(ts)
                    elif isinstance(ts, str):
                        try:
                            tx_timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                        except Exception:
                            tx_timestamp = datetime.utcnow()
                    else:
                        tx_timestamp = datetime.utcnow()

                    values = dict(
                        signature=tx["signature"],
                        wallet_address=tx.get("wallet_address", ""),
                        wallet_label=tx.get("wallet_label"),
                        token_address=tx.get("token_address", ""),
                        token_symbol=tx.get("token_symbol", "???"),
                        token_name=tx.get("token_name", "Unknown"),
                        direction="buy" if tx.get("type", "buy") == "buy" else "sell",
                        amount_usd=float(tx.get("amount_usd", 0)),
                        amount_tokens=float(tx.get("amount_tokens", 0)),
                        price_usd=float(tx.get("price_usd", 0)),
                        dex_name=tx.get("dex_name", "Unknown"),
                        tx_timestamp=tx_timestamp,
                    )

                    if is_pg:
                        stmt = pg_insert(WhaleTransaction).values(**values).on_conflict_do_nothing(index_elements=["signature"])
                    else:
                        # SQLite / other dialects: INSERT OR IGNORE via prefix
                        from sqlalchemy import insert as sa_insert
                        stmt = sa_insert(WhaleTransaction).values(**values).prefix_with("OR IGNORE")

                    result = await session.execute(stmt)
                    if result.rowcount and result.rowcount > 0:
                        new_signatures.append(tx["signature"])
                except Exception as e:
                    logger.debug(f"Failed to insert whale tx {tx.get('signature', '?')}: {e}")
            await session.commit()
        return new_signatures

    async def get_whale_overview(self, hours: int = 24, limit: int = 200) -> dict:
        """Query whale transactions for the smart money overview."""
        if not self._initialized:
            return {"transactions": [], "inflow_usd": 0, "outflow_usd": 0}
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        async with self.async_session() as session:
            stmt = select(WhaleTransaction).where(
                WhaleTransaction.created_at >= cutoff
            ).order_by(WhaleTransaction.tx_timestamp.desc()).limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()

            transactions = []
            inflow_usd = 0.0
            outflow_usd = 0.0
            for row in rows:
                tx_dict = {
                    "signature": row.signature,
                    "wallet_address": row.wallet_address,
                    "wallet_label": row.wallet_label,
                    "token_address": row.token_address,
                    "token_symbol": row.token_symbol,
                    "token_name": row.token_name,
                    "direction": "inflow" if row.direction == "buy" else "outflow",
                    "amount_usd": row.amount_usd,
                    "amount_tokens": row.amount_tokens,
                    "price_usd": row.price_usd,
                    "dex_name": row.dex_name,
                    "timestamp": row.tx_timestamp.isoformat() if row.tx_timestamp else "",
                    "chain": "solana",
                }
                transactions.append(tx_dict)
                if row.direction == "buy":
                    inflow_usd += row.amount_usd
                else:
                    outflow_usd += row.amount_usd

            return {
                "transactions": transactions,
                "inflow_usd": inflow_usd,
                "outflow_usd": outflow_usd,
            }

    async def get_whale_unresolved_token_addresses(self, limit: int = 500) -> list[str]:
        """Return distinct token addresses from whale rows whose symbol is '???'.

        Used to backfill token metadata for rows that were persisted before the
        DexScreener enrichment step ran (e.g., via the RPC poll path).
        """
        if not self._initialized:
            return []
        async with self.async_session() as session:
            stmt = (
                select(WhaleTransaction.token_address)
                .where(WhaleTransaction.token_symbol == "???")
                .where(WhaleTransaction.token_address != "")
                .distinct()
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [r[0] for r in result.all() if r[0]]

    async def update_whale_token_metadata(self, token_address: str, symbol: str, name: str) -> int:
        """Set symbol/name on every whale row matching `token_address`. Returns row count."""
        if not self._initialized:
            return 0
        if not token_address:
            return 0
        from sqlalchemy import update as sa_update
        async with self.async_session() as session:
            stmt = (
                sa_update(WhaleTransaction)
                .where(WhaleTransaction.token_address == token_address)
                .values(token_symbol=symbol or "???", token_name=name or "Unknown")
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount or 0

    async def cleanup_old_whale_transactions(self, hours: int = 24) -> int:
        """Delete whale transactions older than the given window. Returns count deleted."""
        if not self._initialized:
            return 0
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        async with self.async_session() as session:
            from sqlalchemy import delete
            stmt = delete(WhaleTransaction).where(WhaleTransaction.created_at < cutoff)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount or 0

    async def cleanup_non_alpha_whale_transactions(self) -> int:
        """Delete whale rows whose token is a stablecoin, bridged major, or LST.

        Applies the mint- and symbol-level exclusion lists from
        `src.data.token_filters` so rows inserted before the filter existed
        disappear from the UI on stream startup.
        """
        if not self._initialized:
            return 0
        from src.data.token_filters import EXCLUDED_MINTS, EXCLUDED_SYMBOL_RE
        from sqlalchemy import delete
        async with self.async_session() as session:
            mint_stmt = delete(WhaleTransaction).where(
                WhaleTransaction.token_address.in_(list(EXCLUDED_MINTS))
            )
            mint_res = await session.execute(mint_stmt)

            rows_stmt = select(WhaleTransaction.id, WhaleTransaction.token_symbol)
            rows = (await session.execute(rows_stmt)).all()
            bad_ids = [
                rid for rid, sym in rows
                if sym and sym != "???" and EXCLUDED_SYMBOL_RE.match(sym.strip())
            ]
            sym_deleted = 0
            if bad_ids:
                sym_stmt = delete(WhaleTransaction).where(WhaleTransaction.id.in_(bad_ids))
                sym_res = await session.execute(sym_stmt)
                sym_deleted = sym_res.rowcount or 0
            await session.commit()
            return (mint_res.rowcount or 0) + sym_deleted

    async def get_whale_aggregations(self, hours: int) -> dict:
        """Return window rows and prior-window token set for the leaderboard.

        Returns:
            {
                "rows": [ {signature, wallet_address, wallet_label, token_address,
                           token_symbol, token_name, direction, amount_usd,
                           tx_timestamp}, ... ],
                "prior_token_addresses": set[str]  # tokens active in (2*window..window) ago
            }
        """
        if not self._initialized:
            return {"rows": [], "prior_token_addresses": set()}
        now = datetime.utcnow()
        window_cutoff = now - timedelta(hours=hours)
        prior_cutoff = now - timedelta(hours=hours * 2)
        async with self.async_session() as session:
            stmt_window = (
                select(WhaleTransaction)
                .where(WhaleTransaction.tx_timestamp >= window_cutoff)
                .order_by(WhaleTransaction.tx_timestamp.desc())
            )
            result = await session.execute(stmt_window)
            window_rows = result.scalars().all()

            stmt_prior = (
                select(WhaleTransaction.token_address)
                .where(
                    WhaleTransaction.tx_timestamp >= prior_cutoff,
                    WhaleTransaction.tx_timestamp < window_cutoff,
                )
                .distinct()
            )
            prior_result = await session.execute(stmt_prior)
            prior_tokens = {row[0] for row in prior_result.all()}

            rows = [
                {
                    "signature": r.signature,
                    "wallet_address": r.wallet_address,
                    "wallet_label": r.wallet_label,
                    "token_address": r.token_address,
                    "token_symbol": r.token_symbol,
                    "token_name": r.token_name,
                    "direction": r.direction,
                    "amount_usd": float(r.amount_usd),
                    "tx_timestamp": r.tx_timestamp,
                }
                for r in window_rows
            ]

            return {"rows": rows, "prior_token_addresses": prior_tokens}

    async def get_whale_transactions_for_wallet(self, wallet_address: str, hours: int = 24, limit: int = 50) -> list[dict]:
        """Query whale transactions for a specific wallet address."""
        if not self._initialized:
            return []
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        async with self.async_session() as session:
            stmt = (
                select(WhaleTransaction)
                .where(
                    WhaleTransaction.wallet_address == wallet_address,
                    WhaleTransaction.created_at >= cutoff,
                )
                .order_by(WhaleTransaction.tx_timestamp.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            transactions = []
            for row in rows:
                transactions.append({
                    "signature": row.signature,
                    "wallet_address": row.wallet_address,
                    "wallet_label": row.wallet_label,
                    "token_address": row.token_address,
                    "token_symbol": row.token_symbol,
                    "token_name": row.token_name,
                    "direction": "inflow" if row.direction == "buy" else "outflow",
                    "amount_usd": row.amount_usd,
                    "amount_tokens": row.amount_tokens,
                    "price_usd": row.price_usd,
                    "dex_name": row.dex_name,
                    "timestamp": row.tx_timestamp.isoformat() if row.tx_timestamp else "",
                })
            return transactions

    async def get_cached_transactions(self, wallet_address: str, chain: str = "solana", max_age_seconds: int = 300) -> Optional[list]:
        """Return cached transactions if fresh enough, else None."""
        if not self._initialized:
            return None
        cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds)
        async with self.async_session() as session:
            result = await session.execute(
                select(TransactionCache)
                .where(
                    TransactionCache.wallet_address == wallet_address,
                    TransactionCache.chain == chain,
                    TransactionCache.fetched_at >= cutoff,
                )
                .order_by(TransactionCache.fetched_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row:
                return row.transactions_json
        return None

    async def set_cached_transactions(self, wallet_address: str, chain: str, transactions: list) -> None:
        """Upsert transaction cache for a wallet."""
        if not self._initialized:
            return
        async with self.async_session() as session:
            from sqlalchemy import delete
            await session.execute(
                delete(TransactionCache).where(
                    TransactionCache.wallet_address == wallet_address,
                    TransactionCache.chain == chain,
                )
            )
            session.add(TransactionCache(
                wallet_address=wallet_address,
                chain=chain,
                transactions_json=transactions,
                fetched_at=datetime.utcnow(),
            ))
            await session.commit()

    async def get_cached_contract_scan(self, chain: str, address: str) -> Optional[dict]:
        if not self._initialized:
            return None
        async with self.async_session() as session:
            result = await session.execute(
                select(ContractScanCache.result_json)
                .where(ContractScanCache.chain == chain, ContractScanCache.address == address)
                .order_by(ContractScanCache.scanned_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return row

    async def set_cached_contract_scan(self, chain: str, address: str, result: dict) -> None:
        if not self._initialized:
            return
        async with self.async_session() as session:
            from sqlalchemy import delete
            await session.execute(
                delete(ContractScanCache).where(
                    ContractScanCache.chain == chain,
                    ContractScanCache.address == address,
                )
            )
            session.add(ContractScanCache(
                chain=chain, address=address, result_json=result,
                scanned_at=datetime.utcnow(),
            ))
            await session.commit()

    async def get_token_safety_scores(self, token_addresses: list[str]) -> dict[str, dict]:
        """Batch lookup of most recent analysis scores for tokens.
        Returns {token_address: {"score": int, "grade": str}} for found tokens.
        """
        if not self._initialized or not token_addresses:
            return {}

        result = {}
        async with self.async_session() as session:
            from sqlalchemy import func as sqla_func
            # Batch query Blinks
            blink_subq = (
                select(
                    Blink.token_address,
                    sqla_func.max(Blink.created_at).label("latest"),
                )
                .where(Blink.token_address.in_(token_addresses), Blink.overall_score.isnot(None))
                .group_by(Blink.token_address)
                .subquery()
            )
            blink_rows = await session.execute(
                select(Blink.token_address, Blink.overall_score, Blink.grade)
                .join(blink_subq, (Blink.token_address == blink_subq.c.token_address) & (Blink.created_at == blink_subq.c.latest))
            )
            for addr, score, grade in blink_rows:
                if score is not None:
                    result[addr] = {"score": score, "grade": grade}

            # Fill gaps from WebAnalysis
            missing = [a for a in token_addresses if a not in result]
            if missing:
                web_subq = (
                    select(
                        WebAnalysis.token_address,
                        sqla_func.max(WebAnalysis.analyzed_at).label("latest"),
                    )
                    .where(WebAnalysis.token_address.in_(missing), WebAnalysis.overall_score.isnot(None))
                    .group_by(WebAnalysis.token_address)
                    .subquery()
                )
                web_rows = await session.execute(
                    select(WebAnalysis.token_address, WebAnalysis.overall_score, WebAnalysis.grade)
                    .join(web_subq, (WebAnalysis.token_address == web_subq.c.token_address) & (WebAnalysis.analyzed_at == web_subq.c.latest))
                )
                for addr, score, grade in web_rows:
                    if score is not None:
                        result[addr] = {"score": score, "grade": grade}

        return result


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


async def load_token_deployments(wallet_address: str) -> List[TokenDeployment]:
    """Load recent token deployments for a deployer wallet."""
    db = await get_database()
    return await db.get_wallet_deployments(wallet_address, limit=100)
