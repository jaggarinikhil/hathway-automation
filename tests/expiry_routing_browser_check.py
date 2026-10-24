"""Read-only synthetic plan-grid test; no portal access."""
import asyncio,sys
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agents.expiry_routing import plan_expiry
async def main():
 from playwright.async_api import async_playwright
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True);page=await browser.new_page()
  await page.set_content('<table><tr><th>Plan Name</th><th>Expiry Date</th></tr><tr><td>Other Plan</td><td>25/10/2026</td></tr><tr><td>Example Plan</td><td>24/10/2026</td></tr></table>')
  assert await plan_expiry(page,'Example Plan')==date(2026,10,24)
  assert await plan_expiry(page,'Missing Plan') is None
  await page.set_content('<table><tr><th>Plan Name</th><th>End Date</th></tr><tr><td>Example Plan</td><td>24/10/2026</td></tr><tr><td>Example Plan</td><td>25/10/2026</td></tr></table>')
  assert await plan_expiry(page,'Example Plan') is None
  print('PASS: configured-plan expiry only; missing and conflicting plan dates stop safely')
  await browser.close()
asyncio.run(main())
