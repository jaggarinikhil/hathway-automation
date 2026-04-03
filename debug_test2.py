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
        print('>>> LOG IN, SEARCH BOX, CLICK MAIN TV, CLICK ADD PLAN, SELECT HATHWAY BOUQUET')
        print('>>> WHEN PLAN LIST SHOWS — PRESS ENTER <<<')
        input()

        # Click KMM checkbox
        cb_id = await page.evaluate("""
            () => {
                var links = document.querySelectorAll('a');
                for (var i=0; i<links.length; i++) {
                    if (links[i].innerText.trim() === 'HW TL BRONZE KMM 30d') {
                        var row = links[i].closest('tr');
                        if (row) {
                            var cb = row.querySelector('input[type=checkbox]');
                            if (cb) { cb.click(); return cb.id; }
                        }
                    }
                }
                return null;
            }
        """)
        print('Checkbox clicked, ID:', cb_id)
        await asyncio.sleep(2)

        # Click Add button
        await page.evaluate("document.getElementById('MasterBody_btnAddPlan').click()")
        print('Add clicked')
        await asyncio.sleep(3)

        # Check what's visible now
        body = await page.inner_text('body')
        print('Body contains "Please Select":', 'Please Select' in body)
        print('Body contains "Confirmation":', 'Confirmation' in body)
        print('Body contains "Transaction":', 'Transaction' in body)

        # Find all visible buttons
        buttons = await page.query_selector_all('input[type=submit], input[type=button], button')
        for btn in buttons:
            visible = await btn.is_visible()
            val = await btn.get_attribute('value')
            id_ = await btn.get_attribute('id')
            txt = (await btn.inner_text()).strip()
            if visible:
                print(f'VISIBLE BUTTON: id={id_} value={val} text={txt}')

        await asyncio.sleep(5)
        await browser.close()

asyncio.run(test())
