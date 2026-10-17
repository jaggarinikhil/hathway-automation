"""Pure, read-only report validation and Telegram text rendering."""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo('Asia/Kolkata')
LABELS = {
    'vc': ('vcid', 'vcno', 'vcmacid', 'vcnumber'), 'stb': ('newstbno', 'stbno', 'stbnumber', 'stbmacid'),
    'customer': ('customername',), 'phone': ('mobile', 'customermobile', 'mobileno', 'mobilenumber', 'phonenumber', 'customermobileno'),
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


def weekly_period(day):
    """Monday–Saturday preceding the most recent Sunday (including today)."""
    sunday = day - timedelta(days=(day.weekday() + 1) % 7)
    return sunday - timedelta(days=6), sunday - timedelta(days=1)


def parse_grid(kind, headers, rows, report_date, excluded=None, end_date=None):
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
        returned_day=date_value(item['expiry' if kind == 'expiry' else 'time'])
        if not report_date <= returned_day <= (end_date or report_date):
            print(f'[REPORT] Date mismatch: requested {report_date.isoformat()} to {(end_date or report_date).isoformat()}; returned {returned_day.isoformat()}. No customer data printed.')
            raise ReportError('report_date_mismatch')
        # Preserve identifiers as strings, including leading zeros.
        item['vc'] = item.get('vc', '')
        item['box'] = item['vc'] or item.get('stb', '')
        if not re.fullmatch(r'[A-Za-z0-9-]{1,64}', item['box']):
            raise ReportError('report_identifier_missing')
        result.append(item)
    return result, ignored


def utf16_length(value):
    return len(value.encode('utf-16-le')) // 2


def render(kind, report_date, records, collected_at, ignored=0, excluded=None, end_date=None):
    title = 'Plans ending today' if kind == 'expiry' else "Today's transactions"
    if end_date is not None:
        title = 'Weekly transactions (Monday–Saturday)'
    period = (f'Period: {report_date.isoformat()} to {end_date.isoformat()} (IST)' if end_date else f'Date: {report_date.isoformat()} (IST)')
    unique = len({record['box'] for record in records})
    header = (f'{title}\n{period}\nAccount: 1\n'
              f'As of: {collected_at.astimezone(IST).strftime("%H:%M IST")}\n'
              f'Boxes: {unique} | {"Plan entries" if kind == "expiry" else "Transactions"}: {len(records)}\n')
    if kind == 'renewals':
        counts = {}
        for record in records:
            label = record.get('type') or 'Unspecified'
            counts[label] = counts.get(label, 0) + 1
        if counts:
            header += ' | '.join(f'{label}: {count}' for label, count in sorted(counts.items())) + '\n'
        header += 'Source: Hathway Transaction Report; all transaction types.\n'
        header += 'Later transactions are not included.\n'

    else:
        header += 'Source: Hathway Plan Expiry Report; all packages.\n'
    if end_date is not None:
        header = f'{title}\n{period}\nTransactions: {len(records)}\n'
    blocks = []
    if not records:
        blocks.append('No matching entries reported by Hathway.')
    for record in records:
        if end_date is not None:
            lines = [f'Box number: {record["box"]}',
                     f'Name: {record.get("customer") or "Unavailable"}',
                     f'Date: {date_value(record["time"]).isoformat()}']
        else:
            lines = [f'Box: {record["box"]}', f'VC: {record["vc"] or "Unavailable"}', f'STB: {record.get("stb") or "Unavailable"}',
                     f'Customer: {record["customer"] or "Unavailable"}']
            if kind == 'expiry':
                lines += [f'Phone: {record.get("phone") or "Unavailable"}', f'End date: {record["expiry"]}']
                if record.get('renewal_status'):
                    lines += [f'Portal renewal status: {record["renewal_status"]}']
            else:
                lines += [f'Transaction type: {record.get("type") or "Unspecified"}', f'Transaction time: {record["time"]}']
            lines += [f'Plan: {record.get("plan") or "Unavailable"}']
        block = '\n'.join(lines)
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
