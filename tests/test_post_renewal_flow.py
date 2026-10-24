import unittest
from unittest.mock import AsyncMock, Mock, patch
from config import Config
import main

class PostRenewalFlowTests(unittest.IsolatedAsyncioTestCase):
    async def run_flow(self, renewal_success, retrack_only=False):
        page=Mock();page.evaluate=AsyncMock()
        context=Mock();context.new_page=AsyncMock(return_value=page)
        browser=Mock();browser.new_context=AsyncMock(return_value=context);browser.close=AsyncMock()
        playwright=Mock();playwright.chromium.launch=AsyncMock(return_value=browser)
        manager=Mock();manager.__aenter__=AsyncMock(return_value=playwright);manager.__aexit__=AsyncMock(return_value=False)
        logger=Mock();logger.get_summary.return_value={}
        login=Mock();login.login=AsyncMock(return_value=True)
        nav=Mock();nav.handle_post_login_slides=AsyncMock();nav.go_to_package_management=AsyncMock(return_value=True)
        renewal=Mock();renewal.renew_box=AsyncMock(return_value=renewal_success)
        renewal.details={'retrack_only':retrack_only}
        retrack=Mock();retrack.run=AsyncMock(return_value={'status':'failed','stage':'button','reason':'control_missing_or_timeout'})
        with patch('main.async_playwright',return_value=manager),patch('main.LoggerAgent',return_value=logger),patch('main.LoginAgent',return_value=login),patch('main.NavigationAgent',return_value=nav),patch('main.AccountRouter',return_value=renewal),patch('main.RetrackAgent',return_value=retrack) as factory,patch('main.asyncio.sleep',new=AsyncMock()):
            result=await main.run_automation(Config(username='mock',password='mock',box_numbers=['BOX1']))
        return result,renewal,retrack,factory

    async def test_successful_renewal_does_not_retrack(self):
        result,renewal,retrack,factory=await self.run_flow(True)
        self.assertEqual(result[0],['BOX1']);self.assertEqual(result[1],[])
        self.assertEqual(result[2]['post_renewal_retrack'],{})
        renewal.renew_box.assert_awaited_once_with('BOX1')
        factory.assert_not_called();retrack.run.assert_not_awaited()

    async def test_separate_retrack_only_path_is_preserved(self):
        result,renewal,retrack,_=await self.run_flow(True,retrack_only=True)
        self.assertEqual(result[2]['post_renewal_retrack']['BOX1']['status'],'failed')
        renewal.renew_box.assert_awaited_once_with('BOX1')
        retrack.run.assert_awaited_once_with('BOX1')

    async def test_failed_renewal_never_retracks(self):
        result,renewal,retrack,factory=await self.run_flow(False)
        self.assertEqual(result[0],[]);self.assertEqual(result[1],['BOX1'])
        factory.assert_not_called();retrack.run.assert_not_awaited()
