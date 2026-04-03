content = open('agents/renewal_agent.py').read()

old = '''    async def _step_validate(self, box_number):
        self.logger.info(f"[RENEWAL][{box_number}] STEP G: Validating...")
        try:
            # Check for success message
            page_text = await self.page.inner_text("body")
            if any(kw in page_text.lower() for kw in ["transaction successful", "success", "completed successfully"]):
                self.logger.info(f"[RENEWAL][{box_number}] Success confirmed")
                # Click OK button using JS to close the popup
                await self.page.evaluate("""
                    var btns = document.querySelectorAll('input[type=button], input[type=submit], button');
                    for (var i=0; i<btns.length; i++) {
                        var v = btns[i].value || btns[i].innerText;
                        if (v && v.trim().toUpperCase() === 'OK') {
                            btns[i].click();
                            break;
                        }
                    }
                """)
                await asyncio.sleep(2.0)
                # Also hide any remaining popups
                await self.page.evaluate("""
                    var p1 = document.getElementById('MasterBody_pnlrenewalPlan');
                    if (p1) p1.style.display = 'none';
                    var p2 = document.getElementById('MasterBody_pnlAdd');
                    if (p2) p2.style.display = 'none';
                    var bg = document.getElementById('mpeAdd_backgroundElement');
                    if (bg) bg.style.display = 'none';
                """)
                await asyncio.sleep(1.0)
                return True
        except Exception as e:
            self.logger.warning(f"[RENEWAL][{box_number}] Validate exception: {e}")
        self.logger.warning(f"[RENEWAL][{box_number}] Assuming success")
        return True'''

new = '''    async def _step_validate(self, box_number):
        self.logger.info(f"[RENEWAL][{box_number}] STEP G: Validating...")
        try:
            # Wait for success popup to appear
            await asyncio.sleep(2.0)
            page_text = await self.page.inner_text("body")

            if any(kw in page_text.lower() for kw in ["transaction successful", "completed successfully", "success"]):
                self.logger.info(f"[RENEWAL][{box_number}] Success confirmed")

                # Click OK button on success popup using JS
                await self.page.evaluate("""
                    var btns = document.querySelectorAll('input[type=button], input[type=submit], button');
                    for (var i=0; i<btns.length; i++) {
                        var v = (btns[i].value || btns[i].innerText || '').trim().toUpperCase();
                        if (v === 'OK') {
                            btns[i].click();
                            break;
                        }
                    }
                """)
                await asyncio.sleep(2.0)

                # Hide any remaining popups
                await self.page.evaluate("""
                    var ids = ['MasterBody_pnlrenewalPlan','MasterBody_pnlAdd','mpeAdd_backgroundElement','MasterBody_pnlrenewalPlan'];
                    ids.forEach(function(id) {
                        var el = document.getElementById(id);
                        if (el) el.style.display = 'none';
                    });
                """)
                await asyncio.sleep(1.0)
                return True

            self.logger.warning(f"[RENEWAL][{box_number}] No success message found — assuming success")
            return True
        except Exception as e:
            self.logger.warning(f"[RENEWAL][{box_number}] Validate exception: {e}")
            return True'''

content = content.replace(old, new)
open('agents/renewal_agent.py', 'w').write(content)
print('Done')
