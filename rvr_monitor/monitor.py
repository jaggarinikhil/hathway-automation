"""Headless RVR monitor. Logs contain counts only; no credentials or customer data."""
import asyncio
import base64
import copy
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
ROOT = Path(__file__).parent


class MonitorError(ValueError):
    """Only fixed, non-sensitive diagnostic messages."""


def in_window(now):
    local = now.astimezone(IST)
    return 360 <= local.hour * 60 + local.minute < 721


def assess(groups, accounts, online, previous, now):
    """Unknown accounts invalidate the entire snapshot; never infer an outage."""
    wanted = {u for members in groups.values() for u in members}
    if wanted - accounts.keys():
        raise MonitorError("Configured accounts missing from complete portal list")
    state, alerts = copy.deepcopy(previous), []
    for name, members in groups.items():
        eligible = [u for u in members if accounts[u] == "active"]
        offline = sum(u not in online for u in eligible)
        threshold = math.ceil(len(eligible) / 2)
        old = previous.get(name, {})
        last = old.get("checked_at")
        gap = (now - datetime.fromisoformat(last)).total_seconds() if last else 0
        signature = sorted(eligible)
        # Do not treat yesterday or skipped/failed checks as consecutive evidence.
        consecutive = (last and 0 < gap <= 15 * 60
                       and old.get("date") == now.astimezone(IST).date().isoformat()
                       and old.get("eligible") == signature)
        hit = bool(eligible) and offline >= threshold
        streak = (old.get("streak", 0) if consecutive else 0) + 1 if hit else 0
        notified = bool(old.get("notified")) if hit else False
        state[name] = {"checked_at": now.isoformat(),
                       "date": now.astimezone(IST).date().isoformat(),
                       "eligible": signature, "streak": streak,
                       "notified": notified, "offline": offline,
                       "total": len(eligible), "threshold": threshold}
        if hit and streak >= 2 and not notified:
            alerts.append(name)
    return state, alerts


def api(method, path, payload=None):
    repo = os.environ["GITHUB_REPOSITORY"]
    request = Request(f"https://api.github.com/repos/{repo}/{path}",
                      data=json.dumps(payload).encode() if payload is not None else None,
                      headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                               "Accept": "application/vnd.github+json",
                               "Content-Type": "application/json"}, method=method)
    with urlopen(request, timeout=30) as response:
        return json.load(response)


class StateStore:
    """Separate repository branch persists notification state without expiring caches."""
    branch = "rvr-monitor-state"

    def __init__(self):
        self.sha = None

    def load(self):
        try:
            api("GET", "git/ref/heads/" + self.branch)
        except HTTPError as exc:
            if exc.code != 404:
                raise
            base = api("GET", "git/ref/heads/" + os.environ["GITHUB_DEFAULT_BRANCH"])
            api("POST", "git/refs", {"ref": "refs/heads/" + self.branch,
                                      "sha": base["object"]["sha"]})
        try:
            record = api("GET", "contents/rvr-monitor-state.json?ref=" + self.branch)
        except HTTPError as exc:
            if exc.code != 404:
                raise
            return {}
        self.sha = record["sha"]
        return json.loads(base64.b64decode(record["content"]))

    def save(self, state):
        payload = {"message": "Update RVR monitoring state [skip ci]",
                   "branch": self.branch,
                   "content": base64.b64encode(json.dumps(state).encode()).decode()}
        if self.sha:
            payload["sha"] = self.sha
        result = api("PUT", "contents/rvr-monitor-state.json", payload)
        self.sha = result["content"]["sha"]


