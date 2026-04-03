"""
agents/logger_agent.py — Structured logging for the automation system.
Writes to both console and a log file.
"""

import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List


class LoggerAgent:
    """
    Central logging agent. All other agents receive an instance of this
    and call its methods to record events.
    """

    def __init__(self, log_file: str = "hathway_automation.log"):
        self.log_file = log_file
        self._events: List[Dict[str, Any]] = []
        self._captcha_attempts: int = 0
        self._login_attempts: int = 0
        self._box_results: Dict[str, str] = {}   # box_number → "success" | "failed"
        self._errors: List[str] = []

        # Python logging setup
        self._logger = logging.getLogger("HathwayAutomation")
        self._logger.setLevel(logging.DEBUG)

        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)

        # File handler
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)

        self._logger.addHandler(ch)
        self._logger.addHandler(fh)

        self.info(f"Logger initialised → {Path(log_file).resolve()}")

    # ── Public logging methods ────────────────────────────────────────────

    def debug(self, msg: str):
        self._logger.debug(msg)
        self._record("DEBUG", msg)

    def info(self, msg: str):
        self._logger.info(msg)
        self._record("INFO", msg)

    def success(self, msg: str):
        self._logger.info(f"✅ {msg}")
        self._record("SUCCESS", msg)

    def warning(self, msg: str):
        self._logger.warning(msg)
        self._record("WARNING", msg)

    def error(self, msg: str, exc_info: bool = False):
        if exc_info:
            tb = traceback.format_exc()
            self._logger.error(f"{msg}\n{tb}")
            self._record("ERROR", f"{msg}\n{tb}")
            self._errors.append(f"{msg}\n{tb}")
        else:
            self._logger.error(msg)
            self._record("ERROR", msg)
            self._errors.append(msg)

    # ── Domain-specific event recorders ───────────────────────────────────

    def log_captcha_attempt(self, attempt: int, extracted: str, success: bool):
        self._captcha_attempts += 1
        status = "✅ OK" if success else "❌ FAIL"
        self.info(f"[CAPTCHA] Attempt {attempt} | Extracted='{extracted}' | {status}")

    def log_login_attempt(self, attempt: int, success: bool):
        self._login_attempts += 1
        status = "SUCCESS" if success else "FAILED"
        self.info(f"[LOGIN] Attempt {attempt} → {status}")

    def log_box_result(self, box_number: str, success: bool, reason: str = ""):
        result = "success" if success else "failed"
        self._box_results[box_number] = result
        tag = "✅" if success else "❌"
        msg = f"[BOX {box_number}] {tag} {result.upper()}"
        if reason:
            msg += f" — {reason}"
        self.info(msg)

    def log_step(self, box_number: str, step: str, success: bool, detail: str = ""):
        status = "OK" if success else "FAIL"
        self.debug(f"[BOX {box_number}][STEP:{step}] {status} {detail}")

    # ── Summary ───────────────────────────────────────────────────────────

    def get_summary(self) -> Dict[str, Any]:
        successful = [k for k, v in self._box_results.items() if v == "success"]
        failed     = [k for k, v in self._box_results.items() if v == "failed"]
        return {
            "timestamp": datetime.now().isoformat(),
            "login_attempts": self._login_attempts,
            "captcha_attempts": self._captcha_attempts,
            "total_boxes": len(self._box_results),
            "successful_boxes": successful,
            "failed_boxes": failed,
            "success_count": len(successful),
            "failure_count": len(failed),
            "errors": self._errors,
        }

    # ── Internal ──────────────────────────────────────────────────────────

    def _record(self, level: str, msg: str):
        self._events.append({
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": msg,
        })
