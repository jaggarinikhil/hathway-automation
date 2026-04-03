import asyncio
from utils.helpers import safe_click, random_delay
from utils.self_healing import SelectorStore, SelfHealingEngine


class NavigationAgent:

    _SKIP_SELECTORS = [
        "#btnSkip",
        "#btnDPASkip",
        "input[value='Skip']",
        "button:has-text('Skip')",
        "a:has-text('Skip')",
    ]

    _CLOSE_SELECTORS = [
        "img#imgclose",
        "img#imgClose4",
        "img#Image17",
        "img#Image9",
        "img#Image8",
        "img#imgClose",
        "img#MasterBody_ImgPODArchive",
        "input[id*='close']",
        "input[id*='Close']",
        "button:has-text('Close')",
        "input[value='Close']",
        "a:has-text('Close')",
        "span:has-text('×')",
        "button:has-text('×')",
        ".ui-dialog-titlebar-close",
        "a.ui-dialog-titlebar-close",
    ]

    def __init__(self, page, config, logger):
        self.page = page
        self.config = config
        self.logger = logger
        self._store = SelectorStore(config.selector_store_path)
        self._healer = SelfHealingEngine(self._store, logger)

    async def handle_post_login_slides(self):
        self.logger.info("[NAV] Handling post-login slideshows and popups...")
        await random_delay(2.0, 3.0)
        for attempt in range(10):
            dismissed = False
            for sel in self._SKIP_SELECTORS:
                if await safe_click(self.page, sel, timeout=3000):
                    self.logger.info(f"[NAV] Clicked Skip ({sel})")
                    await random_delay(2.0, 3.0)
                    dismissed = True
                    break
            if not dismissed:
                for sel in self._CLOSE_SELECTORS:
                    if await safe_click(self.page, sel, timeout=3000):
                        self.logger.info(f"[NAV] Clicked Close ({sel})")
                        await random_delay(2.0, 3.0)
                        dismissed = True
                        break
            if not dismissed:
                break
        self.logger.info("[NAV] Post-login slide handling complete")

    async def go_to_package_management(self) -> bool:
        self.logger.info("[NAV] Navigating to Package Management...")

        # Step 1: Close STB popup if present (the × button top-right of popup)
        await self._close_stb_popup()

        # Step 2: Click Pack Management from dashboard
        if await self._healer.smart_click(self.page, "pack_management"):
            self.logger.info(f"[NAV] Clicked Pack Management")
            await asyncio.sleep(1.0)

        # Step 3: Close STB popup again if it appears after clicking
        await self._close_stb_popup()

        # Step 4: Wait for search box
        try:
            await self.page.wait_for_selector(
                "#MasterBody_txtSearchParam",
                timeout=self.config.element_timeout,
                state="visible"
            )
            self.logger.info("[NAV] Package Management search box ready")
            return True
        except Exception:
            pass

        self.logger.error("[NAV] Could not reach Package Management search box")
        return False

    async def _close_stb_popup(self):
        """Close the STB acceptance popup using the × circle button."""
        await asyncio.sleep(2.0)

        if await self._healer.smart_click(self.page, "stb_popup_close"):
            self.logger.info(f"[NAV] Closed STB popup")
            await asyncio.sleep(1.0)
            return

        self.logger.debug("[NAV] No STB popup found (OK)")

        self.logger.debug("[NAV] No STB popup found (OK)")

    async def go_back_to_search(self) -> bool:
        try:
            el = await self.page.query_selector("#MasterBody_txtSearchParam")
            if el and await el.is_visible():
                return True
            return await self.go_to_package_management()
        except Exception:
            return False