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

## 🛡️ Self-Healing Automation System (The "Smart" Layer)

A major evolution in this project is the addition of a **Self-Healing Engine** that prevents breakage when the portal's UI (IDs, Classes, or structure) changes slightly.

### The "Heal" Cycle:
1. **Attempt Stored**: The system tries 1-5 prioritized selectors for a logical key (e.g., `ok_button`).
2. **Semantic Recovery**: If all fail, the system uses Playwright's semantic locators (`get_by_role`, `get_by_text`). This is slow but very robust.
3. **Feature Discovery & Re-Learning**: Upon a successful recovery, the engine inspects the found element's DOM properties and generates a new "Stable" CSS selector.
4. **Persistence**: The new selector is pushed to the top of `selectors.json`, making subsequent runs fast again.

### Key Files:
- **`utils/self_healing.py`**: Contains the `SelectorStore` and `SelfHealingEngine`.
- **`selectors.json`**: The shared, persistent database of selectors.

- **Timeout on Confirm**: Usually means a secondary popup is blocking the main button or multiple hidden buttons exist.
- **Login Loop**: Often caused by the portal's "Max session reached" error or incorrect CAPTCHA OCR. Added a 5x retry loop in `LoginAgent`.
