# Expiry report table reader update

Base: 4e10b08. The live run reached extraction and returned report_grid_missing; Telegram correctly delivered an unavailable notice. The existing reader required both exact VC ID and Customer Name headers and sampled the DOM once. The live table HTML was not available, so those are confirmed code limitations, not a proven single cause of the live mismatch.

Changes:
- Schema detection uses customer, date and a VC/STB identifier column. A VC column is optional if an STB column exists. Supported aliases include VC/Mac ID, STB No, Expiry Date, Plan End Date and Valid Upto.
- Bounded polling waits up to 30 seconds for delayed results. An in-progress ASP.NET UpdatePanel cannot be treated as a zero-box result.
- Visible same-origin/inherited-origin report frames are supported; unrelated cross-origin frames are ignored. Pagination clicks use the context where the grid was found.
- Missing-grid diagnostics include only table counts and allowlisted column categories. No raw headers, row values, IDs, URLs, customer data, screenshots or session state are printed/uploaded.
- Existing date validation, pagination and ambiguity guards remain. Missing or partial reports are never labeled complete or zero.

Validation actually performed: 64 Python tests passed; nine actual local headless Chromium synthetic checks passed across the existing report_browser_check.py and new expiry_grid_browser_check.py. These include complete report navigation, filters, multi-page reads, renewal-only filtering, empty/missing reports, delayed grids, STB-only schema, nested headers, report iframe extraction, cross-origin exclusion and stale-empty UpdatePanel guarding. Python syntax passed. No real portal login or renewal was executed. Live table extraction still requires the next read-only Daily Hathway Reports run.

Changed files: agents/report_agent.py; daily_report_data.py; tests/test_daily_reports.py; tests/expiry_grid_browser_check.py; README.md; EXPIRY_GRID_FIX.md. Existing login, renewal, Retrack, workflow schedules, Telegram sender and Cloudflare code are unchanged.


## Live verification — 17 October 2026

Published fix: 8575e3c. A fresh read-only account-1 expiry workflow on this commit succeeded: https://github.com/jaggarinikhil/hathway-automation/actions/runs/39005611076/job/117317349481 . Collection reported 3 matching plan entries and Telegram delivery completed to the configured owner chat. No renewal was submitted. This verifies live expiry extraction and Telegram API acceptance for this run; production pagination beyond this report and the evening renewal report were not tested in this live run.
