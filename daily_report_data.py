"""Pure, read-only report validation and Telegram text rendering."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo('Asia/Kolkata')
LABELS = {
    'vc': ('vcid', 'vcno', 'vcmacid', 'vcnumber'), 'stb': ('newstbno', 'stbno', 'stbnumber', 'stbmacid'),
    'customer': ('customername',), 'phone': ('mobile', 'customermobile'),
    'plan': ('package', 'planname'), 'expiry': ('enddate', 'expirydate', 'planenddate', 'validupto'),
    'type': ('transactiontype',), 'time': ('transactiondatetime',),
    'renewal_status': ('renewalstatus',),
}

class ReportError(Exception):
    pass


def today_ist(now=None):
    return (now or datetime.now(IST)).astimezone(IST).date()


def date_value(value):
    text = re.sub(r'\s+', ' ', str(value)).strip()
    match = re.match(r'^(\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}|\d{1,2}/\d{1,2}/\d{4})', text)
    if not match:
        raise ReportError('unrecognized_date')
    for fmt in ('%d-%b-%Y', '%d/%b/%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(match[1], fmt).date()
        except ValueError:
            continue
    raise ReportError('unrecognized_date')


def normalize(value):
    return re.sub('[^a-z0-9]', '', value.lower())


def parse_grid(kind, headers, rows, report_date, excluded=None):
    columns = [normalize(str(h)) for h in headers]
    def index(key, required=False):
        for alias in LABELS[key]:
            if alias in columns:
                return columns.index(alias)
        if required:
            raise ReportError('report_columns_changed')
        return None
    keys = ['vc', 'customer', 'stb', 'phone', 'plan']
    keys += ['expiry', 'renewal_status'] if kind == 'expiry' else ['type', 'time']
    indices = {key: index(key, key in ('customer', 'expiry', 'type', 'time')) for key in keys}
    if indices['vc'] is None and indices['stb'] is None:
        raise ReportError('report_columns_changed')
    result, ignored = [], 0
    for row in rows:
        if len(row) != len(headers):
            raise ReportError('report_row_changed')
        item = {key: re.sub(r'\s+', ' ', str(row[i])).strip() for key, i in indices.items() if i is not None}
        # Prefer New STB No, but use older STB No if the preferred cell is blank.
        item['stb'] = next((str(row[columns.index(alias)]).strip() for alias in LABELS['stb'] if alias in columns and str(row[columns.index(alias)]).strip()), '')
        # Date mismatches mean the portal did not honor the requested filters.
        if date_value(item['expiry' if kind == 'expiry' else 'time']) != report_date:
            raise ReportError('report_date_mismatch')
        # Preserve identifiers as strings, including leading zeros.
        item['vc'] = item.get('vc', '')
        item['box'] = item['vc'] or item.get('stb', '')
        if not re.fullmatch(r'[A-Za-z0-9-]{1,64}', item['box']):
            raise ReportError('report_identifier_missing')
        if kind == 'renewals' and item['type'].casefold() != 'renewal':
            ignored += 1
            if excluded is not None:
                excluded.append({'box': item['box'], 'type': item['type'] or 'Unspecified'})
            continue
        result.append(item)
    return result, ignored


def utf16_length(value):
    return len(value.encode('utf-16-le')) // 2


def render(kind, report_date, records, collected_at, ignored=0, excluded=None):
    title = 'Plans ending today' if kind == 'expiry' else 'Renewals recorded today'
    unique = len({record['box'] for record in records})
    header = (f'{title}\nDate: {report_date.isoformat()} (IST)\nAccount: 1\n'
              f'As of: {collected_at.astimezone(IST).strftime("%H:%M IST")}\n'
              f'Boxes: {unique} | Plan entries: {len(records)}\n')
    if kind == 'renewals':
        header += 'Source: Hathway Transaction Report; Transaction Type = Renewal.\n'
        header += 'Later transactions are not included.\n'
        if ignored:
            header += f'Other transaction entries excluded: {ignored}\n'
    else:
        header += 'Source: Hathway Plan Expiry Report; all packages.\n'
    blocks = []
    if not records:
        blocks.append('No matching entries reported by Hathway.')
    for record in records:
        lines = [f'Box: {record["box"]}', f'VC: {record["vc"] or "Unavailable"}', f'STB: {record.get("stb") or "Unavailable"}',
                 f'Customer: {record["customer"] or "Unavailable"}']
        if kind == 'expiry':
            lines += [f'Phone: {record.get("phone") or "Unavailable"}', f'End date: {record["expiry"]}']
            if record.get('renewal_status'):
                lines += [f'Portal renewal status: {record["renewal_status"]}']
        else:
            lines += [f'Transaction time: {record["time"]}']
        lines += [f'Plan: {record.get("plan") or "Unavailable"}']
        block = '\n'.join(lines)
        if utf16_length(block) > 2700:
            raise ReportError('report_field_too_long')
        blocks.append(block)
    if kind == 'renewals' and excluded:
        blocks.append('Other transactions (excluded from renewal totals):')
        for entry in excluded:
            block = f'Box: {entry["box"]}\nTransaction type: {entry["type"]}'
            if utf16_length(block) > 2700:
                raise ReportError('report_field_too_long')
            blocks.append(block)
    chunks, current = [], header
    for block in blocks:
        if utf16_length(current + '\n' + block) > 3400:
            chunks.append(current)
            current = header
        current += '\n' + block + '\n'
    chunks.append(current)
    return [f'{text}\nPart {i}/{len(chunks)}' for i, text in enumerate(chunks, 1)]
