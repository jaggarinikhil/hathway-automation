# Customer details and notification fix

Base GitHub commit: 89f5e0a.

The old reader required the exact searched box in the same table as contact fields and never opened Customer Details. The earlier user-provided video shows the separate Customer Details and Main TV tabs. This fix opens Customer Details when needed, supports colon-prefixed identity values, separate form tables, readonly inputs and inline labeled fields. Values must have an unambiguous label and validated box context. No names/phones are guessed. Customer fields are read after status detection; the existing renewal flow next clicks Main TV. Missing metadata does not block renewal. Logs show captured field names only.

Telegram omits all Retrack lines and the retry reminder, including on retries of older stored notifications. Retrack still executes and its internal results/Actions logs remain available.

Changed files:
- agents/portal_results.py
- agents/renewal_agent.py
- telegram-worker/src/index.js
- tests/test_customer_tab.py
- telegram-worker/tests/worker.test.js
- README.md
- CUSTOMER_NOTIFICATION_FIX.md

Actual checks:
- 36 Python unit tests passed.
- 25 Worker tests passed, using mock external APIs and in-memory SQLite.
- Python and JavaScript syntax checks passed.
- Six actual local headless Chromium synthetic cases passed: old grid format; separate identity/contact tables plus colon cells and readonly inputs; Customer Details tab switch; wrong/unvalidated box guard; inline labels; ambiguity guard.
- No real portal login, renewal, Retrack or customer-data transmission was performed during testing. Live Hathway contact labels/markup remain unverified. The reference recording shows the tab, not its customer fields. If fields remain Unavailable, provide a redacted screenshot of the open Customer Details tab; do not run another renewal only to test metadata.

Publish the patch in the existing publishing clone, push GitHub main, and deploy the Worker from that clone's telegram-worker directory. No new secrets or D1 migration is needed. Existing queued runs check out the commit selected when dispatched, so this affects new runs after the push/deployment.
