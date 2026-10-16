"""Read-only portal result parsing. Never log customer contact information."""
import re

REJECTIONS = {
    'vc_terminated_or_missing': re.compile(r'^\s*VC which you are searching is either Terminated or does not exist\.?\s*$', re.I),
    'insufficient_balance': re.compile(r'^\s*(?:(?:you have|account has|your account has)\s+)?insuff(?:icient|ecent|icent)\s+balance(?:\s+in\s+your\s+account)?[.!]?\s*$', re.I),
}

async def rejection(page):
    for code, pattern in REJECTIONS.items():
        if await page.get_by_text(pattern).first.is_visible():
            return code
    return None

async def customer_details(page, box, *, context=None, validated=False):
    """Extract unambiguous labeled customer fields in the validated box context.

    No page-wide name/phone guessing; unsupported layouts return unavailable.
    """
    try:
        data = await page.evaluate(r'''({box, validated}) => {
    const visible = el => !!el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
    const text = el => ((el.matches('input,textarea,select') ? el.value : el.innerText) || '').replace(/\s+/g,' ').trim();
    const norm = value => value.toLowerCase().replace(/[^a-z0-9]/g,'');
    const strip = value => value.replace(/^\s*:\s*/, '').trim();
    const fields = {customername:'full_name',customermobile:'phone',firstname:'first_name',customerfirstname:'first_name',lastname:'last_name',customerlastname:'last_name',
        mobileno:'phone',mobilenumber:'phone',mobile:'phone',phoneno:'phone',phonenumber:'phone',phone:'phone',rmn:'phone',
        registeredmobile:'phone',contact:'phone',registeredmobileno:'phone',registeredmobilenumber:'phone',contactno:'phone',contactnumber:'phone'};
    const value = el => {
        const input = el.querySelector('input:not([type=hidden]):not([type=button]):not([type=submit]),textarea,select');
        return strip(text(input && visible(input) ? input : el));
    };
    const search = document.getElementById('MasterBody_txtSearchParam');
    if (search && search.value.trim().toUpperCase() !== box.toUpperCase()) return {};
    const tables = [...document.querySelectorAll('table')].filter(visible);
    const ownsBox = table => [...table.querySelectorAll('td,th')].some(cell => visible(cell) && !cell.querySelector('table') && strip(text(cell)).toUpperCase() === box.toUpperCase());
    let scopes = tables.filter(ownsBox).sort((a,b) => a.querySelectorAll('*').length-b.querySelectorAll('*').length);
    // In Hathway the search box, identity, and contact form can be separate tables.
    // Require the matching search input plus an actual customer result control.
    const mainTV = document.getElementById('MasterBody_lnkAddon1');
    const boxMatched = scopes.length > 0;
    if (search && mainTV && visible(mainTV) && (boxMatched || validated)) scopes.push(document.body);
    if (!scopes.length) return {};
    const candidates = {full_name:new Set(),first_name:new Set(),last_name:new Set(),phone:new Set()};
    const add = (key, raw) => {
        if (!candidates[key]) return;
        const cleaned = strip(raw);
        if (!cleaned || fields[norm(cleaned)] || cleaned.length>100) return;
        if (key==='phone' && !/^[+\d ()-]{5,30}$/.test(cleaned)) return;
        candidates[key].add(cleaned);
    };
    for (const root of scopes) {
        // Column-oriented grids: use the row tied to the exact VC/STB.
        for (const table of (root.matches?.('table') ? [root,...root.querySelectorAll('table')] : root.querySelectorAll('table'))) {
            const rows=[...table.rows].filter(row => row.closest('table')===table && visible(row));
            const dataRows=rows.filter(row => [...row.cells].some(cell => !cell.querySelector('table') && strip(text(cell)).toUpperCase()===box.toUpperCase()));
            if(dataRows.length!==1) continue;
            const cells=[...dataRows[0].cells];
            for(const row of rows) {
                const headers=[...row.cells];
                if(headers.length!==cells.length)continue;
                headers.forEach((head,i)=>{const key=fields[norm(text(head))];if(key&&visible(cells[i])&&!cells[i].querySelector('table'))add(key,value(cells[i]));});
            }
        }
        // Labeled forms: label, optional colon cell, then span or readonly input.
        for(const row of root.querySelectorAll('tr')) {
            if(!visible(row))continue;
            const cells=[...row.cells];
            for(let i=0;i<cells.length;i++) {
                if(!visible(cells[i]) || cells[i].querySelector('table'))continue;
                const key=fields[norm(text(cells[i]))];
                if(!key)continue;
                let next=i+1;
                while(next<cells.length && !strip(text(cells[next])) && !cells[next].querySelector('input,textarea,select'))next++;
                if(next<cells.length&&visible(cells[next])&&!cells[next].querySelector('table'))add(key,value(cells[next]));
            }
        }
        for(const cell of root.querySelectorAll('td,dd')) {
            if(!visible(cell) || cell.querySelector('table'))continue;
            const match=text(cell).match(/^(Customer Name|Customer Mobile|First Name|Customer First Name|Last Name|Customer Last Name|Mobile(?: No\.?| Number)?|Phone(?: No\.?| Number)?|Registered Mobile(?: No\.?| Number)?|Contact(?: No\.?| Number)?|RMN)\s*:\s*(.+)$/i);
            if(match)add(fields[norm(match[1])],match[2]);
        }
        for(const label of root.querySelectorAll('label[for]')) {
            if(!visible(label))continue;
            const key=fields[norm(text(label))], control=document.getElementById(label.htmlFor);
            if(key&&control&&visible(control))add(key,text(control));
        }
    }
    const result={};
    for(const [key,values] of Object.entries(candidates))if(values.size===1)result[key]=[...values][0];
    return {...result, __box_matched:boxMatched || validated};
}''', {'box':box, 'validated':validated})
        if not isinstance(data, dict):
            return {}
        if context is not None:
            context['box_matched'] = data.get('__box_matched') is True
        result = {}
        for key in ('full_name', 'first_name', 'last_name', 'phone'):
            value = data.get(key)
            if not isinstance(value, str):
                continue
            value = ' '.join(value.split())[:100]
            if key == 'phone' and not re.fullmatch(r'[+\d ()-]{5,30}', value):
                continue
            if value:
                result[key] = value
        return result
    except Exception:
        return {}


async def read_customer_tab(page, box, timeout=5000):
    """Read the optional Customer Details tab; existing flow next clicks Main TV."""
    context = {}
    details = await customer_details(page, box, context=context)
    if details.get('phone') and (details.get('full_name') or (details.get('first_name') and details.get('last_name'))):
        return details
    try:
        tab = page.get_by_text('Customer Details', exact=True).first
        if await tab.is_visible():
            await tab.click(timeout=timeout)
            # Some portals never become network-idle; still read rendered fields.
            try:
                await page.wait_for_load_state('networkidle', timeout=min(timeout, 5000))
            except Exception:
                pass
            refreshed = await customer_details(page, box, validated=context.get('box_matched', False))
            if refreshed:
                return refreshed
    except Exception:
        # Metadata failure must never block renewal or expose portal content.
        pass
    return details
