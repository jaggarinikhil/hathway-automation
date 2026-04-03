"""
agents/captcha_agent.py — OCR-based CAPTCHA solving using Tesseract.

Strategy:
1. Screenshot the CAPTCHA image element from the page.
2. Pre-process the image (greyscale, threshold, denoise) to improve OCR accuracy.
3. Run pytesseract with digit-only config.
4. Strip all non-numeric characters.
5. Return the cleaned string (or empty string on failure).
"""

import re
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

from playwright.async_api import Page
from utils.self_healing import SelectorStore, SelfHealingEngine

try:
    from PIL import Image, ImageFilter, ImageEnhance, ImageOps
    import pytesseract
    import io
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


class CaptchaAgent:
    """
    Handles CAPTCHA detection and OCR-based solving.
    All methods are async to stay compatible with the Playwright event loop.
    """

    # Tesseract config: digits-only, single text line
    _TESS_CONFIG = "--psm 8 --oem 3 -c tessedit_char_whitelist=0123456789"

    def __init__(self, page: Page, config, logger):
        self.page = page
        self.config = config
        self.logger = logger
        self._debug_dir = Path(config.captcha_debug_dir)
        self._debug_dir.mkdir(exist_ok=True)
        self._store = SelectorStore(config.selector_store_path)
        self._healer = SelfHealingEngine(self._store, logger)

        if not OCR_AVAILABLE:
            self.logger.warning(
                "⚠️  Pillow / pytesseract not installed. "
                "Install with: pip install pillow pytesseract"
            )

    # ── Public API ────────────────────────────────────────────────────────

    async def solve(self) -> str:
        """
        Take a screenshot of the CAPTCHA element, run OCR, return digits.
        Returns empty string if anything fails.
        """
        if not OCR_AVAILABLE:
            self.logger.error("OCR libraries not available — cannot solve CAPTCHA")
            return ""

        try:
            raw_bytes = await self._screenshot_captcha()
            if not raw_bytes:
                return ""

            cleaned = await asyncio.get_event_loop().run_in_executor(
                None, self._ocr_bytes, raw_bytes
            )
            self.logger.debug(f"[CAPTCHA] OCR raw result: '{cleaned}'")
            return cleaned

        except Exception as e:
            self.logger.error(f"[CAPTCHA] solve() exception: {e}")
            return ""

    async def refresh(self):
        """Click the CAPTCHA image to force a refresh (common pattern)."""
        try:
            await self.page.click(self.config.sel_captcha_image, timeout=5_000)
            await asyncio.sleep(self.config.delay_captcha_refresh)
            self.logger.debug("[CAPTCHA] Refreshed via image click")
        except Exception:
            # Try a dedicated refresh link/button
            try:
                refresh_sel = (
                    "a:has-text('Refresh'), a[id*='Captcha'][id*='Refresh'], "
                    "#lnkRefreshCaptcha, a[onclick*='captcha']"
                )
                await self.page.click(refresh_sel, timeout=5_000)
                await asyncio.sleep(self.config.delay_captcha_refresh)
                self.logger.debug("[CAPTCHA] Refreshed via refresh link")
            except Exception as e2:
                self.logger.warning(f"[CAPTCHA] Could not refresh: {e2}")

    # ── Private helpers ───────────────────────────────────────────────────

    async def _screenshot_captcha(self) -> Optional[bytes]:
        """Return raw PNG bytes of the CAPTCHA element."""
        try:
            el = await self._healer.smart_locator(self.page, "captcha_image")
            if not el:
                self.logger.error("[CAPTCHA] Element not found")
                return None

            raw = await el.screenshot(type="png")

            # Save debug copy
            ts = datetime.now().strftime("%H%M%S_%f")
            (self._debug_dir / f"captcha_{ts}_raw.png").write_bytes(raw)

            return raw

        except Exception as e:
            self.logger.error(f"[CAPTCHA] Screenshot failed: {e}")
            return None

    def _ocr_bytes(self, raw_bytes: bytes) -> str:
        """
        CPU-bound: pre-process image then run Tesseract.
        Called via run_in_executor so it doesn't block the event loop.
        """
        img = Image.open(io.BytesIO(raw_bytes))

        # ── Pre-processing pipeline ────────────────────────────────────
        # 1. Scale up (Tesseract works better on larger images)
        w, h = img.size
        scale = max(1, int(120 / h))   # aim for ~120px height
        img = img.resize((w * scale, h * scale), Image.LANCZOS)

        # 2. Convert to greyscale
        img = img.convert("L")

        # 3. Increase contrast
        img = ImageEnhance.Contrast(img).enhance(3.0)

        # 4. Binarise (Otsu-like threshold)
        img = img.point(lambda p: 255 if p > 128 else 0)

        # 5. Remove noise with a median filter
        img = img.filter(ImageFilter.MedianFilter(size=3))

        # 6. Invert if background is mostly dark
        histogram = img.histogram()
        dark_pixels = sum(histogram[:128])
        light_pixels = sum(histogram[128:])
        if dark_pixels > light_pixels:
            img = ImageOps.invert(img)

        # Save processed debug image
        ts = datetime.now().strftime("%H%M%S_%f")
        img.save(str(self._debug_dir / f"captcha_{ts}_processed.png"))

        # ── OCR ────────────────────────────────────────────────────────
        text = pytesseract.image_to_string(img, config=self._TESS_CONFIG)
        cleaned = re.sub(r"[^0-9]", "", text)
        return cleaned
