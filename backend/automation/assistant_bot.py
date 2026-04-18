import asyncio
import sys
import re
import os
import argparse
import logging
from playwright.async_api import async_playwright

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def run_bot(meeting_url: str, assistant_name: str, headless: bool = True):
    profile_dir = os.path.join(os.path.dirname(__file__), ".bot_profile")
    if not os.path.exists(profile_dir):
        logger.error(f"Bot profile not found at {profile_dir}. Please run setup_bot_profile.py first.")
        return

    async with async_playwright() as p:
        logger.info(f"Launching {'headless ' if headless else ''}browser with persistent profile...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            channel="chrome",
            headless=headless,
            permissions=['microphone', 'camera'],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars"
            ]
        )
        
        page = context.pages[0] if len(context.pages) > 0 else await context.new_page()
        
        logger.info(f"Navigating to {meeting_url}...")
        await page.goto(meeting_url, wait_until="networkidle")
        
        try:
            # We try multiple ways to find the name input
            name_input = None
            locators = [
                page.get_by_role("textbox", name=re.compile(r"your name", re.IGNORECASE)),
                page.get_by_placeholder("Your name"),
                page.get_by_label("Your name"),
                page.locator('input[type="text"]')
            ]
            
            logger.info("Waiting for lobby elements to appear (up to 30s)...")
            for _ in range(15): # Total 30s check
                # 1. Handle "Dismiss" or "Continue without" popups if they appear during the wait
                for btn_text in ["Dismiss", "Got it", "continue without"]:
                    try:
                        btn = page.get_by_role("button", name=re.compile(btn_text, re.IGNORECASE))
                        if await btn.is_visible(timeout=500):
                            await btn.click()
                            logger.info(f"Clicked '{btn_text}' popup.")
                    except:
                        pass

                # 2. Check for name input
                for loc in locators:
                    try:
                        if await loc.is_visible(timeout=1000):
                            name_input = loc
                            break
                    except:
                        continue
                if name_input:
                    break
                await asyncio.sleep(1)

            # 3. Mute Microphone and Camera using shortcuts just in case
            modifier = "Control" if sys.platform != "darwin" else "Meta"
            await page.keyboard.press(f"{modifier}+d") # Mute Mic
            await page.keyboard.press(f"{modifier}+e") # Mute Cam
            logger.info("Sent mute shortcuts (Mic/Cam).")

            if name_input:
                await name_input.fill(assistant_name)
                logger.info(f"Entered name: {assistant_name}")
            else:
                logger.warning("Name input not found after 30s. Taking screenshot for debug.")
                await page.screenshot(path="backend/automation/debug_lobby.png")
                logger.info("Saved debug screenshot to backend/automation/debug_lobby.png")

            # 4. Click Join
            # Google Meet has "Ask to join" for guests and "Join now" for signed-in users.
            join_btn = page.get_by_role("button", name=re.compile(r"Ask to join|Join now|Join meeting", re.IGNORECASE))
            if await join_btn.is_visible(timeout=10000):
                await join_btn.click()
                logger.info("Clicked Join button.")
            else:
                logger.error("Could not find Join button.")
                if not name_input:
                     pass
                else:
                    await page.screenshot(path="backend/automation/debug_join.png")
                return

            print("SUCCESS: JOINED") # Marker for the caller
            
            # 5. Keep alive
            while True:
                await asyncio.sleep(5)
                # Optional: Check if we were kicked or meeting ended
                if await page.get_by_role("button", name="Return to home screen").is_visible(timeout=1000):
                    logger.info("Meeting ended or assistant removed.")
                    break
                    
        except Exception as e:
            logger.error(f"Error during join automation: {e}")
        finally:
            logger.info("Closing browser...")
            await context.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parrot Script Meeting Assistant Bot")
    parser.add_argument("--url", required=True, help="Meeting URL")
    parser.add_argument("--name", default="Parrot Script Assistant", help="Display name for the bot")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser window")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(run_bot(args.url, args.name, headless=not args.headed))
    except KeyboardInterrupt:
        logger.info("Bot manually interrupted.")
