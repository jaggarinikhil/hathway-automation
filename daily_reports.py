"""Read-only scheduled portal reports; collect and notify are separate commands."""
import argparse
import asyncio
import json
import os
import re
import sys
import traceback
from datetime import date, datetime
from pathlib import Path
from daily_report_data import IST, ReportError, render, today_ist

RESULT = Path('daily_report_result.json')

class PrivateLogger:
    """Existing login/navigation helpers get no raw portal/credential log sink."""
    def info(self,*args,**kwargs): pass
    debug = warning = error = success = log_login_attempt = log_captcha_attempt = info


def write_result(data):
    RESULT.touch(mode=0o600, exist_ok=True)
    RESULT.chmod(0o600)
    RESULT.write_text(json.dumps(data,ensure_ascii=False)+'\n')


def settings():
    kind=os.getenv('REPORT_TYPE','expiry')
    if kind not in ('expiry','renewals'):
        raise ReportError('invalid_report_type')
    requested=os.getenv('REPORT_DATE','').strip()
    try:
        day=date.fromisoformat(requested) if requested else today_ist()
    except ValueError:
        raise ReportError('invalid_report_date') from None
    if not os.getenv('HATHWAY_USERNAME','').strip() or not os.getenv('HATHWAY_PASSWORD',''):
        raise ReportError('primary_credentials_missing')
    return kind,day


def build_primary_config():
    from config import Config
    return Config(username=os.environ['HATHWAY_USERNAME'].strip(),
                  password=os.environ['HATHWAY_PASSWORD'], headless=True)


def failure_details(error):
    """Classify internally; publish only fixed codes and our own code locations."""
    if isinstance(error,ReportError):
        reason=str(error)
    else:
        message=str(error).lower()
        if 'execution context was destroyed' in message or 'cannot find context' in message:
            reason='report_navigation_pending'
        elif 'strict mode violation' in message:
            reason='report_control_ambiguous'
        elif 'timeout' in type(error).__name__.lower() or 'timeout' in message:
            reason='report_load_timeout'
        elif isinstance(error,(KeyError,TypeError,ValueError)):
            reason='report_data_shape_error'
        elif 'referenceerror' in message or 'typeerror' in message:
            reason='report_script_error'
        else:
            reason='portal_or_browser_error'
    allowed={'daily_reports.py','daily_report_data.py','report_agent.py'}
    locations=[f'{Path(frame.filename).name}:{frame.lineno}' for frame in traceback.extract_tb(error.__traceback__) if Path(frame.filename).name in allowed]
    return reason,locations[-2:]


async def collect():
    # A stale ready result must never be reused after a failed collection.
    write_result({'status':'failed','stage':'workflow','reason':'report_not_completed'})
    stage='configuration'
    try:
        kind,day=settings()
        from agents.login_agent import LoginAgent
        from agents.navigation_agent import NavigationAgent
        from agents.report_agent import ReportAgent
        from playwright.async_api import async_playwright
        cfg=build_primary_config()
        logger=PrivateLogger()
        stage='browser'
        async with async_playwright() as playwright:
            browser=await playwright.chromium.launch(headless=True)
            try:
                page=await browser.new_page(viewport={'width':1600,'height':1100})
                stage='login'
                print('Daily report: logging in to account 1 (read-only).')
                if not await LoginAgent(page,cfg,logger).login():
                    raise ReportError('login_or_captcha_failed')
                stage='navigation'
                await NavigationAgent(page,cfg,logger).handle_post_login_slides()
                report=ReportAgent(page,cfg)
                await report.open(kind)
                stage='filters'
                await report.filters(kind,day)
                stage='extraction'
                records,ignored=await report.collect(kind,day)
                stage='formatting'
                messages=render(kind,day,records,datetime.now(IST),ignored)
                write_result({'status':'ready','type':kind,'date':day.isoformat(),
                              'rows':len(records),'messages':messages})
                print(f'Daily report collected: {len(records)} matching plan entries. Customer data is not printed.')
            finally:
                await browser.close()
        return 0
    except Exception as error:
        reason,locations=failure_details(error)
        write_result({'status':'failed','stage':stage,'reason':reason})
        safe_reason = reason
        print('Daily report failed at '+stage+'; reason: '+safe_reason+'. No raw exception or customer data printed.')
        if locations:
            print('Report code location: '+', '.join(locations))
        return 1


