import unittest
from unittest.mock import AsyncMock, Mock, patch
from agents.portal_results import read_customer_tab
from agents.renewal_agent import RenewalAgent

class CustomerTabTests(unittest.IsolatedAsyncioTestCase):
    def page(self):
        page=Mock()
        page.get_by_text.return_value.first.is_visible=AsyncMock(return_value=True)
        page.get_by_text.return_value.first.click=AsyncMock()
        page.wait_for_load_state=AsyncMock()
        return page

    async def test_complete_fields_do_not_click_tab(self):
        page=self.page()
        with patch('agents.portal_results.customer_details',new=AsyncMock(return_value={'first_name':'Example','last_name':'Customer','phone':'9000000000'})):
            details=await read_customer_tab(page,'001')
        self.assertEqual(len(details),3)
        page.get_by_text.return_value.first.click.assert_not_awaited()

    async def test_reads_customer_tab_even_when_network_never_idle(self):
        page=self.page();page.wait_for_load_state.side_effect=TimeoutError()
        async def read(page,box,**kwargs):
            if 'context' in kwargs:
                kwargs['context']['box_matched']=True
                return {}
            self.assertTrue(kwargs['validated'])
            return {'first_name':'Example','last_name':'Customer','phone':'9000000000'}
        with patch('agents.portal_results.customer_details',side_effect=read):
            self.assertEqual((await read_customer_tab(page,'001'))['first_name'],'Example')
        page.get_by_text.return_value.first.click.assert_awaited_once()

    async def test_metadata_error_does_not_block_renewal(self):
        page=self.page();page.get_by_text.return_value.first.click.side_effect=TimeoutError()
        with patch('agents.portal_results.customer_details',new=AsyncMock(return_value={})):
            self.assertEqual(await read_customer_tab(page,'001'),{})

    async def test_customer_tab_is_read_after_status_before_renewal(self):
        agent=RenewalAgent.__new__(RenewalAgent)
        agent.config=Mock(element_timeout=1000);agent.logger=Mock();agent.page=Mock()
        events=[]
        async def status(box):events.append('status');return 'ACTIVE'
        async def read(*args):events.append('customer');return {'first_name':'Example'}
        async def renew(box):events.append('renew');return True
        agent._step_search=AsyncMock(return_value=True)
        agent._popup=Mock();agent._popup.dismiss_popups_if_present=AsyncMock()
        agent._get_box_status=AsyncMock(side_effect=status)
        agent._step_select_main_tv=AsyncMock(side_effect=renew)
        with patch('agents.renewal_agent.read_customer_tab',side_effect=read):
            self.assertTrue(await agent._run_renewal_steps('001'))
        self.assertEqual(events,['status','customer','renew'])
        self.assertNotIn('Example',str(agent.logger.mock_calls))

    async def test_full_customer_name_and_phone_need_no_tab_click(self):
        page=self.page()
        with patch('agents.portal_results.customer_details',new=AsyncMock(return_value={'full_name':'Example Customer','phone':'9000000000'})):
            details=await read_customer_tab(page,'001')
        self.assertEqual(details['full_name'],'Example Customer')
        page.get_by_text.return_value.first.click.assert_not_awaited()
