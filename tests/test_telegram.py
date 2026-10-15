import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from telegram_run import classify, execute, outcome_details
from telegram_notify import main
from config import Config


class TelegramTests(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(classify(['001'], [], {}, ['001']), 'reported_success')
        self.assertEqual(classify(['001'], [], {'renewal_verified': True}, ['001']), 'confirmed_success')
        self.assertEqual(classify([], ['001'], {'renewal_verified': False}, ['001']), 'confirmed_failure')
        self.assertEqual(classify([], ['001'], {}, ['001']), 'unknown')
        self.assertEqual(classify([], ['001'], {'errors': ['Login failed after all retries']}, ['001']), 'login_failure')
        self.assertEqual(classify([], ['001'], {'errors': ['CAPTCHA failed', 'Login failed after all retries']}, ['001']), 'captcha_failure')

    def test_existing_core_adapter_and_crash(self):
        cfg=Config(username='mock',password='mock',box_numbers=['001'])
        async def success(config): return ['001'], [], {}
        async def crash(config): raise ValueError('private portal content')
        previous=os.getcwd()
        with tempfile.TemporaryDirectory() as d, patch('telegram_run.build_config_from_env',return_value=cfg):
            try:
                os.chdir(d)
                self.assertEqual(asyncio.run(execute(success)),0)
                self.assertEqual(json.loads(Path('telegram_result.json').read_text())['outcome'],'reported_success')
                self.assertEqual(asyncio.run(execute(crash)),1)
                self.assertNotIn('private portal',Path('telegram_result.json').read_text())
                self.assertEqual(json.loads(Path('telegram_result.json').read_text())['outcome'],'browser_failure')
            finally:os.chdir(previous)

    def test_notification_api_and_unknown_result(self):
        previous=os.getcwd()
        env={'TELEGRAM_ENABLED':'true','TELEGRAM_REQUEST_ID':'tg-12','TELEGRAM_CHAT_ID':'42','GITHUB_RUN_ID':'123','TELEGRAM_WORKER_URL':'https://worker.example','RESULT_CALLBACK_SECRET':'mock','TELEGRAM_BOT_TOKEN':'mock'}
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,env,clear=True):
            try:
                os.chdir(d)
                calls=[]
                def sender(url,payload,headers=None):
                    calls.append((url,payload))
                    if url.endswith('/complete'):return {'notify':True,'message':'Unknown result'}
                    return {'ok':True}
                self.assertEqual(main(sender),0)
                self.assertEqual(calls[0][1]['outcome'],'unknown')
                self.assertTrue(calls[1][0].endswith('/sendMessage'))
                self.assertTrue(calls[2][0].endswith('/notified'))
                def failed(*args):raise RuntimeError('secret')
                self.assertEqual(main(failed),1)
            finally:os.chdir(previous)

    def test_manual_run_does_not_notify(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(main(lambda *args:self.fail('unexpected API call')),0)

    def test_failure_stage_and_reason(self):
        details=outcome_details('unknown', {'errors':['STEP E old timeout', 'STEP G exception: Confirm button not found or not visible', 'Automatic retry stopped']})
        self.assertEqual(details,('confirmation','confirmation_control_missing'))
        self.assertEqual(outcome_details('unknown',{'errors':['STEP A exception: Timeout; popup intercepts pointer events']}),('box_search','popup_blocked_action'))
        self.assertEqual(outcome_details('reported_success',{}),('final_confirmation','automation_reported_success'))

    def test_retrack_failure_keeps_renewal_outcome_separate(self):
        cfg=Config(username='mock',password='mock',box_numbers=['001'])
        async def success_with_retrack_failure(config):
            return ['001'],[],{'post_renewal_retrack':{'001':{'status':'failed','stage':'button','reason':'control_missing_or_timeout'}}}
        previous=os.getcwd()
        with tempfile.TemporaryDirectory() as d,patch('telegram_run.build_config_from_env',return_value=cfg):
            try:
                os.chdir(d)
                self.assertEqual(asyncio.run(execute(success_with_retrack_failure)),1)
                result=json.loads(Path('telegram_result.json').read_text())
                self.assertEqual(result['outcome'],'reported_success')
                self.assertEqual(result['retrack_status'],'failed')
                self.assertEqual(result['retrack_stage'],'button')
            finally:os.chdir(previous)
