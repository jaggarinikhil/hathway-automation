"""
run_gha.py — GitHub Actions entry point for Hathway renewal.
Wraps the existing run_automation() without modifying any existing file.

Usage (GitHub Actions):
    python run_gha.py

Environment variables required:
    HATHWAY_USERNAME     - portal username
    HATHWAY_PASSWORD     - portal password
    HATHWAY_BOX_NUMBER   - single box number (from workflow_dispatch input)

Optional:
    HATHWAY_BOXES        - comma-separated box numbers (alternative to HATHWAY_BOX_NUMBER)
"""

import asyncio
import os
import sys
import re
from datetime import datetime


def build_config_from_env():
    """Build a Config object from environment variables only — no prompts, no files."""
    # Import existing Config class unchanged
    from config import Config

    # Manually construct — bypass from_args_or_env() which may call argparse
    cfg = Config()

    cfg.username  = os.environ.get("HATHWAY_USERNAME", "").strip()
    cfg.password  = os.environ.get("HATHWAY_PASSWORD", "").strip()
    cfg.headless  = True   # always headless in GHA
    cfg.slow_mo   = 80

    # Box numbers: prefer HATHWAY_BOX_NUMBER (single), fallback to HATHWAY_BOXES (list)
    single = os.environ.get("HATHWAY_BOX_NUMBER", "").strip()
    multi  = os.environ.get("HATHWAY_BOXES", "").strip()

    if single:
        cfg.box_numbers = [single]
    elif multi:
        cfg.box_numbers = [b.strip() for b in re.split(r"[\s,]+", multi) if b.strip()]
    else:
        cfg.box_numbers = []

    return cfg


def validate_config(cfg):
    errors = []
    if not cfg.username:
        errors.append("HATHWAY_USERNAME secret is not set")
    if not cfg.password:
        errors.append("HATHWAY_PASSWORD secret is not set")
    if not cfg.box_numbers:
        errors.append("HATHWAY_BOX_NUMBER (or HATHWAY_BOXES) input is not set")
    return errors


def write_github_summary(successful, failed, duration):
    """Write a job summary card visible in the GitHub Actions UI."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    total  = len(successful) + len(failed)
    if failed and not successful:
        status = "❌ All failed"
    elif failed:
        status = "⚠️ Partial success"
    else:
        status = "✅ All succeeded"

    lines = [
        "# 📺 Hathway Renewal Summary\n\n",
        f"| | |\n|---|---|\n",
        f"| **Status** | {status} |\n",
        f"| **Total boxes** | {total} |\n",
        f"| **Successful** | {len(successful)} |\n",
        f"| **Failed** | {len(failed)} |\n",
        f"| **Duration** | {duration:.1f}s |\n\n",
    ]
    if successful:
        lines.append("## ✅ Successful\n")
        for b in successful:
            lines.append(f"- `{b}`\n")
    if failed:
        lines.append("\n## ❌ Failed\n")
        for b in failed:
            lines.append(f"- `{b}`\n")

    with open(summary_path, "w") as f:
        f.writelines(lines)


async def main():
    cfg = build_config_from_env()

    errors = validate_config(cfg)
    if errors:
        print("❌ Configuration errors:")
        for e in errors:
            print(f"   • {e}")
        sys.exit(2)

    print(f"✅ Config loaded — box(es): {cfg.box_numbers}")
    print(f"🖥️  Headless: {cfg.headless}")

    start = datetime.now()

    # Import and call the existing run_automation — completely unchanged
    from main import run_automation
    successful, failed, _ = await run_automation(cfg)

    duration = (datetime.now() - start).total_seconds()
    write_github_summary(successful, failed, duration)

    # Exit code: 0 = all ok, 1 = partial/full failure
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    asyncio.run(main())
