# Hathway STB Renewal Automation

## Telegram bot integration

The existing manual `renew.yml` workflow and Python Playwright/Tesseract renewal
remain available. Optional Telegram inputs add a Cloudflare Worker trigger,
persistent duplicate protection and completion messages, without another browser
execution service. The workflow uploads no sensitive artifacts.

Follow [the complete Telegram setup guide](telegram-worker/README.md) for BotFather,
secret configuration, authorization, Cloudflare D1, deployment and webhook setup.
Use [TELEGRAM_TEST_RESULTS.md](TELEGRAM_TEST_RESULTS.md) for actual checks and
unverified items. No Telegram or Cloudflare token should be pasted into chat.

The current portal core reports success through its existing UI checks. Telegram
labels that honestly as reported success; it does not invent independent
transaction verification. Unknown results retain a box lock for manual review.

A production-ready, agent-based browser automation system built with **Playwright** and **Tesseract OCR** for bulk renewal of Hathway set-top boxes on the partner portal.

---

## Project Structure

```
hathway-automation/
├── main.py                      # Entry point
├── config.py                    # Central configuration (credentials, selectors, timeouts)
├── requirements.txt
├── config.example.json          # Template — copy and fill in credentials
├── boxes.txt                    # One box number per line
│
├── agents/
│   ├── logger_agent.py          # Structured logging (console + file)
│   ├── captcha_agent.py         # OCR-based CAPTCHA solving (Tesseract)
│   ├── login_agent.py           # Login + CAPTCHA retry loop
│   ├── popup_handler_agent.py   # Post-login popup/ad dismissal
│   ├── navigation_agent.py      # Menu navigation (Package Management)
│   └── renewal_agent.py         # Core renewal workflow per box
│
├── utils/
│   └── helpers.py               # Shared Playwright helpers (click, type, retry)
│
└── captcha_debug/               # CAPTCHA screenshots saved here (auto-created)
```

---

## Prerequisites

### 1. Python 3.9+
```bash
python --version
```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Install Playwright browsers
```bash
playwright install chromium
```

### 4. Install Tesseract OCR

**Windows:**
Download installer from https://github.com/UB-Mannheim/tesseract/wiki  
Add to PATH: `C:\Program Files\Tesseract-OCR`

**macOS:**
```bash
brew install tesseract
```

**Ubuntu/Debian:**
```bash
sudo apt install tesseract-ocr
```

Verify:
```bash
tesseract --version
```

---

## Configuration

### Option A — JSON config file (recommended)
```bash
cp config.example.json config.json
# Edit config.json with your credentials and box numbers
python main.py --config-file config.json
```

### Option B — Command-line arguments
```bash
python main.py \
  --username YOUR_USER \
  --password YOUR_PASS \
  --boxes BOX001 BOX002 BOX003
```

### Option C — boxes.txt file
```bash
python main.py \
  --username YOUR_USER \
  --password YOUR_PASS \
  --boxes-file boxes.txt
```

### Option D — Environment variables
```bash
export HATHWAY_USERNAME=your_user
export HATHWAY_PASSWORD=your_pass
export HATHWAY_BOXES="BOX001,BOX002,BOX003"
python main.py
```

---

## Usage Examples

**Single box (visible browser):**
```bash
python main.py --username admin --password secret --boxes BOX001234
```

**Bulk renewal from file (headless):**
```bash
python main.py --config-file config.json --boxes-file boxes.txt --headless
```

**Custom plan override:**
```bash
python main.py --config-file config.json --plan "HW TL BRONZE KMM 30d"
```

---

## Architecture — Agent Roles

| Agent | File | Responsibility |
|-------|------|----------------|
| **LoggerAgent** | `agents/logger_agent.py` | Writes structured logs to console + file |
| **CaptchaAgent** | `agents/captcha_agent.py` | Screenshots CAPTCHA, pre-processes image, runs Tesseract OCR |
| **LoginAgent** | `agents/login_agent.py` | Fills credentials, handles CAPTCHA retry loop (up to 5×) |
| **PopupHandlerAgent** | `agents/popup_handler_agent.py` | Dismisses ads, STB popups, native dialogs |
| **NavigationAgent** | `agents/navigation_agent.py` | Clicks Package Management menu, detects page state |
| **RenewalAgent** | `agents/renewal_agent.py` | Full 7-step renewal per box with per-step retry |

