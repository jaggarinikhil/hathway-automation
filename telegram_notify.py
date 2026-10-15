"""Runs with always() after Telegram execution; never changes the renewal step outcome."""
import json
import os
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def post(url, payload, headers=None):
    request = Request(url, json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json', 'User-Agent': 'Hathway-Renewal-Notifier/1.0', **(headers or {})}, method='POST')
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
    stage = 'Worker completion callback'
    try:
        # Persist outcome before Telegram transmission; cron recovers failed notifications.
        accepted = sender(callback+'/complete', payload, headers)
        if accepted.get('notify'):
            stage = 'Telegram sendMessage'
            sent = sender('https://api.telegram.org/bot'+os.environ['TELEGRAM_BOT_TOKEN']+'/sendMessage',
                          {'chat_id': chat_id, 'text': accepted['message']})
            if not sent.get('ok'):
                raise RuntimeError('notification rejected')
            stage = 'Worker notification receipt'
            sender(callback+'/notified', payload, headers)
        print('Telegram completion notification handled.')
        return 0
    except HTTPError as error:
        print(stage+' failed: HTTP '+str(error.code)+'.')
        if error.code == 401:
            print('Check TELEGRAM_BOT_TOKEN in GitHub.' if stage == 'Telegram sendMessage' else 'Check that RESULT_CALLBACK_SECRET matches in GitHub and Cloudflare.')
        print('Do not rerun renewal to retry a notification.')
        return 1
    except Exception:
        print(stage+' failed. No secrets or raw exception were printed. Check configuration and connectivity; do not rerun renewal.')
        return 1


def check(sender=post):
    """Validate the exact GitHub notification credentials without renewing or messaging."""
    token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    callback = os.getenv('TELEGRAM_WORKER_URL', '').strip().rstrip('/')
    secret = os.getenv('RESULT_CALLBACK_SECRET', '')
    if not token or not secret or not callback.startswith('https://'):
        print('Missing TELEGRAM_BOT_TOKEN, RESULT_CALLBACK_SECRET, or HTTPS TELEGRAM_WORKER_URL.')
        return 1
    ok = True
    try:
        data = sender('https://api.telegram.org/bot'+token+'/getMe', {})
        if not data.get('ok'):
            raise RuntimeError('bot authentication rejected')
        print('PASS: GitHub Telegram bot token is valid.')
    except HTTPError as error:
        print('FAIL: Telegram bot token check returned HTTP '+str(error.code)+'. Update GitHub TELEGRAM_BOT_TOKEN with the current BotFather token.')
        ok = False
    except Exception:
        print('FAIL: Telegram bot identity check; no secret or request URL was printed.')
        ok = False
    try:
        # Empty result is intentionally invalid: authenticated Worker returns 400
        # before reading or changing any request. A mismatched secret returns 401.
        sender(callback+'/complete', {}, {'Authorization':'Bearer '+secret})
        print('FAIL: Worker returned an unexpected response to invalid input.')
        ok = False
    except HTTPError as error:
        if error.code == 400:
            print('PASS: GitHub callback secret is accepted by the Worker.')
        elif error.code == 401:
            print('FAIL: RESULT_CALLBACK_SECRET differs between GitHub and Cloudflare.')
            ok = False
        else:
            print('FAIL: Worker credential check returned HTTP '+str(error.code)+'. Verify TELEGRAM_WORKER_URL.')
            ok = False
    except Exception:
        print('FAIL: Worker connection check; verify TELEGRAM_WORKER_URL and connectivity.')
        ok = False
    print('No renewal was executed, no Telegram message sent, and no request state changed.')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(check() if sys.argv[1:] == ['--check'] else main())
