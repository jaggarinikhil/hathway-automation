"""
agents/renewal_agent.py — Core renewal workflow for each STB box.

Steps per box:
  A. Search box number
  B. Click "Main TV"
  C. Click "Add Plan"
  D. Click "Hathway Bouquet"
  E. Select "HW TL BRONZE KMM 30d"
  F. Click Submit  ← reliable force-click with JS fallback
  G. Click Confirm ← waits for modal/page to settle first
  H. Click OK      ← final confirmation dialog
"""

import asyncio
from playwright.async_api import Page
from agents.navigation_agent import NavigationAgent
from agents.popup_handler_agent import PopupHandlerAgent
from utils.helpers import (
    wait_and_click, human_type, random_delay,
    safe_click, scroll_into_view_and_click
)
from utils.self_healing import SelectorStore, SelfHealingEngine


class RenewalAgent:

    def __init__(self, page: Page, config, logger):
        self.page = page
        self.config = config
        self.logger = logger
        self._nav = NavigationAgent(page, config, logger)
        self._popup = PopupHandlerAgent(page, config, logger)
        
        # Initialize Self-Healing Engine
        self._store = SelectorStore(config.selector_store_path)
        self._healer = SelfHealingEngine(self._store, logger)

    # ── Public entry point ────────────────────────────────────────────────

    async def renew_box(self, box_number: str) -> bool:
        """
        Run the full renewal workflow for one box.
        Retries up to renewal_max_retries times on failure.
        Returns True if renewed successfully.
        """
        for attempt in range(1, self.config.renewal_max_retries + 2):
            self.logger.info(
                f"[RENEWAL][{box_number}] Attempt {attempt}/"
                f"{self.config.renewal_max_retries + 1}"
            )
            try:
                success = await self._run_renewal_steps(box_number)
                if success:
                    self.logger.log_box_result(box_number, True)
                    return True
            except Exception as e:
                self.logger.error(
                    f"[RENEWAL][{box_number}] Exception on attempt {attempt}: {e}",
                    exc_info=True
                )

            if attempt <= self.config.renewal_max_retries:
                self.logger.warning(f"[RENEWAL][{box_number}] Retrying — going back to search...")
                await self._nav.go_back_to_search()
                await random_delay(2.0, 3.5)
            else:
                self.logger.log_box_result(box_number, False, "Exceeded retry limit")

        return False

    # ── Step orchestrator ─────────────────────────────────────────────────

    async def _run_renewal_steps(self, box_number: str) -> bool:
        """Execute all renewal steps in sequence based on status. Returns True on success."""

        # 1. Search for box (Step A)
        if not await self._step_search(box_number):
            return False

        await self._popup.dismiss_popups_if_present()

        # 2. Check Status (ACTIVE or DEACTIVE)
        status = await self._get_box_status(box_number)
        self.logger.info(f"[RENEWAL][{box_number}] Box status: {status}")

        if status == "ACTIVE":
            self.logger.info(f"[RENEWAL][{box_number}] Processing ACTIVE box renewal flow")
            return await self._step_renew_active(box_number)
        else:
            self.logger.info(f"[RENEWAL][{box_number}] Processing DEACTIVE box 'Add Plan' flow")
            
            # --- DEACTIVE FLOW ---
            # 2a. Select Main TV (Step B)
            if not await self._step_select_main_tv(box_number):
                return False

            # 3a. Click Add Plan (Step C)
            if not await self._step_add_plan(box_number):
                return False

            # 4a. Select Hathway Bouquet (Step D)
            if not await self._step_select_bouquet(box_number):
                return False

            # 5a. Search for Plan, Select Checkbox, and Click 'Add' (Step E)
            if not await self._step_select_plan(box_number):
                return False

            # 6a. Click 'Confirm' in the popup (Step G)
            if not await self._step_confirm(box_number):
                return False

            # 7a. Click 'OK' in the final popup (Step H)
            success = await self._step_ok(box_number)
            self.logger.log_step(box_number, "FINAL-SUCCESS", success)
            return success

    # ── Individual steps ──────────────────────────────────────────────────

    async def _step_search(self, box_number: str) -> bool:
        """Enter box number in search bar and submit. Clears previous input first."""
        self.logger.info(f"[RENEWAL][{box_number}] STEP A: Searching...")
        try:
            search_box = await self._healer.smart_locator(self.page, "search_box")
            if not search_box:
                raise RuntimeError("Search box not found")

            # Reliable clear
            await search_box.click(click_count=3)
            await self.page.keyboard.press("Backspace")
            
            await asyncio.sleep(0.2)
            await human_type(self.page, search_box, box_number)
            await random_delay(0.5, 1.0)

            clicked = await self._healer.smart_click(self.page, "search_button")
            if not clicked:
                await self.page.keyboard.press("Enter")

            await self.page.wait_for_load_state("networkidle", timeout=self.config.page_load_timeout)
            await random_delay(1.0, 2.0)

            self.logger.log_step(box_number, "A-SEARCH", True)
            return True

        except Exception as e:
            self.logger.error(f"[RENEWAL][{box_number}] STEP A exception: {e}")
            self.logger.log_step(box_number, "A-SEARCH", False, str(e))
            return False

    async def _step_select_main_tv(self, box_number: str) -> bool:
        """Click on 'Main TV' in the results. Uses self-healing for robustness."""
        self.logger.info(f"[RENEWAL][{box_number}] STEP B: Selecting Main TV...")
        try:
            await asyncio.sleep(1.5)

            clicked = await self._healer.smart_click(self.page, "main_tv_link")
            
            if not clicked:
                # Strategy 2: Search for 'Main TV' text via JS (fallback)
                self.logger.debug(f"[RENEWAL][{box_number}] smart_click failed, trying JS click for 'Main TV'...")
                clicked = await self.page.evaluate("""
                    () => {
                        var links = document.querySelectorAll('a, span');
                        for (var i = 0; i < links.length; i++) {
                            if (links[i].innerText.trim() === 'Main TV') {
                                links[i].click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)

            if not clicked:
                raise RuntimeError("'Main TV' link not found in results")

            # Wait for navigation / state change
            await asyncio.sleep(2.0)
            await self.page.wait_for_load_state("networkidle", timeout=self.config.page_load_timeout)
            await random_delay(1.0, 2.0)

            self.logger.log_step(box_number, "B-MAIN-TV", True)
            return True

        except Exception as e:
            self.logger.error(f"[RENEWAL][{box_number}] STEP B exception: {e}")
            self.logger.log_step(box_number, "B-MAIN-TV", False, str(e))
            return False

    async def _step_add_plan(self, box_number: str) -> bool:
        """Click the 'Add Plan' button."""
        self.logger.info(f"[RENEWAL][{box_number}] STEP C: Clicking Add Plan...")
        try:
            success = await self._healer.smart_click(self.page, "add_plan_button")
            if not success:
                raise RuntimeError("'Add Plan' button not found")

            await self.page.wait_for_load_state("networkidle", timeout=self.config.page_load_timeout)
            await random_delay(1.0, 1.8)

            self.logger.log_step(box_number, "C-ADD-PLAN", True)
            return True

        except Exception as e:
            self.logger.error(f"[RENEWAL][{box_number}] STEP C exception: {e}")
            self.logger.log_step(box_number, "C-ADD-PLAN", False, str(e))
            return False

    async def _step_select_bouquet(self, box_number: str) -> bool:
        """Click 'Hathway Bouquet' radio/button."""
        self.logger.info(f"[RENEWAL][{box_number}] STEP D: Selecting Bouquet...")
        try:
            success = await self._healer.smart_click(self.page, "hathway_bouquet")
            if not success:
                raise RuntimeError("Bouquet selector not found")

            await asyncio.sleep(0.8)
            self.logger.log_step(box_number, "D-BOUQUET", True)
            return True
        except Exception as e:
            self.logger.error(f"[RENEWAL][{box_number}] STEP D exception: {e}")
            self.logger.log_step(box_number, "D-BOUQUET", False, str(e))
            return False

    async def _step_select_plan(self, box_number: str) -> bool:
        """Find and select the target plan from the plan list."""
        self.logger.info(
            f"[RENEWAL][{box_number}] STEP E: Selecting plan '{self.config.target_plan_name}'..."
        )
        try:
            plan_name = self.config.target_plan_name
            await asyncio.sleep(1.5)

            # --- SEARCH SUPPORT ---
            # Look for a search input within the plan modal to filter the list
            try:
                # Try common ASP.NET GridView filter/search selectors
                search_selectors = [
                    "input[type='text'][placeholder*='search']",
                    "input[type='text'][placeholder*='Search']",
                    "input[type='text'][id*='Search']",
                    "input[type='text'][id*='search']",
                    "#MasterBody_grdPlanChan_txtSearch",  # Guess based on common naming
                    ".modal input[type='text']"           # Any text input in modal
                ]
                
                search_box = None
                for sel in search_selectors:
                    candidate = await self.page.query_selector(sel)
                    if candidate and await candidate.is_visible():
                        search_box = candidate
                        break
                
                if search_box:
                    self.logger.debug(f"[RENEWAL][{box_number}] Found plan search box. Filtering...")
                    await search_box.click(click_count=3)
                    await asyncio.sleep(0.1)
                    await search_box.type(plan_name, delay=50)
                    await self.page.keyboard.press("Enter")
                    await asyncio.sleep(0.5)
            except Exception as e:
                self.logger.debug(f"[RENEWAL][{box_number}] Search-and-filter failed (non-critical): {e}")

            # --- ROBUST SELECTION (JS Fallback) ---
            # Find checkbox ID by matching link text (plan name) in the table/list
            cb_id = await self.page.evaluate(f"""
                () => {{
                    var links = document.querySelectorAll('a, span');
                    for (var i = 0; i < links.length; i++) {{
                        if (links[i].innerText.trim().toUpperCase() === '{plan_name.upper()}') {{
                            var row = links[i].closest('tr') || links[i].parentElement;
                            if (row) {{
                                var cb = row.querySelector('input[type=checkbox]');
                                if (cb) return cb.id;
                            }}
                        }}
                    }}
                    return null;
                }}
            """)
            
            self.logger.info(f"[RENEWAL][{box_number}] Found checkbox ID: {cb_id}")

            if not cb_id:
                # One more attempt with partial match if exact failed
                cb_id = await self.page.evaluate(f"""
                    () => {{
                        var links = document.querySelectorAll('a, span');
                        var target = '{plan_name.upper()}';
                        for (var i = 0; i < links.length; i++) {{
                            if (links[i].innerText.trim().toUpperCase().includes(target)) {{
                                var row = links[i].closest('tr') || links[i].parentElement;
                                if (row) {{
                                    var cb = row.querySelector('input[type=checkbox]');
                                    if (cb) return cb.id;
                                }}
                            }}
                        }}
                        return null;
                    }}
                """)

            if not cb_id:
                raise RuntimeError(f"Plan checkbox not found for '{plan_name}'")

            # Click checkbox using JS (bypasses overlay intercepts)
            checked = await self.page.evaluate(f"""
                (id) => {{
                    var el = document.getElementById(id);
                    if (el) {{
                        el.click();
                        return el.checked;
                    }}
                    return false;
                }}
            """, cb_id)
            
            self.logger.info(f"[RENEWAL][{box_number}] Checkbox '{cb_id}' initial state: {{checked}}")
            await asyncio.sleep(1.0)
            
            # Verify it's actually checked (some portals need a second click or have weird behavior)
            final_checked = await self.page.evaluate(f"document.getElementById('{cb_id}').checked")
            if not final_checked:
                self.logger.warning(f"[RENEWAL][{box_number}] Checkbox not checked after first click, retrying JS click...")
                await self.page.evaluate(f"document.getElementById('{cb_id}').click()")
                await asyncio.sleep(1.0)
                final_checked = await self.page.evaluate(f"document.getElementById('{cb_id}').checked")

            if not final_checked:
                self.logger.error(f"[RENEWAL][{box_number}] Failed to check the plan checkbox")
                return False

            # --- CLICK ADD BUTTON ---
            # As per user feedback: "after selecting u should click on add button"
            self.logger.info(f"[RENEWAL][{box_number}] Clicking 'Add' button...")
            try:
                # Use JS click to avoid any overlay issues with the Add button as well
                await self.page.evaluate(f"document.getElementById('MasterBody_btnAddPlan').click()")
                await asyncio.sleep(1.0)
            except Exception as e:
                self.logger.warning(f"[RENEWAL][{box_number}] JS click on 'Add' button failed, trying standard click: {e}")
                await safe_click(self.page, self.config.sel_add_button)

            self.logger.log_step(box_number, "E-PLAN-SELECT", True)
            return True

        except Exception as e:
            self.logger.error(f"[RENEWAL][{box_number}] STEP E exception: {e}")
            self.logger.log_step(box_number, "E-PLAN-SELECT", False, str(e))
            return False

    async def _step_submit(self, box_number: str) -> bool:
        """
        Click the Submit button using multiple strategies to ensure it
        actually fires, not just appears clicked.
        """
        self.logger.info(f"[RENEWAL][{box_number}] STEP F: Clicking Submit...")

        submit_selectors = [
            "input[type='submit']",
            "button[type='submit']",
            "input[value='Submit']",
            "button:has-text('Submit')",
            "a:has-text('Submit')",
            "#btnSubmit",
            "input[id*='Submit']",
            "button[id*='Submit']",
        ]
        combined_sel = ", ".join(submit_selectors)

        try:
            # Wait for any of the Submit buttons to appear
            el = await self.page.wait_for_selector(
                combined_sel, timeout=self.config.short_timeout, state="visible"
            )

            if not el:
                raise RuntimeError("Submit button not found")

            # Scroll into view
            await el.scroll_into_view_if_needed()
            await asyncio.sleep(0.3)

            # Click with fallback strategies
            try:
                await el.click(timeout=3_000, force=False)
            except Exception:
                try:
                    await el.click(timeout=3_000, force=True)
                except Exception:
                    await self.page.evaluate("el => el.click()", el)

            # Faster wait for reaction - next step handles further waits
            try:
                await self.page.wait_for_load_state("load", timeout=5000)
            except Exception:
                pass

            await asyncio.sleep(0.5)
            self.logger.log_step(box_number, "F-SUBMIT", True)
            return True

        except Exception as e:
            self.logger.error(f"[RENEWAL][{box_number}] STEP F exception: {e}")
            self.logger.log_step(box_number, "F-SUBMIT", False, str(e))
            return False

    async def _step_confirm(self, box_number: str) -> bool:
        """
        Click the Confirm button that appears after Submit.
        Waits for it to become visible first.
        """
        self.logger.info(f"[RENEWAL][{box_number}] STEP G: Clicking Confirm...")

        try:
            success = await self._healer.smart_click(self.page, "confirm_button")
            
            if not success:
                # Fallback to older logic if smart_click fails completely
                confirm_selectors = [
                    "button:has-text('Confirm')",
                    "input[value='Confirm']",
                    "#MasterBody_btnaddplanConfirm",
                ]
                for sel in confirm_selectors:
                    if await safe_click(self.page, sel, timeout=3000):
                        success = True
                        break

            if not success:
                raise RuntimeError("Confirm button not found or not visible")

            await asyncio.sleep(0.5)
            self.logger.log_step(box_number, "G-CONFIRM", True)
            return True

        except Exception as e:
            self.logger.error(f"[RENEWAL][{box_number}] STEP G exception: {e}")
            self.logger.log_step(box_number, "G-CONFIRM", False, str(e))
            return False

    async def _step_ok(self, box_number: str) -> bool:
        """
        Click the final OK button/dialog to complete the renewal.
        Handles both native browser dialogs and page-level OK buttons.
        """
        self.logger.info(f"[RENEWAL][{box_number}] STEP H: Clicking OK...")

        try:
            # Quick check for native dialog first
            try:
                async def _accept_dialog(dialog):
                    self.logger.info(f"[RENEWAL][{box_number}] Native dialog accepted")
                    await dialog.accept()
                self.page.once("dialog", _accept_dialog)
                await asyncio.sleep(0.5)
            except Exception:
                pass

            # Search for OK button using smart_click
            success = await self._healer.smart_click(self.page, "ok_button")

            if success:
                self.logger.debug(f"[RENEWAL][{box_number}] OK clicked")
            else:
                self.logger.debug(f"[RENEWAL][{box_number}] No OK button - likely native handled")

            await asyncio.sleep(1.0)
            self.logger.log_step(box_number, "H-OK", True)
            return True

        except Exception as e:
            self.logger.error(f"[RENEWAL][{box_number}] STEP H exception: {e}")
            self.logger.log_step(box_number, "H-OK", False, str(e))
            return False
    async def _get_box_status(self, box_number: str) -> str:
        """Check box status (ACTIVE/DEACTIVE) in the search results table."""
        try:
            # Wait for status cell or table to appear
            await asyncio.sleep(1.0)
            status_cell = await self.page.wait_for_selector(
                self.config.sel_status_cell, timeout=10_000
            )
            if status_cell:
                status_text = (await status_cell.inner_text()).strip().upper()
                if "ACTIVE" in status_text and "DEACTIVE" not in status_text:
                    return "ACTIVE"
                return "DEACTIVE"
            return "DEACTIVE"  # Default
        except Exception as e:
            self.logger.warning(f"[RENEWAL][{box_number}] Could not detect status: {e}")
            return "DEACTIVE"

    async def _step_renew_active(self, box_number: str) -> bool:
        """Flow for ACTIVE boxes: Main TV -> Select existing plan -> Submit -> Confirm -> OK."""
        try:
            # 1. Click Main TV
            if not await self._step_select_main_tv(box_number):
                return False

            # 2. Find and check 'Renew' checkbox/option
            self.logger.info(f"[RENEWAL][{box_number}] Searching for 'Renew' option...")
            try:
                # Use JS to find and click any Renewal checkbox or link
                await self.page.evaluate("""
                    () => {
                        var inputs = document.querySelectorAll('input[type=checkbox]');
                        for (var i = 0; i < inputs.length; i++) {
                            var row = inputs[i].closest('tr');
                            if (row && row.innerText.toUpperCase().includes('ACTIVE')) {
                                // Use click() to trigger onchange/PostBack events
                                inputs[i].click(); 
                                return 'clicked_via_status';
                            }
                        }
                        var links = document.querySelectorAll('a');
                        for (var i = 0; i < links.length; i++) {
                            var t = links[i].innerText.toUpperCase();
                            if (t.includes('RENEW')) { links[i].click(); return 'clicked_renew_link'; }
                        }
                        return 'not_found';
                    }
                """)
                await asyncio.sleep(2.0)
            except Exception as e:
                self.logger.warning(f"[RENEWAL][{box_number}] JS renewal select failed: {e}")

            # 3. Click Submit (Universal JS finder)
            self.logger.info(f"[RENEWAL][{box_number}] Clicking Submit...")
            submit_result = await self.page.evaluate("""
                () => {
                    var btns = document.querySelectorAll('input[type=button], input[type=submit], button, a');
                    for (var i = 0; i < btns.length; i++) {
                        var t = (btns[i].value || btns[i].innerText || '').toUpperCase();
                        if (t === 'SUBMIT' && btns[i].offsetParent !== null) {
                            btns[i].click();
                            return 'clicked_submit';
                        }
                    }
                    return 'not_found';
                }
            """)
            self.logger.debug(f"[RENEWAL][{box_number}] JS Submit result: {submit_result}")
            await asyncio.sleep(1.0)

            # 4. Click Confirm (Universal JS finder)
            self.logger.info(f"[RENEWAL][{box_number}] Clicking Confirm...")
            confirm_result = await self.page.evaluate("""
                () => {
                    var btns = document.querySelectorAll('input[type=button], input[type=submit], button, a');
                    for (var i = 0; i < btns.length; i++) {
                        var t = (btns[i].value || btns[i].innerText || '').toUpperCase();
                        if (t === 'CONFIRM' && btns[i].offsetParent !== null) {
                            btns[i].click();
                            return 'clicked_confirm';
                        }
                    }
                    return 'not_found';
                }
            """)
            self.logger.debug(f"[RENEWAL][{box_number}] JS Confirm result: {confirm_result}")
            await asyncio.sleep(1.0)

            # 5. Click OK (Universal JS finder)
            self.logger.info(f"[RENEWAL][{box_number}] Clicking OK...")
            ok_result = await self.page.evaluate("""
                () => {
                    var btns = document.querySelectorAll('input[type=button], input[type=submit], button, a');
                    for (var i = 0; i < btns.length; i++) {
                        var t = (btns[i].value || btns[i].innerText || '').toUpperCase();
                        if ((t === 'OK' || t === 'CLOSE') && btns[i].offsetParent !== null) {
                            btns[i].click();
                            return 'clicked_ok';
                        }
                    }
                    return 'not_found';
                }
            """)
            self.logger.debug(f"[RENEWAL][{box_number}] JS OK result: {ok_result}")
            
            success = (ok_result == 'clicked_ok') or await self._step_ok(box_number)
            self.logger.log_step(box_number, "FINAL-SUCCESS", success)
            return success

        except Exception as e:
            self.logger.error(f"[RENEWAL][{box_number}] ACTIVE flow exception: {e}")
            return False
