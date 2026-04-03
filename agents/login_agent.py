"""
agents/login_agent.py — Handles login with OCR-based CAPTCHA solving.

Flow:
1. Navigate to portal URL.
2. Fill username + password.
3. Solve CAPTCHA via CaptchaAgent.
4. Submit form.
5. Detect success (URL change / absence of error message).
6. Retry up to captcha_max_retries times on CAPTCHA failure.
"""

import asyncio
from playwright.async_api import Page
from agents.captcha_agent import CaptchaAgent
from utils.helpers import human_type, random_delay, wait_and_click


class LoginAgent:

    def __init__(self, page: Page, config, logger):
        self.page = page
        self.config = config
        self.logger = logger
        self.captcha_agent = CaptchaAgent(page, config, logger)

    async def login(self) -> bool:
        """
        Attempt full login flow. Returns True on success, False on total failure.
        """
        self.logger.info(f"[LOGIN] Navigating to {self.config.portal_url}")

        try:
            await self.page.goto(
                self.config.portal_url,
                wait_until="networkidle",
                timeout=self.config.page_load_timeout
            )
        except Exception as e:
            self.logger.error(f"[LOGIN] Failed to load portal URL: {e}")
            return False

        for attempt in range(1, self.config.captcha_max_retries + 1):
            self.logger.info(f"[LOGIN] Attempt {attempt}/{self.config.captcha_max_retries}")

            try:
                success = await self._attempt_login(attempt)
                self.logger.log_login_attempt(attempt, success)

                if success:
                    return True

                # Login failed — refresh CAPTCHA and try again
                self.logger.warning(f"[LOGIN] Attempt {attempt} failed. Refreshing CAPTCHA...")
                await self.captcha_agent.refresh()
                await random_delay(1.5, 2.5)

                # Re-clear the fields for the next attempt
                await self._clear_login_form()

            except Exception as e:
                self.logger.error(f"[LOGIN] Exception on attempt {attempt}: {e}", exc_info=True)
                await asyncio.sleep(2)

        self.logger.error("[LOGIN] All login attempts exhausted.")
        return False

    # ── Private ───────────────────────────────────────────────────────────

    async def _attempt_login(self, attempt: int) -> bool:
        """Fill credentials + CAPTCHA and submit. Returns True if login succeeded."""

        # Fill username
        await self.page.wait_for_selector(
            self.config.sel_username, timeout=self.config.element_timeout
        )
        await human_type(self.page, self.config.sel_username, self.config.username)
        await random_delay(0.3, 0.7)

        # Fill password
        await human_type(self.page, self.config.sel_password, self.config.password)
        await random_delay(0.3, 0.7)

        # Solve CAPTCHA
        captcha_value = await self.captcha_agent.solve()
        self.logger.log_captcha_attempt(attempt, captcha_value, bool(captcha_value))

        if not captcha_value:
            self.logger.warning("[LOGIN] Empty CAPTCHA result — will retry")
            return False

        await human_type(self.page, self.config.sel_captcha_input, captcha_value)
        await random_delay(0.4, 0.9)

        # Submit
        await wait_and_click(self.page, self.config.sel_login_button, self.config)
        await self.page.wait_for_load_state("networkidle", timeout=self.config.page_load_timeout)

        return await self._is_logged_in()

    async def _is_logged_in(self) -> bool:
        """Detect successful login via URL change or absence of error message."""
        current_url = self.page.url.lower()

        # If still on login page URL, likely failed
        if "login.aspx" in current_url:
            # Check for explicit error message
            try:
                err_el = await self.page.wait_for_selector(
                    self.config.sel_login_error,
                    timeout=self.config.short_timeout
                )
                if err_el:
                    err_text = await err_el.inner_text()
                    self.logger.warning(f"[LOGIN] Error message detected: '{err_text.strip()}'")
                    return False
            except Exception:
                pass  # No error element found — ambiguous, check URL again

            # Last-resort URL check
            if "login" in current_url:
                return False

        self.logger.debug(f"[LOGIN] Post-login URL: {self.page.url}")
        return True

    async def _clear_login_form(self):
        """Clear all login fields for a fresh retry."""
        for sel in [
            self.config.sel_username,
            self.config.sel_password,
            self.config.sel_captcha_input
        ]:
            try:
                el = await self.page.query_selector(sel)
                if el:
                    await el.click(click_count=3)
                    await self.page.keyboard.press("Delete")
            except Exception:
                pass
        await asyncio.sleep(0.3)
