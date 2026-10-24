import unittest
from datetime import date
from unittest.mock import Mock,AsyncMock,patch
from agents.expiry_routing import expiry_day,plan_expiry
from agents.renewal_agent import RenewalAgent
from config import Config

class ExpiryRoutingTests(unittest.IsolatedAsyncioTestCase):
    def test_date_formats(self):
        for value in ['24-Oct-2026','24/10/2026','2026-10-24','24-Oct-2026 11:59 PM','24-\nOct-\n2026','24- OCT - 2026','24-OCT-26']:
            self.assertEqual(expiry_day(value),date(2026,10,24))
        self.assertIsNone(expiry_day('Unavailable'))
        self.assertIsNone(expiry_day('31/02/2026'))

    async def test_missing_and_ambiguous_dates_are_not_guessed(self):
        page=Mock()
        for values in [[],['bad'],['24/10/2026','25/10/2026']]:
            page.evaluate=AsyncMock(return_value=values)
            self.assertIsNone(await plan_expiry(page,'Example Plan'))

    async def flow(self,expires):
        agent=RenewalAgent.__new__(RenewalAgent)
        agent.logger=Mock();agent.config=Config();agent.page=Mock();agent.retrack_only=False
        agent._step_search=AsyncMock(return_value=True)
        agent._popup=Mock();agent._popup.dismiss_popups_if_present=AsyncMock()
        agent._get_box_status=AsyncMock(return_value='ACTIVE')
        agent._step_select_main_tv=AsyncMock(return_value=True)
        agent._step_renew_active=AsyncMock(return_value=True)
        with patch('agents.renewal_agent.read_customer_tab',new=AsyncMock(return_value={})),patch('agents.renewal_agent.plan_expiry',new=AsyncMock(return_value=expires)),patch('agents.renewal_agent.india_today',return_value=date(2026,10,24)):
            result=await agent._run_renewal_steps('BOX1')
        return agent,result

    async def test_expires_today_renews(self):
        agent,result=await self.flow(date(2026,10,24))
        self.assertTrue(result);self.assertFalse(agent.retrack_only)
        agent._step_renew_active.assert_awaited_once_with('BOX1',main_tv_selected=True)
        agent._step_select_main_tv.assert_awaited_once()

    async def test_expires_other_day_retracks_only(self):
        agent,result=await self.flow(date(2026,10,25))
        self.assertTrue(result);self.assertTrue(agent.retrack_only)
        agent._step_renew_active.assert_not_awaited()

    async def test_unknown_expiry_stops_before_submission(self):
        agent,result=await self.flow(None)
        self.assertFalse(result);self.assertFalse(agent.retrack_only)
        agent._step_renew_active.assert_not_awaited()
        self.assertEqual(agent.portal_failure['stage_code'],'verification')


    async def test_expired_box_defaults_to_retrack(self):
        with patch.dict('os.environ',{},clear=True):
            agent,result=await self.flow(date(2026,10,23))
        self.assertTrue(result);self.assertTrue(agent.retrack_only)
        agent._step_renew_active.assert_not_awaited()

    async def test_one_off_only_allows_matching_expired_box(self):
        with patch.dict('os.environ',{'HATHWAY_RENEW_EXPIRED_ONCE':'true','HATHWAY_RENEW_EXPIRED_BOX':'BOX1'}):
            agent,result=await self.flow(date(2026,10,23))
        self.assertTrue(result);self.assertFalse(agent.retrack_only)
        agent._step_renew_active.assert_awaited_once()
        with patch.dict('os.environ',{'HATHWAY_RENEW_EXPIRED_ONCE':'true','HATHWAY_RENEW_EXPIRED_BOX':'OTHER'}):
            agent,result=await self.flow(date(2026,10,23))
        self.assertTrue(agent.retrack_only);agent._step_renew_active.assert_not_awaited()
