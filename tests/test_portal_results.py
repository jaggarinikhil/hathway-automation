import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from agents.portal_results import REJECTIONS, rejection, customer_details
from agents.renewal_agent import RenewalAgent
from config import Config
from telegram_run import execute

class PortalResultsTests(unittest.IsolatedAsyncioTestCase):
    async def test_message_patterns_do_not_match_other_lco_or_success(self):
        for pattern in REJECTIONS.values():
            self.assertIsNone(pattern.fullmatch('You have no privileges to access customer information as s/he belongs to other LCO'))
            self.assertIsNone(pattern.fullmatch('Renewal successful'))
        self.assertTrue(REJECTIONS['vc_terminated_or_missing'].fullmatch('VC which you are searching is either Terminated or does not exist.'))
        self.assertTrue(REJECTIONS['insufficient_balance'].fullmatch('Insufficient balance'))
        self.assertTrue(REJECTIONS['insufficient_balance'].fullmatch('Insuffecent balance.'))

    async def test_hidden_rejections_are_ignored(self):
        page=Mock();page.get_by_text.return_value.first.is_visible=AsyncMock(return_value=False)
        self.assertIsNone(await rejection(page))

    async def test_two_explicit_rejections_stop(self):
        for code in REJECTIONS:
            a=RenewalAgent.__new__(RenewalAgent)
            a.config=Config();a.logger=Mock();a.page=Mock();a.page.url='https://portal.example/pack.aspx'
            a.page.goto=AsyncMock()
            async def rejected(box):
                a._submission_attempted=True
                a.portal_failure={'stage_code':'submission','reason_code':code}
                return False
            a._run_renewal_steps=AsyncMock(side_effect=rejected)
            self.assertFalse(await a.renew_box('001'))
            self.assertEqual(a._run_renewal_steps.await_count,2)
            a.page.goto.assert_awaited_once()
            self.assertFalse(a.other_lco)
            self.assertEqual(a.portal_failure['attempts'],2)

    async def test_ambiguous_submission_still_not_retried(self):
        a=RenewalAgent.__new__(RenewalAgent);a.config=Config();a.logger=Mock();a.page=Mock()
        a.page.locator.return_value.is_visible=AsyncMock(return_value=False)
        a._check_rejection=AsyncMock(return_value=False)
        async def uncertain(box): a._submission_attempted=True;return False
        a._run_renewal_steps=AsyncMock(side_effect=uncertain)
        self.assertFalse(await a.renew_box('001'))
        a._run_renewal_steps.assert_awaited_once()

    async def test_customer_values_filtered_and_extraction_failure_safe(self):
        page=Mock();page.evaluate=AsyncMock(return_value={'first_name':' Test\n Person ','last_name':'Member','phone':'+91 9000000000','password':'do not copy'})
        self.assertEqual(await customer_details(page,'001'),{'first_name':'Test Person','last_name':'Member','phone':'+91 9000000000'})
        page.evaluate=AsyncMock(side_effect=RuntimeError('private'))
        self.assertEqual(await customer_details(page,'001'),{})

    async def test_result_rejection_and_success_metadata(self):
        cfg=Config(username='mock',password='mock',box_numbers=['001'])
        async def failed(c):return [],['001'],{'box_details':{'001':{'account_number':1,'portal_failure':{'reason_code':'insufficient_balance','stage_code':'submission','attempts':2}}}}
        async def succeeded(c):return ['001'],[],{'box_details':{'001':{'account_number':2,'customer':{'first_name':'Test','last_name':'Member','phone':'9000000000'}}}}
        previous=os.getcwd()
        with tempfile.TemporaryDirectory() as d,patch('telegram_run.build_config_from_env',return_value=cfg):
            try:
                os.chdir(d)
                self.assertEqual(await execute(failed),1)
                result=json.loads(Path('telegram_result.json').read_text())
                self.assertEqual((result['outcome'],result['reason_code'],result['attempts']),('confirmed_failure','insufficient_balance',2))
                self.assertNotIn('customer',result)
                self.assertEqual(await execute(succeeded),0)
                result=json.loads(Path('telegram_result.json').read_text())
                self.assertEqual(result['account_number'],2)
                self.assertEqual(result['customer']['first_name'],'Test')
                self.assertEqual(Path('telegram_result.json').stat().st_mode & 0o777,0o600)
            finally:os.chdir(previous)

    async def test_second_attempt_can_recover_without_stale_failure(self):
        a=RenewalAgent.__new__(RenewalAgent);a.config=Config();a.logger=Mock();a.page=Mock()
        a.page.url='https://portal.example/pack.aspx';a.page.goto=AsyncMock()
        count=0
        async def flow(box):
            nonlocal count
            count+=1
            if count==1:
                a.portal_failure={'stage_code':'box_search','reason_code':'vc_terminated_or_missing'}
                return False
            return True
        a._run_renewal_steps=AsyncMock(side_effect=flow)
        self.assertTrue(await a.renew_box('001'))
        self.assertIsNone(a.portal_failure)
        self.assertEqual(count,2)

    async def test_failed_reset_does_not_submit_again(self):
        a=RenewalAgent.__new__(RenewalAgent);a.config=Config();a.logger=Mock();a.page=Mock()
        a.page.url='https://portal.example/pack.aspx';a.page.goto=AsyncMock(side_effect=TimeoutError())
        async def flow(box):
            a.portal_failure={'stage_code':'submission','reason_code':'insufficient_balance'}
            return False
        a._run_renewal_steps=AsyncMock(side_effect=flow)
        self.assertFalse(await a.renew_box('001'))
        a._run_renewal_steps.assert_awaited_once()

    async def test_balance_blocks_acknowledgment_success(self):
        a=RenewalAgent.__new__(RenewalAgent);a.logger=Mock();a.page=Mock()
        a._check_rejection=AsyncMock(return_value=True)
        a._healer=Mock();a._healer.smart_click=AsyncMock()
        self.assertFalse(await a._step_ok('001'))
        a._healer.smart_click.assert_not_awaited()
