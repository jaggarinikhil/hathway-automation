# Screenshot-based customer label fix

Base: 7a3e400.

Cause: the parser recognized First Name/Last Name and generic phone labels, while the user's Customer Details screenshot has Customer Name and Customer Mobile. The displayed full name must not be split by guessing.

Changes: agents/portal_results.py; telegram-worker/src/index.js; tests/test_customer_tab.py; telegram-worker/tests/worker.test.js; README.md; CUSTOMER_LABEL_FIX.md.

The reader now captures full_name and phone using those exact labels, including colon-separated cells and the nested TV Details identity grid. Telegram displays Customer name, Phone, and the existing account number. No address, email, account number or additional customer fields are collected. Retrack execution and renewal steps are unchanged; Retrack notifications remain omitted.

Actual validation: 37 Python tests and 26 Worker tests passed. Python/JavaScript syntax passed. Two actual local headless Chromium checks passed with synthetic values: screenshot-style nested TV grid plus exact Customer Name/Mobile labels (including leading zeros and wrong-box exclusion), and inline label/value layout. No live portal request or real renewal was made. The screenshot establishes label names and visible layout, not actual HTML; live field extraction still needs confirmation on a future intended renewal.

Apply the patch in the publishing clone, push main, then deploy the Worker from the same clone. No new secrets, database migration or webhook registration is needed. Do not repeat a completed renewal only to test metadata.
