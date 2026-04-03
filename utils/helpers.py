import asyncio
import random
from typing import Optional
from playwright.async_api import Page


async def human_type(page: Page, selector_or_loc, text: str, clear: bool = True):
    if isinstance(selector_or_loc, str):
        el = await page.wait_for_selector(selector_or_loc, timeout=15_000)
    else:
        el = selector_or_loc

    if el:
        if clear:
            await el.click(click_count=3)
            await asyncio.sleep(0.15)
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Delete")
            await asyncio.sleep(0.1)
        for char in text:
            await el.type(char, delay=random.uniform(50, 160))
            await asyncio.sleep(random.uniform(0.02, 0.08))


async def random_delay(min_s: float = 0.5, max_s: float = 1.5):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def wait_and_click(page: Page, selector: str, config, timeout: Optional[int] = None) -> bool:
    _timeout = timeout or config.element_timeout
    try:
        el = await page.wait_for_selector(selector, timeout=_timeout, state="visible")
        if not el:
            return False
        await el.scroll_into_view_if_needed()
        await asyncio.sleep(0.2)
        await el.click()
        await asyncio.sleep(config.delay_after_click)
        return True
    except Exception:
        return False


async def safe_click(page: Page, selector: str, timeout: int = 10_000) -> bool:
    try:
        el = await page.wait_for_selector(selector, timeout=timeout, state="visible")
        if el:
            await el.scroll_into_view_if_needed()
            await asyncio.sleep(0.2)
            await el.click()
            return True
    except Exception:
        pass
    return False


async def scroll_into_view_and_click(page: Page, selector: str, config) -> bool:
    try:
        el = await page.wait_for_selector(selector, timeout=config.element_timeout, state="attached")
        if not el:
            return False
        await el.scroll_into_view_if_needed()
        await asyncio.sleep(0.3)
        try:
            await el.click(timeout=5_000)
        except Exception:
            await page.evaluate("el => el.click()", el)
        await asyncio.sleep(config.delay_after_click)
        return True
    except Exception:
        return False


async def retry_async(coro_func, max_retries: int = 3, delay: float = 1.5, *args, **kwargs):
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            return await coro_func(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                await asyncio.sleep(delay * attempt)
    raise last_exc