"""One-shot post-renewal Retrack, based on the supplied portal recording."""
import asyncio
import re


class RetrackAgent:
    def __init__(self, page, config, logger, sleep=None):
        self.page, self.config, self.logger = page, config, logger
        self.timeout = config.element_timeout
        self._sleep = sleep or asyncio.sleep

    async def run(self, box_number):
        stage = 'wait'
        attempted = False
        try:
            self.logger.info('[RETRACK] Waiting 60 seconds on the same box page before Retrack.')
            await self._sleep(60)
            stage = 'context'
            search = self.page.locator(self.config.sel_search_box)
            if (await search.input_value(timeout=self.timeout)).strip().upper() != box_number.upper():
                return self.result('failed', stage, 'box_context_mismatch')
            stage = 'button'
            retrack = self.page.get_by_role('button', name=re.compile(r'^Retrack$', re.I)).or_(
                self.page.get_by_role('link', name=re.compile(r'^Retrack$', re.I)))
            await retrack.first.wait_for(state='visible', timeout=self.timeout)
            attempted = True
            await retrack.first.click(timeout=self.timeout)
            stage = 'confirm'
            popups = self.page.locator('div.Popup:visible, [role="dialog"]:visible, .modal:visible')
            confirm_popup = popups.filter(has_text=re.compile(r'are you sure.*retrack|this will retrack', re.I)).last
            await confirm_popup.wait_for(state='visible', timeout=self.timeout)
            confirm = confirm_popup.get_by_role('button', name=re.compile(r'^(Confirm|OK)$', re.I))
            await confirm.first.click(timeout=self.timeout)
            stage = 'result'
            result_popup = popups.filter(has=self.page.get_by_role('button', name=re.compile(r'^OK$', re.I))).last
            await result_popup.wait_for(state='visible', timeout=self.timeout)
            text = (await result_popup.inner_text()).lower()
            # Record only allowlisted reasons; never emit portal message/account content.
            if 'already submitted' in text or ('15' in text and ('gap' in text or 'minutes' in text)):
                status, reason = 'already_requested', 'cooldown_15_minutes'
            elif re.search(r'\b(failed|failure|error|unable|unsuccessful)\b|not successful|not submitted', text):
                status, reason = 'failed', 'portal_rejected'
            elif 'successfully' in text and re.search(r're[ -]?track|request', text):
                status, reason = 'completed', 'portal_reported_success'
            else:
                status, reason = 'unknown', 'unrecognized_response'
            stage = 'ok'
            await result_popup.get_by_role('button', name=re.compile(r'^OK$', re.I)).first.click(timeout=self.timeout)
            await result_popup.wait_for(state='hidden', timeout=self.timeout)
            self.logger.info('[RETRACK] Post-renewal step: '+status)
            return self.result(status, 'result', reason)
        except Exception:
            self.logger.warning('[RETRACK] Post-renewal step did not complete at stage '+stage+'. Renewal will not be repeated.')
            return self.result('unknown' if attempted else 'failed', stage, 'control_missing_or_timeout')

    @staticmethod
    def result(status, stage, reason):
        return {'status': status, 'stage': stage, 'reason': reason}
