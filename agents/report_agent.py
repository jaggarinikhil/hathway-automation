"""Report navigation and extraction only. Does not import any renewal agent."""
import asyncio
import re
from datetime import datetime
from urllib.parse import urlparse
from playwright.async_api import Error as PlaywrightError
from daily_report_data import ReportError, date_value, parse_grid, LABELS

# All names and report paths below were observed in the supplied recordings.
GRID_SCRIPT = r'''({kind, labels}) => {
 try {if(window.Sys?.WebForms?.PageRequestManager?.getInstance()?.get_isInAsyncPostBack())return {error:'report_grid_missing',loading:true};} catch {}
 const visible=el=>!!el.getClientRects().length&&getComputedStyle(el).visibility!=='hidden';
 const text=el=>(el.innerText||'').replace(/\s+/g,' ').trim();
 const norm=value=>value.toLowerCase().replace(/[^a-z0-9]/g,'');
 const has=(columns,key)=>labels[key].some(alias=>columns.includes(alias));
 const candidates=[], recognized=new Set();
 let tableCount=0;

 for(const table of document.querySelectorAll('table')) {
  if(!visible(table))continue;
  tableCount++;
  const rows=[...table.rows].filter(row=>row.closest('table')===table&&visible(row));
  const h=rows.findIndex(row=>{
   const cols=[...row.cells].map(c=>norm(text(c)));
   for(const key of Object.keys(labels))if(has(cols,key))recognized.add(key);
   return has(cols,'customer')&&(has(cols,'vc')||has(cols,'stb'))&&
    (kind==='expiry'?has(cols,'expiry'):has(cols,'type')&&has(cols,'time'));
  });
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
 if(candidates.length!==1)return {error:candidates.length?'ambiguous_report_grid':'report_grid_missing',diagnostics:{visible_tables:tableCount,recognized_columns:[...recognized].sort()}};
 return candidates[0];
}'''

