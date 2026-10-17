"""Synthetic browser check: calendar clicks update submission state, typing does not."""
import asyncio,sys
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agents.report_agent import ReportAgent
from config import Config
async def main():
 from playwright.async_api import async_playwright
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True)
  page=await browser.new_page()
  await page.set_content('''<div><input id="from" value="17-Oct-2026"><img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" style="width:20px;height:20px" onclick="document.querySelector('.ajax__calendar_container').style.display='block'"></div>
<input id="submitted" type="hidden" value="17-Oct-2026">
<div class="ajax__calendar_container" style="display:none"><div class="ajax__calendar_title">October, 2026</div><div class="ajax__calendar_day" title="Monday, October 12, 2026" onclick="document.getElementById('from').value='12-Oct-2026';document.getElementById('submitted').value='12-Oct-2026';this.parentElement.style.display='none'">12</div></div>''')
  control=page.locator('#from')
  await control.fill('12-Oct-2026')
  assert await page.locator('#submitted').input_value()=='17-Oct-2026'
  agent=ReportAgent(page,Config())
  assert await agent._calendar_date(control,date(2026,10,12))
  assert await page.locator('#submitted').input_value()=='12-Oct-2026'
  print('PASS: calendar day click updates submission state separately from visible text')
  await browser.close()
asyncio.run(main())
