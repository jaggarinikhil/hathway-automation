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
  await page.set_content('<table><tr><th>Plan Name</th><th>Valid<br>Upto</th></tr><tr><td>Other Plan</td><td>25/10/2026</td></tr><tr><td>Example Plan</td><td>24-<br>Oct-<br>2026</td></tr></table>')
  assert await plan_expiry(page,'Example Plan')==date(2026,10,24)
  assert await plan_expiry(page,'Missing Plan') is None
  await page.set_content('<table id="MasterBody_Grdhathwayspecial"><tr><td>Plan Name</td><td>SD</td><td>HD</td><td>Total</td><td>MRP</td><td>BC Share</td><td>LCO Price</td><td>Valid Upto</td><td>Auto Renew</td><td>Renew</td><td>Status</td><td>Action</td></tr><tr><td><a>Example Plan</a></td><td>317</td><td>317</td><td>317</td><td>274.99</td><td>97.27</td><td>158</td><td>24-OCT-26</td><td>Global On</td><td><input type="checkbox"></td><td>Active</td></tr></table>')
  assert await plan_expiry(page,'Example Plan')==date(2026,10,24)
  print('PASS: actual Hathway two-digit year and omitted trailing Action cell')
  await page.set_content('<table><tr><th>Plan Name</th><th>End Date</th></tr><tr><td>Example Plan</td><td>24/10/2026</td></tr><tr><td>Example Plan</td><td>25/10/2026</td></tr></table>')
  assert await plan_expiry(page,'Example Plan') is None
  print('PASS: configured-plan expiry only; missing and conflicting plan dates stop safely')
  await browser.close()
asyncio.run(main())
