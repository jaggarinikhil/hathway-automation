import asyncio
import json
import os
import re
import logging
from typing import List, Optional, Any
from playwright.async_api import Page, Locator, ElementHandle

class SelectorStore:
    """Manages the persistent JSON store of selectors."""
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.data = {}
        self.lock = asyncio.Lock()
        self._load()

    def _load(self):
        if os.path.exists(self.storage_path):
            with open(self.storage_path, "r") as f:
                self.data = json.load(f)
        else:
            self.data = {}

    async def save(self):
        async with self.lock:
            with open(self.storage_path, "w") as f:
                json.dump(self.data, f, indent=2)

    def get_selectors(self, key: str) -> List[str]:
        return self.data.get(key, [])

    async def add_selector(self, key: str, selector: str):
        async with self.lock:
            if key not in self.data:
                self.data[key] = []
            if selector not in self.data[key]:
                # Insert at top as it's the newest validated one
                self.data[key].insert(0, selector)
                # Keep list manageable (max 5)
                self.data[key] = self.data[key][0:5]
        await self.save()


class SelfHealingEngine:
    """Core logic for smart locating and healing."""
    def __init__(self, store: SelectorStore, logger: logging.Logger):
        self.store = store
        self.logger = logger

    async def smart_locator(self, page: Page, key: str, timeout: int = 10000) -> Optional[Locator]:
        """Try stored selectors, then fallbacks, then heal."""
        selectors = self.store.get_selectors(key)
        
        # 1. Try stored selectors
        for selector in selectors:
            try:
                # Use a short timeout for each individual check to be fast
                loc = page.locator(selector).first
                if await loc.is_visible(timeout=2000):
                    self.logger.info(f"[HEALING] Key '{key}' found via stored selector: {selector}")
                    return loc
            except Exception:
                continue

        # 2. Semantic Fallbacks
        self.logger.warning(f"[HEALING] All stored selectors for '{key}' failed. Trying fallbacks...")
        
        # We use common semantic patterns based on the key name
        fallbacks = [
            # Try by text (most common)
            lambda p: p.get_by_text(key.replace("_", " "), exact=False),
            lambda p: p.get_by_role("button", name=key.replace("_", " "), exact=False),
            lambda p: p.get_by_role("link", name=key.replace("_", " "), exact=False),
            lambda p: p.get_by_label(key.replace("_", " "), exact=False),
        ]

        # For specific common keys, use targeted fallbacks
        if "submit" in key:
            fallbacks.insert(0, lambda p: p.get_by_role("button", name="Submit"))
        if "confirm" in key:
            fallbacks.insert(0, lambda p: p.get_by_role("button", name="Confirm"))
        if "search" in key:
            fallbacks.insert(0, lambda p: p.get_by_placeholder(re.compile("search", re.I)))

        for fb in fallbacks:
            try:
                loc = fb(page).first
                if await loc.is_visible(timeout=3000):
                    self.logger.info(f"[HEALING] Key '{key}' recovered via semantic fallback!")
                    # HEAL!
                    await self._heal(loc, key)
                    return loc
            except Exception:
                continue

        self.logger.error(f"[HEALING] CRITICAL: Could not find element for key '{key}'")
        return None

    async def _heal(self, locator: Locator, key: str):
        """Analyze the element and generate a new stable selector."""
        try:
            # Extract features via JS
            features = await locator.evaluate("""(el) => {
                return {
                    id: el.id,
                    name: el.name,
                    tagName: el.tagName.toLowerCase(),
                    type: el.type,
                    innerText: el.innerText.trim().substring(0, 30),
                    role: el.getAttribute('role')
                }
            }""")

            new_sel = ""
            if features.get("id"):
                new_sel = f"#{features['id']}"
            elif features.get("name"):
                new_sel = f"{features['tagName']}[name='{features['name']}']"
            elif features.get("innerText"):
                # Clean text for CSS selector
                text = features["innerText"].replace("'", "\\'")
                new_sel = f"{features['tagName']}:has-text('{text}')"
            
            if new_sel:
                self.logger.info(f"[HEALING] Generated new stable selector for '{key}': {new_sel}")
                await self.store.add_selector(key, new_sel)
        except Exception as e:
            self.logger.error(f"[HEALING] Failed to extract features for self-healing: {e}")

    async def smart_click(self, page: Page, key: str, timeout: int = 15000) -> bool:
        """Robust click with healing."""
        loc = await self.smart_locator(page, key, timeout)
        if loc:
            try:
                await loc.scroll_into_view_if_needed()
                await asyncio.sleep(0.2)
                await loc.click(timeout=timeout)
                return True
            except Exception as e:
                self.logger.error(f"[HEALING] Click failed on '{key}' even after finding it: {e}")
                # Try force click as last resort
                try:
                    await loc.click(force=True, timeout=2000)
                    return True
                except:
                    return False
        return False
