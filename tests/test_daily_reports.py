import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import date,datetime,timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from daily_report_data import ReportError, date_value, parse_grid, render, today_ist, utf16_length, IST
from agents.report_agent import ReportAgent
import daily_reports

EXP=['Sr. No.','Account Number','VC Id','New STB No','STB No','Customer Name','Address','LCO Name','LCO Code','Mobile','Package','City','Plan Type','End Date','Renewal Status']
TX=['Sr. No.','Customer ID','Customer Name','Customer Address','VC ID','New STB No','Plan Name','Plan Type','Transaction Type','Reason','User ID','User Name','Transaction Date & Time','Customer Base Price','LCO Price']
DAY=date(2026,10,17)

def exp_row(vc='0000123'):
    return ['1','123',vc,'T00001','N00001','Example Customer','PRIVATE ADDRESS','LCO','123','9000000000','Example Plan','City','HSP','17/10/2026','N']

def tx_row(kind='Renewal'):
    return ['1','123','Example Customer','PRIVATE ADDRESS','0000123','T00001','Example Plan','HSP',kind,'','123','Operator','17-Oct-2026 12:16:49 AM','100','90']

class ReportDataTests(unittest.TestCase):
    def test_timezone_and_date_formats(self):
        self.assertEqual(today_ist(datetime(2026,10,16,20,tzinfo=timezone.utc)),DAY)
        self.assertEqual(date_value('17-Oct-2026 12:16:49 AM'),DAY)
        self.assertEqual(date_value('17/10/2026'),DAY)
        with self.assertRaises(ReportError):date_value('not a date')

    def test_expiry_all_boxes_and_blank_vc_falls_back_to_stb(self):
        records,ignored=parse_grid('expiry',EXP,[exp_row(),exp_row('')],DAY)
        self.assertEqual(records[0]['box'],'0000123')
        self.assertEqual(records[1]['box'],'T00001')
        self.assertEqual(ignored,0)
        self.assertNotIn('address',records[0]);self.assertNotIn('LCO Name',records[0])

    def test_all_transaction_types_are_included(self):
        records,ignored=parse_grid('renewals',TX,[tx_row('Renewal'),tx_row('Add'),tx_row('Deactivate')],DAY)
        self.assertEqual(len(records),3);self.assertEqual(ignored,0)
        self.assertEqual(records[0]['vc'],'0000123')

    def test_wrong_date_and_layout_are_not_zero(self):
        with self.assertRaises(ReportError):parse_grid('expiry',EXP,[exp_row()],date(2026,10,18))
        with self.assertRaises(ReportError):parse_grid('expiry',['Name'],[['Example']],DAY)
        with self.assertRaises(ReportError):parse_grid('expiry',EXP,[exp_row()[:-1]],DAY)

    def test_render_all_rows_and_unicode_chunks(self):
        rows,_=parse_grid('expiry',EXP,[exp_row()],DAY)
        records=[{**rows[0],'box':f'000{i}','customer':'Example 😀 '*10} for i in range(100)]
        messages=render('expiry',DAY,records,datetime(2026,10,17,10,tzinfo=IST))
        self.assertGreater(len(messages),1)
        self.assertTrue(all(utf16_length(text)<4096 for text in messages))
        self.assertEqual(sum(text.count('Box: 000') for text in messages),100)
        self.assertNotIn('PRIVATE ADDRESS','\n'.join(messages))
        self.assertIn('10:00 IST',messages[0])

    def test_explicit_empty_report_wording(self):
        message=render('renewals',DAY,[],datetime(2026,10,17,19,tzinfo=IST))[0]
        self.assertIn('No matching entries reported',message)
        self.assertIn('Later transactions are not included',message)