---

## Workflow

```
LAUNCH BROWSER
     │
     ▼
LOGIN (CAPTCHA retry × 5)
     │
     ▼
DISMISS POPUPS / ADS
     │
     ▼
NAVIGATE → Package Management
     │
     ▼
FOR EACH BOX NUMBER:
  ├─ A. Search box number
  ├─ B. Click Main TV
  ├─ C. Click Add Plan
  ├─ D. Click Hathway Bouquet
  ├─ E. Select "HW TL BRONZE KMM 30d"
  ├─ F. Click Add → Confirm
  └─ G. Validate success
     │
     ├─ ✅ Log success → next box
     └─ ❌ Retry (×2) → log failure → next box
     │
     ▼
PRINT SUMMARY REPORT
```

---

## Output

**Console + log file (`hathway_automation.log`):**
```
2024-01-15 10:23:01 | INFO     | 🚀 Hathway STB Renewal Automation Started
2024-01-15 10:23:01 | INFO     | 📦 Total boxes to process: 3
2024-01-15 10:23:15 | INFO     | ✅ Login successful
2024-01-15 10:23:20 | INFO     | [BOX BOX001234] ✅ SUCCESS
2024-01-15 10:23:45 | INFO     | [BOX BOX005678] ✅ SUCCESS
2024-01-15 10:24:10 | ERROR    | [BOX BOX009012] ❌ FAILED — Exceeded retry limit
```

**Final report:**
```
╔══════════════════════════════════════════════════════════╗
║           HATHWAY STB RENEWAL — EXECUTION REPORT         ║
╠══════════════════════════════════════════════════════════╣
║  Total Boxes    : 3                                       ║
║  Successful     : 2                                       ║
║  Failed         : 1                                       ║
╠══════════════════════════════════════════════════════════╣
║  ✅ SUCCESSFUL BOXES                                      ║
║    → BOX001234                                            ║
║    → BOX005678                                            ║
╠══════════════════════════════════════════════════════════╣
║  ❌ FAILED BOXES                                          ║
║    → BOX009012                                            ║
╚══════════════════════════════════════════════════════════╝
```

**CAPTCHA debug images** are saved in `captcha_debug/` for manual inspection.

---

## Troubleshooting

### CAPTCHA OCR not working
- Check `captcha_debug/` folder for saved images
- Tesseract not on PATH? Set manually: `pytesseract.pytesseract.tesseract_cmd = r'C:\...\tesseract.exe'`
- Try running `tesseract captcha_debug/captcha_XYZ_raw.png stdout --psm 8 digits` manually

### Element not found errors
- The portal may have updated its HTML. Inspect the live page and update selectors in `config.py`
- Increase `element_timeout` in `config.py` (default: 20,000 ms)

### Login keeps failing
- Verify credentials manually in browser first
- Check if portal requires VPN / IP whitelist

### Popup not dismissed
- Inspect the popup HTML and add its selector to `config.sel_close_stb_popup`

---

## Customisation

All selectors, timeouts, retry counts, and delays are in **`config.py`**.  
No code changes needed for normal parameter tuning — only edit `config.json`.

To add support for a new plan:
```bash
python main.py --config-file config.json --plan "NEW PLAN NAME"
```

---

## Disclaimer

This tool is intended for authorised portal users only. Ensure you have permission to automate actions on the target portal. The authors assume no liability for misuse.

## Post-renewal Retrack

After renewal reports success, the browser stays on the same box for 60 seconds,
then clicks Retrack → Confirm → OK. Telegram shows the renewal result only; Retrack details remain in Actions logs.
The portal's 15-minute repeat-request restriction does not trigger automatic retries. See [RETRACK_SETUP.md](RETRACK_SETUP.md) for rollout and tests.


### Optional second Hathway account

Add repository Actions secrets `HATHWAY_USERNAME_2` and `HATHWAY_PASSWORD_2` for your second authorized Hathway account. Keep the existing primary secrets unchanged. Both manual and Telegram renewals use these optional secrets. No Worker changes are needed.

After search, only the visible message "You have no privileges to access customer information as s/he belongs to other LCO" triggers Signout, a fresh login through the existing CAPTCHA flow, and a search in account 2. Other failures and uncertain submissions never switch accounts. If both accounts deny access, processing stops. Each new box starts with account 1. Existing renewal and one-minute Retrack behavior are unchanged. If Signout does not reach Login.aspx, the switch stops safely.

