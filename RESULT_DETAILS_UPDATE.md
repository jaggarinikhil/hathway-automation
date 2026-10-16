# Renewal result update

Base: b8f4c93 (current GitHub main when inspected).

Changed files:
- agents/portal_results.py (new)
- agents/renewal_agent.py
- agents/account_router.py
- main.py
- telegram_run.py
- telegram_notify.py
- telegram-worker/src/index.js
- tests/test_portal_results.py (new)
- telegram-worker/tests/worker.test.js
- README.md
- RESULT_DETAILS_UPDATE.md (this file)

Validation actually performed:
- 32 Python unit tests passed (mock APIs and automation; no real renewal).
- 24 Worker tests passed (mock Telegram/GitHub and in-memory SQLite).
- Python syntax, JavaScript syntax, existing workflow YAML parsing passed.
- Real local headless Chromium on synthetic HTML: table header extraction tied to exact box including leading zeros; wrong box excluded; labeled detail extraction; visible failure messages; hidden-message isolation. All passed. Chromium initially could not launch in the restricted sandbox; it passed with authorized local execution.

Not verified: live Hathway rejections/retries, customer details in the real portal markup, native browser-alert variants, live result delivery with new metadata. No real renewal was executed. Customer contact fields are not guessed. Ask for a redacted view of the customer-details layout if fields show Unavailable.

Publish the patch to the existing publishing clone, commit/push, then deploy the Worker from that same clone's telegram-worker directory. Do not use an older Worker directory, which could overwrite newer code. Keep the existing DB binding and owner configuration. No migration, new secret, webhook registration, or real renewal is needed to deploy.