def notify(sender=None):
    if sender is None:
        from telegram_notify import post
        sender=post
    chat=os.getenv('TELEGRAM_REPORT_CHAT_ID','').strip()
    token=os.getenv('TELEGRAM_BOT_TOKEN','')
    if not re.fullmatch(r'\d+',chat) or not token:
        RESULT.unlink(missing_ok=True)
        if not re.fullmatch(r'\d+',chat):
            print('Missing or invalid repository variable TELEGRAM_REPORT_CHAT_ID. Set it to the owner private numeric chat ID.')
        if not token:
            print('Missing repository secret TELEGRAM_BOT_TOKEN.')
        return 1
    try:
        data=json.loads(RESULT.read_text())
    except (OSError,ValueError):
        data={'status':'failed','stage':'workflow','reason':'result_missing'}
    if data.get('status')=='ready':
        messages=data.get('messages')
        if not isinstance(messages,list) or not messages or any(not isinstance(x,str) or not x for x in messages):
            RESULT.unlink(missing_ok=True)
            print('Invalid report result; notification stopped.')
            return 1
    else:
        allowed={'configuration','login','navigation','filters','extraction','formatting','workflow','browser'}
        stage=data.get('stage') if data.get('stage') in allowed else 'workflow'
        reasons={
            'transaction_details_not_opened':'The transaction summary did not open the customer-level View Details report.',
            'report_navigation_pending':'The report page was still redirecting when read.',
            'report_control_ambiguous':'More than one report control matched.',
            'report_load_timeout':'The report page did not finish loading in time.',
            'report_data_shape_error':'A report value did not match the expected data structure.',
            'report_script_error':'The report table reader encountered a script error.',
            'primary_credentials_missing':'First-account GitHub credentials are missing.',
            'invalid_report_type':'The report type is invalid.',
            'invalid_report_date':'The report date must use YYYY-MM-DD.',
            'login_or_captcha_failed':'Account 1 login or CAPTCHA attempts did not complete.',
            'unexpected_report_page':'The expected read-only report page did not open.',
            'date_controls_changed':'The two date controls could not be identified.',
            'date_filter_not_set':'The requested report date could not be set.',
            'report_filters_changed':'The report filter options changed.',
            'unexpected_customer_filter':'An unexpected individual-customer filter was present.',
            'report_columns_changed':'The report column labels changed.',
            'report_row_changed':'The report row layout changed.',
            'report_date_mismatch':'The portal returned a different report date.',
            'unrecognized_date':'A report date could not be read safely.',
            'report_identifier_missing':'A row did not contain a usable VC or STB number.',
            'report_grid_missing':'The report table was not found.',
            'ambiguous_report_grid':'More than one report table matched.',
            'pagination_unrecognized':'The report page controls were not recognized.',
            'pagination_repeated':'The report did not advance to the next page.',
            'pagination_grid_id_missing':'The paginated table could not be identified.',
            'pagination_empty_page':'A later report page unexpectedly contained no data.',
            'pagination_limit':'The report exceeded the safe pagination limit.',
            'report_field_too_long':'A report field exceeded the safe message limit.',
            'portal_or_browser_error':'The portal or browser could not complete the report.',
            'result_missing':'The workflow did not produce a usable report result.',
            'report_not_completed':'The report workflow did not finish collecting data.',
        }
        reason=reasons.get(data.get('reason'),'A complete report could not be verified.')
        messages=[f'Hathway daily report unavailable.\nAccount: 1\nStage: {stage}\nReason: {reason}\nNo complete report could be verified. This does not mean zero expiring or renewed boxes.\nCheck the Daily Hathway Reports run in GitHub Actions. No renewal was submitted.']
    if os.getenv('REPORT_SEND_TELEGRAM','true').lower()!='true':
        RESULT.unlink(missing_ok=True)
        print('Telegram sending disabled for this manual check. Report data was not printed.')
        return 0
    try:
        for message in messages:
            result=sender('https://api.telegram.org/bot'+token+'/sendMessage',{'chat_id':chat,'text':message})
            if not result.get('ok'):
                raise RuntimeError('delivery rejected')
        print('Daily report Telegram delivery completed to the configured owner chat.')
        return 0
    except Exception:
        print('Daily report Telegram delivery failed. A multipart report may be incomplete. Do not rerun renewal; rerun only this read-only report if needed.')
        return 1
    finally:
        # Reports are ephemeral, not retained as Actions artifacts or repository files.
        if RESULT.exists():
            RESULT.unlink()


def main():
    parser=argparse.ArgumentParser(description='Read-only account-1 Hathway daily reports')
    parser.add_argument('command',choices=['collect','notify'])
    args=parser.parse_args()
    return asyncio.run(collect()) if args.command=='collect' else notify()

if __name__=='__main__':
    sys.exit(main())
