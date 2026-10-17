import asyncio,sys
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agents.report_agent import ReportAgent
from daily_report_data import ReportError
from config import Config
DAY=date(2026,10,17)
EXP=['Sr. No.','Account Number','VC Id','New STB No','STB No','Customer Name','Mobile','Package','End Date','Renewal Status']
TX=['Customer Name','VC ID','New STB No','Plan Name','Transaction Type','Transaction Date & Time']
def table(headers,rows,id='grid'):
 return '<table id="'+id+'"><tr>'+''.join('<th>'+h+'</th>' for h in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+c+'</td>' for c in row)+'</tr>' for row in rows)+'</table>'
def exp_grid(page):
 row=[str(page),'123','',f'00000{page}','N00001','Example Customer','9000000000','Example Plan','17/10/2026','N']
 html=table(EXP,[row])
 pager='<tr><td colspan="10">'+''.join('<span>'+str(n)+'</span>' if n==page else '<a href="javascript:__doPostBack(\'grid\',\'Page$'+str(n)+'\')" onclick="showPage('+str(n)+');return false;">'+str(n)+'</a> ' for n in [1,2,3])+'</td></tr>'
 return html.replace('</table>',pager+'</table>')
def filters(kind):
 button='Submit' if kind=='expiry' else 'Search'
 action="document.getElementById('results').innerHTML=pages[1]" if kind=='expiry' else "location.href='rptAddPlanTransUSER.aspx'"
 return '''<input id="from" value="16-Oct-2026"><input id="to" value="16-Oct-2026"><select><option>All</option><option>Other</option></select><input id="vc" type="text"><input type="submit" value="'''+button+'''" onclick="'''+action+'''"><div id="results"></div>'''
async def main():
 from playwright.async_api import async_playwright
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True)
  page=await browser.new_page()
  import json
  async def route(r):
   path=r.request.url
   if '/Transaction/Home.aspx' in path:
    html='<a href="../Reports/rptnoncasreport.aspx">Reports</a>'
   elif 'rptnoncasreport.aspx' in path:
    html='<a href="rptExpiry.aspx">Plan Expiry Report</a><a href="rptAddPlanTransMSO.aspx">Transaction Report</a>'
   elif 'rptExpiry.aspx' in path:
    html=filters('expiry')+'<script>const pages='+json.dumps({n:exp_grid(n) for n in [1,2,3]})+';function showPage(n){document.getElementById("results").innerHTML=pages[n];}</script>'
   elif 'rptAddPlanTransMSO.aspx' in path:
    html=filters('renewals')
   elif 'rptAddPlanTransUSER.aspx' in path:
    html='<input type=\"button\" value=\"View Details\" onclick=\"location.href=\'rptAddPlanTransDET.aspx?showall=A\'\">'
   elif 'rptAddPlanTransDET.aspx' in path:
    html=table(TX,[['Example Customer','0000123','T00001','Plan','Renewal','17-Oct-2026 12:16:49 AM'],['Other Customer','0000456','T00002','Plan','Add','17-Oct-2026 12:16:49 AM']])
   else:html='Unknown fixture'
   await r.fulfill(status=200,content_type='text/html',body=html)
  await page.route('**/*',route)
  agent=ReportAgent(page,Config())
  await page.goto('https://portal.example/hathway3/Transaction/Home.aspx')
  await agent.open('expiry');await agent.filters('expiry',DAY)
  assert await page.locator('#from').input_value()=='17-Oct-2026'
  assert await page.locator('#to').input_value()=='17-Oct-2026'
  rows,ignored=await agent.collect('expiry',DAY)
  assert [r['box'] for r in rows]==['000001','000002','000003']
  print('PASS: Home -> Reports -> Plan Expiry -> today filters -> all three ASP-style grid pages; blank VC fallback and leading zeros')
  await page.goto('https://portal.example/hathway3/Transaction/Home.aspx')
  await agent.open('renewals');await agent.filters('renewals',DAY)
  rows,ignored=await agent.collect('renewals',DAY)
  assert len(rows)==1 and rows[0]['box']=='0000123' and ignored==1
  print('PASS: Transaction Report -> today -> operator summary -> View Details -> detail table; Renewal included and Add excluded')
  await page.set_content('<p>No records found.</p>')
  assert await agent.collect('expiry',DAY)==([],0)
  print('PASS: explicit empty portal report')
  await page.set_content('<p>Portal temporarily unavailable</p>')
  try:await agent.collect('expiry',DAY)
  except ReportError:pass
  else:raise AssertionError('Missing grid incorrectly treated as zero')
  print('PASS: missing grid fails rather than claiming zero')
  await browser.close()
asyncio.run(main())
