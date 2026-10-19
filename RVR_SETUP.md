# RVR group monitor

Separate read-only Python Playwright monitor, following this repository's
environment-secret and GitHub-hosted Chromium approach. Existing Hathway flows
are not called. No AI or OCR service is required.

## Schedule and rules

Cloudflare's existing `hathway-telegram` Worker checks its five-minute timer and
starts `rvr-monitor.yml` every ten minutes from 06:00 through 23:50 Asia/Kolkata.
Native GitHub cron is removed to prevent duplicate triggers. GitHub may still queue
runners; this fixes missing scheduled dispatches, not guaranteed execution latency.
The script refuses portal checks outside 06:00–23:59.
Cloudflare uses its existing repository token and D1 `report_dispatches` table.
Each ten-minute slot is claimed before dispatch; duplicate ticks do not start extra
runs. Ticks more than five minutes stale are ignored. Ambiguous network failures
are recorded without blindly retrying. Set Worker `RVR_SCHEDULER_ENABLED=false`
to pause dispatch. Portal credentials and ntfy topic remain only in GitHub.
Manual `dry_run` defaults to true and reads counts without notifications or state.
Cloudflare explicitly passes `dry_run=false` for real monitoring.

The four groups are in `rvr_monitor/groups.json`. Exact, case-sensitive usernames
are matched against the complete account list and complete Active Sessions table.
Expired/suspended/other recognized non-active accounts are excluded. Unknown
accounts, unknown statuses and incomplete pagination fail closed.

Half or more active members offline (rounded up) on two checks triggers one ntfy
alert. Checks must be within 15 minutes on the same India date with unchanged
eligible membership. Long gaps restart confirmation. An existing notified outage
remains suppressed overnight until a successful below-threshold observation.
Recovery rearms the alert silently. No recovery, healthy, or monitoring-error push
messages are sent. Errors only mark the Actions run failed.

## Setup

Add Actions secrets `RVR_USERNAME`, `RVR_PASSWORD`, `NTFY_TOPIC`.
Use a randomly generated 24–64-character alphanumeric/underscore/hyphen topic;
subscribe to it in the ntfy app using the ntfy.sh server. Anyone knowing a free
unprotected topic can read/publish to it. Never use a short name such as rvr.
Messages contain group name and counts only, without customer names or contacts.

The workflow uses its repository-scoped GITHUB_TOKEN with contents write to create
and update `rvr-monitor-state` branch. State contains eligible usernames, group
counters, timestamps and notification flags; never credentials or browser sessions.
Keep the repository private if those group assignments must be private. Branch
protections must allow the workflow to write this dedicated branch. Notifications
stop if persisted state cannot be read; it does not silently start from scratch on
API or corrupt-state errors. The initial missing state file starts unconfirmed.

Merge to the default branch only after live validation. Do not configure a Telegram
webhook or modify the existing Cloudflare Worker for this workflow.
The Cloudflare scheduler is active unless its `RVR_SCHEDULER_ENABLED` variable is false.
The old GitHub variable does not pause workflow_dispatch runs.

## Validation still required

Unit tests cover threshold math, confirmation, duplicate suppression, silent
recovery, missing users, zero eligible users, overnight reset and time-window edges.
Run `python3 -m unittest discover -s tests -p test_rvr_monitor.py`.

Live RVR login and table parsing have NOT been tested end-to-end by this Python code.
Login input names (`username`, `password`) and the Sign In button were verified
on the live sign-in page without entering credentials. They still require a real authorized
run. OTP/CAPTCHA challenges stop login; no bypass is implemented. The live account
DOM was inspected: 35 total accounts with only 25 initial rendered rows inside
`.jazeVirtualScroll`. The reader scrolls and deduplicates rows, requiring the exact
footer count before accepting a snapshot. Multiple actual pages still fail closed;
implement and test pagination if the portal grows beyond a single page.
Zero-session footer handling also requires portal verification.

First test browser collection without notifying using an authorized local development
environment, then verify one deliberate ntfy test outside this monitor. Finally run
the Actions workflow inside the window and measure minutes. Do not deliberately
disconnect real customers for tests.

Private repositories share the account's included Actions minutes. 3,240 runs/30 days
at 1/2/3 billed minutes use approximately 3,240/6,480/9,720 minutes, plus other workflows.
The five-minute job timeout is not a monthly spending cap. Check account usage and
set an appropriate GitHub billing budget that stops usage before enabling schedules.
Public standard runners are free but repository content/logs/state are public.

Notification delivery is at-least-once: if ntfy accepts a message but the response or
subsequent state write fails, the next qualifying run may repeat it. No screenshots,
traces, browser storage or customer tables are uploaded. The script logs only group
counts and safe error classes; examine selectors locally when debugging.