class ReportAgent:
    def __init__(self, page, config):
        self.page, self.config = page, config
        self.origin = None
        self.grid_context = page
        self.empty_contexts = [page]

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
            allowed+=['rptaddplantransuser.aspx','rptaddplantransdet.aspx']
        if '/reports/' not in path or path.rsplit('/',1)[-1] not in allowed:
            raise ReportError('unexpected_report_page')

    async def filters(self, kind, day, end_date=None):
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
        for position,item in enumerate(dates):
            target_day = (end_date or day) if position else day
            expected = target_day.strftime('%d-%b-%Y')
            control=self.page.locator('[id="'+item['id'].replace('"','\\"')+'"]')
            if kind=='renewals' and await self._calendar_date(control,target_day):
                pass
            else:
                await control.evaluate('(el)=>el.removeAttribute("readonly")')
                await control.fill(expected)
                await control.press('Tab')
            if date_value(await control.input_value())!=target_day:
                raise ReportError('date_filter_not_set')
        # No individual VC filter: monitor all account-1 boxes.
        boxes=self.page.locator('input[type="text"]:visible')
        for i in range(await boxes.count()):
            field=boxes.nth(i)
            if await field.get_attribute('id') not in {x['id'] for x in dates} and (await field.input_value()).strip():
                raise ReportError('unexpected_customer_filter')
        await self._log_report_dates('search form')
        button='Submit' if kind=='expiry' else 'Search'
        await self.page.get_by_role('button',name=button,exact=True).click(timeout=self.config.element_timeout)
        await self.page.wait_for_load_state('networkidle',timeout=self.config.page_load_timeout)
        if kind=='renewals':
            await self._transaction_details()
        self._assert_path(kind, detail=True)

    async def _calendar_date(self,control,day):
        # Match the recording: click the adjacent calendar icon and choose a day.
        icons=control.locator('xpath=..').locator('img:visible,input[type="image"]:visible')
        if await icons.count()!=1:
            return False
        await icons.click(timeout=self.config.element_timeout)
        calendar=self.page.locator('.ajax__calendar_container:visible')
        await calendar.wait_for(state='visible',timeout=self.config.element_timeout)
        for _ in range(25):
            title=(await calendar.locator('.ajax__calendar_title').inner_text()).replace(',','').strip()
            try:
                shown=datetime.strptime(title,'%B %Y').date()
            except ValueError:
                raise ReportError('date_controls_changed') from None
            delta=(day.year-shown.year)*12+day.month-shown.month
            if not delta:
                break
            await calendar.locator('.ajax__calendar_next' if delta>0 else '.ajax__calendar_prev').click()
        else:
            raise ReportError('date_filter_not_set')
        candidates=calendar.locator('.ajax__calendar_day[title]')
        for candidate in await candidates.all():
            title=await candidate.get_attribute('title')
            try:
                selected=datetime.strptime(title,'%A, %B %d, %Y').date()
            except (ValueError,TypeError):
                continue
            if selected==day:
                await candidate.click(timeout=self.config.element_timeout)
                await calendar.wait_for(state='hidden',timeout=self.config.element_timeout)
                print('[REPORT] Calendar selection completed: '+day.isoformat())
                return True
        raise ReportError('date_filter_not_set')

    async def _log_report_dates(self, stage):
        # Only date-shaped values, never arbitrary input contents or customer data.
        values=await self.page.evaluate(r"""() => [...document.querySelectorAll('input')].filter(el=>el.getClientRects().length&&/^\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}$/.test(el.value.trim())).map(el=>el.value.trim())""")
        if isinstance(values,list):
            safe=[value for value in values if isinstance(value,str) and re.fullmatch(r'\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}',value)]
            print('[REPORT] '+stage+' dates: '+(', '.join(safe) or 'no visible date controls'))
        visible_dates=await self.page.evaluate(r"() => [...new Set((document.body.innerText||'').match(/\b\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}\b/g)||[])].slice(0,10)")
        if isinstance(visible_dates,list):
            print('[REPORT] '+stage+' displayed dates: '+', '.join(str(x) for x in visible_dates if re.fullmatch(r'\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}',str(x))))

    async def _transaction_details(self):
        # Observed in the recording: Search -> rptAddPlanTransUSER.aspx
        # (operator summary) -> View Details -> rptAddPlanTransDET.aspx.
        summary=re.compile(r'/Reports/rptAddPlanTrans(?:USER|DET)\.aspx(?:[?#]|$)',re.I)
        if not summary.search(self.page.url):
            empty=self.page.get_by_text(re.compile(r'^\s*No (?:records|data|results)(?: found| available)?\.?\s*$',re.I)).first
            if await empty.is_visible():
                return
            await self.page.wait_for_url(summary,timeout=self.config.page_load_timeout)
        await self.page.wait_for_load_state('networkidle',timeout=self.config.page_load_timeout)
        self._assert_path('renewals',detail=True)
        await self._log_report_dates('transaction summary')
        if urlparse(self.page.url).path.lower().endswith('rptaddplantransdet.aspx'):
            return
        # The recording follows the linked User ID, which preserves search state.
        # Use it only when the summary has exactly one operator; never silently
        # omit other operators. Multi-operator summaries retain the all-details path.
        operator_links=self.page.locator('a:visible')
        usable=[]
        for link in await operator_links.all():
            text=(await link.inner_text()).strip()
            if re.fullmatch(r'\d{6,}',text):
                usable.append(link)
        if len(usable)==1:
            control=usable[0]
            print('[REPORT] Following the sole operator User ID detail link.')
        else:
            name=re.compile(r'^View\s+Details$',re.I)
            control=self.page.get_by_role('button',name=name).or_(self.page.get_by_role('link',name=name)).first
        await control.wait_for(state='visible',timeout=self.config.element_timeout)
        popups=[]
        original=self.page
        def remember_popup(popup):
            popups.append(popup)
        original.on('popup',remember_popup)
        try:
            await control.click(timeout=self.config.element_timeout)
            for _ in range(max(1,self.config.page_load_timeout//250)):
                for candidate in [original]+popups:
                    if urlparse(candidate.url).path.lower().endswith('/reports/rptaddplantransdet.aspx'):
                        self.page=candidate
                        self.grid_context=candidate
                        await candidate.wait_for_load_state('networkidle',timeout=self.config.page_load_timeout)
                        self._assert_path('renewals',detail=True)
                        return
                await asyncio.sleep(.25)
            raise ReportError('transaction_details_not_opened')
        finally:
            original.remove_listener('popup',remember_popup)

    async def _snapshot(self, kind):
        contexts=[self.page]
        frames=getattr(self.page,'frames',[])
        if isinstance(frames,list):
            origin=urlparse(self.page.url)
            for frame in frames:
                if frame==self.page.main_frame:
                    continue
                target=urlparse(frame.url)
                same_origin=(target.scheme,target.netloc)==(origin.scheme,origin.netloc)
                if not (same_origin or frame.url in ('about:blank','about:srcdoc')):
                    continue
                try:
                    if await (await frame.frame_element()).is_visible():
                        contexts.append(frame)
                except Exception:
                    continue
        valid, failures=[], []
        self.empty_contexts=contexts
        for context in contexts:
            try:
                snapshot=await context.evaluate(GRID_SCRIPT, {'kind':kind, 'labels':LABELS})
            except PlaywrightError as error:
                # Transaction reports redirect to a separate detail page. A new
                # execution context can replace the form while we inspect it.
                message=str(error).lower()
                if any(marker in message for marker in (
                    'execution context was destroyed', 'cannot find context',
                    'frame was detached', 'frame has been detached',
                )):
                    return {'error':'report_grid_missing','loading':True}
                raise
            if not snapshot.get('error'):
                valid.append((context,snapshot))
            else:
                failures.append(snapshot)
        if any(item.get('loading') for item in failures):
            return {'error':'report_grid_missing','loading':True}
        if len(valid)>1:
            return {'error':'ambiguous_report_grid'}
        if valid:
            self.grid_context,snapshot=valid[0]
            return snapshot
        specific=next((item for item in failures if item.get('error')!='report_grid_missing'),None)
        if specific:
            return specific
        columns=set()
        count=0
        for failure in failures:
            diagnostics=failure.get('diagnostics',{})
            count+=diagnostics.get('visible_tables',0)
            columns.update(diagnostics.get('recognized_columns',[]))
        return {'error':'report_grid_missing','loading':any(item.get('loading') for item in failures),
                'diagnostics':{'visible_tables':count,'recognized_columns':sorted(columns)}}

    async def _wait_for_grid(self, kind):
        # ASP.NET UpdatePanel responses may render after networkidle was observed.
        # Wait for a recognizable schema, not a fixed sleep or a guessed grid ID.
        attempts=max(1,min(120,(self.config.page_load_timeout+249)//250))
        snapshot={}
        for index in range(attempts):
            snapshot=await self._snapshot(kind)
            if snapshot.get('error')!='report_grid_missing':
                return snapshot
            if not snapshot.get('loading'):
                for context in self.empty_contexts:
                    empty=context.get_by_text(re.compile(r'^\s*No (?:records|data|results)(?: found| available)?\.?\s*$',re.I)).first
                    if await empty.is_visible():
                        snapshot['explicit_empty']=True
                        return snapshot
            if index+1<attempts:
                await asyncio.sleep(.25)
        # Only fixed schema names/counts; never print headers, IDs or cell values.
        diagnostics=snapshot.get('diagnostics', {})
        columns=[key for key in diagnostics.get('recognized_columns',[]) if key in LABELS]
        count=diagnostics.get('visible_tables',0)
        if not isinstance(count,int):
            count=0
        print(f'[REPORT] Grid not recognized after waiting. Visible tables: {count}; recognized column types: '+(', '.join(columns) or 'none'))
        return snapshot

    async def collect(self, kind, day, end_date=None):
        records, ignored, seen = [], 0, set()
        self.excluded_transactions = []
        for _ in range(500):
            snapshot=await self._wait_for_grid(kind)
            if snapshot.get('error'):
                # Explicit empty-state text only; a missing grid never implies zero.
                if snapshot['error']=='report_grid_missing' and snapshot.get('explicit_empty'):
                    if records:
                        raise ReportError('pagination_empty_page')
                    return records, ignored
                raise ReportError(snapshot['error'])
            fingerprint=repr((snapshot['headers'],snapshot['rows']))
            if fingerprint in seen:
                raise ReportError('pagination_repeated')
            seen.add(fingerprint)
            rows, skipped=parse_grid(kind,snapshot['headers'],snapshot['rows'],day,self.excluded_transactions,end_date)
            records.extend(rows);ignored+=skipped
            if not snapshot.get('next'):
                return records, ignored
            if not snapshot.get('id'):
                raise ReportError('pagination_grid_id_missing')
            grid=self.grid_context.locator('[id="'+snapshot['id'].replace('"','\\"')+'"]')
            next_page=snapshot['next']
            target=grid.get_by_role('link',name=next_page['text'],exact=True)
            if await target.count()!=1:
                raise ReportError('pagination_unrecognized')
            await target.click(timeout=self.config.element_timeout)
            await self.page.wait_for_load_state('networkidle',timeout=self.config.page_load_timeout)
            for _ in range(20):
                fresh=await self._snapshot(kind)
                if repr((fresh.get('headers'),fresh.get('rows')))!=fingerprint:
                    break
                await asyncio.sleep(.25)
            else:
                raise ReportError('pagination_repeated')
        raise ReportError('pagination_limit')
