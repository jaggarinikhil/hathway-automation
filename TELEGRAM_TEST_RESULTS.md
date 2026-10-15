# Telegram integration test report — 14 October 2026, Asia/Kolkata

## Inspected baseline

Fetched `origin/main` at `d8b975153990ce7e66d1d7676b408a7e1e3e8bee`.
Existing workflow: `.github/workflows/renew.yml`; input: `box_number`; manual
entry: `python run_gha.py`; Chromium/Tesseract run on GitHub-hosted Ubuntu.
Existing required portal secrets: `HATHWAY_USERNAME`, `HATHWAY_PASSWORD`.
Secret values were not inspected. Existing results: returned successful/failed
box lists and logger summary; GitHub job summary/logs. Core success uses UI
heuristics, without an independent transaction-verification flag.

Earlier local edits from the headless/testing work were already present. This
Telegram change adds adapters; no core/login/renewal/selectors were changed in
this task. A feature-only patch is provided to exclude those earlier core edits.
The manual workflow uses the same installation, browser/OCR setup and entry point
as the fetched working upstream version; Telegram fields are optional.

## Actual checks

- **14 Worker tests passed** on Node 25.9.0. Telegram/GitHub fetches mocked;
  persistent queries exercised using real SQLite with the provided D1 schema.
- **12 Python tests passed** on Python 3.14: eight previous tests plus four new
  Telegram tests. Mocked core/API calls only; no live renewal executed.
- Worker syntax checked with `node --check`.
- Python syntax checked using `compileall`.
- Python dependency check: no broken requirements found.
- Workflow YAML parsed; assertions verified original box input, Telegram disabled
  by default, original manual entry command, always-running notifier, no artifact
  upload step. This is not a GitHub-hosted execution/schema validation result.
- Wrangler 4.150.0 installed with a lockfile; installation audit reported zero
  vulnerabilities at install time. Dry-run bundle succeeded with D1 binding and
  expected environment variables. Nothing deployed.
- `git diff --check` passed.
- Feature-only patch applied cleanly to a temporary copy of fetched upstream;
  all 14 Worker tests and four Telegram Python tests passed against that unchanged
  original core/configuration. No core files are included in the patch.

Coverage includes: valid identifiers and leading zeros, malformed input,
unauthorized numeric user/chat IDs, private-chat restriction, webhook secret,
GitHub dispatch rejection and acceptance (200/current and 204/legacy), queued
acknowledgment ordering, sequential/concurrent duplicate updates, persistent
ambiguous-dispatch claim, active-box locks and blocked-update tombstones,
commands, completion success/failure/reported-success/unknown messages, invalid
callback metadata, cancellation reconciliation, notification retry without another
renewal, Python outcome classification, browser exception privacy, completion
API calls, missing result => unknown, and manual execution without notification.

The first Wrangler dry run hit local sandbox configuration-directory restrictions.
It passed outside that restriction. Initial dependency installation was interrupted
in the network-restricted sandbox and completed with approved network access.
No failures were labeled successes.

## Unverified and remaining acceptance work

No Telegram token, Worker credentials, D1 production binding or GitHub dispatch
PAT was available. Bot creation, Cloudflare deployment, actual D1 service behavior,
webhook registration, real bot acknowledgment/delivery, cron production execution,
and live GitHub dispatch/renewal remain unverified. Follow telegram-worker/README.md
and configure secrets directly in provider interfaces/prompts, not in chat.

A real end-to-end renewal was not executed as a test. No credentials, cookies,
portal session, CAPTCHA images or raw logs were uploaded. The integration itself
has no artifact upload step.

Current core reports UI success; it cannot independently verify a transaction.
Telegram reports that limitation explicitly. Verified-success acceptance cannot
be claimed until trustworthy portal verification is available and a live test
is performed. This task intentionally does not change success detection.

D1 deduplication prevents repeat Worker dispatches, not manual Actions job re-runs
or existing portal retry behavior. Keep uncertain boxes locked until portal review.
Telegram delivery is at least once: send success followed by a failed persisted
marker may yield a duplicate completion message, never another Worker dispatch.

## Integration files

Modified: `.github/workflows/renew.yml`, `.gitignore`, `README.md`.
Added: `telegram_run.py`, `telegram_notify.py`, `telegram_setup.py`,
`tests/test_telegram.py`, `TELEGRAM_TEST_RESULTS.md`, and:

- `telegram-worker/src/index.js`
- `telegram-worker/schema.sql`
- `telegram-worker/wrangler.toml`
- `telegram-worker/package.json`
- `telegram-worker/package-lock.json`
- `telegram-worker/README.md`
- `telegram-worker/tests/worker.test.js`

No credentials/configuration state is contained in the feature-only patch.