class ReportAgentTests(unittest.IsolatedAsyncioTestCase):
    def agent(self):
        page=Mock();cfg=Mock(element_timeout=1000,page_load_timeout=1000)
        page.wait_for_load_state=AsyncMock()
        return ReportAgent(page,cfg)

    async def test_collects_every_page(self):
        a=self.agent()
        first={'headers':EXP,'rows':[exp_row('0001')],'id':'grid','next':{'text':'2','href':'Page$2'}}
        second={'headers':EXP,'rows':[exp_row('0002')],'id':'grid','next':None}
        a.page.evaluate=AsyncMock(side_effect=[first,second,second])
        link=a.page.locator.return_value.get_by_role.return_value
        link.count=AsyncMock(return_value=1);link.click=AsyncMock()
        records,_=await a.collect('expiry',DAY)
        self.assertEqual([r['box'] for r in records],['0001','0002'])
        link.click.assert_awaited_once()

    async def test_repeated_page_fails_not_partial_report(self):
        a=self.agent();data={'headers':EXP,'rows':[exp_row()],'id':'grid','next':{'text':'2','href':'Page$2'}}
        a.page.evaluate=AsyncMock(return_value=data)
        link=a.page.locator.return_value.get_by_role.return_value
        link.count=AsyncMock(return_value=1);link.click=AsyncMock()
        with patch('agents.report_agent.asyncio.sleep',new=AsyncMock()):
            with self.assertRaisesRegex(ReportError,'pagination_repeated'):await a.collect('expiry',DAY)

    async def test_missing_grid_is_not_empty(self):
        a=self.agent();a.page.evaluate=AsyncMock(return_value={'error':'report_grid_missing'})
        a.page.get_by_text.return_value.first.is_visible=AsyncMock(return_value=False)
        with self.assertRaises(ReportError):await a.collect('expiry',DAY)
        a.page.get_by_text.return_value.first.is_visible=AsyncMock(return_value=True)
        self.assertEqual(await a.collect('expiry',DAY),([],0))

    def test_report_agent_refuses_renewal_page(self):
        a=self.agent();a.page.url='https://portal.example/hathway3/Transaction/frmAssignPlan.aspx'
        with self.assertRaises(ReportError):a._assert_path('expiry')

class ReportNotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.previous=os.getcwd();os.chdir(self.temp.name)
        self.env=patch.dict(os.environ,{'TELEGRAM_REPORT_CHAT_ID':'7272926644','TELEGRAM_BOT_TOKEN':'mock','REPORT_SEND_TELEGRAM':'true'},clear=True);self.env.start()
    def tearDown(self):
        self.env.stop();os.chdir(self.previous);self.temp.cleanup()

    def test_owner_only_delivery_and_cleanup(self):
        daily_reports.write_result({'status':'ready','messages':['Private report part 1','Private report part 2']})
        self.assertEqual(Path('daily_report_result.json').stat().st_mode&0o777,0o600)
        calls=[]
        def sender(url,body):calls.append(body);return {'ok':True}
        output=io.StringIO()
        with contextlib.redirect_stdout(output):self.assertEqual(daily_reports.notify(sender),0)
        self.assertEqual([x['chat_id'] for x in calls],['7272926644']*2)
        self.assertNotIn('Private report part',output.getvalue())
        self.assertFalse(Path('daily_report_result.json').exists())

    def test_failure_never_claims_zero(self):
        calls=[]
        def sender(url,body):calls.append(body);return {'ok':True}
        self.assertEqual(daily_reports.notify(sender),0)
        self.assertIn('does not mean zero',calls[0]['text'])

    def test_telegram_failure_returns_nonzero_without_secret(self):
        daily_reports.write_result({'status':'ready','messages':['Report']})
        output=io.StringIO()
        with contextlib.redirect_stdout(output):self.assertEqual(daily_reports.notify(lambda *a: (_ for _ in ()).throw(ValueError('mock SECRET'))),1)
        self.assertNotIn('SECRET',output.getvalue());self.assertFalse(Path('daily_report_result.json').exists())

    def test_no_send_mode_does_not_transmit(self):
        os.environ['REPORT_SEND_TELEGRAM']='false'
        daily_reports.write_result({'status':'ready','messages':['Private']})
        self.assertEqual(daily_reports.notify(lambda *a:self.fail('Unexpected API call')),0)
        self.assertFalse(Path('daily_report_result.json').exists())

    def test_missing_primary_configuration_cannot_use_account_two(self):
        os.environ.update(HATHWAY_USERNAME_2='second',HATHWAY_PASSWORD_2='secret')
        with self.assertRaisesRegex(ReportError,'primary_credentials_missing'):daily_reports.settings()

    def test_user_date_validation(self):
        os.environ.update(HATHWAY_USERNAME='first',HATHWAY_PASSWORD='mock',REPORT_DATE='invalid')
        with self.assertRaisesRegex(ReportError,'invalid_report_date'):daily_reports.settings()

