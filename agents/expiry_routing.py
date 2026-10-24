"""Read the configured plan's expiry; never infer it from the box ACTIVE flag."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

IST=ZoneInfo('Asia/Kolkata')

def expiry_day(value):
    value=re.sub(r'\s+',' ',str(value)).strip()
    match=re.match(r'^(\d{4}-\d{2}-\d{2}|\d{1,2}[-/](?:[A-Za-z]{3}|\d{1,2})[-/]\d{4})(?:\s|$)',value)
    if not match:return None
    for fmt in ('%Y-%m-%d','%d-%b-%Y','%d/%b/%Y','%d/%m/%Y','%d-%m-%Y'):
        try:return datetime.strptime(match[1],fmt).date()
        except ValueError:pass
    return None

async def plan_expiry(page,plan_name):
    values=await page.evaluate(r'''plan => {
      const norm=s=>String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
      const text=e=>(e.innerText||'').replace(/\s+/g,' ').trim();
      const visible=e=>!!e.getClientRects().length;
      const found=[];
      for(const table of document.querySelectorAll('table')){
        if(!visible(table))continue;
        const rows=[...table.rows].filter(r=>r.closest('table')===table&&visible(r));
        for(let h=0;h<rows.length;h++){
          const cols=[...rows[h].cells].map(c=>norm(text(c)));
          const name=cols.findIndex(c=>['planname','package','packagename','bouquetname'].includes(c));
          const end=cols.findIndex(c=>['enddate','expirydate','planenddate','packenddate','validupto'].includes(c));
          if(name<0||end<0)continue;
          for(const row of rows.slice(h+1)){
            const cells=[...row.cells];
            if(cells.length===cols.length&&norm(text(cells[name]))===norm(plan))found.push(text(cells[end]));
          }
          break;
        }
      }
      return found;
    }''',plan_name)
    if not isinstance(values,list) or not values:return None
    days=[expiry_day(value) for value in values]
    if any(day is None for day in days) or len(set(days))!=1:return None
    return days[0]

def india_today():
    return datetime.now(IST).date()
