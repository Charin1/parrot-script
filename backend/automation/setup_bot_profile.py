import asyncio
import os
from playwright.async_api import async_playwright
import argparse

async def run_setup():
    print("="*60)
    print("🤖 Parrot Script Bot Profile Setup")
    print("="*60)
    print("A browser window will open shortly. Please follow these steps:")
    print("1. Log in to a generic/dummy Google Account that you want the bot to use.")
    print("2. Once you have fully logged in, close the browser window.")
    print("3. The session will be saved locally so the bot can use it later.")
    print("="*60)
    print("Launching browser...")

    profile_dir = os.path.join(os.path.dirname(__file__), ".bot_profile")
    os.makedirs(profile_dir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        page = await browser.new_page()
        await page.goto("https://accounts.google.com/")
        
        print("\nWaiting for you to log in and close the browser...")
        
        try:
            # Wait until all pages in the context are closed
            while len(browser.pages) > 0:
                await asyncio.sleep(1)
        except Exception as e:
            print(f"Browser closed or error: {e}")
            
        print("\n✅ Setup complete! Profile saved successfully.")

if __name__ == "__main__":
    try:
        asyncio.run(run_setup())
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
