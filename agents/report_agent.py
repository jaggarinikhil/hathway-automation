"""Report navigation and extraction only. Does not import any renewal agent."""
import asyncio
import re
from urllib.parse import urlparse
from daily_report_data import ReportError, date_value, parse_grid

# All names and report paths below were observed in the supplied recordings.
GRID_SCRIPT = r'''() => {
 const visible=el=>!!el.getClientRects().length&&getComputedStyle(el).visibility!=='hidden';
 const text=el=>(el.innerText||'').replace(/\s+/g,' ').trim();
 const norm=value=>value.toLowerCase().replace(/[^a-z0-9]/g,'');
 const candidates=[];
 for(const table of document.querySelectorAll('table')) {
  if(!visible(table))continue;
  const rows=[...table.rows].filter(row=>row.closest('table')===table&&visible(row));
  const h=rows.findIndex(row=>{const cols=[...row.cells].map(c=>norm(text(c)));return cols.includes('vcid')&&cols.includes('customername');});
  if(h<0)continue;
  const headers=[...rows[h].cells].map(text), data=[], pagers=[];
  for(const row of rows.slice(h+1)) {
   if(row.querySelector('a[href*="Page$"]')) {pagers.push(row);continue;}
   const cells=[...row.cells];
   if(cells.length===headers.length) {
    const values=cells.map(text);
    if(values.every(x=>!x))continue;
    if(values.every((v,i)=>norm(v)===norm(headers[i])))continue;
    data.push(values);
   } else if(text(row)&&!/^no (records|data|results)/i.test(text(row))) {
    // Unknown totals/row layouts must not silently truncate the report.
    if(!row.querySelector('a'))return {error:'report_row_changed'};
   }
  }
  let next=null, paging=pagers.length>0;
  for(const pager of pagers) {
   const links=[...pager.querySelectorAll('a')].filter(visible);
   const numbered=links.filter(a=>/Page\$\d+/.test(a.getAttribute('href')||''));
   const current=[...pager.querySelectorAll('span')].find(s=>/^\d+$/.test(text(s))&&!s.closest('a'));
   if(current) {
    const wanted=Number(text(current))+1;
    const link=numbered.find(a=>(a.getAttribute('href')||'').match(/Page\$(\d+)/)?.[1]===String(wanted));
    if(link)next={text:text(link),href:link.getAttribute('href')};
    else if(numbered.some(a=>Number((a.getAttribute('href')||'').match(/Page\$(\d+)/)?.[1])>wanted))return {error:'pagination_unrecognized'};
   } else {
    const link=links.find(a=>/Page\$Next/i.test(a.getAttribute('href')||'')||/^(Next|›|>)$/i.test(text(a)));
    if(link)next={text:text(link),href:link.getAttribute('href')};
    else if(numbered.length)return {error:'pagination_unrecognized'};
   }
  }
  // Pager implementations not recognized above cannot be called complete.
  if(!paging&&[...table.querySelectorAll('a')].some(a=>/^(Next|›|>|\d+)$/i.test(text(a))))return {error:'pagination_unrecognized'};
  candidates.push({id:table.id,headers,rows:data,next,paging});
 }
 if(candidates.length!==1)return {error:candidates.length?'ambiguous_report_grid':'report_grid_missing'};
 return candidates[0];
}'''

