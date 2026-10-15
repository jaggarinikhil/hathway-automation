"""Runs with always() after Telegram execution; never changes the renewal step outcome."""
import json
import os
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen


def post(url, payload, headers=None):
    request = Request(url, json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json', **(headers or {})}, method='POST')
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def main(sender=post):
    if os.getenv('TELEGRAM_ENABLED') != 'true':
        return 0
    request_id = os.getenv('TELEGRAM_REQUEST_ID', '')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
    run_id = os.getenv('GITHUB_RUN_ID', '')
    if not re.fullmatch(r'tg-\d+', request_id) or not re.fullmatch(r'\d+', chat_id) or not re.fullmatch(r'\d+', run_id):
        print('Invalid Telegram metadata; notification skipped.')
        return 1
    result = {'outcome': 'unknown'}
    try:
        result = json.loads(Path('telegram_result.json').read_text())
    except (OSError, ValueError):
        pass
    allowed = {'confirmed_success', 'confirmed_failure', 'reported_success', 'unknown',
               'navigation_failure', 'login_failure', 'browser_failure', 'captcha_failure', 'configuration_error'}
    if result.get('outcome') not in allowed:
        result = {'outcome': 'unknown'}
    payload = {k: v for k, v in result.items() if k in ('outcome', 'duration_seconds', 'failure_reason_code')}
    payload.update(request_id=request_id, chat_id=chat_id, run_id=run_id)
    callback = os.getenv('TELEGRAM_WORKER_URL', '').rstrip('/')
    if not callback.startswith('https://'):
        print('Missing HTTPS Worker callback configuration.')
        return 1
    headers = {'Authorization': 'Bearer '+os.getenv('RESULT_CALLBACK_SECRET', '')}
    try:
        # Persist outcome before Telegram transmission; cron recovers failed notifications.
        accepted = sender(callback+'/complete', payload, headers)
        if accepted.get('notify'):
            sent = sender('https://api.telegram.org/bot'+os.environ['TELEGRAM_BOT_TOKEN']+'/sendMessage',
                          {'chat_id': chat_id, 'text': accepted['message']})
            if not sent.get('ok'):
                raise RuntimeError('notification rejected')
            sender(callback+'/notified', payload, headers)
        print('Telegram completion notification handled.')
        return 0
    except Exception:
        print('Telegram completion notification failed; Worker reconciliation will retry. Check workflow logs and portal before retrying renewal.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
