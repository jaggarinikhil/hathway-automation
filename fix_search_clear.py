content = open('agents/renewal_agent.py').read()
old = '''    async def _step_search(self, box_number):
        self.logger.info(f"[RENEWAL][{box_number}] STEP A: Searching...")
        try:
            # Close any open popup first using JS
            await self.page.evaluate("""
                var popup = document.getElementById('MasterBody_pnlAdd');
                if (popup) popup.style.display = 'none';
                var bg = document.getElementById('mpeAdd_backgroundElement');
                if (bg) bg.style.display = 'none';
            """)
            await asyncio.sleep(0.5)
            search_box = await self.page.wait_for_selector(
                self.config.sel_search_box, timeout=self.config.element_timeout
            )
            await search_box.click(click_count=3)'''

new = '''    async def _step_search(self, box_number):
        self.logger.info(f"[RENEWAL][{box_number}] STEP A: Searching...")
        try:
            # Close any open popups and clear search box using JS
            await self.page.evaluate("""
                var ids = ['MasterBody_pnlAdd','mpeAdd_backgroundElement','MasterBody_pnlrenewalPlan'];
                ids.forEach(function(id) {
                    var el = document.getElementById(id);
                    if (el) el.style.display = 'none';
                });
                var sb = document.getElementById('MasterBody_txtSearchParam');
                if (sb) sb.value = '';
            """)
            await asyncio.sleep(0.8)
            search_box = await self.page.wait_for_selector(
                self.config.sel_search_box, timeout=self.config.element_timeout
            )
            await search_box.click(click_count=3)'''

content = content.replace(old, new)
open('agents/renewal_agent.py', 'w').write(content)
print('Done')
