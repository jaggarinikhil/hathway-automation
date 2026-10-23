"""Synthetic regression checks; never accesses Hathway or customer records."""
import asyncio
import json
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agents.report_agent import ReportAgent
from config import Config
from daily_report_data import ReportError

GRID='<table id="result"><tr><th>New STB No</th><th>Customer Name</th><th>Expiry Date</th><th>Mobile</th></tr><tr><td>00000123</td><td>Example Customer</td><td>17/10/2026</td><td>9000000000</td></tr></table>'
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        page=await browser.new_page()
        async def route(request):
            await request.fulfill(status=200,content_type='text/html',body=GRID)
        await page.route('**/*',route)
        await page.goto('https://portal.example/Reports/rptExpiry.aspx')
        agent=ReportAgent(page,Config(page_load_timeout=2000))
        await page.set_content('<div id="content"></div><script>setTimeout(()=>document.getElementById("content").innerHTML='+json.dumps(GRID)+',600)</script>')
        rows,_=await agent.collect('expiry',date(2026,10,17))
        assert rows[0]['box']=='00000123' and rows[0]['vc']==''
        print('PASS: delayed ASP-style grid; no VC column; STB and expiry aliases; leading zeros')
        nested='<table><tr><td><table id="result"><tr><th>VC/Mac ID</th><th>Customer<br>Name</th><th>End Date</th></tr><tr><td>00000123</td><td>Example Customer</td><td>17/10/2026</td></tr></table></td></tr></table>'
        await page.set_content(nested)
        rows,_=await agent.collect('expiry',date(2026,10,17))
        assert len(rows)==1 and rows[0]['vc']=='00000123'
        print('PASS: nested report table with multiline headers and VC/Mac ID alias')
        linked=GRID.replace('<td>00000123</td>','<td><a href="customer.aspx?id=mock">00000123</a></td>')
        await page.set_content(linked)
        rows,_=await agent.collect('expiry',date(2026,10,17))
        assert len(rows)==1 and rows[0]['box']=='00000123'
        print('PASS: numeric customer/box links are not pagination')
        unknown=GRID.replace('</table>','<tr><td colspan="4"><a href="unknown.aspx">2</a></td></tr></table>')
        await page.set_content(unknown)
        try:
            await agent.collect('expiry',date(2026,10,17))
        except ReportError as error:
            assert str(error)=='pagination_unrecognized'
        else:
            raise AssertionError('Unknown pager was silently ignored')
        print('PASS: unknown pager still fails safely')
        await page.set_content('<iframe src="https://portal.example/Reports/inner.aspx"></iframe>')
        rows,_=await agent.collect('expiry',date(2026,10,17))
        assert len(rows)==1 and rows[0]['box']=='00000123'
        print('PASS: report inside visible same-origin iframe')
        await page.set_content('<iframe src="https://untrusted.example/Reports/inner.aspx"></iframe>')
        agent.config.page_load_timeout=1
        try:
            await agent.collect('expiry',date(2026,10,17))
        except ReportError:
            pass
        else:
            raise AssertionError('Untrusted frame was accepted')
        print('PASS: cross-origin frame ignored rather than accepted as a report')
        agent.config.page_load_timeout=2000
        await page.set_content('<p id="empty">No records found.</p><div id="content"></div><script>let busy=true;window.Sys={WebForms:{PageRequestManager:{getInstance:()=>({get_isInAsyncPostBack:()=>busy})}}};setTimeout(()=>{document.getElementById("empty").remove();document.getElementById("content").innerHTML='+json.dumps(GRID)+';busy=false},600)</script>')
        rows,_=await agent.collect('expiry',date(2026,10,17))
        assert len(rows)==1
        print('PASS: in-progress UpdatePanel does not produce a false empty report')
        await browser.close()
asyncio.run(main())
