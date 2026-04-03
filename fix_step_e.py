content = open('agents/renewal_agent.py').read()

old = '''    async def _step_select_plan(self, box_number):
        self.logger.info(f"[RENEWAL][{box_number}] STEP E: Selecting plan \'{self.config.target_plan_name}\'...")
        try:
            plan_name = self.config.target_plan_name
            await asyncio.sleep(1.5)

            # Step 1: Scroll plan list to find the plan using JS directly
            # No need to search - just scroll and find exact match
            await asyncio.sleep(1.0)

            # Click checkbox by matching exact link text in the row
            result = await self.page.evaluate(f"""
                () => {{
                    var links = document.querySelectorAll('a');
                    for (var i = 0; i < links.length; i++) {{
                        if (links[i].innerText.trim() === '{plan_name}') {{
                            var row = links[i].closest('tr');
                            if (row) {{
                                var cb = row.querySelector('input[type=checkbox]');
                                if (cb) {{ cb.click(); return 'checkbox_clicked:' + cb.id; }}
                            }}
                            links[i].click();
                            return 'link_clicked';
                        }}
                    }}
                    return 'not_found';
                }}
            """)
            self.logger.info(f"[RENEWAL][{box_number}] Plan select JS result: {result}")

            if result == \'not_found\':
                raise RuntimeError(f"Plan not found: {plan_name}")

            await asyncio.sleep(1.0)

            # Verify checkbox is actually checked
            checked = await self.page.evaluate(f"""
                () => {{
                    var links = document.querySelectorAll('a');
                    for (var i=0; i<links.length; i++) {{
                        if (links[i].innerText.trim() === '{plan_name}') {{
                            var row = links[i].closest('tr');
                            if (row) {{
                                var cb = row.querySelector('input[type=checkbox]');
                                return cb ? cb.checked : false;
                            }}
                        }}
                    }}
                    return false;
                }}
            """)
            self.logger.info(f"[RENEWAL][{box_number}] Checkbox checked: {checked}")

            self.logger.log_step(box_number, "E-PLAN-SELECT", True)
            return True
        except Exception as e:
            self.logger.error(f"[RENEWAL][{box_number}] STEP E exception: {e}")
            return False'''

new = '''    async def _step_select_plan(self, box_number):
        self.logger.info(f"[RENEWAL][{box_number}] STEP E: Selecting plan \'{self.config.target_plan_name}\'...")
        try:
            plan_name = self.config.target_plan_name
            await asyncio.sleep(1.5)

            # Find checkbox ID by matching link text, then click it via Playwright
            cb_id = await self.page.evaluate(f"""
                () => {{
                    var links = document.querySelectorAll('a');
                    for (var i = 0; i < links.length; i++) {{
                        if (links[i].innerText.trim() === '{plan_name}') {{
                            var row = links[i].closest('tr');
                            if (row) {{
                                var cb = row.querySelector('input[type=checkbox]');
                                if (cb) return cb.id;
                            }}
                        }}
                    }}
                    return null;
                }}
            """)
            self.logger.info(f"[RENEWAL][{box_number}] Checkbox ID: {cb_id}")

            if not cb_id:
                raise RuntimeError(f"Plan checkbox not found: {plan_name}")

            # Click checkbox using Playwright (reliable)
            cb_el = await self.page.query_selector(f"#{cb_id}")
            if cb_el:
                await cb_el.scroll_into_view_if_needed()
                await asyncio.sleep(0.5)
                await self.page.evaluate(f"document.getElementById('{cb_id}').click()")
                await asyncio.sleep(1.0)

                # Verify checked
                checked = await self.page.evaluate(f"document.getElementById('{cb_id}').checked")
                self.logger.info(f"[RENEWAL][{box_number}] Checkbox checked: {checked}")

                if not checked:
                    # Try one more time
                    await self.page.evaluate(f"document.getElementById('{cb_id}').click()")
                    await asyncio.sleep(1.0)

            self.logger.log_step(box_number, "E-PLAN-SELECT", True)
            return True
        except Exception as e:
            self.logger.error(f"[RENEWAL][{box_number}] STEP E exception: {e}")
            return False'''

content = content.replace(old, new)
open('agents/renewal_agent.py', 'w').write(content)
print('Done')
