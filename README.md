# Hathway STB Renewal Automation

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
