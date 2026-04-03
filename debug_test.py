import asyncio, sys
sys.argv = ['x', '--config-file', 'config.json']
from playwright.async_api import async_playwright
from config import Config

async def test():
    config = Config.from_args_or_env()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=150)
        page = await browser.new_page()
        await page.goto('https://partners.hathway-connect.com/Login.aspx', wait_until='networkidle', timeout=60000)
        print('>>> LOG IN, SEARCH T403135945802, CLICK MAIN TV, CLICK ADD PLAN')
        print('>>> STOP WHEN PLAN LIST OPENS — PRESS ENTER <<<')
        input()

        # Step D: Click Hathway Bouquet radio using JS
        result = await page.evaluate("""
            () => {
                var rb = document.getElementById('MasterBody_radhwayspecial');
                if (!rb) return 'radio not found';
                rb.click();
                return 'clicked, checked=' + rb.checked;
            }
        """)
        print('Step D result:', result)
        await asyncio.sleep(3)

        # Step E: Find and click KMM checkbox
        cb_id = await page.evaluate("""
            () => {
                var links = document.querySelectorAll('a');
                for (var i=0; i<links.length; i++) {
                    if (links[i].innerText.trim() === 'HW TL BRONZE KMM 30d') {
                        var row = links[i].closest('tr');
                        if (row) {
                            var cb = row.querySelector('input[type=checkbox]');
                            if (cb) return cb.id;
                        }
                    }
                }
                return null;
            }
        """)
        print('Checkbox ID:', cb_id)

        if cb_id:
            await page.evaluate(f"document.getElementById('{cb_id}').click()")
            await asyncio.sleep(1)
            checked = await page.evaluate(f"document.getElementById('{cb_id}').checked")
            print('Checked:', checked)

            # Step F: Click Add
            await asyncio.sleep(1)
            await page.evaluate("document.getElementById('MasterBody_btnAddPlan').click()")
            await asyncio.sleep(3)
            print('Page text after Add:', (await page.inner_text('body'))[:200])

        await asyncio.sleep(5)
        await browser.close()

asyncio.run(test())
