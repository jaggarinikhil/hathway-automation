# Hathway Telegram integration: end-to-end setup

This Worker validates Telegram messages and dispatches `.github/workflows/renew.yml`.
Chromium and Tesseract run only in GitHub Actions. JavaScript/Node tooling is used
only for Worker development/deployment, not as a replacement renewal engine.

## 1. Create the bot privately

In Telegram, open the verified **@BotFather**, send `/newbot`, choose a display name
and a unique username ending in `bot`, and retain the supplied token privately.
Do not paste tokens into chat, commit them, or put them in workflow inputs.

Send `/start` to your new bot. Before registering its webhook, run from repository
root `python telegram_setup.py ids`; enter the bot token at its hidden prompt.
This prints only numeric private sender/chat IDs from `getUpdates`, not message
content. Record your own user ID and private chat ID. `getUpdates` cannot operate
while a webhook is registered; do this bootstrap step before registration. IDs
must be explicitly allowed—Telegram usernames are never authorization.

## 2. GitHub token and repository settings

Create a fine-grained personal access token restricted to this repository with
**Actions: Read and write**, plus GitHub's mandatory metadata access. No Contents
write permission is needed or permitted for the Worker. Set an expiry and rotate
before it expires. The owner must approve the token if organization policy
requires it. Read/write Actions supports both dispatch and reconciliation.

Keep the existing `HATHWAY_USERNAME` and `HATHWAY_PASSWORD` Actions secrets.
Add these repository secrets:

- `TELEGRAM_BOT_TOKEN`: the same bot token as the Worker.
- `RESULT_CALLBACK_SECRET`: a new independent random value, also stored in Worker.

Add repository variable `TELEGRAM_WORKER_URL` after deployment (HTTPS origin only,
for example `https://hathway-telegram.YOUR-SUBDOMAIN.workers.dev`).
Keep the repository private if it contains sensitive account/automation details.
The source was inspected at upstream commit `d8b9751`; no stored portal credential
file was found among tracked files. Secret *values* were not read from GitHub.

## 3. Install tooling and create storage

Use Node 24 or newer for the automated SQLite tests, and a supported Node LTS for
Wrangler. This is deployment tooling only. In `telegram-worker/`:

```sh
npm ci
npx wrangler login
npx wrangler d1 create hathway-telegram
```

Copy the returned database ID into `wrangler.toml` (`database_id`). The small D1
database is necessary for persistent, atomic duplicate protection and same-box
locks; it is not a database used by the renewal automation.

```sh
npx wrangler d1 execute hathway-telegram --remote --file=schema.sql
```

Set each secret through Wrangler's hidden/interactive prompt:

```sh
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_WEBHOOK_SECRET
npx wrangler secret put TELEGRAM_ALLOWED_USER_IDS
npx wrangler secret put TELEGRAM_ALLOWED_CHAT_IDS
npx wrangler secret put GITHUB_TOKEN
npx wrangler secret put RESULT_CALLBACK_SECRET
```

Use comma-separated numeric IDs for the two allowlists. Initially set both to
your own IDs. `TELEGRAM_WEBHOOK_SECRET` must be a separate random string containing
only letters, digits, `_`, or `-`; `secrets.token_urlsafe(32)` provides an appropriate
value. Generate two independent secrets for webhook and callback authentication.

The nonsecret variables in `wrangler.toml` are:
`GITHUB_OWNER`, `GITHUB_REPO`, `GITHUB_WORKFLOW_FILE=renew.yml`, `GITHUB_REF=main`, and
`BOX_PATTERN`. The default accepts 1–64 letters, digits or hyphens, matching the
existing examples (including `T403107718641`) and preserving leading zeros. This
is an input safety policy, not a claim that every matching identifier exists in
Hathway. Tighten it only after confirming your actual box-number requirements.

```sh
npm test
npx wrangler deploy --dry-run
npx wrangler deploy
```

No production deployment was performed by the implementation task. D1 database ID
is a deliberate placeholder until you create your own resource. Publishing
requires your Cloudflare account; keep the Workers Free plan selected.

## 4. Publish the GitHub changes

A feature-only `telegram-integration.patch` is supplied to avoid bringing earlier
local edits to the core into this change. In a **clean clone of current main**,
place the patch beside the clone and run:

