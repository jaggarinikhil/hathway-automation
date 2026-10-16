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

async def customer_details(page, box):
    """Only extract labeled fields from a visible table containing the exact box.

    No page-wide name/phone guessing; unsupported layouts return unavailable.
    """
    try:
        data = await page.evaluate(r'''(box) => {
            const visible = el => !!el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
            const text = el => (el.innerText || '').replace(/\s+/g, ' ').trim();
            const norm = value => value.toLowerCase().replace(/[^a-z0-9]/g, '');
            const fields = {firstname:'first_name', lastname:'last_name', mobileno:'phone',
                mobilenumber:'phone', mobile:'phone', phoneno:'phone', phonenumber:'phone', phone:'phone', rmn:'phone'};
            for (const table of document.querySelectorAll('table')) {
                if (!visible(table)) continue;
                const rows = [...table.rows].filter(row => row.closest('table') === table && visible(row));
                const matches = rows.filter(row => [...row.cells].some(cell => text(cell).toUpperCase() === box.toUpperCase()));
                if (matches.length !== 1) continue;
                const result = {};
                const cells = [...matches[0].cells];
                for (const row of rows) {
                    const heads = [...row.cells];
                    if (heads.length !== cells.length) continue;
                    heads.forEach((head, i) => {
                        const key = fields[norm(text(head))];
                        if (key && visible(cells[i]) && !cells[i].querySelector('table')) result[key] = text(cells[i]);
                    });
                }
                // Labeled detail rows in the same box-scoped table.
                for (const row of rows) {
                    const items = [...row.cells];
                    for (let i=0; i+1<items.length; i++) {
                        const key = fields[norm(text(items[i]))];
                        if (key && !fields[norm(text(items[i+1]))] && visible(items[i+1]) && !items[i+1].querySelector('table')) result[key] = text(items[i+1]);
                    }
                }
                if (Object.keys(result).length) return result;
            }
            return {};
        }''', box)
        if not isinstance(data, dict):
            return {}
        result = {}
        for key in ('first_name', 'last_name', 'phone'):
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
