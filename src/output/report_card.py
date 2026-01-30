"""
Visual report card generator for token analysis.

This module generates beautiful PNG report cards with risk metrics,
security checks, market data, and QR codes for quick trading.

Extracted from bot.py lines 2210-2358.
"""

import logging
from io import BytesIO
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont
import qrcode

from src.core.models import AnalysisResult, TokenInfo
from src.config import settings

logger = logging.getLogger(__name__)


class ReportCardGenerator:
    """
    Generates visual report cards for token analysis.

    Creates high-resolution PNG images with:
    - Token header with symbol and name
    - Circular overall score indicator
    - Market data (price, liquidity, mcap, volume)
    - Risk metric bars (safety, liquidity, social)
    - Security check badges (mint auth, freeze auth, LP lock)
    - QR code for quick buy link
    - Professional dark theme design

    Extracted from bot.py lines 2210-2358.
    """

    # High-resolution scaling factor
    SCALE = 3

    # Color palette
    COLORS = {
        'bg': (10, 14, 23),          # Dark blue background
        'card': (22, 27, 40),         # Card background
        'card_border': (45, 55, 75),  # Card borders
        'text': (255, 255, 255),      # Primary text
        'subtext': (160, 174, 192),   # Secondary text
        'accent': (99, 102, 241),     # Accent color (blue)
        'green': (34, 197, 94),       # Success/positive
        'red': (239, 68, 68),         # Danger/negative
        'yellow': (234, 179, 8),      # Warning/caution
    }

    def __init__(self):
        """Initialize report card generator with dimensions"""
        self.w = 800 * self.SCALE  # Width: 2400px
        self.h = 1000 * self.SCALE  # Height: 3000px

    def _color(self, score: int) -> Tuple[tuple, tuple]:
        """
        Get color scheme for a score.

        Args:
            score: Score from 0-100

        Returns:
            Tuple of (foreground_color, background_color)
        """
        if score >= 80:
            return self.COLORS['green'], (20, 50, 35)
        elif score >= 60:
            return self.COLORS['yellow'], (50, 45, 20)
        elif score >= 40:
            return self.COLORS['yellow'], (50, 30, 20)
        else:
            return self.COLORS['red'], (50, 20, 20)

    def _font(self, size: int, bold: bool = False):
        """
        Load font with fallbacks.

        Tries multiple font paths for cross-platform compatibility.

        Args:
            size: Font size (will be multiplied by SCALE)
            bold: Whether to use bold variant

        Returns:
            ImageFont object
        """
        s = size * self.SCALE

        # Font paths for different platforms (ordered by preference)
        fonts = [
            # Linux - Liberation Sans (most common)
            "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Regular.ttf",
            # Linux - Open Sans
            "/usr/share/fonts/open-sans/OpenSans-Bold.ttf" if bold else "/usr/share/fonts/open-sans/OpenSans-Regular.ttf",
            # Linux - Droid Sans
            "/usr/share/fonts/google-droid-sans-fonts/DroidSans-Bold.ttf" if bold else "/usr/share/fonts/google-droid-sans-fonts/DroidSans.ttf",
            # Linux - DejaVu (Ubuntu/Debian)
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            # Linux - Noto Sans
            "/usr/share/fonts/noto/NotoSans-Bold.ttf" if bold else "/usr/share/fonts/noto/NotoSans-Regular.ttf",
            # macOS
            "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
            # Windows
            "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
        ]

        for font_path in fonts:
            try:
                return ImageFont.truetype(font_path, s)
            except OSError:
                continue

        # Fallback to default font with size
        logger.warning(f"No system fonts found, using default font at size {s}")
        return ImageFont.load_default(size=s)

    def _fmt(self, n: float) -> str:
        """
        Format number as currency string.

        Args:
            n: Number to format

        Returns:
            Formatted string like "$1.2M", "$450K", etc.
        """
        if n >= 1e9:
            return f"${n/1e9:.2f}B"
        elif n >= 1e6:
            return f"${n/1e6:.2f}M"
        elif n >= 1e3:
            return f"${n/1e3:.1f}K"
        else:
            return f"${n:.0f}"

    def _bar(self, draw, x: int, y: int, w: int, score: int, label: str):
        """
        Draw a progress bar with label and score.

        Args:
            draw: ImageDraw object
            x: X position
            y: Y position
            w: Width
            score: Score value (0-100)
            label: Label text
        """
        s = self.SCALE
        col, _ = self._color(score)

        # Label
        draw.text((x, y), label, fill=self.COLORS['subtext'], font=self._font(20, True))

        # Score value
        draw.text((x + w - 100*s, y - 5*s), str(score), fill=col, font=self._font(30, True))
        draw.text((x + w - 30*s, y + 10*s), "/100", fill=self.COLORS['subtext'], font=self._font(14))

        # Bar background
        by = y + 45*s
        bh = 16*s
        draw.rounded_rectangle([x, by, x+w, by+bh], radius=bh//2, fill=self.COLORS['card_border'])

        # Bar filled portion
        pw = int(w * score / 100)
        if pw > bh:
            draw.rounded_rectangle([x, by, x+pw, by+bh], radius=bh//2, fill=col)

    def _add_watermark(self, img: Image, draw: ImageDraw):
        """
        Add diagonal @AISentinelBot watermark for viral branding.

        Creates a semi-transparent watermark across the image center
        to ensure brand visibility when users share report cards.

        Args:
            img: PIL Image object
            draw: ImageDraw object
        """
        s = self.SCALE
        watermark_text = "@AISentinelBot"

        # Create watermark with transparency
        # We'll draw it with low opacity color
        watermark_color = (255, 255, 255, 25)  # Very transparent white

        # Get font for watermark
        font = self._font(35, True)

        # Calculate center position
        # Draw watermark diagonally from bottom-left to top-right area
        try:
            # Draw multiple watermarks across the image for visibility
            positions = [
                (self.w // 4, self.h // 2 - 100*s),
                (self.w // 2, self.h // 2 + 50*s),
                (self.w * 3 // 4, self.h // 2 - 50*s),
            ]

            for x, y in positions:
                # Semi-transparent watermark (RGB only, alpha not directly supported)
                # Use a light gray that blends with the dark background
                draw.text(
                    (x, y),
                    watermark_text,
                    fill=(100, 100, 120),  # Light gray, visible but not intrusive
                    font=font,
                    anchor="mm"
                )
        except Exception as e:
            logger.debug(f"Watermark drawing failed: {e}")
            # Continue without watermark on error

    def create(self, result: AnalysisResult) -> BytesIO:
        """
        Generate PNG report card for analysis result.

        Creates a visually appealing report card with all key metrics
        and security information.

        Args:
            result: AnalysisResult with complete token analysis

        Returns:
            BytesIO buffer containing PNG image
        """
        s = self.SCALE
        token = result.token

        # Create image
        img = Image.new('RGB', (self.w, self.h), self.COLORS['bg'])
        draw = ImageDraw.Draw(img)

        # ═══════════════════════════════════════════════════════════
        # HEADER SECTION
        # ═══════════════════════════════════════════════════════════

        draw.rounded_rectangle([25*s, 25*s, self.w-25*s, 200*s], radius=20*s, fill=self.COLORS['card'])

        # App name (no emoji for font compatibility)
        draw.text((50*s, 45*s), "AI SENTINEL", fill=self.COLORS['accent'], font=self._font(24, True))

        # Token symbol
        sym = f"${token.symbol}" if token.symbol != "???" else "UNKNOWN"
        draw.text((50*s, 90*s), sym, fill=self.COLORS['text'], font=self._font(60, True))

        # Token name
        draw.text((50*s, 160*s), token.name[:25], fill=self.COLORS['subtext'], font=self._font(24))

        # ═══════════════════════════════════════════════════════════
        # SCORE CIRCLE (top right)
        # ═══════════════════════════════════════════════════════════

        cx, cy, cr = self.w - 150*s, 115*s, 80*s  # Center X, Y, Radius
        col, bg = self._color(result.overall_score)

        # Circle outline
        draw.ellipse([cx-cr, cy-cr, cx+cr, cy+cr], outline=self.COLORS['card_border'], width=10*s)

        # Progress arc
        end_angle = -90 + (360 * (result.overall_score / 100))
        draw.arc([cx-cr, cy-cr, cx+cr, cy+cr], -90, end_angle, fill=col, width=10*s)

        # Score number
        st = str(result.overall_score)
        font_score = self._font(65, True)
        bbox = draw.textbbox((0, 0), st, font=font_score)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((cx - tw/2, cy - th/1.3), st, fill=col, font=font_score)

        # Grade letter
        draw.text((cx - 15*s, cy + 20*s), result.grade, fill=self.COLORS['text'], font=self._font(30, True))

        # ═══════════════════════════════════════════════════════════
        # MARKET DATA SECTION
        # ═══════════════════════════════════════════════════════════

        y = 230*s
        draw.rounded_rectangle([25*s, y, self.w-25*s, y+180*s], radius=20*s, fill=self.COLORS['card'])

        col_width = (self.w - 50*s) // 2

        # Price (left)
        draw.text((50*s, y+25*s), "PRICE USD", fill=self.COLORS['subtext'], font=self._font(18))
        price_val = f"${token.price_usd:.8f}" if token.price_usd < 0.001 else f"${token.price_usd:.4f}"
        draw.text((50*s, y+55*s), price_val, fill=self.COLORS['text'], font=self._font(42, True))

        # Liquidity (right)
        liq_x = 50*s + col_width
        draw.text((liq_x, y+25*s), "LIQUIDITY", fill=self.COLORS['subtext'], font=self._font(18))
        liq_col = self.COLORS['green'] if token.liquidity_usd > 50000 else self.COLORS['red']
        liq_txt = self._fmt(token.liquidity_usd) + (" [LOCKED]" if token.liquidity_locked else "")
        draw.text((liq_x, y+55*s), liq_txt, fill=liq_col, font=self._font(42, True))

        # Second row: MCap and Volume
        y_row2 = y + 110*s
        draw.text((50*s, y_row2), "MCAP", fill=self.COLORS['subtext'], font=self._font(16))
        draw.text((50*s + 70*s, y_row2-5*s), self._fmt(token.market_cap), fill=self.COLORS['text'], font=self._font(26, True))

        draw.text((liq_x, y_row2), "VOL 24H", fill=self.COLORS['subtext'], font=self._font(16))
        draw.text((liq_x + 90*s, y_row2-5*s), self._fmt(token.volume_24h), fill=self.COLORS['text'], font=self._font(26, True))

        # ═══════════════════════════════════════════════════════════
        # RISK METRICS SECTION
        # ═══════════════════════════════════════════════════════════

        y = 440*s
        draw.rounded_rectangle([25*s, y, self.w-25*s, y+320*s], radius=20*s, fill=self.COLORS['card'])

        # Section title (no emoji for font compatibility)
        draw.text((50*s, y+25*s), "RISK METRICS", fill=self.COLORS['text'], font=self._font(24, True))

        # Score bars
        bar_w = self.w - 150*s
        self._bar(draw, 50*s, y+80*s, bar_w, result.safety_score, "Safety")
        self._bar(draw, 50*s, y+150*s, bar_w, result.liquidity_score, "Liquidity")
        self._bar(draw, 50*s, y+220*s, bar_w, result.social_score, "Socials")

        # ═══════════════════════════════════════════════════════════
        # SECURITY CHECKS SECTION
        # ═══════════════════════════════════════════════════════════

        y = 790*s
        draw.rounded_rectangle([25*s, y, self.w-25*s, y+120*s], radius=20*s, fill=self.COLORS['card'])

        # Security checks
        checks = [
            ("Mint Auth", not token.mint_authority_enabled),
            ("Freeze Auth", not token.freeze_authority_enabled),
            ("LP Lock", token.liquidity_locked),
        ]

        cw = (self.w - 100*s) // 3  # Column width

        for i, (name, is_safe) in enumerate(checks):
            cx = 50*s + cw*i
            status_text = "SAFE" if is_safe else "RISK"
            status_col = self.COLORS['green'] if is_safe else self.COLORS['red']

            # Draw label
            draw.text((cx, y+25*s), name, fill=self.COLORS['subtext'], font=self._font(18))
            # Draw status with colored indicator
            draw.text((cx, y+60*s), status_text, fill=status_col, font=self._font(26, True))

        # ═══════════════════════════════════════════════════════════
        # WATERMARK (Viral branding)
        # ═══════════════════════════════════════════════════════════

        self._add_watermark(img, draw)

        # ═══════════════════════════════════════════════════════════
        # FOOTER SECTION
        # ═══════════════════════════════════════════════════════════

        # Contract address
        ca_short = f"{token.address[:6]}...{token.address[-6:]}"
        draw.text((50*s, self.h-70*s), f"CA: {ca_short}", fill=self.COLORS['subtext'], font=self._font(20))

        # Branding
        draw.text((50*s, self.h-40*s), "Generated by AI Sentinel Bot", fill=self.COLORS['accent'], font=self._font(16))

        # ═══════════════════════════════════════════════════════════
        # QR CODE (bottom right)
        # ═══════════════════════════════════════════════════════════

        try:
            # Generate QR code for quick buy link
            qr = qrcode.QRCode(box_size=2*s, border=1)

            # Get primary affiliate buy link
            buy_link = settings.get_primary_affiliate_link(token.address)
            if buy_link:
                qr.add_data(buy_link)
                qr.make(fit=True)

                # Create QR image
                qr_img = qr.make_image(fill_color="white", back_color=self.COLORS['bg'])
                qr_w, qr_h = qr_img.size

                # Paste QR code
                img.paste(qr_img, (self.w - qr_w - 30*s, self.h - qr_h - 30*s))

                # QR label (no emoji for font compatibility)
                draw.text(
                    (self.w - qr_w - 30*s, self.h - qr_h - 60*s),
                    "QUICK BUY",
                    fill=self.COLORS['green'],
                    font=self._font(16, True)
                )
        except Exception as e:
            logger.debug(f"QR code generation failed: {e}")
            # Continue without QR code

        # ═══════════════════════════════════════════════════════════
        # FINAL IMAGE PROCESSING
        # ═══════════════════════════════════════════════════════════

        # Downscale for final output (high-quality LANCZOS resampling)
        img = img.resize((self.w // self.SCALE, self.h // self.SCALE), Image.Resampling.LANCZOS)

        # Save to buffer
        buf = BytesIO()
        img.save(buf, format='PNG', quality=100)
        buf.seek(0)

        logger.info(f"✅ Report card generated for {token.symbol}")
        return buf