class ReportWorkflowTests(unittest.TestCase):
    def test_cli_help_and_invalid_command(self):
        import subprocess,sys
        help_result=subprocess.run([sys.executable,'daily_reports.py','--help'],capture_output=True,text=True)
        self.assertEqual(help_result.returncode,0)
        bad=subprocess.run([sys.executable,'daily_reports.py','renew'],capture_output=True,text=True)
        self.assertEqual(bad.returncode,2)

    def test_report_code_has_no_renewal_or_second_account_import(self):
        source=Path('daily_reports.py').read_text()+Path('agents/report_agent.py').read_text()
        self.assertNotIn('from main import',source)
        self.assertNotIn('from agents.renewal_agent',source)
        self.assertNotIn('HATHWAY_USERNAME_2',source)

    def test_schedule_configuration(self):
        # Check schedule and owner-only credential boundaries without external APIs.
        workflow=Path('.github/workflows/daily-reports.yml').read_text()
        self.assertIn("cron: '30 4 * * *'",workflow)
        self.assertIn("cron: '30 13 * * *'",workflow)
        self.assertIn('if: always()',workflow)
        self.assertNotIn('HATHWAY_USERNAME_2',workflow)
        self.assertNotIn('upload-artifact',workflow)

    def test_empty_preferred_stb_uses_legacy_stb(self):
        row=exp_row('');row[3]=''
        records,_=parse_grid('expiry',EXP,[row],DAY)
        self.assertEqual(records[0]['box'],'N00001')