```sh
git apply ../telegram-integration.patch
git add .github/workflows/renew.yml .gitignore README.md telegram_run.py telegram_notify.py telegram_setup.py tests/test_telegram.py telegram-worker TELEGRAM_TEST_RESULTS.md
git diff --cached --stat
git commit -m "Add Telegram renewal trigger and result notifications"
git push origin main
```

Do not apply the patch again inside the already-modified local workspace. Review
that the staged change contains no core automation files or secrets.

Push the Telegram files and updated workflow to the default branch before
registering the webhook. Review changes first. The workflow preserves `box_number`
and the existing manual `python run_gha.py` invocation. Its optional new inputs
are `telegram_enabled`, `telegram_chat_id`, and `telegram_request_id`.
Normal manual runs leave them blank/default false. Worker dispatch sets them.

Add `TELEGRAM_WORKER_URL` in repository Variables and the two new Secrets described
above. Do not upload `.dev.vars`, `.env`, CAPTCHA files, browser profiles, or logs.

## 5. Register and verify webhook

From repository root:

```sh
python telegram_setup.py register
python telegram_setup.py info
```

The first command prompts for the token and webhook secret privately, then makes
this exact request (shown with placeholders, never real secrets):

```http
POST https://api.telegram.org/bot<BOT_TOKEN>/setWebhook
Content-Type: application/json

{"url":"https://<WORKER_HOST>/telegram/webhook","secret_token":"<TELEGRAM_WEBHOOK_SECRET>","allowed_updates":["message"],"max_connections":1,"drop_pending_updates":true}
```

`drop_pending_updates:true` intentionally discards old messages so deployment
cannot unexpectedly renew boxes from stale Telegram messages. Confirm that choice
before running registration. Send new messages only after registration succeeds.

Verification request:

```http
POST https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo
Content-Type: application/json

{}
```

The helper displays webhook URL, pending update count, and last webhook error.
Do not print full request URLs containing the token in screenshots or tickets.

## 6. Use Telegram

- `/start`: welcome and instructions.
- `/help`: configured format and commands.
- `/status`: honest explanation that completion notifications arrive automatically;
  no fake live status is implemented.
- Send one complete box number: this authorizes its real renewal using the existing
  plan logic. Send only boxes you intend to renew.

Only after GitHub accepts dispatch does the bot send **Status: Queued** and a
stable `tg-<update_id>` request identifier. Queue acceptance isn't browser start.
The GitHub run title contains that identifier. The same Telegram update is never
dispatched twice by this integration, including concurrent redelivery.

## Outcomes, duplicate protection, and recovery

Requests are persisted in D1 before asynchronous work begins. An atomic claim is
stored before the external GitHub call. Pending rows are recoverable by a cron
trigger every five minutes. A network-ambiguous dispatch is **never retried**;
reconciliation checks the returned run ID (current API) or matching run title
(legacy no-content response). An unresolved dispatch becomes **unknown** after
one hour, and its box remains locked. The legacy fallback searches the latest
100 runs; if it cannot find a run it reports uncertainty, never redispatches.

The GitHub Telegram adapter calls the same async renewal core and produces an
allowlisted local JSON result. An `always()` step first persists that result to
`/complete`, then sends its completion message directly through Telegram Bot API,
then marks `/notified`. The bot token is a GitHub Secret, never a workflow input.
Notification failure leaves persistent state for a five-minute cron retry. No raw
portal error, credentials, screenshots, cookies, or logs are transmitted.

Portal success detection is **unchanged**. The current core returns a boolean
based on UI buttons/dialogs. It does not expose an independent transaction
verification flag. Thus a true result is worded **Automation reported success.
Independent portal verification is unavailable.** It is not labeled verified.
The adapter supports `renewal_verified: true/false` if the existing core later
provides trustworthy structured verification; this integration does not invent it.

Login/CAPTCHA/navigation/config errors detected before renewal are reported as such. Failure
later in the renewal flow is **unknown**, since a submission may already have
occurred. Browser crashes are reported as browser failure with unknown portal
outcome. Recognized renewal step errors are sent as allowlisted failure-stage
labels, never raw exception text. Installation failures, timeout, cancellation, and missing callback are
reconciled from GitHub terminal state but **never inferred to be portal success
or failure**. The notification step does not use `continue-on-error`, so a failed
renewal remains a failed job; notification failure also remains visible.