Validation: mocked account tests, existing Python tests, Python compilation and workflow YAML parsing. Real account switching, actual Signout markup/redirect, and real renewals have not been executed for this update.

### Portal rejections and completion details

Only the visible other-LCO search message triggers an account switch. The terminated/nonexistent VC message and insufficient balance remain in the current account. Renewal is limited to two total attempts per account (including the first attempt). A second attempt after Submit is permitted only when the portal explicitly displays one of those rejection messages; ambiguous submissions still stop immediately. The rejected form is discarded with a fresh GET of the same page before another search. Failure to reset stops further attempts.

Telegram results include the recognized rejection reason, stage, number of attempts, and Account 1 or Account 2. Success results additionally include first name, last name, and phone only when labeled fields can be tied to the exact requested box. Unsupported/missing fields are displayed as Unavailable; values are never guessed. Labels currently supported: First Name, Last Name, Mobile/Mobile No/Mobile Number, Phone/Phone No/Phone Number, Registered Mobile Number, Contact Number, and RMN. The reader opens the Customer Details tab when needed and supports separate identity/contact tables, colon cells, and readonly form fields. It validates the box context, then the existing Main TV renewal step continues. Ambiguous values are withheld.

Customer contact fields go to the existing requester and configured admin notification recipients. They are not printed in Actions logs/job summaries or uploaded as artifacts. The private result file uses mode 0600; the rendered notification is stored in the existing D1 request record to recover failed deliveries. Consider this when authorizing members/admins and retaining request history.

Deploy both Python updates to GitHub and the Worker update to Cloudflare. No new secrets or D1 schema changes are required. Real Hathway customer-field layout and error popup/native-dialog variants still require validation; unsupported layouts show Unavailable and unsupported messages remain unknown rather than fabricated success/failure.


### Customer tab and notification fix

The previous reader required an exact box cell in the same table as contact details and did not open Customer Details. The reader now validates the displayed box, opens that tab when fields are incomplete, and reads explicitly labeled values across the validated customer form. Account switching, renewal actions and Retrack execution remain unchanged. Box status is read before opening Customer Details, so tab changes cannot affect the ACTIVE/DEACTIVE decision. Logs record only which field names were captured, never customer values.

Telegram no longer includes Retrack status/stage/reason or the Retrack retry reminder. This also applies to delivery retries of older stored notifications. Internal results and Actions logs still retain Retrack information.

### Hathway Customer Name / Customer Mobile labels

The Customer Details page uses a single `Customer Name` field and `Customer Mobile`. These exact labels are supported, including separate colon cells, spans, and the nested TV Details table that identifies the requested VC. Leading zeros are preserved. Telegram shows `Customer name` as the full portal-provided name and `Phone`; it does not guess a first/last-name split. Legacy separately labeled first/last fields remain supported and are joined for display. Retrack messages remain omitted; its execution is unchanged.

## Daily account-1 reports

A separate **Daily Hathway Reports** workflow reads the first account's portal reports and sends the owner:

- **10 AM IST:** today's Plan Expiry Report for all packages/boxes.
- **7 PM IST:** today's Transaction Report entries together, including Activation and Renewal, with each box number and transaction type plus totals by type. This is a snapshot; later transactions are not included.

Set repository variable `TELEGRAM_REPORT_CHAT_ID` to the owner's private chat ID. Existing primary Hathway credentials and Telegram bot secret are reused. No Cloudflare deployment is required. Schedules run from the default branch and may be delayed by GitHub. The report workflow never invokes renewal or Retrack. Customer data is not printed or uploaded as an artifact.

For setup, first manual read-only tests, privacy, pagination limits, actual local test results and live-test limitations, see [DAILY_REPORTS_SETUP.md](DAILY_REPORTS_SETUP.md).

The daily-report reader waits for delayed ASP.NET results and supports visible same-origin report frames. Expiry tables can use a VC or STB identifier column, including reports without a VC column. If detection still fails, Actions logs show only safe table counts and recognized column categories. See [EXPIRY_GRID_FIX.md](EXPIRY_GRID_FIX.md) for compatibility checks and live-test limitations.
