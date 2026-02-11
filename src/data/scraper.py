"""
Website scraper for token project analysis.

This module provides an async client for scraping and analyzing token
project websites, extracting content, and detecting potential red flags.
"""

import logging
import asyncio
import re
from typing import Dict, List, Optional, Any
from datetime import datetime
import aiohttp
from bs4 import BeautifulSoup

# Optional playwright import for JS-rendered sites
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logger = logging.getLogger(__name__)

# Log Playwright availability at module load
if PLAYWRIGHT_AVAILABLE:
    logger.info("✅ Playwright available for JavaScript rendering")
else:
    logger.warning("⚠️ Playwright not installed - JavaScript sites may not scrape correctly. Run: pip install playwright && playwright install chromium")


class WebsiteScraper:
    """
    Async website scraper for token project analysis.

    Scrapes websites, extracts clean content, detects red flags,
    and prepares data for AI analysis.
    """

    DEFAULT_TIMEOUT = 10  # seconds
    MAX_CONTENT_LENGTH = 5000  # characters for AI analysis
    MIN_CONTENT_LENGTH = 100  # minimum for valid content

    # User agent strings
    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    def __init__(
        self,
        session: Optional[aiohttp.ClientSession] = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_content_length: int = MAX_CONTENT_LENGTH
    ):
        """
        Initialize website scraper.

        Args:
            session: Optional existing aiohttp session
            timeout: Request timeout in seconds
            max_content_length: Maximum content length for AI analysis
        """
        self._session = session
        self._owns_session = session is None
        self.timeout = timeout
        self.max_content_length = max_content_length

    async def __aenter__(self):
        """Async context manager entry"""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup resources"""
        await self.close()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """
        Ensure we have a valid session.

        Returns:
            Active aiohttp ClientSession
        """
        if self._session is None or self._session.closed:
            headers = {
                'User-Agent': self.USER_AGENTS[0],
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers=headers
            )
            self._owns_session = True
        return self._session

    async def close(self):
        """Close the aiohttp session if we own it"""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _scrape_with_playwright(self, url: str) -> Optional[str]:
        """
        Scrape a JavaScript-rendered website using Playwright headless browser.

        This is used as a fallback when the initial aiohttp request detects a
        SPA framework (React, Vue, Angular) but returns minimal content.

        Args:
            url: The website URL to scrape

        Returns:
            Rendered HTML content or None if failed
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not available - cannot render JS content")
            return None

        try:
            async with async_playwright() as p:
                # Launch headless Chromium
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=self.USER_AGENTS[0],
                    viewport={'width': 1280, 'height': 720}
                )
                page = await context.new_page()

                try:
                    # Navigate with timeout
                    await page.goto(url, timeout=15000, wait_until='domcontentloaded')

                    # Wait for content to render (give JS time to execute)
                    await asyncio.sleep(2)

                    # Wait for body to have content (common pattern)
                    try:
                        await page.wait_for_selector('body *', timeout=5000)
                    except Exception:
                        pass  # Continue even if selector times out

                    # Get rendered HTML
                    html = await page.content()

                    logger.info(f"✅ Playwright rendered {len(html)} chars for {url}")
                    return html

                finally:
                    await context.close()
                    await browser.close()

        except Exception as e:
            logger.error(f"Playwright scraping failed for {url}: {e}")
            return None

    def _clean_html(self, html: str) -> str:
        """
        Clean HTML and extract pure text content.

        Removes scripts, styles, navigation, and other non-content elements.
        Normalizes whitespace and limits length.

        Args:
            html: Raw HTML content

        Returns:
            Cleaned text content (max self.max_content_length characters)
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Remove unwanted tags
            for tag in soup([
                'script', 'style', 'nav', 'footer', 'header',
                'iframe', 'noscript', 'svg', 'path', 'meta',
                'link', 'button', 'input', 'form'
            ]):
                tag.decompose()

            # Extract text
            text = soup.get_text(separator=' ', strip=True)

            # Clean whitespace
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            text = ' '.join(lines)

            # Remove multiple spaces
            while '  ' in text:
                text = text.replace('  ', ' ')

            # Limit length
            return text[:self.max_content_length]

        except Exception as e:
            logger.error(f"HTML cleaning error: {e}")
            return ""

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract page title from soup"""
        title_tag = soup.find('title')
        if title_tag:
            return title_tag.get_text(strip=True)

        # Fallback: check og:title meta tag
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            return og_title['content']

        return ""

    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Extract meta description"""
        # Check standard meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            return meta_desc['content']

        # Check og:description
        og_desc = soup.find('meta', property='og:description')
        if og_desc and og_desc.get('content'):
            return og_desc['content']

        return ""

    def _detect_red_flags(self, soup: BeautifulSoup, html: str) -> List[str]:
        """
        Detect suspicious patterns and red flags in website content.

        Args:
            soup: BeautifulSoup parsed HTML
            html: Raw HTML string

        Returns:
            List of red flag messages
        """
        flags = []
        html_lower = html.lower()
        text = soup.get_text()
        text_lower = text.lower()

        # ═══════════════════════════════════════════════════════════════
        # PLACEHOLDER TEXT
        # ═══════════════════════════════════════════════════════════════
        if "lorem ipsum" in html_lower:
            flags.append("🚨 Contains placeholder text (Lorem Ipsum)")

        # ═══════════════════════════════════════════════════════════════
        # TEMPLATE MARKERS
        # ═══════════════════════════════════════════════════════════════
        template_markers = [
            "starter template", "bootstrap template", "free template",
            "template by", "designed by bootstrapmade", "colorlib"
        ]
        for marker in template_markers:
            if marker in html_lower:
                flags.append("⚠️ Uses unmodified template")
                break

        # ═══════════════════════════════════════════════════════════════
        # COPY-PASTE TEMPLATE CONTENT
        # ═══════════════════════════════════════════════════════════════
        template_content = [
            "your company name", "company name here", "logo here",
            "[token name]", "[project name]", "insert text",
            "your email", "example@email.com", "john doe",
            "your tagline here", "add your content", "sample text"
        ]
        template_count = sum(1 for t in template_content if t in text_lower)
        if template_count >= 2:
            flags.append("🚨 Copy-paste template content detected")
        elif template_count == 1:
            flags.append("⚠️ Possible template placeholder found")

        # ═══════════════════════════════════════════════════════════════
        # VERY LITTLE CONTENT
        # ═══════════════════════════════════════════════════════════════
        text_stripped = text.strip()
        if len(text_stripped) < 200:
            flags.append(f"⚠️ Very little content ({len(text_stripped)} chars)")

        # ═══════════════════════════════════════════════════════════════
        # UNDER CONSTRUCTION
        # ═══════════════════════════════════════════════════════════════
        construction_markers = ["under construction", "coming soon", "work in progress"]
        for marker in construction_markers:
            if marker in html_lower:
                flags.append("⚠️ Website under construction")
                break

        # ═══════════════════════════════════════════════════════════════
        # EXCESSIVE URGENCY LANGUAGE
        # ═══════════════════════════════════════════════════════════════
        urgency_patterns = [
            "buy now", "don't miss", "limited time", "act fast",
            "hurry", "last chance", "ending soon", "before it's too late",
            "time is running out", "exclusive offer", "act now"
        ]
        urgency_count = sum(1 for p in urgency_patterns if p in text_lower)
        if urgency_count >= 3:
            flags.append("🚨 EXCESSIVE urgency language - high pressure tactics")
        elif urgency_count >= 2:
            flags.append("⚠️ Multiple urgency phrases detected")

        # ═══════════════════════════════════════════════════════════════
        # UNREALISTIC PROMISES
        # ═══════════════════════════════════════════════════════════════
        unrealistic_patterns = [
            (r'\b1000x\b', "1000x"),
            (r'\b100x\b', "100x"),
            (r'\bguaranteed\s+returns?\b', "guaranteed returns"),
            (r'\bno\s+risk\b', "no risk"),
            (r'\brisk[- ]?free\b', "risk-free"),
            (r'\bcan\'t\s+lose\b', "can't lose"),
            (r'\bget\s+rich\b', "get rich"),
            (r'\beasy\s+money\b', "easy money"),
            (r'\bfinancial\s+freedom\b', "financial freedom"),
            (r'\bmake\s+millions?\b', "make millions"),
            (r'\b\d+%\s+daily\b', "% daily returns"),
            (r'\bpassive\s+income\b', "passive income")
        ]
        for pattern, label in unrealistic_patterns:
            if re.search(pattern, text_lower):
                flags.append(f"🚨 Unrealistic promise: '{label}'")
                break  # Only report first match

        # ═══════════════════════════════════════════════════════════════
        # SUSPICIOUS KEYWORDS (existing)
        # ═══════════════════════════════════════════════════════════════
        suspicious_keywords = [
            "guaranteed returns", "risk-free", "10x guaranteed",
            "no risk", "quick profit", "get rich"
        ]
        found_keywords = [kw for kw in suspicious_keywords if kw in html_lower]
        if found_keywords and "Unrealistic promise" not in str(flags):
            flags.append(f"🚨 Suspicious claims: {', '.join(found_keywords[:2])}")

        # ═══════════════════════════════════════════════════════════════
        # PLACEHOLDER IMAGES
        # ═══════════════════════════════════════════════════════════════
        placeholder_imgs = [
            'placeholder', 'via.placeholder', 'placehold.it',
            'picsum.photos', 'dummyimage.com', 'placekitten', 'unsplash.it'
        ]
        for img in soup.find_all('img', src=True):
            src = img.get('src', '').lower()
            if any(p in src for p in placeholder_imgs):
                flags.append("⚠️ Placeholder images detected - incomplete site")
                break

        # ═══════════════════════════════════════════════════════════════
        # BROKEN/PLACEHOLDER LINKS
        # ═══════════════════════════════════════════════════════════════
        hash_links = soup.find_all('a', href='#')
        if len(hash_links) > 5:
            flags.append("⚠️ Many broken/placeholder links")

        # ═══════════════════════════════════════════════════════════════
        # SUSPICIOUS EXTERNAL LINKS (URL shorteners)
        # ═══════════════════════════════════════════════════════════════
        suspicious_domains = ['bit.ly', 'tinyurl.com', 'goo.gl', 't.co']
        for link in soup.find_all('a', href=True):
            href = link.get('href', '').lower()
            if any(d in href for d in suspicious_domains):
                flags.append("⚠️ URL shortener detected - link destination hidden")
                break

        # ═══════════════════════════════════════════════════════════════
        # CRYPTO SCAM PATTERNS
        # ═══════════════════════════════════════════════════════════════
        scam_patterns = [
            (r'elon\s*musk', "Elon Musk reference"),
            (r'binance\s+listing\s+soon', "Binance listing claim"),
            (r'coinbase\s+listing', "Coinbase listing claim"),
            (r'cex\s+listing\s+confirmed', "CEX listing claim"),
            (r'anti[- ]?whale', "anti-whale"),
            (r'anti[- ]?bot', "anti-bot"),
            (r'moon\s+soon', "moon soon"),
            (r'to\s+the\s+moon', "to the moon"),
            (r'next\s+\d+x', "next Xx claim"),
            (r'millionaire', "millionaire claim")
        ]
        scam_found = []
        for pattern, label in scam_patterns:
            if re.search(pattern, text_lower):
                scam_found.append(label)
        if len(scam_found) >= 2:
            flags.append(f"🚨 Multiple scam patterns: {', '.join(scam_found[:2])}")
        elif len(scam_found) == 1:
            flags.append(f"⚠️ Common scam phrase: {scam_found[0]}")

        # ═══════════════════════════════════════════════════════════════
        # NO HTTPS (from URL check in scrape_website)
        # This will be added by the main scrape function
        # ═══════════════════════════════════════════════════════════════

        return flags

    def _check_for_sections(self, soup: BeautifulSoup) -> Dict[str, bool]:
        """
        Check for presence of important website sections.

        Args:
            soup: BeautifulSoup parsed HTML

        Returns:
            Dict with boolean flags for section presence
        """
        text_lower = soup.get_text().lower()

        return {
            'has_whitepaper': any(keyword in text_lower for keyword in [
                'whitepaper', 'white paper', 'litepaper', 'technical paper'
            ]),
            'has_roadmap': any(keyword in text_lower for keyword in [
                'roadmap', 'road map', 'timeline', 'milestones'
            ]),
            'has_team': any(keyword in text_lower for keyword in [
                'team', 'founders', 'developers', 'about us', 'leadership'
            ]),
            'has_tokenomics': any(keyword in text_lower for keyword in [
                'tokenomics', 'token economics', 'distribution', 'allocation'
            ])
        }

    def _extract_trust_signals(self, soup: BeautifulSoup, html: str) -> Dict[str, Any]:
        """
        Extract trust and legitimacy signals from website.

        Args:
            soup: BeautifulSoup parsed HTML
            html: Raw HTML string

        Returns:
            Dict with trust signal indicators
        """
        signals = {}
        text_lower = html.lower()

        # Privacy policy detection
        signals['has_privacy_policy'] = any(x in text_lower for x in [
            'privacy policy', '/privacy', 'data protection'
        ]) or bool(soup.find('a', href=re.compile(r'privacy', re.I)))

        # Terms of service detection
        signals['has_terms'] = any(x in text_lower for x in [
            'terms of service', 'terms and conditions', '/terms', '/tos'
        ]) or bool(soup.find('a', href=re.compile(r'terms', re.I)))

        # Copyright detection with year extraction
        copyright_match = re.search(
            r'(?:copyright|©|\(c\))\s*(?:20\d{2}[-–])?(\d{4})',
            text_lower
        )
        signals['has_copyright'] = bool(copyright_match)
        signals['copyright_year'] = int(copyright_match.group(1)) if copyright_match else None

        # Contact info detection
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(email_pattern, html)
        # Filter out common non-contact emails
        filtered_emails = [e for e in emails if not any(x in e.lower() for x in [
            'noreply', 'no-reply', 'example.com', 'yourdomain', 'email.com'
        ])]
        signals['has_contact_info'] = bool(filtered_emails) or 'contact' in text_lower
        signals['contact_email'] = filtered_emails[0] if filtered_emails else None

        # Company/team name detection
        company_patterns = [
            r'(?:©|copyright)\s*(?:\d{4})?\s*([A-Z][a-zA-Z0-9\s]{2,30}(?:LLC|Inc|Ltd|Corp|Team|Labs|Protocol|DAO)?)',
            r'([A-Z][a-zA-Z0-9\s]{2,20}(?:Labs|Protocol|DAO|Team|Foundation))'
        ]
        company_name = None
        for pattern in company_patterns:
            match = re.search(pattern, html)
            if match:
                company_name = match.group(1).strip()
                break
        signals['has_company_name'] = company_name is not None
        signals['company_name'] = company_name

        # Physical address detection
        address_patterns = [
            r'\d+\s+[A-Za-z]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd)',
            r'[A-Z][a-z]+,\s*[A-Z]{2}\s*\d{5}'  # City, State ZIP
        ]
        signals['has_physical_address'] = any(
            re.search(pattern, html) for pattern in address_patterns
        )

        return signals

    def _extract_token_signals(self, soup: BeautifulSoup, html: str) -> Dict[str, Any]:
        """
        Extract token-specific information from website.

        Args:
            soup: BeautifulSoup parsed HTML
            html: Raw HTML string

        Returns:
            Dict with token-specific signals
        """
        signals = {}
        text_lower = html.lower()

        # Contract address detection (Solana format: base58, 32-44 chars)
        solana_address_pattern = r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'
        addresses = re.findall(solana_address_pattern, html)
        # Filter likely token addresses (not common words that match pattern)
        signals['has_contract_address'] = len(addresses) > 0
        signals['contract_displayed'] = addresses[0] if addresses else None

        # Tokenomics with actual numbers
        tokenomics_patterns = [
            r'(\d{1,3}(?:\.\d+)?)\s*%\s*(?:to|for)?\s*(?:team|dev|liquidity|marketing|burn|community|treasury)',
            r'(?:team|dev|liquidity|marketing|burn|community|treasury)\s*:?\s*(\d{1,3}(?:\.\d+)?)\s*%'
        ]
        tokenomics_found = []
        for pattern in tokenomics_patterns:
            matches = re.findall(pattern, text_lower)
            tokenomics_found.extend(matches)
        signals['has_tokenomics_numbers'] = len(tokenomics_found) > 0
        signals['tokenomics_details'] = tokenomics_found[:5]  # First 5 allocations

        # Buy button / DEX links
        dex_domains = ['raydium.io', 'jupiter.ag', 'orca.so', 'dexscreener.com', 'birdeye.so']
        buy_links = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if any(dex in href for dex in dex_domains):
                buy_links.append(href)
        signals['has_buy_button'] = (
            len(buy_links) > 0 or
            'buy now' in text_lower or
            'buy token' in text_lower or
            'swap now' in text_lower
        )
        signals['buy_links'] = buy_links[:3]  # Limit to 3

        # Audit mention
        audit_providers = ['certik', 'hacken', 'slowmist', 'peckshield', 'quantstamp', 'solidproof', 'cyberscope']
        found_auditor = next((p for p in audit_providers if p in text_lower), None)
        signals['has_audit_mention'] = (
            found_auditor is not None or
            'audit' in text_lower or
            'audited' in text_lower
        )
        signals['audit_provider'] = found_auditor

        return signals

    def _extract_technical_quality(self, soup: BeautifulSoup, html: str, url: str) -> Dict[str, Any]:
        """
        Extract technical quality indicators from website.

        Args:
            soup: BeautifulSoup parsed HTML
            html: Raw HTML string
            url: Website URL

        Returns:
            Dict with technical quality signals
        """
        signals = {}

        # Mobile viewport
        viewport = soup.find('meta', attrs={'name': 'viewport'})
        signals['has_mobile_viewport'] = viewport is not None

        # Favicon
        favicon = soup.find('link', rel=re.compile(r'icon', re.I))
        signals['has_favicon'] = favicon is not None

        # Analytics detection
        analytics_patterns = [
            'google-analytics.com', 'googletagmanager.com', 'gtag',
            'plausible.io', 'analytics', 'mixpanel', 'segment.io'
        ]
        signals['has_analytics'] = any(p in html.lower() for p in analytics_patterns)

        # Modern framework detection
        framework_indicators = {
            'react': ['__NEXT_DATA__', 'react-root', '_next/', 'data-reactroot'],
            'vue': ['__vue__', 'v-app', 'nuxt', 'data-v-'],
            'angular': ['ng-version', 'angular', '_ngcontent']
        }
        detected_framework = None
        for framework, indicators in framework_indicators.items():
            if any(ind in html for ind in indicators):
                detected_framework = framework
                break
        signals['uses_modern_framework'] = detected_framework is not None
        signals['framework_detected'] = detected_framework

        # SPA detection - expanded indicators for JS-rendered sites
        spa_indicators = [
            '<div id="root">', '<div id="app">', '<div id="__next">',
            '<div id="main">', '<div id="application">',
            'bundle.js', 'main.js', 'app.js', 'chunk.js',
            'webpackJsonp', '__NUXT__', '__GATSBY',
            'window.__INITIAL_STATE__', 'window.__PRELOADED_STATE__'
        ]
        signals['is_spa'] = (
            detected_framework is not None or
            any(indicator in html for indicator in spa_indicators)
        )

        # Custom domain check (not free hosting)
        free_domains = [
            '.vercel.app', '.netlify.app', '.github.io', '.herokuapp.com',
            '.replit.app', '.carrd.co', '.wixsite.com', '.webflow.io',
            '.framer.app', '.squarespace.com', '.blogspot.com'
        ]
        signals['has_custom_domain'] = not any(d in url.lower() for d in free_domains)

        # Social links extraction
        social_platforms = {
            'twitter': ['twitter.com', 'x.com'],
            'telegram': ['t.me', 'telegram.me'],
            'discord': ['discord.gg', 'discord.com'],
            'medium': ['medium.com'],
            'github': ['github.com']
        }
        social_links = {}
        for platform, domains in social_platforms.items():
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                if any(d in href for d in domains):
                    social_links[platform] = href
                    break
        signals['social_links'] = social_links
        signals['has_discord'] = 'discord' in social_links
        signals['has_medium'] = 'medium' in social_links
        signals['has_github'] = 'github' in social_links

        return signals

    async def scrape_website(self, url: str) -> Dict[str, Any]:
        """
        Scrape website and extract all relevant information.

        Args:
            url: Website URL to scrape

        Returns:
            Dict with structure:
            {
                "success": bool,           # Scrape succeeded
                "content": str,            # Cleaned text content
                "title": str,              # Page title
                "description": str,        # Meta description
                "error": Optional[str],    # Error message if failed
                "load_time": float,        # Load time in seconds
                "has_content": bool,       # Has meaningful content
                "url": str,                # Final URL (after redirects)
                "red_flags": List[str],    # Detected red flags
                "has_whitepaper": bool,    # Has whitepaper section
                "has_roadmap": bool,       # Has roadmap section
                "has_team": bool,          # Has team section
                "has_tokenomics": bool     # Has tokenomics section
            }
        """
        # Default result with all fields
        result = {
            # Core fields
            "success": False,
            "content": "",
            "title": "",
            "description": "",
            "error": None,
            "load_time": 0,
            "has_content": False,
            "url": url,
            "red_flags": [],
            # Section presence
            "has_whitepaper": False,
            "has_roadmap": False,
            "has_team": False,
            "has_tokenomics": False,
            # Trust signals
            "has_privacy_policy": False,
            "has_terms": False,
            "has_copyright": False,
            "copyright_year": None,
            "has_contact_info": False,
            "contact_email": None,
            "has_company_name": False,
            "company_name": None,
            "has_physical_address": False,
            # Token signals
            "has_contract_address": False,
            "contract_displayed": None,
            "has_tokenomics_numbers": False,
            "tokenomics_details": [],
            "has_buy_button": False,
            "buy_links": [],
            "has_audit_mention": False,
            "audit_provider": None,
            # Technical quality
            "has_mobile_viewport": False,
            "has_favicon": False,
            "has_analytics": False,
            "uses_modern_framework": False,
            "framework_detected": None,
            "is_spa": False,
            "has_custom_domain": True,
            # Social links
            "social_links": {},
            "has_discord": False,
            "has_medium": False,
            "has_github": False
        }

        if not url:
            result["error"] = "URL not provided"
            return result

        # Normalize URL
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            result["url"] = url

        # Check for HTTP (not HTTPS) - red flag
        if url.startswith('http://'):
            result["red_flags"].append("⚠️ Not using HTTPS")

        try:
            session = await self._ensure_session()
            start_time = datetime.now()

            logger.info(f"🌐 Scraping website: {url}")

            # Additional headers for the request
            request_headers = {
                "User-Agent": self.USER_AGENTS[0],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/",
            }

            async with session.get(
                url,
                allow_redirects=True,
                ssl=False,  # Allow self-signed certificates
                headers=request_headers
            ) as resp:
                result["load_time"] = (datetime.now() - start_time).total_seconds()

                # Update URL if redirected
                result["url"] = str(resp.url)

                if resp.status != 200:
                    result["error"] = f"HTTP {resp.status}"
                    logger.warning(f"Website returned {resp.status}: {url}")
                    return result

                # Check content type
                content_type = resp.headers.get('Content-Type', '')
                if 'text/html' not in content_type.lower():
                    result["error"] = f"Not HTML: {content_type}"
                    return result

                # Read HTML
                html = await resp.text()

                # Parse with BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')

                # Extract metadata
                result["title"] = self._extract_title(soup)
                result["description"] = self._extract_description(soup)

                # Clean content
                content = self._clean_html(html)
                result["content"] = content
                result["has_content"] = len(content) >= self.MIN_CONTENT_LENGTH

                # Detect red flags
                result["red_flags"] = self._detect_red_flags(soup, html)

                # Check for important sections
                sections = self._check_for_sections(soup)
                result.update(sections)

                # Extract trust signals
                trust_signals = self._extract_trust_signals(soup, html)
                result.update(trust_signals)

                # Extract token-specific signals
                token_signals = self._extract_token_signals(soup, html)
                result.update(token_signals)

                # Extract technical quality signals
                final_url = result["url"]
                technical_signals = self._extract_technical_quality(soup, html, final_url)
                result.update(technical_signals)

                # ════════════════════════════════════════════════════════════
                # PLAYWRIGHT FALLBACK FOR SPA/JS SITES
                # ════════════════════════════════════════════════════════════
                # If we got very little content but the site loaded successfully,
                # it's likely JavaScript-rendered. Try Playwright.
                # Low content alone is sufficient reason - SPA/framework detection
                # often fails on minimal initial HTML since the detection patterns
                # are in the JS-rendered DOM, not the server response.
                should_try_playwright = (
                    PLAYWRIGHT_AVAILABLE and
                    len(content) < 500  # Any site with < 500 chars likely needs JS rendering
                )

                if not PLAYWRIGHT_AVAILABLE and len(content) < 500:
                    logger.warning(f"⚠️ Low content ({len(content)} chars) but Playwright unavailable for {url}")
                    result["red_flags"].append(f"⚠️ Low content extracted ({len(content)} chars) - site may require JavaScript rendering")

                if should_try_playwright:
                    logger.info(f"🔄 Low content detected ({len(content)} chars), retrying with Playwright: {url}")

                    # Try to get rendered HTML with Playwright
                    rendered_html = await self._scrape_with_playwright(url)

                    if rendered_html and len(rendered_html) > len(html):
                        # Re-parse with the rendered HTML
                        soup = BeautifulSoup(rendered_html, 'html.parser')
                        html = rendered_html

                        # Re-extract everything with the rendered content
                        result["title"] = self._extract_title(soup)
                        result["description"] = self._extract_description(soup)

                        content = self._clean_html(html)
                        result["content"] = content
                        result["has_content"] = len(content) >= self.MIN_CONTENT_LENGTH

                        # Re-detect red flags with rendered content
                        result["red_flags"] = self._detect_red_flags(soup, html)

                        # Re-check sections
                        sections = self._check_for_sections(soup)
                        result.update(sections)

                        # Re-extract all signals
                        trust_signals = self._extract_trust_signals(soup, html)
                        result.update(trust_signals)

                        token_signals = self._extract_token_signals(soup, html)
                        result.update(token_signals)

                        # Mark that Playwright was used
                        result["playwright_used"] = True

                        logger.info(f"✅ Playwright rendered {len(content)} chars for {url}")

                # Mark as successful
                result["success"] = True

                logger.info(
                    f"✅ Scraped {len(content)} chars from {url} "
                    f"in {result['load_time']:.2f}s, "
                    f"flags: {len(result['red_flags'])}, "
                    f"trust: {sum([trust_signals.get('has_privacy_policy', False), trust_signals.get('has_terms', False), trust_signals.get('has_copyright', False)])}/3"
                )

        except asyncio.TimeoutError:
            result["error"] = "Timeout - website not responding"
            logger.warning(f"Website timeout: {url}")

        except aiohttp.ClientError as e:
            result["error"] = f"Connection error: {str(e)[:50]}"
            logger.warning(f"Website connection error: {url} - {e}")

        except Exception as e:
            result["error"] = f"Error: {str(e)[:50]}"
            logger.error(f"Website scrape error: {url} - {e}")

        return result
