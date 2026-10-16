import unittest
from unittest.mock import AsyncMock, Mock, patch
from agents.account_router import AccountRouter
from config import Config

class AccountTests(unittest.IsolatedAsyncioTestCase):
    async def scenario(self, denied, successful, switch_ok=True, missing=False):
        with patch.dict('os.environ', {'HATHWAY_USERNAME_2':'second','HATHWAY_PASSWORD_2':'secret'}):
            router=AccountRouter(Mock(),Config(),Mock())
        if missing: router.secondary_password=''
        router._switch=AsyncMock(return_value=switch_ok)
        agents=[Mock(other_lco=d,renew_box=AsyncMock(return_value=s)) for d,s in zip(denied,successful)]
        with patch('agents.account_router.RenewalAgent',side_effect=agents) as factory:
            result=await router.renew_box('00123')
            calls=factory.call_count
        for a in agents[:calls]: a.renew_box.assert_awaited_once_with('00123')
        return result,router,calls

    async def test_first_success(self):
        result,r,n=await self.scenario([False],[True])
        self.assertTrue(result);r._switch.assert_not_awaited()
    async def test_uncertain_failure_never_switches(self):
        result,r,n=await self.scenario([False],[False])
        self.assertFalse(result);r._switch.assert_not_awaited()
    async def test_explicit_denial_switches_once(self):
        result,r,n=await self.scenario([True,False],[False,True])
        self.assertTrue(result);r._switch.assert_awaited_once_with(2)
    async def test_both_denied_stops(self):
        result,r,n=await self.scenario([True,True],[False,False])
        self.assertFalse(result);self.assertEqual(n,2);r._switch.assert_awaited_once_with(2)
    async def test_missing_secrets(self):
        result,r,n=await self.scenario([True],[False],missing=True)
        self.assertFalse(result);r._switch.assert_not_awaited()
    async def test_failed_login_no_second_renewal(self):
        result,r,n=await self.scenario([True],[False],switch_ok=False)
        self.assertFalse(result);self.assertEqual(n,1)

    async def test_logout_login_navigation_order(self):
        router=AccountRouter(Mock(),Config(),Mock())
        router.secondary_username,router.secondary_password='second','secret'
        router.page.get_by_role.return_value.first.click=AsyncMock()
        router.page.wait_for_url=AsyncMock()
        router.page.context.clear_cookies=AsyncMock()
        events=[]
        router.page.get_by_role.return_value.first.click.side_effect=lambda **kw: events.append('logout')
        router.page.wait_for_url.side_effect=lambda *a,**kw: events.append('login_page')
        with patch('agents.account_router.LoginAgent') as login, patch('agents.account_router.NavigationAgent') as nav:
            login.return_value.login=AsyncMock(return_value=True)
            nav.return_value.handle_post_login_slides=AsyncMock()
            nav.return_value.go_to_package_management=AsyncMock(return_value=True)
            self.assertTrue(await router._switch(2))
            self.assertEqual(login.call_args.args[1].username,'second')
            self.assertEqual(login.call_args.args[1].password,'secret')
        self.assertEqual(events,['logout','login_page'])
        self.assertEqual(router.active_account,2)

    async def test_logout_failure_prevents_login(self):
        router=AccountRouter(Mock(),Config(),Mock())
        router.page.get_by_role.return_value.first.click=AsyncMock(side_effect=TimeoutError())
        with patch('agents.account_router.LoginAgent') as login:
            self.assertFalse(await router._switch(2))
            login.assert_not_called()
        self.assertFalse(router.session_ready)

    async def test_search_denial_stops_before_plan(self):
        from agents.renewal_agent import RenewalAgent
        a=RenewalAgent.__new__(RenewalAgent)
        a.config=Config();a.logger=Mock();a.page=Mock();a._healer=Mock()
        a._healer.smart_locator=AsyncMock()
        a._healer.smart_click=AsyncMock(return_value=True)
        a.page.keyboard.press=AsyncMock();a.page.wait_for_load_state=AsyncMock()
        a.page.get_by_text.return_value.first.is_visible=AsyncMock(return_value=True)
        a._popup=Mock();a._popup.dismiss_popups_if_present=AsyncMock()
        with patch('agents.renewal_agent.asyncio.sleep',new=AsyncMock()), patch('agents.renewal_agent.random_delay',new=AsyncMock()), patch('agents.renewal_agent.human_type',new=AsyncMock()):
            self.assertFalse(await a.renew_box('00123'))
        self.assertTrue(a.other_lco)
        a._popup.dismiss_popups_if_present.assert_not_awaited()
        self.assertEqual(a._healer.smart_click.await_count,1)
