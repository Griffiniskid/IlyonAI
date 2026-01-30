"""
Dynamic icon generator for Solana Blinks.

Generates PNG icons with score badges for Twitter unfurling.
"""

import io
import logging
import math
from typing import Tuple, Optional

from PIL import Image, ImageDraw, ImageFont

from src.config import settings
from src.storage.database import get_database

logger = logging.getLogger(__name__)

# Icon dimensions (square for Twitter cards)
ICON_SIZE = 512
PADDING = 40

# Colors
COLORS = {
    "background": "#1a1a2e",
    "text": "#ffffff",
    "text_secondary": "#a0a0a0",
    "safe": "#00d26a",       # Green - score >= 70
    "caution": "#ffc107",    # Yellow - score >= 50
    "risky": "#ff6b35",      # Orange - score >= 30
    "danger": "#ff3860",     # Red - score < 30
    "arc_bg": "#2d2d44",
}


class IconGenerator:
    """
    Generator for dynamic Blink icons.

    Creates square PNG icons with:
    - Colored arc showing score
    - Score number in center
    - Grade letter
    - Token symbol at bottom
    """

    def __init__(self):
        self.size = ICON_SIZE
        self.padding = PADDING
        self._font_cache = {}

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        """Get or load a font"""
        cache_key = (size, bold)
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]

        # Try to load a good font, fall back to default
        font_names = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]

        for font_name in font_names:
            try:
                font = ImageFont.truetype(font_name, size)
                self._font_cache[cache_key] = font
                return font
            except (OSError, IOError):
                continue

        # Fall back to default
        font = ImageFont.load_default()
        self._font_cache[cache_key] = font
        return font

    def _get_score_color(self, score: int) -> str:
        """Get color based on score"""
        if score >= 70:
            return COLORS["safe"]
        elif score >= 50:
            return COLORS["caution"]
        elif score >= 30:
            return COLORS["risky"]
        else:
            return COLORS["danger"]

    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """Convert hex color to RGB tuple"""
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def _draw_arc(
        self,
        draw: ImageDraw.Draw,
        bbox: Tuple[int, int, int, int],
        start: float,
        end: float,
        color: str,
        width: int,
    ):
        """Draw an arc segment"""
        draw.arc(bbox, start=start, end=end, fill=color, width=width)

    def generate(
        self,
        score: int,
        grade: str,
        symbol: str,
        verdict: Optional[str] = None,
    ) -> io.BytesIO:
        """
        Generate a blink icon image.

        Args:
            score: Overall score (0-100)
            grade: Letter grade (A-F)
            symbol: Token symbol
            verdict: Optional verdict text

        Returns:
            BytesIO containing PNG image
        """
        # Create image
        img = Image.new("RGB", (self.size, self.size), COLORS["background"])
        draw = ImageDraw.Draw(img)

        # Calculate arc dimensions
        arc_margin = 60
        arc_bbox = (
            arc_margin,
            arc_margin,
            self.size - arc_margin,
            self.size - arc_margin,
        )
        arc_width = 20

        # Draw background arc (full circle)
        draw.arc(
            arc_bbox,
            start=135,  # Start from bottom-left
            end=405,    # End at bottom-right (270 degrees total)
            fill=COLORS["arc_bg"],
            width=arc_width,
        )

        # Draw score arc
        score_color = self._get_score_color(score)
        # Map score (0-100) to arc degrees (0-270)
        score_degrees = (score / 100) * 270
        if score_degrees > 0:
            draw.arc(
                arc_bbox,
                start=135,
                end=135 + score_degrees,
                fill=score_color,
                width=arc_width,
            )

        # Draw score number in center
        score_font = self._get_font(80, bold=True)
        score_text = str(score)
        score_bbox = draw.textbbox((0, 0), score_text, font=score_font)
        score_width = score_bbox[2] - score_bbox[0]
        score_height = score_bbox[3] - score_bbox[1]
        score_x = (self.size - score_width) // 2
        score_y = (self.size - score_height) // 2 - 30
        draw.text((score_x, score_y), score_text, fill=score_color, font=score_font)

        # Draw "/100" below score
        sub_font = self._get_font(24)
        sub_text = "/100"
        sub_bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
        sub_width = sub_bbox[2] - sub_bbox[0]
        sub_x = (self.size - sub_width) // 2
        sub_y = score_y + score_height + 5
        draw.text((sub_x, sub_y), sub_text, fill=COLORS["text_secondary"], font=sub_font)

        # Draw grade
        grade_font = self._get_font(36, bold=True)
        grade_text = f"Grade: {grade}"
        grade_bbox = draw.textbbox((0, 0), grade_text, font=grade_font)
        grade_width = grade_bbox[2] - grade_bbox[0]
        grade_x = (self.size - grade_width) // 2
        grade_y = sub_y + 40
        draw.text((grade_x, grade_y), grade_text, fill=COLORS["text"], font=grade_font)

        # Draw token symbol at bottom
        symbol_font = self._get_font(28, bold=True)
        symbol_text = f"${symbol[:10]}" if symbol else "$TOKEN"
        symbol_bbox = draw.textbbox((0, 0), symbol_text, font=symbol_font)
        symbol_width = symbol_bbox[2] - symbol_bbox[0]
        symbol_x = (self.size - symbol_width) // 2
        symbol_y = self.size - 70
        draw.text((symbol_x, symbol_y), symbol_text, fill=COLORS["text"], font=symbol_font)

        # Draw "AI Sentinel" branding at top
        brand_font = self._get_font(20)
        brand_text = "AI Sentinel"
        brand_bbox = draw.textbbox((0, 0), brand_text, font=brand_font)
        brand_width = brand_bbox[2] - brand_bbox[0]
        brand_x = (self.size - brand_width) // 2
        brand_y = 20
        draw.text((brand_x, brand_y), brand_text, fill=COLORS["text_secondary"], font=brand_font)

        # Save to BytesIO
        output = io.BytesIO()
        img.save(output, format="PNG", optimize=True)
        output.seek(0)

        return output

    async def generate_for_blink(self, blink_id: str) -> io.BytesIO:
        """
        Generate icon for a specific blink.

        Args:
            blink_id: Blink identifier

        Returns:
            BytesIO containing PNG image

        Raises:
            ValueError: If blink not found
        """
        db = await get_database()
        blink = await db.get_blink(blink_id)

        if not blink:
            raise ValueError("Blink not found")

        return self.generate(
            score=blink.overall_score or 0,
            grade=blink.grade or "?",
            symbol=blink.token_symbol or "TOKEN",
            verdict=blink.ai_verdict,
        )

    def generate_default(self) -> io.BytesIO:
        """Generate default icon when blink not found"""
        return self.generate(
            score=0,
            grade="?",
            symbol="TOKEN",
            verdict=None,
        )


# Global generator instance
_icon_generator: Optional[IconGenerator] = None


def get_icon_generator() -> IconGenerator:
    """Get or create global icon generator"""
    global _icon_generator
    if _icon_generator is None:
        _icon_generator = IconGenerator()
    return _icon_generator
