"""Switch accounts only after explicit other-LCO search denial."""
import os
import re
from dataclasses import replace
from agents.login_agent import LoginAgent
from agents.navigation_agent import NavigationAgent
from agents.renewal_agent import RenewalAgent

class AccountRouter:
    def __init__(self, page, config, logger):
        self.page, self.config, self.logger = page, config, logger
        self.active_account, self.session_ready = 1, True
        self.details = {}
        self.secondary_username = os.getenv('HATHWAY_USERNAME_2', '').strip()
        self.secondary_password = os.getenv('HATHWAY_PASSWORD_2', '')

    async def _switch(self, number):
        self.session_ready = False
        try:
            await self.page.get_by_role('link', name=re.compile(r'^\s*(sign\s*out|log\s*out)\s*$', re.I)).first.click(timeout=self.config.element_timeout)
            await self.page.wait_for_url(re.compile(r'login\.aspx', re.I), timeout=self.config.page_load_timeout)
            await self.page.context.clear_cookies()
            cfg = replace(self.config, **({} if number == 1 else {
                'username': self.secondary_username, 'password': self.secondary_password}))
            if not await LoginAgent(self.page, cfg, self.logger).login():
                self.logger.error('[ACCOUNT] Login failed after all retries during account switch')
                return False
            nav = NavigationAgent(self.page, cfg, self.logger)
            await nav.handle_post_login_slides()
            if not await nav.go_to_package_management():
                self.logger.error('[ACCOUNT] Could not navigate to Package Management')
                return False
            self.active_account, self.session_ready = number, True
            self.logger.info(f'[ACCOUNT] Switched to account {number}')
            return True
        except Exception:
            self.logger.error('[ACCOUNT] Signout or account switch failed; stopped safely')
            return False

    async def renew_box(self, box_number):
        self.details = {}
        if not self.session_ready:
            return self._fail(box_number, 'Account session unavailable')
        if self.active_account != 1 and not await self._switch(1):
            return self._fail(box_number, 'Could not restore first account')
        agent = RenewalAgent(self.page, self.config, self.logger)
        success = await agent.renew_box(box_number)
        self._capture(agent, success)
        if success or not agent.other_lco:
            return success
        if not self.secondary_username or not self.secondary_password:
            return self._fail(box_number, 'Other LCO: second account secrets missing')
        self.logger.info('[ACCOUNT] Other LCO response; signing out before second account search')
        if not await self._switch(2):
            return self._fail(box_number, 'Second account login/navigation failed')
        agent = RenewalAgent(self.page, self.config, self.logger)
        success = await agent.renew_box(box_number)
        self._capture(agent, success)
        if agent.other_lco:
            return self._fail(box_number, 'Customer belongs to neither configured account')
        return success

    def _capture(self, agent, success):
        self.details = {'account_number': self.active_account, 'retrack_only': getattr(agent,'retrack_only',False) is True}
        if isinstance(agent.portal_failure, dict):
            self.details['portal_failure'] = dict(agent.portal_failure)
        if success and isinstance(agent.customer, dict):
            self.details['customer'] = dict(agent.customer)

    def _fail(self, box, reason):
        self.logger.error(f'[ACCOUNT] {reason}')
        self.logger.log_box_result(box, False, reason)
        return False