class PrimaryReportConfigTests(unittest.TestCase):
    def test_real_existing_config_constructor(self):
        from config import Config
        with patch.dict(os.environ,{'HATHWAY_USERNAME':'first','HATHWAY_PASSWORD':'mock'},clear=True):
            cfg=daily_reports.build_primary_config()
        self.assertIsInstance(cfg,Config)
        self.assertEqual(cfg.username,'first')
        self.assertTrue(cfg.headless)

    def test_missing_chat_variable_names_only_missing_setting(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(daily_reports,'RESULT',Path(directory)/'result.json'),patch.dict(os.environ,{'TELEGRAM_BOT_TOKEN':'mock'},clear=True):
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(daily_reports.notify(lambda *a:self.fail('Unexpected API call')),1)
            self.assertIn('Missing or invalid repository variable TELEGRAM_REPORT_CHAT_ID',output.getvalue())
            self.assertNotIn('Missing repository secret',output.getvalue())

class ReportStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_config_reaches_login_with_mock_browser(self):
        browser=Mock();browser.new_page=AsyncMock(return_value=Mock());browser.close=AsyncMock()
        playwright=Mock();playwright.chromium.launch=AsyncMock(return_value=browser)
        manager=Mock();manager.__aenter__=AsyncMock(return_value=playwright);manager.__aexit__=AsyncMock(return_value=False)
        login=Mock();login.login=AsyncMock(return_value=False)
        with tempfile.TemporaryDirectory() as directory,patch.object(daily_reports,'RESULT',Path(directory)/'result.json'),patch.dict(os.environ,{'HATHWAY_USERNAME':'first','HATHWAY_PASSWORD':'mock','REPORT_TYPE':'expiry'},clear=True),patch('playwright.async_api.async_playwright',return_value=manager),patch('agents.login_agent.LoginAgent',return_value=login):
            self.assertEqual(await daily_reports.collect(),1)
            result=json.loads(daily_reports.RESULT.read_text())
            self.assertEqual(result['stage'],'login')
            self.assertEqual(result['reason'],'login_or_captcha_failed')
            login.login.assert_awaited_once()
            browser.close.assert_awaited_once()

class ExpiryGridCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_grid_waits_for_delayed_result(self):
        from config import Config
        a=ReportAgent(Mock(),Config(page_load_timeout=1000))
        a.page.evaluate=AsyncMock(side_effect=[{'error':'report_grid_missing'}, {'headers':EXP,'rows':[exp_row()],'next':None}])
        a.page.get_by_text.return_value.first.is_visible=AsyncMock(return_value=False)
        with patch('agents.report_agent.asyncio.sleep',new=AsyncMock()):
            records,_=await a.collect('expiry',DAY)
        self.assertEqual(len(records),1)
        self.assertEqual(a.page.evaluate.await_count,2)

    async def test_async_postback_does_not_turn_stale_empty_message_into_zero(self):
        from config import Config
        a=ReportAgent(Mock(),Config(page_load_timeout=1000))
        a.page.evaluate=AsyncMock(side_effect=[{'error':'report_grid_missing','loading':True},{'headers':EXP,'rows':[exp_row()],'next':None}])
        a.page.get_by_text.return_value.first.is_visible=AsyncMock(return_value=True)
        with patch('agents.report_agent.asyncio.sleep',new=AsyncMock()):
            records,_=await a.collect('expiry',DAY)
        self.assertEqual(len(records),1)

    async def test_expiry_without_vc_column_and_alternate_date_label(self):
        headers=['New STB No','Customer Name','Expiry Date','Mobile','Package']
        records,_=parse_grid('expiry',headers,[['00000123','Example Customer','17/10/2026','9000000000','Plan']],DAY)
        self.assertEqual(records[0]['box'],'00000123')
        self.assertEqual(records[0]['vc'],'')

    async def test_diagnostics_never_print_raw_headers_or_values(self):
        from config import Config
        a=ReportAgent(Mock(),Config(page_load_timeout=1))
        a.page.evaluate=AsyncMock(return_value={'error':'report_grid_missing','diagnostics':{'visible_tables':3,'recognized_columns':['customer','PRIVATE_NAME']}})
        a.page.get_by_text.return_value.first.is_visible=AsyncMock(return_value=False)
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaises(ReportError):await a.collect('expiry',DAY)
        self.assertIn('Visible tables: 3',output.getvalue())
        self.assertNotIn('PRIVATE_NAME',output.getvalue())

class RenewalNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_destroyed_context_is_waited_out_without_resubmitting(self):
        from config import Config
        from playwright.async_api import Error
        a=ReportAgent(Mock(),Config(page_load_timeout=1000))
        a.page.evaluate=AsyncMock(side_effect=[Error('Execution context was destroyed, most likely because of a navigation. PRIVATE'),{'headers':TX,'rows':[tx_row()],'next':None}])
        with patch('agents.report_agent.asyncio.sleep',new=AsyncMock()):
            records,_=await a.collect('renewals',DAY)
        self.assertEqual(len(records),1)
        self.assertEqual(a.page.evaluate.await_count,2)

    async def test_safe_failure_details_do_not_publish_portal_text(self):
        reason,locations=daily_reports.failure_details(KeyError('PRIVATE CUSTOMER VALUE'))
        self.assertEqual(reason,'report_data_shape_error')
        self.assertNotIn('PRIVATE',str((reason,locations)))
        from playwright.async_api import Error
        self.assertEqual(daily_reports.failure_details(Error('TypeError: private portal content'))[0],'report_script_error')

class TransactionSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_operator_summary_is_followed_to_details(self):
        from config import Config
        page=Mock();page.url='https://portal.example/Reports/rptAddPlanTransUSER.aspx'
        page.wait_for_load_state=AsyncMock()
        control=page.get_by_role.return_value.or_.return_value.first
        control.wait_for=AsyncMock()
        async def click(**kwargs):page.url='https://portal.example/Reports/rptAddPlanTransDET.aspx?showall=A'
        control.click=AsyncMock(side_effect=click)
        agent=ReportAgent(page,Config())
        await agent._transaction_details()
        control.click.assert_awaited_once()
        self.assertTrue(agent.page.url.endswith('showall=A'))
        page.on.assert_called_once()
        page.remove_listener.assert_called_once()

    async def test_direct_detail_page_is_not_clicked_again(self):
        from config import Config
        page=Mock();page.url='https://portal.example/Reports/rptAddPlanTransDET.aspx?showall=A'
        page.wait_for_load_state=AsyncMock()
        agent=ReportAgent(page,Config())
        await agent._transaction_details()
        page.get_by_role.assert_not_called()


class TransactionReportTests(unittest.TestCase):
    def test_activation_and_renewal_share_one_list(self):
        rows,count=parse_grid('renewals',TX,[tx_row('Activation'),tx_row('Renewal')],DAY)
        text='\n'.join(render('renewals',DAY,rows,datetime(2026,10,17,19,tzinfo=IST),count))
        self.assertIn("Today's transactions",text)
        self.assertIn('Boxes: 1 | Transactions: 2',text)
        self.assertIn('Activation: 1 | Renewal: 1',text)
        self.assertIn('Box: 0000123',text)
        self.assertIn('Transaction type: Activation',text)
        self.assertIn('Transaction type: Renewal',text)
        self.assertNotIn('excluded',text)
        self.assertNotIn('PRIVATE ADDRESS',text)

    def test_all_transactions_chunk_without_loss(self):
        rows,count=parse_grid('renewals',TX,[tx_row('Activation')]*100,DAY)
        messages=render('renewals',DAY,rows,datetime(2026,10,17,19,tzinfo=IST),count)
        self.assertTrue(all(utf16_length(message)<3500 for message in messages))
        self.assertEqual(sum(message.count('Transaction type: Activation') for message in messages),100)
        self.assertIn('Transactions: 100',messages[0])
