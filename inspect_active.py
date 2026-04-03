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
        print('>>> LOG IN, SEARCH AN ACTIVE BOX, CLICK MAIN TV TAB')
        print('>>> WHEN YOU SEE THE EXISTING PLAN TABLE — PRESS ENTER <<<')
        input()

        print('URL:', page.url)

        # Get all table rows with their content
        rows = await page.evaluate('''
            () => {
                var rows = document.querySelectorAll("tr");
                var data = [];
                rows.forEach(function(r) {
                    var cells = Array.from(r.querySelectorAll("td")).map(c => c.innerText.trim());
                    var inputs = Array.from(r.querySelectorAll("input")).map(i => ({
                        id: i.id, type: i.type, value: i.value, name: i.name
                    }));
                    if (cells.length > 0 && (cells.join("").includes("ACTIVE") || inputs.length > 0)) {
                        data.push({cells: cells, inputs: inputs});
                    }
                });
                return data;
            }
        ''')
        for r in rows:
            print('ROW:', r)

        await browser.close()

asyncio.run(test())
