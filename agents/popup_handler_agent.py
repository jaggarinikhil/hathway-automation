"""
agents/popup_handler_agent.py — Detects and dismisses post-login popups.

Handles:
• Ad "Skip" overlays
• "Acceptance of STB's issued" modal (close ✕)
• Generic unexpected modal/dialog dismissal
• Playwright dialog events (alert, confirm, prompt)
"""

import asyncio
from playwright.async_api import Page
from utils.helpers import safe_click, random_delay


class PopupHandlerAgent:

    # Extra selectors tried in sequence for closing any modal
    _GENERIC_CLOSE_SELECTORS = [
        "button:has-text('Close')",
        "button:has-text('OK')",
        "button:has-text('No')",
        "button[aria-label='Close']",
        ".modal-header .close",
        ".close",
        "[data-dismiss='modal']",
        "button.btn-close",
        "#btnClose",
        "#btnCancel",
    ]

    def __init__(self, page: Page, config, logger):
        self.page = page
        self.config = config
        self.logger = logger
        self._register_dialog_handler()

    # ── Public ────────────────────────────────────────────────────────────

    async def handle_all_popups(self):
        """
        Run the full popup-clearing sweep after login.
        Called once; individual steps are retried internally.
        """
        self.logger.info("[POPUP] Sweeping for post-login popups...")

        await random_delay(1.5, 2.5)   # let the page settle

        await self._dismiss_skip_ad()
        await self._dismiss_stb_popup()
        await self._dismiss_any_remaining_modals()

        self.logger.info("[POPUP] Popup sweep complete")

    async def dismiss_popups_if_present(self):
        """
        Lightweight version — called between steps to clear any
        unexpected popups that may have appeared mid-workflow.
        """
        await self._dismiss_skip_ad()
        await self._dismiss_any_remaining_modals()

    # ── Private ───────────────────────────────────────────────────────────

    def _register_dialog_handler(self):
        """Auto-dismiss native browser dialogs (alert/confirm/prompt)."""
        async def _handler(dialog):
            self.logger.warning(
                f"[POPUP] Native dialog: type={dialog.type} "
                f"message='{dialog.message[:80]}' → dismissing"
            )
            await dialog.dismiss()

        self.page.on("dialog", _handler)

    async def _dismiss_skip_ad(self):
        """Click 'Skip' button/link if an ad overlay is present."""
        try:
            skip_el = await self.page.wait_for_selector(
                self.config.sel_skip_ad,
                timeout=self.config.short_timeout
            )
            if skip_el and await skip_el.is_visible():
                await skip_el.click()
                await asyncio.sleep(0.8)
                self.logger.info("[POPUP] Ad 'Skip' clicked")
        except Exception:
            self.logger.debug("[POPUP] No 'Skip' ad found (OK)")

    async def _dismiss_stb_popup(self):
        """
        Detect the 'Acceptance of STB's issued' modal and close it
        via the ✕ button.
        """
        try:
            popup = await self.page.wait_for_selector(
                self.config.sel_stb_popup,
                timeout=self.config.short_timeout
            )
            if not popup or not await popup.is_visible():
                return

            self.logger.info("[POPUP] STB acceptance popup detected — closing...")

            # Try the configured close selector first
            closed = await safe_click(
                self.page, self.config.sel_close_stb_popup, timeout=5_000
            )

            if not closed:
                # Fallback: generic close buttons
                for sel in self._GENERIC_CLOSE_SELECTORS:
                    if await safe_click(self.page, sel, timeout=2_000):
                        closed = True
                        break

            if closed:
                await asyncio.sleep(0.8)
                self.logger.info("[POPUP] STB popup dismissed")
            else:
                self.logger.warning("[POPUP] Could not dismiss STB popup — continuing anyway")

        except Exception:
            self.logger.debug("[POPUP] No STB popup found (OK)")

    async def _dismiss_any_remaining_modals(self):
        """
        Final sweep: close any visible modal that is still open.
        """
        try:
            # Check if any modal backdrop is still visible
            backdrop = await self.page.query_selector(
                ".modal-backdrop, .overlay, [class*='overlay']"
            )
            if not backdrop or not await backdrop.is_visible():
                return

            self.logger.warning("[POPUP] Unexpected modal backdrop still visible — trying to close")

            for sel in self._GENERIC_CLOSE_SELECTORS:
                if await safe_click(self.page, sel, timeout=2_000):
                    await asyncio.sleep(0.8)
                    self.logger.info(f"[POPUP] Closed remaining modal via: {sel}")
                    break

            # Last resort: press Escape
            await self.page.keyboard.press("Escape")
            await asyncio.sleep(0.5)

        except Exception as e:
            self.logger.debug(f"[POPUP] _dismiss_any_remaining_modals: {e}")
