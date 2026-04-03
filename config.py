"""
config.py — Central configuration for Hathway automation.
All timeouts, selectors, retries, and credentials live here.
"""

from __future__ import annotations
import os
import json
import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class Config:
    # ── Credentials ──────────────────────────────────────────────────────
    portal_url: str = "https://partners.hathway-connect.com/Login.aspx"
    username: str = ""
    password: str = ""

    # ── Box Numbers ───────────────────────────────────────────────────────
    box_numbers: List[str] = field(default_factory=list)

    # ── Plan Details ──────────────────────────────────────────────────────
    target_plan_name: str = "HW TL BRONZE KMM 30d"
    bouquet_name: str = "Hathway Bouquet"

    # ── Browser Settings ─────────────────────────────────────────────────
    headless: bool = False
    slow_mo: int = 80          # ms between each Playwright action

    # ── Timeouts (ms) ────────────────────────────────────────────────────
    page_load_timeout: int = 60_000
    element_timeout: int = 20_000
    short_timeout: int = 5_000

    # ── Retry Settings ───────────────────────────────────────────────────
    captcha_max_retries: int = 5
    login_max_retries: int = 3
    renewal_max_retries: int = 2
    step_max_retries: int = 3

    # ── Delays (seconds) ─────────────────────────────────────────────────
    delay_between_actions: float = 0.8
    delay_between_boxes: float = 2.0
    delay_after_click: float = 1.2
    delay_captcha_refresh: float = 1.5

    # ── Logging ───────────────────────────────────────────────────────────
    log_file: str = "hathway_automation.log"
    captcha_debug_dir: str = "captcha_debug"   # save captcha images here
    selector_store_path: str = "selectors.json"

    # ── Selectors ─────────────────────────────────────────────────────────
    # Login page
    sel_username: str = "#txtUsername"
    sel_password: str = "#txtPassword"
    sel_captcha_image: str = "#imgCaptcha"
    sel_captcha_input: str = "#txtcaptcha"
    sel_login_button: str = "#ibtLogIn"
    sel_login_error: str = ".error-message, #lblError, .alert-danger"

    # Post-login popups
    sel_skip_ad: str = "button:has-text('Skip'), a:has-text('Skip'), #btnSkip"
    sel_close_stb_popup: str = ".modal .close, button[aria-label='Close'], #btnClose, .modal-header .close"
    sel_stb_popup: str = ".modal, #divPopup, [id*='popup'], [id*='Popup']"

    # Package Management navigation
    sel_package_mgmt_menu: str = (
        "a:has-text('Package Management'), "
        "li:has-text('Package Management') a, "
        "#menuPackageManagement, "
        "a[href*='PackageMgmt'], "
        "a[href*='packagemgmt']"
    )

    # Search
    sel_search_box: str = "#MasterBody_txtSearchParam"
    sel_search_button: str = "#MasterBody_btnSearch"

    # Results table / Main TV
    sel_main_tv_link: str = "#MasterBody_lnkAddon1"

    # Add Plan
    sel_add_plan_button: str = "#MasterBody_btnOpenAddPopup"

    # Bouquet
    sel_hathway_bouquet: str = "#MasterBody_radhwayspecial"

    # Plan selection
    sel_plan_row_template: str = "tr:has-text('{plan_name}')"
    sel_plan_select_button: str = (
        "button:has-text('Select'), a:has-text('Select'), "
        "input[value='Select']"
    )

    # Confirm / Add
    sel_add_button: str = "#MasterBody_btnAddPlan"
    sel_confirm_button: str = "#MasterBody_btnaddplanConfirm"

    # Success indicators
    sel_success_message: str = (
        ".success, .alert-success, "
        "span:has-text('Success'), div:has-text('successfully')"
    )

    # Status check
    sel_status_cell: str = "//td[text()='Main TV']/following-sibling::td[3]"
    
    # Renewal flow for ACTIVE boxes
    sel_renew_link: str = "a:has-text('Renew')"
    sel_submit_plan_button: str = "input[value='Submit']"
    sel_renewal_status_ok: str = "input[value='OK']"

    # ── Class methods ─────────────────────────────────────────────────────
    @classmethod
    def from_args_or_env(cls) -> "Config":
        parser = argparse.ArgumentParser(description="Hathway STB Renewal Automation")
        parser.add_argument("--url",      default=None)
        parser.add_argument("--username", default=None)
        parser.add_argument("--password", default=None)
        parser.add_argument("--boxes",    nargs="+", default=None,
                            help="Space-separated box numbers")
        parser.add_argument("--boxes-file", default=None,
                            help="Path to file with one box number per line")
        parser.add_argument("--config-file", default=None,
                            help="Path to JSON config file")
        parser.add_argument("--headless", action="store_true", default=False)
        parser.add_argument("--plan",     default=None,
                            help="Target plan name override")
        args = parser.parse_args()

        cfg = cls()

        # Load JSON config first (lowest priority)
        if args.config_file:
            with open(args.config_file) as f:
                data = json.load(f)
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)

        # Environment variables (medium priority)
        cfg.portal_url = os.getenv("HATHWAY_URL",      cfg.portal_url)
        cfg.username   = os.getenv("HATHWAY_USERNAME",  cfg.username)
        cfg.password   = os.getenv("HATHWAY_PASSWORD",  cfg.password)

        # CLI args (highest priority)
        if args.url:      cfg.portal_url = args.url
        if args.username: cfg.username   = args.username
        if args.password: cfg.password   = args.password
        if args.headless: cfg.headless   = True
        if args.plan:     cfg.target_plan_name = args.plan

        # Box numbers
        if args.boxes:
            cfg.box_numbers = args.boxes
        elif args.boxes_file:
            p = Path(args.boxes_file)
            cfg.box_numbers = [
                line.strip() for line in p.read_text().splitlines()
                if line.strip()
            ]
        elif not cfg.box_numbers:
            box_env = os.getenv("HATHWAY_BOXES", "")
            cfg.box_numbers = [b.strip() for b in box_env.split(",") if b.strip()]

        # Validate
        if not cfg.username or not cfg.password:
            raise ValueError(
                "Username and password are required. "
                "Set via --username/--password or HATHWAY_USERNAME/HATHWAY_PASSWORD env vars."
            )
        if not cfg.box_numbers:
            raise ValueError(
                "At least one box number is required. "
                "Set via --boxes or HATHWAY_BOXES env var."
            )

        # Create captcha debug dir
        Path(cfg.captcha_debug_dir).mkdir(exist_ok=True)

        return cfg
