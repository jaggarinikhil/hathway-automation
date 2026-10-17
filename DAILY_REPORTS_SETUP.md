# Daily reports — first Hathway account

This is a separate read-only workflow. It does not call renewal, activation, account switching or Retrack. The existing manual/Telegram renewal workflow and Cloudflare Worker are unchanged.

## Schedule and coverage

- 10:00 AM IST: Plan Expiry Report with From Date and To Date set to the current India date; Package = All; no individual VC filter. All accessible account-1 rows/pages are collected.
- 7:00 PM IST: Transaction Report for the same date; Plan Type, Transaction Type and Pay Term = All; no individual VC filter. Only rows whose Transaction Type equals Renewal are included. This includes renewals made outside the bot.
- The evening report is a snapshot when collection runs, not a full-day reconciliation. Transactions after collection are not included. Use a manual historical-date report to review them later.
- GitHub schedule expressions are UTC: 04:30 and 13:30. The workflow must be on the default branch. GitHub may delay, drop or disable scheduled runs; exact-time delivery is not guaranteed. See [GitHub scheduled-event documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
- Each plan entry is listed. Multiple plans can refer to the same box; unique box and plan-entry counts are separate. When VC ID is blank (as in the supplied expiry recording), New STB No or older STB No is used as the box identifier. Leading zeros are preserved. Portal renewal-status codes are shown without inventing their meaning.

## Set up GitHub

1. Apply and push the provided daily-reports.patch from the existing publishing clone.
2. Open Settings > Secrets and variables > Actions > Variables > New repository variable.
3. Name: `TELEGRAM_REPORT_CHAT_ID`. Value: your owner's private Telegram chat ID (`7272926644` for the owner identified in this chat). Reports go only to this ID, not every bot member. Review this variable carefully because reports contain customer contact details.
4. Keep existing repository secrets `HATHWAY_USERNAME`, `HATHWAY_PASSWORD`, and `TELEGRAM_BOT_TOKEN`. No second-account secrets are passed to this workflow.
5. The bot must be able to message the owner (open the bot and send /start if needed).
6. No Cloudflare change, D1 migration, new token or webhook registration is needed.

## First read-only tests

1. Open Actions > Daily Hathway Reports > Run workflow.
2. Choose `expiry`, leave report_date blank, leave send_telegram enabled, then Run workflow.
3. Open Read account 1 report (no renewal actions) and Send report or failure notice to owner. Logs show stages/counts, not customer data. Check that Telegram matches today's portal expiry report.
4. Repeat with `renewals` and compare with today's Transaction Report, Transaction Type Renewal.
5. These tests do not submit a renewal. Do not run Hathway Renewal to test reports.
6. A manual report_date in YYYY-MM-DD can inspect a previous day. Turning send_telegram off verifies collection without sending customer data.

Once pushed to the default branch with Actions enabled, the two schedules are eligible to run automatically. The workflow was not deployed or run against the live portal during local development.

## Failure handling and privacy

Report failure is reported as unavailable, with a safe stage/reason. Missing grids, unexpected date/column changes, pagination loops or unsupported pagination never produce a false zero-box report or a partial list labeled complete. Explicit portal no-records messages may produce a zero report. ASP.NET numeric/Next pagination is supported with a 500-page safety limit; other controls fail closed.

Telegram text is split below its message limit, with part numbers. An interrupted delivery can leave a multipart report incomplete; check the workflow status. No automatic delivery retries are made after an ambiguous send. Rerun only Daily Hathway Reports if needed. Report reads do not change renewal locks or dispatch renewals.

A private mode-0600 JSON file exists only between collection and notification, is ignored by Git, and is deleted by the notifier. No cookies, browser state, screenshots, raw exports or customer reports are uploaded as Actions artifacts. Customer addresses, email and financial amounts are not selected for Telegram reports. Existing login/CAPTCHA helpers use a suppressed logger in this workflow. A terminated runner may skip the final notification; check GitHub if a report does not arrive. This report workflow is serialized with itself but does not change existing renewal concurrency; overlapping portal logins may fail if Hathway limits sessions.

This uses existing GitHub-hosted Ubuntu, Python, Playwright, Tesseract and Telegram. Additional runs count against your GitHub Actions allowance; free operation depends on account limits and total usage. No paid service or new always-running host is introduced. GitHub may disable inactive scheduled workflows; see its documentation.

## Actual local validation

Base GitHub commit: 4a57539.

- Both supplied recordings reviewed locally. Observed Home > Reports; Plan Expiry Report at rptExpiry.aspx; Transaction Report at rptAddPlanTransMSO.aspx, with results at rptAddPlanTransDET.aspx. Actual runtime element IDs were not supplied, so controls are discovered semantically.
- 57 Python tests passed, including existing tests and date/IST handling, leading zeros, blank-VC/STB fallback, renewal-only filtering, wrong-date rejection, paging/repeated-page guard, unknown/empty results, chunk limits, private file permissions/deletion, owner-only mock delivery, Telegram failures, CLI and missing credentials.
- 26 existing Worker tests passed.
- Four real local headless Chromium synthetic checks passed: Home/Reports/Expiry navigation, date filters and three numeric ASP-style pages; Transaction Report/detail navigation with renewal-only filtering; explicit empty report; missing grid failure. Fixtures use synthetic values and intercepted example-domain requests only.
- Python syntax and both workflow YAML parses passed.
- NOT verified: real Hathway login, live report HTML/IDs, real production pagination, scheduled GitHub execution and actual Telegram report delivery. No real renewal was run. The first manual read-only workflow test remains required after publishing.

Changed files: .github/workflows/daily-reports.yml; .gitignore; daily_report_data.py; daily_reports.py; agents/report_agent.py; tests/test_daily_reports.py; tests/report_browser_check.py; README.md; DAILY_REPORTS_SETUP.md.
