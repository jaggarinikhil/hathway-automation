"""
Hathway STB Renewal Automation System
======================================
Entry point for the complete automation workflow.
"""

import asyncio
from config import Config
from agents.logger_agent import LoggerAgent
from agents.login_agent import LoginAgent
from agents.navigation_agent import NavigationAgent
from agents.renewal_agent import RenewalAgent
from playwright.async_api import async_playwright


async def run_automation(config: Config):
    logger = LoggerAgent(config.log_file)
    logger.info("🚀 Hathway STB Renewal Automation Started")
    logger.info(f"📦 Total boxes to process: {len(config.box_numbers)}")

    successful_boxes = []
    failed_boxes = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=config.headless,
            slow_mo=config.slow_mo,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            # STEP 1: Login
            login_agent = LoginAgent(page, config, logger)
            login_success = await login_agent.login()
            if not login_success:
                logger.error("❌ Login failed after all retries. Aborting.")
                await browser.close()
                return [], config.box_numbers, logger.get_summary()
            logger.success("✅ Login successful")

            # STEP 2: Handle post-login slides and popups
            nav_agent = NavigationAgent(page, config, logger)
            await nav_agent.handle_post_login_slides()

            # STEP 3: Navigate to Package Management
            nav_success = await nav_agent.go_to_package_management()
            if not nav_success:
                logger.error("❌ Could not navigate to Package Management. Aborting.")
                await browser.close()
                return [], config.box_numbers, logger.get_summary()

            # STEP 4: Renewal Loop
            renewal_agent = RenewalAgent(page, config, logger)
            for idx, box_number in enumerate(config.box_numbers, 1):
                logger.info(f"📺 Processing box {idx}/{len(config.box_numbers)}: {box_number}")
                success = await renewal_agent.renew_box(box_number)
                if success:
                    successful_boxes.append(box_number)
                    logger.success(f"✅ Box {box_number} renewed successfully")
                else:
                    failed_boxes.append(box_number)
                    logger.error(f"❌ Box {box_number} failed after retries")

                # Close any remaining popups before next box
                await asyncio.sleep(2.0)
                await page.evaluate("""
                    // Click OK or Cancel on any visible popup
                    var btns = document.querySelectorAll('input[type=button],input[type=submit],button');
                    for (var i=0; i<btns.length; i++) {
                        var v = (btns[i].value || btns[i].innerText || '').trim().toUpperCase();
                        if (v === 'OK') { btns[i].click(); break; }
                    }
                """)
                await asyncio.sleep(1.0)
                await page.evaluate("""
                    // Click Cancel if still visible
                    var btns = document.querySelectorAll('input[type=button],input[type=submit],button');
                    for (var i=0; i<btns.length; i++) {
                        var v = (btns[i].value || btns[i].innerText || '').trim().toUpperCase();
                        if (v === 'CANCEL') {
                            var el = btns[i];
                            if (el.offsetParent !== null) { el.click(); break; }
                        }
                    }
                    // Hide all popups
                    var ids = ['MasterBody_pnlrenewalPlan','MasterBody_pnlAdd','mpeAdd_backgroundElement'];
                    ids.forEach(function(id) {
                        var el = document.getElementById(id);
                        if (el) el.style.display = 'none';
                    });
                """)
                await asyncio.sleep(1.0)
                # Clear search box for next box
                await page.evaluate("""
                    var sb = document.getElementById('MasterBody_txtSearchParam');
                    if (sb) sb.value = '';
                """)
                await asyncio.sleep(config.delay_between_boxes)

        except Exception as e:
            logger.error(f"💥 Unexpected error in main workflow: {e}", exc_info=True)
        finally:
            await browser.close()
            logger.info("🔒 Browser closed")

    summary = logger.get_summary()
    _print_final_report(successful_boxes, failed_boxes, summary, logger)
    return successful_boxes, failed_boxes, summary


def _print_final_report(successful, failed, summary, logger):
    successful_lines = "".join(f"║    → {b:<52} ║\n" for b in successful) or "║    (none)                                                ║\n"
    failed_lines = "".join(f"║    → {b:<52} ║\n" for b in failed) or "║    (none)                                                ║\n"
    report = (
        "\n╔══════════════════════════════════════════════════════════╗\n"
        "║           HATHWAY STB RENEWAL — EXECUTION REPORT         ║\n"
        "╠══════════════════════════════════════════════════════════╣\n"
        f"║  Total Boxes    : {len(successful) + len(failed):<38} ║\n"
        f"║  Successful     : {len(successful):<38} ║\n"
        f"║  Failed         : {len(failed):<38} ║\n"
        "╠══════════════════════════════════════════════════════════╣\n"
        "║  ✅ SUCCESSFUL BOXES                                      ║\n"
        + successful_lines +
        "╠══════════════════════════════════════════════════════════╣\n"
        "║  ❌ FAILED BOXES                                          ║\n"
        + failed_lines +
        "╚══════════════════════════════════════════════════════════╝\n"
    )
    print(report)
    logger.info(report)


if __name__ == "__main__":
    config = Config.from_args_or_env()

    # Interactive box number prompt (overrides config file / CLI)
    print("\n" + "="*55)
    print("  HATHWAY STB RENEWAL — Box Number Entry")
    print("="*55)
    print("Enter box numbers to renew (one per line, or comma/")
    print("space separated). Press ENTER twice when done:")
    print("-"*55)

    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "" and lines:
            break
        if line.strip():
            lines.append(line.strip())

    # Parse: split on commas, spaces, or newlines
    import re
    raw = " ".join(lines)
    boxes = [b.strip() for b in re.split(r"[\s,]+", raw) if b.strip()]

    if boxes:
        config.box_numbers = boxes
        print(f"\n✅ {len(boxes)} box(es) loaded:")
        for b in boxes:
            print(f"   • {b}")
        print("="*55 + "\n")
    else:
        print("\n⚠️  No boxes entered — using boxes from config.json\n")

    asyncio.run(run_automation(config))