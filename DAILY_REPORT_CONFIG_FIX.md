# Daily-report startup fix

Base: 6055865. The first live report run failed before login because Config does not support the save_captcha_debug constructor argument. Removed that argument, factored a compatible build_primary_config helper, and added tests exercising the actual Config constructor and startup through login using a mocked browser.

The notification failure also occurred because TELEGRAM_REPORT_CHAT_ID was absent from GitHub repository variables. The owner variable was separately added in GitHub and verified as 7272926644. Existing password and bot secrets were not changed.

Report errors now print only safe reason codes; browser startup gets its own stage. Missing owner-variable and bot-secret errors are distinct. No raw exception, credential, token, browser session or customer data is printed.

Actual checks: 60 Python tests passed and Python syntax passed. New tests use mocks; no portal login or renewal was performed. Live report collection still needs a new Daily Hathway Reports run after this fix is pushed. Use Run workflow on main, not Re-run jobs for the old commit.

Changed files: daily_reports.py; tests/test_daily_reports.py; DAILY_REPORT_CONFIG_FIX.md. No workflow or Cloudflare change is needed.
