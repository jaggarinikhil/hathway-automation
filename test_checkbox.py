import asyncio, sys
sys.argv = ['x', '--config-file', 'config.json']
from playwright.async_api import async_playwright
from config import Config

async def test():
    config = Config.from_args_or_env()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=100)
        page = await browser.new_page()
        await page.goto('https://partners.hathway-connect.com/Login.aspx', wait_until='networkidle', timeout=60000)
        print('>>> LOG IN, SEARCH BOX, CLICK MAIN TV, CLICK ADD PLAN, SELECT HATHWAY BOUQUET')
        print('>>> WHEN PLAN LIST SHOWS — PRESS ENTER <<<')
        input()

        # Try clicking KMM checkbox via its known ID using Playwright directly
        cb = await page.query_selector('#MasterBody_grdPlanChan_ChkPlanAdd_16')
        if cb:
            print('Checkbox found, visible:', await cb.is_visible())
            # Use Playwright click directly on the checkbox
            await cb.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)
            await page.evaluate("document.getElementById('MasterBody_grdPlanChan_ChkPlanAdd_16').click()")
            await asyncio.sleep(1)
            checked = await page.evaluate("document.getElementById('MasterBody_grdPlanChan_ChkPlanAdd_16').checked")
            print('Checked after JS click:', checked)
        else:
            print('Checkbox NOT found')

        await asyncio.sleep(5)
        await browser.close()

asyncio.run(test())
