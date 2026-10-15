"""Optional Telegram adapter around the existing core, without changing its selectors."""
import asyncio
import json
import os
import time
from pathlib import Path
from run_gha import build_config_from_env


def classify(successful, failed, summary, requested):
    errors = '\n'.join(summary.get('errors', [])).lower()
    if 'login failed after all retries' in errors or 'login attempts exhausted' in errors:
        return 'captcha_failure' if 'captcha' in errors else 'login_failure'
    if 'could not navigate to package management' in errors:
        return 'navigation_failure'
    if summary.get('renewal_verified') is True and successful == requested and not failed:
        return 'confirmed_success'
    if summary.get('renewal_verified') is False:
        return 'confirmed_failure'
    if successful == requested and not failed:
        # Existing OK-button heuristic isn't an independent transaction check.
        return 'reported_success'
    return 'unknown'


async def execute(automation=None):
    started = time.monotonic()
    outcome, code, reason = 'unknown', 1, None
    try:
        try:
            cfg = build_config_from_env()
        except (ValueError, OSError):
            cfg = None
        if cfg is None or not cfg.username or not cfg.password or len(cfg.box_numbers) != 1:
            outcome, code = 'configuration_error', 2
        else:
            if automation is None:
                from main import run_automation
                automation = run_automation
            successful, failed, summary = await automation(cfg)
            outcome = classify(successful, failed, summary, cfg.box_numbers)
            if outcome == 'unknown':
                errors = '\n'.join(summary.get('errors', [])).lower()
                for marker, label in [('step h', 'final_confirmation_error'), ('step g', 'confirmation_error'),
                                      ('confirm button not found', 'confirmation_error'), ('step f', 'submission_error'),
                                      ('submit button not found', 'submission_error'), ('step e', 'plan_selection_error'),
                                      ('step d', 'bouquet_selection_error'), ('step c', 'add_plan_error'),
                                      ('step b', 'main_tv_error'), ('step a', 'box_search_error')]:
                    if marker in errors:
                        reason = label
                        break
            # Preserve the existing reported-success exit status while wording honestly.
            code = 0 if outcome in ('confirmed_success', 'reported_success') else 1
    except Exception:
        # Browser errors may contain credential/session details; never publish them.
        outcome, code = 'browser_failure', 1
    result = {'schema_version': 1, 'outcome': outcome,
              'duration_seconds': round(time.monotonic()-started, 3), 'exit_code': code}
    if reason:
        result['failure_reason_code'] = reason
    Path('telegram_result.json').write_text(json.dumps(result)+'\n')
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
            f.write(f'\n## Telegram renewal\n\nOutcome: {outcome}\n\nDuration: {result["duration_seconds"]} seconds\n')
    return code


if __name__ == '__main__':
    raise SystemExit(asyncio.run(execute()))
