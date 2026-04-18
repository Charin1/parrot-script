import asyncio
from playwright.async_api import async_playwright
import re

async def test_lobby():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(permissions=[])
        page = await context.new_page()
        print("Navigating...")
        await page.goto("https://meet.google.com/eyu-wauu-ckh", wait_until="networkidle")
        print("At page, looking for name input...")
        
        for _ in range(15):
            for btn in ["Dismiss", "Got it", "continue without"]:
                try:
                    b = page.get_by_role("button", name=re.compile(btn, re.IGNORECASE))
                    if await b.is_visible(timeout=500):
                        await b.click()
                        print(f"Clicked {btn}")
                except: pass
                
            loc = page.locator('input[type="text"]')
            if await loc.is_visible():
                print("Found input!")
                await page.screenshot(path="test_bot_success.png")
                return
            await asyncio.sleep(1)
        
        print("Timeout, taking screenshot")
        await page.screenshot(path="test_bot_fail.png")

asyncio.run(test_lobby())