A partial unique index prevents an additional active request for the same exact
box string. Unknown, browser-failure, and reported-success requests retain this
lock for manual portal review. Manual Actions runs bypass Worker admission and
must not be run concurrently for the same box. Existing portal internal retries
are preserved; the integration adds no automatic repeat renewal.

After you inspect the portal and confirm the previous request is resolved, you
may explicitly release its lock using its stable request ID:

```sh
npx wrangler d1 execute hathway-telegram --remote --command="UPDATE requests SET active=0 WHERE id='tg-REPLACE_WITH_UPDATE_ID';"
```

This permits a **new Telegram message**, not redelivery of the old update. Do not
release a lock based solely on a failed GitHub job. Do not re-run a workflow job
for an uncertain renewal. Inflight work is not transactionally reversible.

Exactly-once delivery across GitHub, Telegram, and D1 is impossible without their
shared transaction. A successful Telegram send followed by a failed marker write
can yield a duplicate notification, but never another Worker dispatch. D1/cron
outage, quota exhaustion, revoked tokens, bot blocking, or Cloudflare account
suspension can delay recovery. Reconciliation is best effort, not a delivery SLA.
Retained IDs prevent old updates being dispatched again; don't delete them unless
you accept that risk. The first recorded terminal outcome is retained; late
callbacks after unknown reconciliation do not turn uncertainty into success.

## Troubleshooting

- No acknowledgment: check `getWebhookInfo`, Worker invocation metrics, D1 binding,
  numeric allowlists and private chat. Unauthorized requests get no bot response.
- HTTP 401 webhook: webhook secret/header mismatch. Re-register with the same secret.
- GitHub HTTP 401/403: expired token, wrong repository access, missing Actions write,
  or organization approval. No queued message is sent on rejection.
- GitHub 404/422: check `GITHUB_REF`, workflow filename, default branch presence,
  and optional inputs on that branch.
- Queued for a long time: check Actions runner availability/usage limits. Do not
  resend the box; the active lock intentionally blocks another dispatch.
- Login/CAPTCHA errors: inspect existing Actions logs privately and the portal.
- Unknown outcome: inspect the portal and Actions before releasing a lock.
- Notification failed: verify the token is identical in GitHub and Cloudflare,
  callback secret matches, repository variable URL is correct, and bot isn't blocked.
- Logs: Actions steps and summaries; Cloudflare dashboard invocation errors. This
  Worker doesn't log message bodies or API tokens. Keep D1 account access private.

## Free-tier budget (checked 14 October 2026)

Target additional hosting cost is $0 at roughly 300 requests/month. Workers Free
allows 100,000 requests/day; D1 includes 5 million rows read/day, 100,000 rows
written/day, and 5 GB storage. The five-minute reconciliation schedule is about
288 invocations/day. These allocations are ample for this design at the target
volume, subject to your account's other usage and provider limits. Stay on Free;
paid plan overages are not automatically free.

GitHub Free includes 2,000 private-repository runner minutes/month shared across
account usage. At 300 renewals × 4 minutes = 1,200 minutes; at 7 minutes = 2,100,
which exceeds that allowance. Include setup and rounded runtime, not just renewal
time. Standard public runners are free but don't publish sensitive code/account
details to save money. Configure GitHub budgets/blocking appropriately. Renewal
charges themselves are separate from hosting cost. Telegram ordinary bot messaging
is free within its rate limits; no paid broadcast feature is enabled.

Sources:
[Telegram API](https://core.telegram.org/bots/api#setwebhook),
[GitHub dispatch permissions](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event),
[GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions),
[Workers limits](https://developers.cloudflare.com/workers/platform/limits/),
[D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/).

## Tests and acceptance

`npm test` uses mocked Telegram/GitHub HTTP and real in-memory SQLite with the D1
schema. Repository root: `python -m unittest discover -s tests -v`. These tests
never contact Hathway or execute a real renewal. See `TELEGRAM_TEST_RESULTS.md`.
The live end-to-end acceptance test remains pending bot creation, account secrets,
deployment, and an explicitly authorized real box. The existing core's independent
verification limitation must also be resolved before claiming verified renewal.
