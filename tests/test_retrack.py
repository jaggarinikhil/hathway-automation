import unittest
from unittest.mock import AsyncMock, Mock
from config import Config
from agents.retrack_agent import RetrackAgent

class RetrackTests(unittest.IsolatedAsyncioTestCase):
    def agent(self, text='Retrack request sent successfully', box='BOX1'):
        page=Mock()
        search=Mock();search.input_value=AsyncMock(return_value=box)
        retrack=Mock();retrack.first=retrack;retrack.wait_for=AsyncMock();retrack.click=AsyncMock()
        page.get_by_role.return_value.or_.return_value=retrack
        confirm=Mock();confirm.first=confirm;confirm.click=AsyncMock()
        confirmation=Mock();confirmation.wait_for=AsyncMock();confirmation.get_by_role.return_value=confirm
        ok=Mock();ok.first=ok;ok.click=AsyncMock()
        result=Mock();result.wait_for=AsyncMock();result.inner_text=AsyncMock(return_value=text);result.get_by_role.return_value=ok
        popups=Mock();popups.filter.side_effect=[Mock(last=confirmation),Mock(last=result)]
        page.locator.side_effect=[search,popups]
        sleep=AsyncMock()
        agent=RetrackAgent(page,Config(),Mock(),sleep=sleep)
        return agent,sleep,retrack,confirm,ok

    async def test_wait_confirm_ok_success(self):
        agent,sleep,retrack,confirm,ok=self.agent()
        events=[]
        sleep.side_effect=lambda n:events.append(('wait',n))
        retrack.click.side_effect=lambda **kwargs:events.append(('retrack',))
        confirm.click.side_effect=lambda **kwargs:events.append(('confirm',))
        ok.click.side_effect=lambda **kwargs:events.append(('ok',))
        result=await agent.run('BOX1')
        self.assertEqual(result['status'],'completed')
        self.assertEqual(events,[('wait',60),('retrack',),('confirm',),('ok',)])

    async def test_cooldown_is_not_new_success(self):
        agent,_,retrack,confirm,ok=self.agent('You have already submitted request. Try after 15 min. A gap of 15 minutes is required.')
        result=await agent.run('BOX1')
        self.assertEqual(result['status'],'already_requested')
        self.assertEqual(result['reason'],'cooldown_15_minutes')
        retrack.click.assert_awaited_once();confirm.click.assert_awaited_once();ok.click.assert_awaited_once()

    async def test_box_mismatch_never_clicks(self):
        agent,_,retrack,_,_=self.agent(box='OTHERBOX')
        result=await agent.run('BOX1')
        self.assertEqual(result['reason'],'box_context_mismatch')
        retrack.click.assert_not_awaited()

    async def test_no_repeat_on_uncertain_confirmation(self):
        agent,_,retrack,confirm,_=self.agent()
        confirm.click.side_effect=TimeoutError('private portal data')
        result=await agent.run('BOX1')
        self.assertEqual(result,{'status':'unknown','stage':'confirm','reason':'control_missing_or_timeout'})
        retrack.click.assert_awaited_once();confirm.click.assert_awaited_once()
        self.assertNotIn('private',str(result))

    async def test_unrecognized_response_not_success(self):
        agent,*_=self.agent('Your request is being processed')
        self.assertEqual((await agent.run('BOX1'))['status'],'unknown')

    async def test_portal_failure_not_success(self):
        agent,*_=self.agent('Retrack request unsuccessful')
        self.assertEqual((await agent.run('BOX1'))['status'],'failed')
