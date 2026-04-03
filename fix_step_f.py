content = open('agents/renewal_agent.py').read()

old = '''    async def _step_add_and_confirm(self, box_number):
        self.logger.info(f"[RENEWAL][{box_number}] STEP F: Add then Confirm...")
        try:
            await asyncio.sleep(1.0)

            # Click Add button using JS to bypass overlay
            await self.page.evaluate("""
                var btn = document.getElementById('MasterBody_btnAddPlan');
                if (btn) btn.click();
            """)
            await asyncio.sleep(2.0)

            # Check if error popup appeared (Please Select Plan)
            page_text = await self.page.inner_text('body')
            if 'please select plan' in page_text.lower():
                self.logger.warning(f"[RENEWAL][{box_number}] Please Select Plan error — plan not checked")
                # Close error popup
                await self.page.evaluate("""
                    var btns = document.querySelectorAll('input[type=button],input[type=submit],button');
                    for (var i=0; i<btns.length; i++) {
                        var v = (btns[i].value || btns[i].innerText || '').trim().toUpperCase();
                        if (v === 'OK' || v === 'CANCEL') { btns[i].click(); break; }
                    }
                """)
                await asyncio.sleep(1.0)
                raise RuntimeError('Plan not selected — checkbox not ticked')

            # Click Confirm button using JS
            await self.page.evaluate("""
                var btn = document.getElementById('MasterBody_btnaddplanConfirm');
                if (btn) btn.click();
            """)
            await asyncio.sleep(2.0)
            await self.page.wait_for_load_state('networkidle', timeout=self.config.page_load_timeout)
            await random_delay(1.5, 2.5)
            self.logger.log_step(box_number, "F-ADD-CONFIRM", True)
            return True
        except Exception as e:
            self.logger.error(f"[RENEWAL][{box_number}] STEP F exception: {e}")
            return False'''

new = '''    async def _step_add_and_confirm(self, box_number):
        self.logger.info(f"[RENEWAL][{box_number}] STEP F: Add then Confirm...")
        try:
            await asyncio.sleep(1.0)

            # Step F1: Click Add button using JS
            await self.page.evaluate("document.getElementById('MasterBody_btnAddPlan').click()")
            await asyncio.sleep(2.5)

            # Check what appeared
            page_text = await self.page.inner_text('body')

            if 'please select plan' in page_text.lower():
                self.logger.warning(f"[RENEWAL][{box_number}] Please Select Plan error")
                await self.page.evaluate("""
                    var btns = document.querySelectorAll('input[type=submit],input[type=button],button');
                    for (var i=0; i<btns.length; i++) {
                        var v = (btns[i].value || btns[i].innerText || '').trim().toUpperCase();
                        if (v === 'OK' || v === 'CANCEL') { btns[i].click(); break; }
                    }
                """)
                await asyncio.sleep(1.0)
                raise RuntimeError('Plan checkbox was not selected')

            if 'confirmation' in page_text.lower():
                self.logger.info(f"[RENEWAL][{box_number}] Confirmation popup detected — clicking Confirm")
                # Step F2: Click Confirm button
                await self.page.evaluate("document.getElementById('MasterBody_btnaddplanConfirm').click()")
                await asyncio.sleep(3.0)
                self.logger.log_step(box_number, "F-ADD-CONFIRM", True)
                return True

            self.logger.warning(f"[RENEWAL][{box_number}] Neither confirmation nor error found — proceeding")
            self.logger.log_step(box_number, "F-ADD-CONFIRM", True)
            return True

        except Exception as e:
            self.logger.error(f"[RENEWAL][{box_number}] STEP F exception: {e}")
            return False'''

content = content.replace(old, new)
open('agents/renewal_agent.py', 'w').write(content)
print('Done')
