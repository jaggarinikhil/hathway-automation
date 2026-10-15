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


def outcome_details(outcome, summary):
    """Allowlisted user-facing details, never raw portal exception text."""
    defaults = {
        'confirmed_success': ('verification', 'verified'),
        'reported_success': ('final_confirmation', 'automation_reported_success'),
        'confirmed_failure': ('verification', 'portal_confirmed_failure'),
        'configuration_error': ('configuration', 'invalid_configuration'),
        'login_failure': ('login', 'login_not_completed'),
        'captcha_failure': ('captcha', 'captcha_attempts_exhausted'),
        'navigation_failure': ('navigation', 'package_management_unavailable'),
        'browser_failure': ('browser', 'browser_execution_error'),
    }
    if outcome in defaults:
        return defaults[outcome]
    errors = summary.get('errors', [])
    stage = 'renewal'
    stages = [('step h', 'final_confirmation'), ('step g', 'confirmation'),
              ('confirm button not found', 'confirmation'), ('step f', 'submission'),
              ('submit button not found', 'submission'), ('step e', 'plan_selection'),
              ('plan checkbox not found', 'plan_selection'), ('step d', 'bouquet_selection'),
              ('step c', 'add_plan'), ('step b', 'main_tv'), ('step a', 'box_search')]
    for error in reversed(errors):
        matched = next((value for marker, value in stages if marker in error.lower()), None)
        if matched:
            stage = matched
            break
    combined = '\n'.join(errors).lower()
    if 'confirm button not found' in combined:
        return stage, 'confirmation_control_missing'
    if 'intercepts pointer events' in combined:
        return stage, 'popup_blocked_action'
    if 'timeout' in combined:
        return stage, 'element_timeout'
    if 'not found' in combined:
        return stage, 'required_element_missing'
    if 'retry suppressed' in combined or 'automatic retry stopped' in combined:
        return stage, 'submission_outcome_uncertain'
    return stage, 'no_verified_result'


async def execute(automation=None):
    started = time.monotonic()
    outcome, code, reason = 'unknown', 1, None
    summary = {}
    retrack = None
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
            retrack = summary.get("post_renewal_retrack", {}).get(cfg.box_numbers[0])
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
    result['stage_code'], result['reason_code'] = outcome_details(outcome, summary)
    if retrack:
        result['retrack_status'] = retrack['status']
        result['retrack_stage'] = retrack['stage']
        result['retrack_reason'] = retrack['reason']
        if retrack['status'] not in ('completed', 'already_requested'):
            code = result['exit_code'] = 1
    if reason:
        result['failure_reason_code'] = reason
    Path('telegram_result.json').write_text(json.dumps(result)+'\n')
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
            f.write(f'\n## Telegram renewal\n\nOutcome: {outcome}\n\nDuration: {result["duration_seconds"]} seconds\n')
    return code


if __name__ == '__main__':
    raise SystemExit(asyncio.run(execute()))
