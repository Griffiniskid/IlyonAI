"""
Token scoring engine.

This module calculates risk scores based on multiple factors including
on-chain metrics, AI analysis, social presence, and contract quality.
"""

import logging
from typing import List, Tuple

from src.core.models import TokenInfo, AnalysisResult, RiskLevel

logger = logging.getLogger(__name__)


class TokenScorer:
    """
    AI-Primary Token Risk Scoring Engine.

    The AI score IS the final score. Metric scores (safety, liquidity, etc.)
    are calculated for display as context explaining why the AI scored as it did,
    but they do not mathematically combine into the final score.

    Scoring Flow:
        AI Analysis → Hard Cap Check → Final Score

    Hard Caps (only overrides):
        - Known scammer deployer: max 25
        - Already rugged: 0 (detected in Phase 1)

    Metric Scores (for display/context only):
        - Security: Contract safety indicators
        - Liquidity: Liquidity depth indicators
        - Distribution: Holder concentration indicators
        - Social: Social presence indicators
        - Activity: Trading health indicators
        - Deployer Reputation: Wallet forensics indicators
        - Behavioral Anomaly: Pattern detection indicators
    """

    # Weight configuration (totals 100%)
    # Updated to include advanced analytics and honeypot detection
    BASE_WEIGHTS = {
        'security': 0.20,
        'liquidity': 0.15,
        'distribution': 0.12,
        'social': 0.08,
        'activity': 0.08,
        'contract_quality': 0.07,
        'deployer_reputation': 0.10,   # High weight: bad deployers are fatal
        'behavioral_anomaly': 0.08,
        'honeypot': 0.12,              # High weight: cannot sell = worthless
    }

    def _get_weights(self) -> dict:
        """
        Get scoring weights.

        Returns:
            Dict with weights summing to 1.0
        """
        return self.BASE_WEIGHTS.copy()

    def calculate(self, token: TokenInfo) -> AnalysisResult:
        """
        Calculate all scores and produce final AnalysisResult.

        Args:
            token: TokenInfo with all data collected

        Returns:
            AnalysisResult with scores, grade, and recommendation
        """
        risks: List[str] = []
        goods: List[str] = []

        # ═══════════════════════════════════════════════════════════
        # PHASE 1: Detect Already Rugged Tokens (CRITICAL CHECK)
        # ═══════════════════════════════════════════════════════════

        is_rugged, rug_signals = self._check_if_rugged(token)
        if is_rugged:
            return self._create_rugged_result(token, rug_signals)

        # ═══════════════════════════════════════════════════════════
        # PHASE 2: Calculate Individual Scores
        # ═══════════════════════════════════════════════════════════

        safety_score, safety_risks, safety_goods = self._calc_safety(token)
        liquidity_score, liq_risks, liq_goods = self._calc_liquidity(token)
        distribution_score, dist_risks, dist_goods = self._calc_distribution(token)
        social_score, social_risks, social_goods = self._calc_social(token)
        activity_score, act_risks, act_goods = self._calc_activity(token)
        contract_score, contract_risks, contract_goods = self._calc_contract_quality(token)

        # NEW: Advanced analytics scoring
        deployer_score, deployer_risks, deployer_goods = self._calc_deployer_reputation(token)
        anomaly_score, anomaly_risks, anomaly_goods = self._calc_behavioral_anomaly(token)

        # Honeypot detection scoring
        honeypot_score, honeypot_risks, honeypot_goods = self._calc_honeypot(token)

        # Aggregate risks and goods
        risks.extend(safety_risks + liq_risks + dist_risks + social_risks + act_risks + contract_risks)
        risks.extend(deployer_risks + anomaly_risks + honeypot_risks)
        goods.extend(safety_goods + liq_goods + dist_goods + social_goods + act_goods + contract_goods)
        goods.extend(deployer_goods + anomaly_goods + honeypot_goods)

        # ═══════════════════════════════════════════════════════════
        # PHASE 3: Hybrid AI-Centric Scoring (Enhanced)
        # ═══════════════════════════════════════════════════════════
        #
        # The AI Score is the primary baseline (80-90% weight equivalent).
        # We apply OBJECTIVE BONUSES and PENALTIES to this baseline to ensure:
        # 1. Good tokens get the boost they deserve (e.g., LP locked, high reputation).
        # 2. Bad tokens get punished (e.g., mint enabled, low liquidity).
        #
        # This approach respects the AI's qualitative analysis while enforcing
        # strict mathematical standards for critical security metrics.

        base_score = token.ai_score
        adjustments = 0
        adjustment_reasons = []

        # --- BONUSES (Reward Good Behavior) ---

        # 1. Liquidity Lock (The most important safety feature)
        if token.liquidity_locked and token.lp_lock_percent >= 90:
            adjustments += 5
            adjustment_reasons.append("+5 LP Fully Locked")
        
        # 2. Perfect Security (No Mint/Freeze)
        if not token.mint_authority_enabled and not token.freeze_authority_enabled:
            adjustments += 5
            adjustment_reasons.append("+5 Contracts Renounced")

        # 3. Established History
        if token.age_hours > 168:  # 1 week
            adjustments += 2
            adjustment_reasons.append("+2 Established Token")

        # 4. Strong Socials (Website + Twitter + Telegram)
        if token.socials_count >= 3 and token.website_quality > 70:
            adjustments += 3
            adjustment_reasons.append("+3 Strong Social Presence")
            
        # 5. Doxxed/Reputable Deployer
        if deployer_score > 80:
            adjustments += 5
            adjustment_reasons.append("+5 High Rep Deployer")

        # --- PENALTIES (Punish Critical Risks) ---

        # 1. Mint Authority (Infinite inflation risk)
        if token.mint_authority_enabled:
            adjustments -= 20
            adjustment_reasons.append("-20 Mint Authority Enabled")

        # 2. Freeze Authority (Censorship risk)
        if token.freeze_authority_enabled:
            adjustments -= 10
            adjustment_reasons.append("-10 Freeze Authority Enabled")

        # 3. Unlocked Liquidity (Rug risk)
        if not token.liquidity_locked:
            adjustments -= 15
            adjustment_reasons.append("-15 LP Unlocked")
        elif token.lp_lock_percent < 50:
            adjustments -= 5
            adjustment_reasons.append("-5 Low LP Lock %")

        # 4. Suspicious Holder Concentration
        if distribution_score < 30: # derived from strict concentration metrics
            adjustments -= 10
            adjustment_reasons.append("-10 High Whale Concentration")

        # 5. Low Liquidity
        if liquidity_score < 30:
            adjustments -= 10
            adjustment_reasons.append("-10 Thin Liquidity")

        # Apply Adjustments
        overall = base_score + adjustments
        
        # Clamp Score (0-100)
        overall = max(0, min(100, overall))

        logger.info(
            f"📈 Scoring Calculation for {token.symbol}: "
            f"AI Base ({base_score}) + Adjustments ({adjustments}) = {overall} "
            f"| Reasons: {', '.join(adjustment_reasons)}"
        )


        # Add AI flags to risks/goods for display
        for flag in token.ai_red_flags[:5]:
            if flag and flag not in risks:
                risks.append(f"🤖 {flag}")

        for flag in token.ai_green_flags[:3]:
            if flag and flag not in goods:
                goods.append(f"🤖 {flag}")

        # ═══════════════════════════════════════════════════════════
        # PHASE 4: Apply ONLY Hard Caps (Minimal Overrides)
        # ═══════════════════════════════════════════════════════════
        #
        # AI has full authority. Only these overrides apply:

        # Hard cap 1: Known scammer deployer → max 25
        if token.deployer_is_known_scammer:
            original = overall
            overall = min(overall, 25)
            if original != overall:
                risks.append(f"⛔ KNOWN SCAMMER DEPLOYER - Score capped at 25 (was {original})")
                logger.warning(f"⛔ {token.symbol}: Known scammer detected, capping score from {original} to {overall}")

        # Hard cap 2: Confirmed honeypot → max 15
        if token.honeypot_is_honeypot:
            original = overall
            overall = min(overall, 15)
            if original != overall:
                risks.append(f"🍯 HONEYPOT DETECTED - Score capped at 15 (was {original})")
                logger.warning(f"🍯 {token.symbol}: HONEYPOT - capping score from {original} to {overall}")

        logger.info(f"🤖 AI-driven final score for {token.symbol}: {overall}")

        # ═══════════════════════════════════════════════════════════
        # PHASE 5: Determine Grade and Recommendation
        # ═══════════════════════════════════════════════════════════

        grade = self._calc_grade(overall)
        recommendation = self._calc_recommendation(overall, token)
        risk_level = self._calc_risk_level(overall)

        # Store in token
        token.risk_score = overall
        token.risk_level = risk_level
        token.risk_factors = risks[:10]  # Limit to top 10
        token.positive_factors = goods[:10]

        return AnalysisResult(
            token=token,
            safety_score=safety_score,
            liquidity_score=liquidity_score,
            distribution_score=distribution_score,
            social_score=social_score,
            activity_score=activity_score,
            deployer_reputation_score=deployer_score,
            behavioral_anomaly_score=anomaly_score,
            honeypot_score=honeypot_score,
            overall_score=overall,
            grade=grade,
            recommendation=recommendation,
            ai_analysis=token.ai_summary or ""
        )

    def _check_if_rugged(self, token: TokenInfo) -> Tuple[bool, List[str]]:
        """
        Check if token has already been rugged.

        Extracted from bot.py lines 1783-1840.

        Returns:
            (is_rugged, rug_signals) tuple
        """
        is_rugged = False
        rug_signals = []

        # Signal 1: No liquidity or critically low
        if token.liquidity_usd < 100:
            rug_signals.append(f"💀 Ликвидность почти 0 (${token.liquidity_usd:.0f})")
            is_rugged = True
        elif token.liquidity_usd < 500 and token.market_cap > 10000:
            rug_signals.append(f"💀 Ликвидность исчезла (${token.liquidity_usd:.0f} при MCap ${token.market_cap:,.0f})")
            is_rugged = True

        # Signal 2: Huge price dump
        if token.price_change_24h < -90:
            rug_signals.append(f"💀 Цена упала на {token.price_change_24h:.0f}% за 24h")
            is_rugged = True
        elif token.price_change_24h < -80 and token.liquidity_usd < 1000:
            rug_signals.append(f"💀 Обвал {token.price_change_24h:.0f}% + низкая ликвидность")
            is_rugged = True

        # Signal 3: No trading activity
        if token.volume_24h < 10 and token.age_hours > 24:
            rug_signals.append("💀 Нет торговли более 24 часов")
            if token.liquidity_usd < 1000:
                is_rugged = True

        # Signal 4: Anomalous MCap/Liquidity ratio
        if token.market_cap > 0 and token.liquidity_usd > 0:
            ratio = token.market_cap / token.liquidity_usd
            if ratio > 100 and token.liquidity_usd < 1000:
                rug_signals.append(f"💀 Аномальный MCap/Liq ratio: {ratio:.0f}x")
                is_rugged = True

        # Signal 5: Mass dump (sells >> buys)
        if token.sells_24h > 0 and token.buys_24h > 0:
            sell_ratio = token.sells_24h / token.buys_24h
            if sell_ratio > 10 and token.price_change_24h < -50:
                rug_signals.append(f"💀 Массовый дамп: {sell_ratio:.0f}x больше продаж")
                is_rugged = True

        return is_rugged, rug_signals

    def _create_rugged_result(self, token: TokenInfo, rug_signals: List[str]) -> AnalysisResult:
        """Create result for already rugged token"""
        logger.warning(f"💀 RUGGED TOKEN DETECTED: {token.symbol} | Signals: {len(rug_signals)}")

        token.risk_level = RiskLevel.CRITICAL
        token.risk_factors = rug_signals + ["⛔ ТОКЕН УЖЕ RUG PULLED!"]
        token.positive_factors = []

        return AnalysisResult(
            token=token,
            safety_score=0,
            liquidity_score=0,
            distribution_score=0,
            activity_score=0,
            social_score=0,
            overall_score=0,
            grade="F",
            recommendation="⛔ DEAD TOKEN — Already RUG PULLED! Do not buy!",
            ai_analysis="Token has already been rug pulled. Liquidity withdrawn."
        )

    def _calc_safety(self, token: TokenInfo) -> Tuple[int, List[str], List[str]]:
        """
        Calculate safety score (25% weight).

        Enhanced with RugCheck score integration and LP lock percentage.

        Returns:
            (score, risks, goods) tuple
        """
        safety = 100
        risks = []
        goods = []

        # ═══════════════════════════════════════════════════════════
        # AUTHORITY CHECKS
        # ═══════════════════════════════════════════════════════════

        # Mint authority check
        if token.mint_authority_enabled:
            safety -= 45
            risks.append("🚨 Mint Authority ENABLED (CRITICAL!)")
        else:
            safety += 5  # Small bonus for disabled
            goods.append("✅ Mint Authority отключен")

        # Freeze authority check
        if token.freeze_authority_enabled:
            safety -= 25
            risks.append("⚠️ Freeze Authority ENABLED")
        else:
            safety += 5  # Small bonus for disabled
            goods.append("✅ Freeze Authority отключен")

        # ═══════════════════════════════════════════════════════════
        # LP LOCK STATUS (with percentage consideration)
        # ═══════════════════════════════════════════════════════════

        if token.liquidity_locked:
            if token.lp_lock_percent >= 95:
                safety += 15
                goods.append(f"🔒 LP полностью заблокирован ({token.lp_lock_percent:.0f}%)")
            elif token.lp_lock_percent >= 80:
                safety += 10
                goods.append(f"🔒 LP заблокирован ({token.lp_lock_percent:.0f}%)")
            elif token.lp_lock_percent >= 50:
                safety += 5
                goods.append(f"🔒 LP частично заблокирован ({token.lp_lock_percent:.0f}%)")
            else:
                goods.append(f"🔒 LP заблокирован ({token.lp_lock_percent:.0f}%)")
        else:
            safety -= 20
            risks.append("🚨 LP НЕ ЗАЛОЧЕН!")

        # ═══════════════════════════════════════════════════════════
        # RUGCHECK SCORE INTEGRATION
        # ═══════════════════════════════════════════════════════════

        # RugCheck scoring: lower is better (0 = perfect, higher = more risk)
        if token.rugcheck_score > 0:
            if token.rugcheck_score >= 3000:
                safety -= 40
                risks.append(f"🔴 RugCheck: EXTREME RISK ({token.rugcheck_score})")
            elif token.rugcheck_score >= 1500:
                safety -= 30
                risks.append(f"🔴 RugCheck: HIGH RISK ({token.rugcheck_score})")
            elif token.rugcheck_score >= 800:
                safety -= 20
                risks.append(f"🟠 RugCheck: ELEVATED ({token.rugcheck_score})")
            elif token.rugcheck_score >= 400:
                safety -= 10
                risks.append(f"🟡 RugCheck: MODERATE ({token.rugcheck_score})")
            elif token.rugcheck_score < 100:
                safety += 15
                goods.append(f"✅ RugCheck: EXCELLENT ({token.rugcheck_score})")
            elif token.rugcheck_score < 200:
                safety += 10
                goods.append(f"✅ RugCheck: GOOD ({token.rugcheck_score})")

            # Add specific RugCheck risks
            for risk in (token.rugcheck_risks or [])[:2]:
                if risk and len(risk) < 80:
                    risks.append(f"⚠️ RC: {risk}")

        # ═══════════════════════════════════════════════════════════
        # TOKEN AGE CHECK
        # ═══════════════════════════════════════════════════════════

        if token.age_hours < 1:
            safety -= 30
            risks.append(f"🆕 ОЧЕНЬ НОВЫЙ ({token.age_hours:.1f}h) - ОПАСНО!")
        elif token.age_hours < 6:
            safety -= 20
            risks.append(f"⚠️ Новый токен ({token.age_hours:.1f}h)")
        elif token.age_hours < 24:
            safety -= 10
        elif token.age_hours >= 720:  # 30+ days
            safety += 10
            goods.append("✅ Токену > 30 дней")
        elif token.age_hours >= 168:  # 7+ days
            safety += 5
            goods.append("✅ Токену > 7 дней")

        return max(0, min(100, safety)), risks, goods

    def _calc_liquidity(self, token: TokenInfo) -> Tuple[int, List[str], List[str]]:
        """
        Calculate liquidity score (20% weight).

        Enhanced with multi-factor analysis including depth, MCap ratio, and lock quality.
        Starts at neutral 50 and adjusts based on actual metrics.

        Returns:
            (score, risks, goods) tuple
        """
        risks = []
        goods = []

        liq_usd = token.liquidity_usd

        # ═══════════════════════════════════════════════════════════
        # BASE SCORE - Start at 50 (neutral) and adjust based on data
        # ═══════════════════════════════════════════════════════════

        liq = 50

        # ═══════════════════════════════════════════════════════════
        # ABSOLUTE LIQUIDITY DEPTH - up to +/- 25 points
        # ═══════════════════════════════════════════════════════════

        if liq_usd < 500:
            liq -= 25
            risks.append(f"💧 CRITICAL: Liquidity only ${liq_usd:,.0f}")
        elif liq_usd < 1000:
            liq -= 20
            risks.append(f"💧 Dangerously low liquidity (${liq_usd:,.0f})")
        elif liq_usd < 5000:
            liq -= 15
            risks.append(f"⚠️ Low liquidity (${liq_usd:,.0f})")
        elif liq_usd < 10000:
            liq -= 10
            risks.append(f"⚠️ Below average liquidity (${liq_usd:,.0f})")
        elif liq_usd < 20000:
            liq -= 5
        elif liq_usd >= 500000:
            liq += 25
            goods.append(f"✅ Excellent liquidity (${liq_usd:,.0f})")
        elif liq_usd >= 100000:
            liq += 20
            goods.append(f"✅ Strong liquidity (${liq_usd:,.0f})")
        elif liq_usd >= 50000:
            liq += 15
            goods.append(f"✅ Good liquidity (${liq_usd:,.0f})")
        elif liq_usd >= 20000:
            liq += 10
            goods.append("✅ Acceptable liquidity depth")

        # ═══════════════════════════════════════════════════════════
        # LIQUIDITY / MARKET CAP RATIO - up to +/- 15 points
        # ═══════════════════════════════════════════════════════════

        if token.market_cap > 0 and liq_usd > 0:
            liq_mcap_ratio = liq_usd / token.market_cap

            if liq_mcap_ratio < 0.01:
                liq -= 15
                risks.append(f"⚠️ Dangerous liquidity ratio ({liq_mcap_ratio*100:.2f}% of MCap)")
            elif liq_mcap_ratio < 0.03:
                liq -= 10
                risks.append(f"⚠️ Low liquidity ratio ({liq_mcap_ratio*100:.2f}% of MCap)")
            elif liq_mcap_ratio < 0.05:
                liq -= 5
                risks.append(f"⚠️ Below average ratio ({liq_mcap_ratio*100:.1f}%)")
            elif liq_mcap_ratio >= 0.20:
                liq += 15
                goods.append(f"✅ Strong liquidity ratio ({liq_mcap_ratio*100:.1f}% of MCap)")
            elif liq_mcap_ratio >= 0.15:
                liq += 10
                goods.append(f"✅ Healthy liquidity ratio ({liq_mcap_ratio*100:.1f}%)")
            elif liq_mcap_ratio >= 0.10:
                liq += 5
                goods.append("✅ Good liquidity ratio")

        # ═══════════════════════════════════════════════════════════
        # LP LOCK STATUS - up to +/- 20 points (most important factor)
        # ═══════════════════════════════════════════════════════════

        if token.liquidity_locked:
            lock_pct = token.lp_lock_percent

            if lock_pct >= 95:
                liq += 20
                goods.append(f"🔒 LP fully locked ({lock_pct:.0f}%)")
            elif lock_pct >= 80:
                liq += 15
                goods.append(f"🔒 LP mostly locked ({lock_pct:.0f}%)")
            elif lock_pct >= 60:
                liq += 10
                goods.append(f"🔒 LP partially locked ({lock_pct:.0f}%)")
            elif lock_pct >= 40:
                liq += 5
                risks.append(f"⚠️ Only {lock_pct:.0f}% LP locked")
            elif lock_pct > 0:
                liq += 2
                risks.append(f"⚠️ Minimal LP lock ({lock_pct:.0f}%)")
            else:
                # Locked but percentage unknown - give minimal bonus, not full credit
                liq += 5
                goods.append("🔒 LP locked (% unknown)")
        else:
            liq -= 20
            risks.append("🚨 LP NOT LOCKED — high rug risk!")

        # ═══════════════════════════════════════════════════════════
        # SLIPPAGE RISK (Volume vs Liquidity) - up to +/- 10 points
        # ═══════════════════════════════════════════════════════════

        if liq_usd > 0 and token.volume_24h > 0:
            vol_liq_ratio = token.volume_24h / liq_usd

            if vol_liq_ratio > 10:
                liq -= 10
                risks.append(f"⚠️ Extreme slippage risk (vol {vol_liq_ratio:.0f}x liquidity)")
            elif vol_liq_ratio > 5:
                liq -= 7
                risks.append("⚠️ High slippage risk")
            elif vol_liq_ratio > 3:
                liq -= 3
            elif vol_liq_ratio < 0.5:
                liq += 5
                goods.append("✅ Low slippage risk")
            elif vol_liq_ratio < 1.0:
                liq += 2

        return max(0, min(100, liq)), risks, goods

    def _calc_distribution(self, token: TokenInfo) -> Tuple[int, List[str], List[str]]:
        """
        Calculate distribution score (15% weight).

        Enhanced with AI whale risk analysis integration.

        Returns:
            (score, risks, goods) tuple
        """
        risks = []
        goods = []

        # ═══════════════════════════════════════════════════════════
        # CHECK DATA AVAILABILITY FIRST
        # ═══════════════════════════════════════════════════════════

        conc = token.holder_concentration
        top1 = token.top_holder_pct
        has_holder_data = len(token.top_holders) > 0

        # If no holder data available, return a low score with major penalty
        if not has_holder_data or (conc == 0 and top1 == 0):
            risks.append("🚨 Holder data unavailable - cannot verify distribution")
            risks.append("⚠️ Unable to assess whale concentration risk")
            # Return a low score when data is missing - this is a significant risk
            return 35, risks, []

        # ═══════════════════════════════════════════════════════════
        # BASE SCORE - Start at 50 (neutral) and adjust based on data
        # ═══════════════════════════════════════════════════════════

        dist = 50  # Start neutral, not optimistic

        # ═══════════════════════════════════════════════════════════
        # TOP-10 HOLDER CONCENTRATION (Primary Factor) - up to +/- 30
        # ═══════════════════════════════════════════════════════════

        if conc > 95:
            dist -= 30
            risks.append(f"🐋 EXTREME: top-10 = {conc:.0f}%!")
        elif conc > 90:
            dist -= 25
            risks.append(f"🐋 Critical concentration: top-10 = {conc:.0f}%")
        elif conc > 80:
            dist -= 20
            risks.append(f"⚠️ High concentration: top-10 = {conc:.0f}%")
        elif conc > 70:
            dist -= 15
            risks.append(f"⚠️ Elevated concentration: top-10 = {conc:.0f}%")
        elif conc > 60:
            dist -= 10
            risks.append(f"⚠️ Moderate concentration: top-10 = {conc:.0f}%")
        elif conc > 50:
            dist -= 5
        elif conc <= 30:
            dist += 30
            goods.append(f"✅ Excellent distribution (top-10 = {conc:.0f}%)")
        elif conc <= 40:
            dist += 20
            goods.append(f"✅ Good distribution (top-10 = {conc:.0f}%)")
        elif conc <= 50:
            dist += 10
            goods.append("✅ Acceptable distribution")

        # ═══════════════════════════════════════════════════════════
        # TOP-1 HOLDER (DEV WALLET RISK) - up to +/- 25
        # ═══════════════════════════════════════════════════════════

        if top1 > 50:
            dist -= 25
            risks.append(f"🚨 EXTREME top-1: {top1:.1f}%!")
        elif top1 > 30:
            dist -= 20
            risks.append(f"🚨 High top-1 concentration: {top1:.1f}%")
        elif top1 > 20:
            dist -= 15
            risks.append(f"⚠️ Elevated top-1: {top1:.1f}%")
        elif top1 > 15:
            dist -= 10
            risks.append(f"⚠️ Above average top-1: {top1:.1f}%")
        elif top1 > 10:
            dist -= 5
        elif top1 > 0 and top1 < 3:
            dist += 15
            goods.append(f"✅ Very low top holder ({top1:.1f}%)")
        elif top1 > 0 and top1 < 5:
            dist += 10
            goods.append(f"✅ Low top holder ({top1:.1f}%)")
        elif top1 > 0 and top1 < 10:
            dist += 5
            goods.append(f"✅ Reasonable top holder ({top1:.1f}%)")

        # ═══════════════════════════════════════════════════════════
        # HOLDER DISPARITY RATIO (top-1 dominance of top-10)
        # ═══════════════════════════════════════════════════════════

        if conc > 0 and top1 > 0:
            top1_ratio = top1 / conc
            if top1_ratio > 0.7:
                dist -= 10
                risks.append(f"🐋 Top-1 dominates ({top1_ratio*100:.0f}% of top-10)")
            elif top1_ratio > 0.5:
                dist -= 5
            elif top1_ratio < 0.2:
                dist += 5
                goods.append("✅ Well-distributed among top holders")

        # ═══════════════════════════════════════════════════════════
        # SUSPICIOUS WALLETS
        # ═══════════════════════════════════════════════════════════

        if token.suspicious_wallets >= 5:
            dist -= 25
            risks.append(f"🚨 {token.suspicious_wallets} suspicious wallets — likely manipulation!")
        elif token.suspicious_wallets >= 3:
            dist -= 15
            risks.append(f"⚠️ {token.suspicious_wallets} suspicious wallets detected")
        elif token.suspicious_wallets >= 1:
            dist -= 8
            risks.append(f"⚠️ {token.suspicious_wallets} suspicious wallet(s)")
        elif token.suspicious_wallets == 0 and has_holder_data:
            dist += 5
            goods.append("✅ No suspicious wallets detected")

        # ═══════════════════════════════════════════════════════════
        # AI WHALE RISK INTEGRATION
        # ═══════════════════════════════════════════════════════════

        if token.ai_whale_risk:
            whale_text = token.ai_whale_risk.lower()
            if any(word in whale_text for word in ['critical', 'extreme', 'very high', 'dangerous']):
                dist -= 15
                risks.append("🐋 AI: Critical whale concentration detected")
            elif any(word in whale_text for word in ['high', 'elevated', 'significant']):
                dist -= 10
                risks.append("🐋 AI: High whale risk")
            elif any(word in whale_text for word in ['low', 'minimal', 'healthy', 'distributed']):
                dist += 10
                goods.append("🤖 AI: Healthy token distribution")

        # Add holder flags (max 2)
        for flag in (token.holder_flags or [])[:2]:
            if flag and flag not in risks:
                risks.append(flag)

        return max(0, min(100, dist)), risks, goods

    def _calc_activity(self, token: TokenInfo) -> Tuple[int, List[str], List[str]]:
        """
        Calculate activity score (10% weight).

        Enhanced with multi-timeframe price momentum analysis and volume metrics.
        Starts at neutral 50 and adjusts based on actual metrics.

        Returns:
            (score, risks, goods) tuple
        """
        risks = []
        goods = []

        # ═══════════════════════════════════════════════════════════
        # BASE SCORE - Start at 50 (neutral) and adjust based on data
        # ═══════════════════════════════════════════════════════════

        act = 50

        # ═══════════════════════════════════════════════════════════
        # VOLUME / MARKET CAP RATIO - up to +/- 15 points
        # ═══════════════════════════════════════════════════════════

        if token.market_cap > 0 and token.volume_24h > 0:
            vol_mcap_ratio = token.volume_24h / token.market_cap

            if vol_mcap_ratio > 5.0:
                act -= 15
                risks.append(f"⚠️ Abnormal volume/MCap: {vol_mcap_ratio:.1f}x (possible wash trading)")
            elif vol_mcap_ratio > 2.0:
                act -= 8
                risks.append(f"⚠️ High volume/MCap: {vol_mcap_ratio:.1f}x")
            elif vol_mcap_ratio < 0.01:
                act -= 12
                risks.append("⚠️ Very low trading activity")
            elif vol_mcap_ratio < 0.05:
                act -= 6
                risks.append("⚠️ Low trading volume")
            elif 0.1 <= vol_mcap_ratio <= 1.0:
                act += 15
                goods.append(f"✅ Healthy volume/MCap ({vol_mcap_ratio:.2f}x)")
            elif 0.05 <= vol_mcap_ratio < 0.1:
                act += 5

        # ═══════════════════════════════════════════════════════════
        # BUY/SELL RATIO ANALYSIS - up to +/- 20 points
        # ═══════════════════════════════════════════════════════════

        if token.buys_24h > 0 and token.sells_24h > 0:
            ratio = token.buys_24h / token.sells_24h
            if ratio < 0.15:
                act -= 20
                risks.append("📉 EXTREME SELLING — likely dump!")
            elif ratio < 0.3:
                act -= 15
                risks.append("📉 Mass selling — dump in progress")
            elif ratio < 0.5:
                act -= 10
                risks.append("📉 High sell pressure")
            elif ratio < 0.7:
                act -= 5
                risks.append("📉 More sells than buys")
            elif ratio > 8:
                act += 20
                goods.append("📈 Strong buy pressure")
            elif ratio > 4:
                act += 15
                goods.append("📈 Good buy momentum")
            elif ratio > 2:
                act += 10
                goods.append("📈 Positive buy/sell ratio")
            elif ratio >= 1.0:
                act += 5
                goods.append("📈 Balanced buy/sell activity")
        elif token.sells_24h > 50 and token.buys_24h == 0:
            act -= 20
            risks.append("📉 ONLY SELLS — dump in progress!")

        # ═══════════════════════════════════════════════════════════
        # TRANSACTION COUNT ANALYSIS - up to +/- 15 points
        # ═══════════════════════════════════════════════════════════

        if token.txns_24h < 5:
            act -= 15
            risks.append("⚠️ Dead token — no transactions")
        elif token.txns_24h < 20:
            act -= 12
            risks.append("⚠️ Very few transactions")
        elif token.txns_24h < 50:
            act -= 8
            risks.append("⚠️ Low transaction count")
        elif token.txns_24h < 100:
            act -= 3
        elif token.txns_24h > 2000:
            act += 15
            goods.append(f"✅ Very active trading ({token.txns_24h:,} txns)")
        elif token.txns_24h > 500:
            act += 12
            goods.append(f"✅ Active trading ({token.txns_24h:,} txns)")
        elif token.txns_24h > 200:
            act += 8
            goods.append(f"✅ Good activity level ({token.txns_24h:,} txns)")
        elif token.txns_24h >= 100:
            act += 5
            goods.append("✅ Acceptable activity")

        # ═══════════════════════════════════════════════════════════
        # HOURLY VOLUME TREND - up to +/- 8 points
        # ═══════════════════════════════════════════════════════════

        if token.volume_24h > 0 and token.volume_1h > 0:
            hourly_avg = token.volume_24h / 24
            if hourly_avg > 0:
                volume_ratio = token.volume_1h / hourly_avg
                if volume_ratio > 5.0:
                    act -= 8
                    risks.append(f"⚠️ Volume spike: {volume_ratio:.1f}x hourly average")
                elif volume_ratio < 0.2:
                    act -= 6
                    risks.append("⚠️ Declining trading interest")
                elif 0.8 <= volume_ratio <= 2.0:
                    act += 5
                    goods.append("✅ Consistent trading volume")

        # ═══════════════════════════════════════════════════════════
        # MULTI-TIMEFRAME PRICE MOMENTUM - up to +/- 15 points
        # ═══════════════════════════════════════════════════════════

        # Pump detection: sharp short-term rise
        if token.price_change_5m > 100:
            act -= 15
            risks.append(f"🚨 EXTREME PUMP: +{token.price_change_5m:.0f}% (5m) — likely manipulation!")
        elif token.price_change_5m > 50 and token.price_change_1h > 100:
            act -= 12
            risks.append(f"🚨 PUMP pattern: +{token.price_change_5m:.0f}% (5m), +{token.price_change_1h:.0f}% (1h)")
        elif token.price_change_1h > 200:
            act -= 10
            risks.append(f"⚠️ Sharp pump: +{token.price_change_1h:.0f}% (1h)")

        # Dump detection: sharp short-term decline
        if token.price_change_5m < -30:
            act -= 15
            risks.append(f"📉 SHARP DROP: {token.price_change_5m:.0f}% (5m) — possible rug!")
        elif token.price_change_5m < -15:
            act -= 10
            risks.append(f"📉 Quick drop: {token.price_change_5m:.0f}% (5m)")
        elif token.price_change_1h < -40:
            act -= 12
            risks.append(f"📉 Hourly dump: {token.price_change_1h:.0f}%")

        # Healthy growth pattern: gradual increase across timeframes
        healthy_growth = (
            0 < token.price_change_5m < 10 and
            0 < token.price_change_1h < 25 and
            0 < token.price_change_6h < 40 and
            token.price_change_24h > 0
        )
        if healthy_growth:
            act += 10
            goods.append("📈 Healthy organic growth pattern")

        # Volume/price divergence (bearish signal)
        if token.price_change_24h > 50 and token.volume_1h < (token.volume_24h / 48) if token.volume_24h > 0 else False:
            act -= 8
            risks.append("⚠️ Volume declining despite price rise")

        # Sustained momentum (bullish signal)
        sustained_momentum = (
            token.price_change_5m > 0 and
            token.price_change_1h > 0 and
            token.price_change_6h > 0 and
            token.price_change_24h > 10
        )
        if sustained_momentum and token.txns_24h > 100:
            act += 8
            goods.append("📈 Sustained positive momentum")

        return max(0, min(100, act)), risks, goods

    def _calc_social(self, token: TokenInfo) -> Tuple[int, List[str], List[str]]:
        """
        Calculate social score (10% weight).

        Enhanced with AI sentiment analysis and website quality details.

        Returns:
            (score, risks, goods) tuple
        """
        social = 100
        risks = []
        goods = []

        # ═══════════════════════════════════════════════════════════
        # SOCIAL PRESENCE CHECKS
        # ═══════════════════════════════════════════════════════════

        # Twitter presence
        if not token.has_twitter:
            social -= 35
            risks.append("❌ Нет Twitter — подозрительно")
        else:
            social += 5
            goods.append("✅ Twitter есть")

        # Website presence
        if not token.has_website:
            social -= 30
            risks.append("❌ Нет Website — подозрительно")
        else:
            social += 5
            goods.append("✅ Website есть")

        # Telegram presence
        if not token.has_telegram:
            social -= 25
            risks.append("❌ Нет Telegram")
        else:
            social += 5
            goods.append("✅ Telegram есть")

        # All socials bonus/penalty
        if token.socials_count == 3:
            social += 15
            goods.append("🌐 Полное присутствие в соцсетях")
        elif token.socials_count == 0:
            social -= 25
            risks.append("🚨 НЕТ СОЦСЕТЕЙ — вероятно скам!")

        # ═══════════════════════════════════════════════════════════
        # WEBSITE QUALITY ANALYSIS
        # ═══════════════════════════════════════════════════════════

        if token.has_website:
            # Quality scoring - more lenient for simple meme token sites
            if token.website_quality >= 80:
                social += 15
                goods.append(f"🌐 Отличный сайт ({token.website_quality}/100)")
            elif token.website_quality >= 60:
                social += 10
                goods.append(f"🌐 Хороший сайт ({token.website_quality}/100)")
            elif token.website_quality >= 40:
                social += 5
                goods.append(f"🌐 Приемлемый сайт ({token.website_quality}/100)")
            elif token.website_quality >= 20:
                social -= 5
                risks.append(f"🌐 Слабый сайт ({token.website_quality}/100)")
            else:
                social -= 10
                risks.append(f"🌐 Очень низкое качество сайта ({token.website_quality}/100)")

            # Legitimacy check - only penalize truly bad sites
            if not token.website_is_legitimate and token.website_quality < 30:
                social -= 10
                risks.append("⚠️ Сайт выглядит подозрительно")

            # Website load time penalty
            if token.website_load_time > 10.0:
                social -= 10
                risks.append(f"🐌 Очень медленный сайт ({token.website_load_time:.1f}s)")
            elif token.website_load_time > 5.0:
                social -= 5

            # Website red flags
            for flag in (token.website_red_flags or [])[:2]:
                if flag and len(flag) < 80:
                    risks.append(f"🌐 {flag}")

        # ═══════════════════════════════════════════════════════════
        # AI SENTIMENT INTEGRATION
        # ═══════════════════════════════════════════════════════════

        # Parse AI sentiment text for social signals
        if token.ai_sentiment:
            sentiment_text = token.ai_sentiment.lower()
            if any(word in sentiment_text for word in ['scam', 'fake', 'fraud', 'honeypot']):
                social -= 20
                risks.append("🤖 AI: Negative sentiment detected")
            elif any(word in sentiment_text for word in ['strong community', 'active', 'legitimate', 'growing']):
                social += 10
                goods.append("🤖 AI: Positive community sentiment")
            elif any(word in sentiment_text for word in ['minimal', 'quiet', 'no activity']):
                social -= 10

        return max(0, min(100, social)), risks, goods

    def _calc_contract_quality(self, token: TokenInfo) -> Tuple[int, List[str], List[str]]:
        """
        Calculate contract quality score (8% weight).

        Evaluates contract immutability, standard implementation,
        and supply manipulation indicators.

        Returns:
            (score, risks, goods) tuple
        """
        score = 100
        risks = []
        goods = []

        # ═══════════════════════════════════════════════════════════
        # CONTRACT IMMUTABILITY
        # ═══════════════════════════════════════════════════════════

        # Mint authority is the most critical factor
        if not token.mint_authority_enabled:
            score += 20
            goods.append("✅ Contract immutable (no mint authority)")
        else:
            score -= 40
            risks.append("🚨 Contract mutable - can mint new tokens!")

        # Freeze authority
        if not token.freeze_authority_enabled:
            score += 15
            goods.append("✅ No freeze authority")
        else:
            score -= 25
            risks.append("⚠️ Freeze authority enabled")

        # ═══════════════════════════════════════════════════════════
        # LP LOCK QUALITY
        # ═══════════════════════════════════════════════════════════

        if token.liquidity_locked:
            if token.lp_lock_percent >= 95:
                score += 20
                goods.append(f"🔒 LP fully locked ({token.lp_lock_percent:.0f}%)")
            elif token.lp_lock_percent >= 80:
                score += 15
                goods.append(f"🔒 LP mostly locked ({token.lp_lock_percent:.0f}%)")
            elif token.lp_lock_percent >= 50:
                score += 5
            else:
                score -= 10
                risks.append(f"⚠️ Low LP lock ({token.lp_lock_percent:.0f}%)")
        else:
            score -= 35
            risks.append("🚨 LP not locked - high rug risk!")

        # ═══════════════════════════════════════════════════════════
        # RUGCHECK INTEGRATION
        # ═══════════════════════════════════════════════════════════

        if token.rugcheck_score > 0:
            if token.rugcheck_score < 100:
                score += 15
                goods.append(f"✅ RugCheck: Excellent ({token.rugcheck_score})")
            elif token.rugcheck_score < 300:
                score += 10
                goods.append(f"✅ RugCheck: Good ({token.rugcheck_score})")
            elif token.rugcheck_score >= 1500:
                score -= 30
                risks.append(f"🚨 RugCheck: High risk ({token.rugcheck_score})")
            elif token.rugcheck_score >= 800:
                score -= 20
                risks.append(f"⚠️ RugCheck: Elevated ({token.rugcheck_score})")
            elif token.rugcheck_score >= 400:
                score -= 10

        return max(0, min(100, score)), risks, goods

    # ═══════════════════════════════════════════════════════════════════════════
    # NOTE: _apply_ai_adjustments() and _apply_penalties() have been REMOVED
    #
    # The AI score IS the final score. No more complex blending or penalty
    # multipliers. This makes scoring objective and predictable:
    #   - AI analyzes all data and gives a score
    #   - Only hard caps for known scammers (max 25) and rugged tokens (0)
    #   - Metric scores are displayed for context but don't modify the final score
    # ═══════════════════════════════════════════════════════════════════════════

    def _calc_grade(self, score: int) -> str:
        """
        Calculate letter grade from overall score.

        Extracted from bot.py lines 2156-2161.
        """
        if score >= 85:
            return "A"
        elif score >= 75:
            return "B"
        elif score >= 60:
            return "C"
        elif score >= 45:
            return "D"
        else:
            return "F"

    def _calc_recommendation(self, score: int, token: TokenInfo) -> str:
        """
        Calculate recommendation based on score and risk level.

        Extracted from bot.py lines 2164-2185.

        Args:
            score: Overall score
            token: TokenInfo

        Returns:
            Recommendation string
        """
        if score >= 80:
            rec = "✅ RELATIVELY SAFE — но DYOR!"
        elif score >= 65:
            rec = "🟡 CAUTION — есть риски"
        elif score >= 50:
            rec = "🟠 HIGH RISK — будьте осторожны!"
        elif score >= 35:
            rec = "🔴 DANGER — высокий риск потери!"
        else:
            rec = "⛔ AVOID — вероятно скам!"

        # Override with AI recommendation if AVOID
        if token.ai_recommendation and 'AVOID' in token.ai_recommendation.upper():
            rec = token.ai_recommendation

        return rec

    def _calc_risk_level(self, score: int) -> RiskLevel:
        """
        Calculate risk level enum from score.

        Args:
            score: Overall score

        Returns:
            RiskLevel enum
        """
        if score >= 80:
            return RiskLevel.SAFE
        elif score >= 65:
            return RiskLevel.LOW
        elif score >= 50:
            return RiskLevel.MEDIUM
        elif score >= 35:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL

    # ═══════════════════════════════════════════════════════════════════════════
    # ADVANCED ANALYTICS SCORING (NEW FEATURES)
    # ═══════════════════════════════════════════════════════════════════════════

    def _calc_deployer_reputation(self, token: TokenInfo) -> Tuple[int, List[str], List[str]]:
        """
        Calculate deployer reputation score (8% weight).

        Uses wallet forensics data to assess deployer risk.
        Identifies serial scammers and rewards clean track records.

        Returns:
            (score, risks, goods) tuple
        """
        score = 50  # Neutral default
        risks = []
        goods = []

        # If forensics not available, return neutral
        if not token.deployer_forensics_available:
            return 50, ["Deployer history unavailable"], []

        # Known scammer = instant fail
        if token.deployer_is_known_scammer:
            logger.warning(f"⛔ KNOWN SCAMMER detected for {token.symbol}!")
            return 0, ["⛔ DEPLOYER IS KNOWN SCAMMER!"], []

        # Get reputation score from token
        reputation = token.deployer_reputation_score

        # Convert reputation to component score
        if reputation >= 80:
            score = 100
            goods.append(f"Deployer has excellent reputation ({token.deployer_tokens_deployed} tokens, clean history)")
        elif reputation >= 60:
            score = 75
            if token.deployer_tokens_deployed > 0:
                goods.append(f"Deployer has good history ({token.deployer_tokens_deployed} tokens)")
        elif reputation >= 40:
            score = 50
            if token.deployer_rugged_tokens > 0:
                risks.append(f"Deployer has mixed history ({token.deployer_rugged_tokens} rugs)")
        elif reputation >= 20:
            score = 25
            risks.append(f"⚠️ DEPLOYER HIGH RISK: {token.deployer_rug_percentage:.0f}% rug rate!")
        else:
            score = 10
            risks.append(f"⛔ DEPLOYER CRITICAL: Serial rugger detected!")

        # Add pattern-specific risks
        for pattern in token.deployer_patterns_detected[:2]:
            risks.append(f"Pattern: {pattern}")

        # Add evidence if critical
        if score <= 25 and token.deployer_evidence_summary:
            risks.append(token.deployer_evidence_summary[:100])

        return max(0, min(100, score)), risks, goods

    def _calc_behavioral_anomaly(self, token: TokenInfo) -> Tuple[int, List[str], List[str]]:
        """
        Calculate behavioral anomaly score (7% weight).

        Uses time-series analysis for predictive rug detection.
        Higher anomaly = lower score.

        Returns:
            (score, risks, goods) tuple
        """
        score = 100  # Start optimistic (no anomalies = good)
        risks = []
        goods = []

        # If anomaly detection not available, return neutral
        if not token.anomaly_available:
            return 70, ["Behavioral monitoring unavailable"], []

        # Get anomaly severity
        severity = token.anomaly_severity

        if severity == "CRITICAL":
            score = 10
            risks.append(f"⛔ CRITICAL: {token.anomaly_recommendation}")
            if token.anomaly_time_to_rug == "imminent":
                risks.append("💀 RUG IMMINENT - Exit recommended!")
        elif severity == "HIGH":
            score = 35
            risks.append(f"⚠️ HIGH RISK: Behavioral patterns suggest {token.anomaly_rug_probability:.0f}% rug probability")
        elif severity == "ELEVATED":
            score = 60
            risks.append("Elevated anomaly activity detected")
        else:
            goods.append("Normal behavioral patterns")

        # Add specific anomalies as risks (limit to 2)
        for anomaly_type in token.anomalies_detected[:2]:
            if anomaly_type not in ["normal"]:
                risks.append(f"Anomaly: {anomaly_type.replace('_', ' ').title()}")

        # Adjust score based on rug probability
        if token.anomaly_rug_probability >= 70:
            score = min(score, 25)
        elif token.anomaly_rug_probability >= 50:
            score = min(score, 45)
        elif token.anomaly_rug_probability >= 30:
            score = min(score, 65)

        # Data quality affects confidence
        if token.anomaly_data_quality < 30:
            # Low data quality = less confidence in score
            score = int((score + 50) / 2)  # Move toward neutral

        return max(0, min(100, score)), risks, goods

    def _calc_honeypot(self, token: TokenInfo) -> Tuple[int, List[str], List[str]]:
        """
        Calculate honeypot score (8% weight).

        Uses sell simulation results to assess if token can be sold.
        Detected via Jupiter quote + Solana transaction simulation.

        Scoring:
        - HONEYPOT (can't sell) → score 0
        - EXTREME_TAX (>50% tax) → score 20
        - HIGH_TAX (20-50% tax) → score 45
        - UNABLE_TO_VERIFY → score 60
        - SAFE (can sell normally) → score 100

        Returns:
            (score, risks, goods) tuple
        """
        score = 70  # Neutral default if not checked
        risks = []
        goods = []

        # If honeypot detection wasn't performed
        if not token.honeypot_checked:
            return 70, ["Honeypot check unavailable"], []

        status = token.honeypot_status

        # HONEYPOT = Critical failure (hard cap applied separately)
        if status == "honeypot":
            score = 0
            risks.append("🍯 HONEYPOT: Token CANNOT be sold!")
            if token.honeypot_explanation:
                risks.append(f"🍯 {token.honeypot_explanation[:80]}")
            return 0, risks, []

        # EXTREME TAX = Very bad (>50% sell tax)
        if status == "extreme_tax":
            score = 20
            tax = token.honeypot_sell_tax_percent or 0
            risks.append(f"💸 EXTREME sell tax: {tax:.1f}%")
            risks.append("Most value will be lost when selling")
            return 20, risks, []

        # HIGH TAX = Bad (20-50% sell tax)
        if status == "high_tax":
            score = 45
            tax = token.honeypot_sell_tax_percent or 0
            risks.append(f"💸 High sell tax: {tax:.1f}%")
            return 45, risks, []

        # UNABLE TO VERIFY = Unknown (no Jupiter route)
        if status == "unable_to_verify":
            score = 60
            risks.append("Sell capability unverified (no Jupiter route)")
            return 60, risks, []

        # ERROR = Something went wrong
        if status == "error":
            score = 60
            risks.append("Honeypot check encountered error")
            return 60, risks, []

        # SAFE = Good (can sell normally)
        if status == "safe":
            score = 100
            goods.append("✅ Token can be sold normally")
            if token.honeypot_route_dex:
                goods.append(f"Verified via {token.honeypot_route_dex}")
            if token.honeypot_sell_tax_percent is not None:
                if token.honeypot_sell_tax_percent < 5:
                    goods.append(f"Low sell tax: {token.honeypot_sell_tax_percent:.1f}%")
                elif token.honeypot_sell_tax_percent < 20:
                    # Moderate tax - not a risk but not a plus
                    pass
            return 100, [], goods

        # Unknown status = neutral
        return 70, ["Honeypot status unknown"], []
