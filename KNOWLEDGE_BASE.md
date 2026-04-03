# Hathway Automation — Knowledge Base

This document stores key technical insights, architecture patterns, and "learnings" discovered during the development and optimization of the Hathway STB Renewal Automation.

## 🏗️ Architecture Overview

The system follows a **Multi-Agent Design** where each agent is responsible for a specific stage of the workflow:

| Agent | Responsibility | Key Learning |
|-------|----------------|--------------|
| **LoginAgent** | Credentials + CAPTCHA loop | Use `asyncio.sleep` between retries to allow the portal's session state to reset. |
| **CaptchaAgent** | Tesseract OCR OCR | CAPTCHA images often need binary thresholding for better OCR accuracy. |
| **PopupHandlerAgent** | Ad/Modal dismissal | Non-deterministic popups are best handled with a "bundled selector" approach. |
| **NavigationAgent** | Portal Menu Navigation | Sequential `wait_for_selector` calls are too slow; use `:is(...):visible` to find the first active link. |
| **RenewalAgent** | Core 7-step renewal | ASP.NET portals often have dozens of hidden buttons with the same name. Always use `:visible` filtering. |

## 🚀 Performance Optimizations (Major Learnings)

### 1. Bundled Selector Strategy
**Problem**: Checking 10+ different selectors sequentially with 20s timeouts was causing massive delays (up to 2 minutes per step).
**Solution**: Use comma-separated selectors in a single `wait_for_selector` or `locator` call.
**Learning**: `f":is({combined_selectors}):visible"` is the fastest and most robust way to find "any match that is actually on screen."

### 2. The "31 Hidden Buttons" Gotcha
**Observation**: In the Hathway portal, many elements exist in the DOM but are hidden. Standard Playwright locators might match dozens of background elements.
**Solution**: Always use `.filter(visible=True)` or the `:visible` pseudo-class.
**Learning**: If `locator.count()` is high but `click()` times out, it's almost certainly because Playwright is picking a hidden element first.

## 🛠️ Deployment Insights

- **Local Use**: The `.command` and `.app` launchers provide a user-friendly way to run the Python script without terminal knowledge.
- **Cloud Use**: For server deployment, **Google Cloud Run** via Docker is the recommended path because it supports the Playwright/Chromium environment and Tesseract dependencies perfectly.
- **GitHub**: Always use a `.gitignore` to protect `config.json` and `*.log` files to avoid leaking sensitive partner credentials.

## 📝 Troubleshooting Log

- **Timeout on Confirm**: Usually means a secondary popup is blocking the main button or multiple hidden buttons exist.
- **Login Loop**: Often caused by the portal's "Max session reached" error or incorrect CAPTCHA OCR. Added a 5x retry loop in `LoginAgent`.
