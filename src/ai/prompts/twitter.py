"""
Twitter/Narrative analysis prompt for Grok.
This module generates sophisticated prompts for deep narrative research using Grok 2/Beta.
"""

from typing import Union, Any

def get_narrative_prompt(token: Any) -> str:
    """
    Generate a prompt for Grok to analyze token narrative on Twitter.
    Accepts TokenInfo or TokenAnalysisRequest (duck typing).
    
    This prompt is designed to force Grok to use its real-time search capabilities.
    """
    symbol = token.symbol
    name = token.name
    twitter_url = getattr(token, 'twitter_url', 'N/A') or "N/A"
    address = token.address
    
    return f"""
PERFORM DEEP SEARCH AND ANALYSIS ON THIS TOKEN:
Name: {name}
Symbol: ${symbol}
Contract: {address}
Twitter: {twitter_url}

ROLE: You are a "DEGEN" CRYPTO ANALYST. Your job is to identify potential 100x gems, viral narratives, and cult-like communities.
You are NOT a safety auditor. You are looking for VIBES, NARRATIVE, and MEMETIC POTENTIAL.

OBJECTIVE:
Analyze the "Narrative Heat" of this token. Even if the token is new or low volume, does the *CONCEPT* or *MEME* have viral potential?

Step 1: SEARCH Twitter/X for ${symbol}, "{name}", and the contract address.
Step 2: EVALUATE THE MEME/NARRATIVE:
   - Is this topic trending globally? (e.g. Politics, AI, Celebrities, Scandals)
   - Is it funny, edgy, or controversial? (Controversy = Attention = Bullish)
   - Is it a "Community Takeover" (CTO)?
Step 3: CHECK ENGAGEMENT:
   - Who is talking about it? (KOLs, Alpha callers, or just bots?)
   - Are the comments "based" or just "LFG" spam?

SCORING RULES:
- NARRATIVE SCORE: Base this on the *POTENTIAL* of the meme/narrative.
  - 80-100: Globally trending topic , Cult community, Tier-1 KOLs.
  - 50-79: Good meme, funny, some organic chatter, decent art.
  - 20-49: Generic dog/cat coin, low effort, no unique angle.
  - 0-19: Proven scam, rugged, or completely dead/silent.

OUTPUT FORMAT (JSON ONLY):
{{
    "narrative_score": <0-100>,
    "sentiment": "BULLISH|NEUTRAL|BEARISH|MOONSHOT",
    "narrative_category": "<category e.g. PolitiFi, AI Agent, Dark Humor, Cabal>",
    "trending_status": "VIRAL|TRENDING|accumulating|QUIET|DEAD",
    "narrative_summary": "<2-3 sentences. Focus on the MEME potential and VIBE. Be direct and use crypto slang if appropriate.>",
    "influencer_tier": "TIER-1|DEGEN|NONE",
    "influencer_activity": "<Who is talking about it?>",
    "community_vibe": "<CULT|BASED|BOTS|NONEXISTENT>",
    "organic_score": <0-100 score of real engagement vs bots>,
    "key_themes": ["<theme1>", "<theme2>"],
    "fud_warnings": ["<warning1>"]
}}

CRITICAL:
- Do NOT dismiss a token just because it's new. If the meme is fire, the score should be high.
- Acknowledge "Dark Humor" or "Controversial" topics as HIGH POTENTIAL in the current meta.
- Use your live data to find the *latest* tweets.
"""
