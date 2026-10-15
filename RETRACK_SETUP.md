# Post-renewal Retrack

Based on the user's 26-second recording and explicit one-minute-wait instruction:

1. The existing renewal flow reports success for a box.
2. Stay on the same page and wait 60 seconds.
3. Verify the search field still identifies that box.
4. Click Retrack, then Confirm in the retrack confirmation popup.
5. Read the resulting portal message, click its OK button, and wait for it to close.
6. Continue existing cleanup. Report renewal and retrack separately in Telegram.

The recording shows a Confirm button before the final OK. Its final message says
that a retrack request was already submitted and that two retrack requests for the
same customer need a 15-minute gap. This response is reported as already_requested,
not as a successful new submission. There is no automatic Retrack retry.
An unfamiliar response remains unverified. Retrack failure never restarts renewal.
Reported successful retrack submission is not independent confirmation that the
physical STB received the signal.

## Publish

The feature patch is saved beside the original local repository. In your existing
publishing clone (with previous changes committed), run:

```sh
cd ~/hathway-telegram-publish
git pull --ff-only origin main
git apply /Users/sunny/.codex/.chatgpt-projects/g-p-6acd294abf28819184f0192c1ee5dd5f/retrack-update.patch
git add main.py agents/retrack_agent.py telegram_run.py telegram_notify.py tests/test_retrack.py tests/test_post_renewal_flow.py tests/test_telegram.py telegram-worker/src/index.js telegram-worker/schema.sql telegram-worker/wrangler.toml telegram-worker/tests/worker.test.js README.md RETRACK_SETUP.md
git commit -m "Retrack each box one minute after successful renewal"
git push origin main
```

The patch is built against upstream 514bea4. If git apply reports a conflict, stop
and review the changed baseline; don't overwrite files or reset local work.
The included main.py diff contains only the new import, post-success hook and
structured summary, not earlier unrelated local edits.

Deploy the original local Worker folder after the push:

```sh
cd /Users/sunny/.codex/.chatgpt-projects/g-p-6acd294abf28819184f0192c1ee5dd5f/hathway-automation/telegram-worker
npx wrangler deploy
```

No new secrets, hosting services, schema changes beyond the already-deployed name
storage, or workflow inputs are required. Existing job duration includes the extra
60 seconds for each box. Use only the next genuinely intended renewal to exercise
the live new step; don't repeat an existing renewal merely for testing.

## Actual validation

- 36 Python unit tests passed, including six Retrack tests and separate renewal /
  Retrack outcome reporting.
- 22 Worker tests passed, including separate Retrack status, stage and reason.
- Three actual headless Chromium tests passed against synthetic local pages for
  successful submission, 15-minute cooldown, and portal rejection. The 60-second
  delay was mocked and its exact requested value asserted; tests don't wait 60s.
- Python syntax and git diff whitespace checks passed.
- Video inspected locally; no video, extracted frames, credentials, cookies or
  portal session artifacts are included in the feature patch.
- No real renewal or Retrack was executed. Live portal DOM selectors are inferred
  from visible labels and popup structure, not obtained from an authenticated DOM.
  Live compatibility and exact successful response wording remain unverified.