class ReportAgent:
    def __init__(self, page, config):
        self.page, self.config = page, config
        self.origin = None

    async def open(self, kind):
        # Reuse the existing authenticated home page, never hardcode a hathwayN host.
        parsed=urlparse(self.page.url)
        if parsed.scheme!='https' or not parsed.netloc:
            raise ReportError('unexpected_report_page')
        self.origin=(parsed.scheme,parsed.netloc)
        reports=self.page.get_by_role('link', name=re.compile(r'^Reports$',re.I))
        if not await reports.count():
            reports=self.page.locator('a[href$="/Reports/rptnoncasreport.aspx"],a[href$="../Reports/rptnoncasreport.aspx"]')
        if await reports.count():
            await reports.first.click(timeout=self.config.element_timeout)
        else:
            tile=self.page.get_by_text('Reports',exact=True)
            await tile.first.click(timeout=self.config.element_timeout)
        await self.page.wait_for_load_state('networkidle',timeout=self.config.page_load_timeout)
        name='Plan Expiry Report' if kind=='expiry' else 'Transaction Report'
        await self.page.get_by_role('link',name=name,exact=True).click(timeout=self.config.element_timeout)
        await self.page.wait_for_load_state('networkidle',timeout=self.config.page_load_timeout)
        self._assert_path(kind, detail=False)

    def _assert_path(self, kind, detail=False):
        current=urlparse(self.page.url)
        if self.origin and (current.scheme,current.netloc)!=self.origin:
            raise ReportError('unexpected_report_page')
        path=current.path.lower()
        allowed=['rptexpiry.aspx'] if kind=='expiry' else ['rptaddplantransmso.aspx']
        if detail and kind=='renewals':
            allowed+=['rptaddplantransdet.aspx']
        if '/reports/' not in path or path.rsplit('/',1)[-1] not in allowed:
            raise ReportError('unexpected_report_page')

    async def filters(self, kind, day):
        self._assert_path(kind)
        # The recordings show two prefilled date text boxes. Discover their actual IDs.
        dates=await self.page.evaluate(r'''() => [...document.querySelectorAll('input')].filter(el=>el.getClientRects().length&&/^\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}$/.test(el.value.trim())).map(el=>({id:el.id,value:el.value}))''')
        if len(dates)!=2 or any(not x['id'] for x in dates):
            raise ReportError('date_controls_changed')
        expected=day.strftime('%d-%b-%Y')
        # Select All for Package / Plan Type / Transaction Type / Pay Term.
        # Reject unexpected selects instead of silently applying a restricted filter.
        selects=self.page.locator('select:visible')
        for i in range(await selects.count()):
            control=selects.nth(i)
            labels=await control.locator('option').all_text_contents()
            if 'All' in [x.strip() for x in labels]:
                await control.select_option(label='All')
                await self.page.wait_for_load_state('networkidle',timeout=self.config.page_load_timeout)
            elif any(x.strip().lower()=='english' for x in labels):
                continue
            else:
                raise ReportError('report_filters_changed')
        for item in dates:
            control=self.page.locator('[id="'+item['id'].replace('"','\\"')+'"]')
            await control.evaluate('''(el,value)=>{el.removeAttribute('readonly');el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}''',expected)
            if date_value(await control.input_value())!=day:
                raise ReportError('date_filter_not_set')
        # No individual VC filter: monitor all account-1 boxes.
        boxes=self.page.locator('input[type="text"]:visible')
        for i in range(await boxes.count()):
            field=boxes.nth(i)
            if await field.get_attribute('id') not in {x['id'] for x in dates} and (await field.input_value()).strip():
                raise ReportError('unexpected_customer_filter')
        button='Submit' if kind=='expiry' else 'Search'
        await self.page.get_by_role('button',name=button,exact=True).click(timeout=self.config.element_timeout)
        await self.page.wait_for_load_state('networkidle',timeout=self.config.page_load_timeout)
        self._assert_path(kind, detail=True)

    async def collect(self, kind, day):
        records, ignored, seen = [], 0, set()
        for _ in range(500):
            snapshot=await self.page.evaluate(GRID_SCRIPT)
            if snapshot.get('error'):
                # Explicit empty-state text only; a missing grid never implies zero.
                if snapshot['error']=='report_grid_missing' and await self.page.get_by_text(re.compile(r'^\s*No (?:records|data|results)(?: found| available)?\.?\s*$',re.I)).first.is_visible():
                    if records:
                        raise ReportError('pagination_empty_page')
                    return records, ignored
                raise ReportError(snapshot['error'])
            fingerprint=repr((snapshot['headers'],snapshot['rows']))
            if fingerprint in seen:
                raise ReportError('pagination_repeated')
            seen.add(fingerprint)
            rows, skipped=parse_grid(kind,snapshot['headers'],snapshot['rows'],day)
            records.extend(rows);ignored+=skipped
            if not snapshot.get('next'):
                return records, ignored
            if not snapshot.get('id'):
                raise ReportError('pagination_grid_id_missing')
            grid=self.page.locator('[id="'+snapshot['id'].replace('"','\\"')+'"]')
            next_page=snapshot['next']
            target=grid.get_by_role('link',name=next_page['text'],exact=True)
            if await target.count()!=1:
                raise ReportError('pagination_unrecognized')
            await target.click(timeout=self.config.element_timeout)
            await self.page.wait_for_load_state('networkidle',timeout=self.config.page_load_timeout)
            for _ in range(20):
                fresh=await self.page.evaluate(GRID_SCRIPT)
                if repr((fresh.get('headers'),fresh.get('rows')))!=fingerprint:
                    break
                await asyncio.sleep(.25)
            else:
                raise ReportError('pagination_repeated')
        raise ReportError('pagination_limit')