async def read_table(page, path, required):
    await page.goto("https://service.rvrnet.com" + path, wait_until="domcontentloaded")
    await page.get_by_role("table").wait_for(timeout=45000)
    # Require a settled, complete footer before interpreting absence as offline.
    footer = page.get_by_text(re.compile(r"\d+\s*-\s*\d+\s+of\s+\d+\s+entries"))
    await footer.wait_for(timeout=45000)
    text = await footer.inner_text()
    match = re.search(r"(\d+)\s*-\s*(\d+)\s+of\s+(\d+)\s+entries", text)
    if not match or int(match[1]) != (1 if int(match[3]) else 0) or int(match[2]) != int(match[3]):
        raise MonitorError("Portal list is paginated or incomplete; monitoring stopped")
    rows = await page.get_by_role("table").locator("tr").evaluate_all(
        "rows => rows.map(r => Array.from(r.querySelectorAll('th,td')).map(c => (c.querySelector('a.jazeLink') || c).innerText.trim()))")
    header = next((r for r in rows if all(any(k in c.upper() for c in r) for k in required)), None)
    if header is None:
        raise MonitorError("Portal columns not recognized")
    indexes = {k: next(i for i, c in enumerate(header) if k in c.upper()) for k in required}
    result = {}
    for _ in range(100):
        records = [r for r in rows if r != header and len(r) == len(header)
                   and not any("No Matching Records" in c for c in r)]
        batch = set()
        for row in records:
            username = row[indexes["USERNAME"]].strip()
            value = row[indexes["STATUS"]].lower() if "STATUS" in indexes else True
            if not username or username in batch or (username in result and result[username] != value):
                raise MonitorError("Ambiguous customer/session rows")
            batch.add(username)
            result[username] = value
        if len(result) == int(match[3]):
            return result
        # RVR virtualizes account rows inside this observed scroll container.
        scroller = page.locator('.jazeVirtualScroll')
        if await scroller.count() != 1:
            break
        moved = await scroller.evaluate("el => {const before=el.scrollTop; el.scrollTop += Math.max(100, el.clientHeight * 0.7); return el.scrollTop > before;}")
        if not moved:
            break
        await page.wait_for_timeout(250)
        rows = await page.get_by_role("table").locator("tr").evaluate_all(
            "rows => rows.map(r => Array.from(r.querySelectorAll('th,td')).map(c => (c.querySelector('a.jazeLink') || c).innerText.trim()))")
    raise MonitorError("Portal row count does not match footer after scrolling")


async def collect():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            page.set_default_timeout(45000)
            await page.goto("https://service.rvrnet.com/signin", wait_until="domcontentloaded")
            await page.locator('input[name="username"]').fill(os.environ["RVR_USERNAME"])
            await page.locator('input[name="password"]').fill(os.environ["RVR_PASSWORD"])
            await page.get_by_role("button", name="Sign In", exact=True).click()
            await page.wait_for_url("**/dashboard", timeout=45000)
            accounts = await read_table(page, "/users/allusers", ["USERNAME", "STATUS"])
            allowed = {"active", "expired", "suspended", "blocked", "frozen", "pending", "disabled", "inactive"}
            if any(status not in allowed for status in accounts.values()):
                raise MonitorError("Unrecognized account status")
            online = await read_table(page, "/monitoring/active_sessions", ["USERNAME", "START TIME"])
            return accounts, set(online)
        finally:
            await browser.close()


def notify(name, group, now):
    topic = os.environ["NTFY_TOPIC"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{24,64}", topic):
        raise MonitorError("Use a random ntfy topic of 24-64 characters")
    body = (f"{name}: {group['offline']} of {group['total']} active connections offline. "
            f"Threshold: {group['threshold']}. Confirmed on two checks. "
            f"Checked {now.astimezone(IST):%Y-%m-%d %I:%M %p} IST.")
    request = Request("https://ntfy.sh/" + quote(topic, safe=""), data=body.encode(),
                      headers={"Title": "RVR group outage", "Priority": "high"}, method="POST")
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise MonitorError("Notification not accepted")


async def main():
    now = datetime.now(IST)
    dry_run = os.environ.get("RVR_DRY_RUN", "false").lower() == "true"
    if not dry_run and not in_window(now):
        print("Outside India monitoring window; skipped")
        return
    required = ("RVR_USERNAME", "RVR_PASSWORD") if dry_run else ("RVR_USERNAME", "RVR_PASSWORD", "NTFY_TOPIC", "GITHUB_TOKEN")
    for key in required:
        if not os.environ.get(key):
            raise MonitorError("Required secret missing: " + key)
    groups = json.loads((ROOT / "groups.json").read_text())
    if dry_run:
        accounts, online = await collect()
        state, _ = assess(groups, accounts, online, {}, now)
        summary = ["| Group | Online | Offline | Threshold |", "|---|---:|---:|---:|"]
        for name, group in state.items():
            summary.append(f"| {name} | {group['total'] - group['offline']} | {group['offline']} | {group['threshold']} |")
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text("Read-only validation: no notifications or saved state.\n\n" + "\n".join(summary))
        print(f"Read-only validation completed for {len(state)} groups; no notification sent")
        return
    store = StateStore()
    previous = store.load()
    accounts, online = await collect()
    state, alerts = assess(groups, accounts, online, previous, now)
    # Persist observed state before notifications. A failed run is visible only in Actions.
    store.save(state)
    for name in alerts:
        notify(name, state[name], now)
        state[name]["notified"] = True
        store.save(state)
    print(f"Checked {len(groups)} groups; sent {len(alerts)} threshold alerts")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        # Browser exceptions may include field values, URLs or DOM content.
        print("RVR monitor failed (" + type(exc).__name__ + "). No outage inferred.")
        if isinstance(exc, MonitorError):
            print(str(exc))
        raise SystemExit(1)
