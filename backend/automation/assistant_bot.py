import asyncio
import sys
import re
import os
import argparse
import logging
import json
import time
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

    # Flag for graceful shutdown
    shutdown_requested = asyncio.Event()

    async def watch_stdin():
        loop = asyncio.get_event_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            if line.strip().upper() == "QUIT":
                logger.info("Shutdown command received via stdin.")
                shutdown_requested.set()
                break

    stdin_task = asyncio.create_task(watch_stdin())
    context = None

    try:
        async with async_playwright() as p:
            logger.info(f"Launching {'headless ' if headless else ''}browser with persistent profile...")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                channel="chrome",
                headless=headless,
                viewport={'width': 1920, 'height': 1080},
                permissions=['microphone', 'camera'],
                args=[
                    "--window-size=1280,720",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars"
                ]
            )
            
            page = context.pages[0] if len(context.pages) > 0 else await context.new_page()
            
            # Pipe browser console logs to python logger for debugging
            page.on("console", lambda msg: logger.info(f"BROWSER: {msg.text}"))
            logger.info(f"Navigating to {meeting_url}...")
            await page.goto(meeting_url, wait_until="networkidle")
            
            # ... join logic ...
            name_input_locators = [
                page.get_by_role("textbox", name=re.compile(r"your name", re.IGNORECASE)),
                page.get_by_placeholder("Your name"),
                page.get_by_label("Your name"),
                page.locator('input[type="text"]')
            ]
            
            join_btn_locator = page.get_by_role("button", name=re.compile(r"Ask to join|Join now|Join meeting", re.IGNORECASE))
            
            logger.info("Waiting for lobby elements to appear...")
            joined = False
            for i in range(30): # Up to 30s total
                if shutdown_requested.is_set():
                    break

                popups = ["Dismiss", "Got it", "continue without", "Check your audio and video", "Close"]
                for btn_text in popups:
                    try:
                        btn = page.get_by_role("button", name=re.compile(btn_text, re.IGNORECASE))
                        if await btn.is_visible(timeout=100):
                            await btn.click()
                            logger.info(f"Dismissed '{btn_text}' popup.")
                    except:
                        pass

                if await join_btn_locator.is_visible(timeout=100):
                    for loc in name_input_locators:
                        try:
                            if await loc.is_visible(timeout=100):
                                current_val = await loc.input_value()
                                if not current_val:
                                    await loc.fill(assistant_name)
                                    logger.info(f"Filled name: {assistant_name}")
                                break
                        except:
                            continue
                    
                    await join_btn_locator.click()
                    logger.info("Clicked Join button.")
                    joined = True
                    break

                # 3. Explicitly mute Microphone and Camera via buttons
                try:
                    mic_btn = page.get_by_role("button", name=re.compile(r"Turn off microphone", re.IGNORECASE))
                    if await mic_btn.is_visible(timeout=100):
                        await mic_btn.click()
                        logger.info("Clicked 'Turn off microphone' button.")
                    
                    cam_btn = page.get_by_role("button", name=re.compile(r"Turn off camera", re.IGNORECASE))
                    if await cam_btn.is_visible(timeout=100):
                        await cam_btn.click()
                        logger.info("Clicked 'Turn off camera' button.")
                except:
                    pass

                # 4. Fallback: Mute Microphone and Camera using shortcuts
                if i == 2:
                    modifier = "Control" if sys.platform != "darwin" else "Meta"
                    await page.keyboard.press(f"{modifier}+d")
                    await page.keyboard.press(f"{modifier}+e")
                    logger.info("Sent mute shortcuts (Mic/Cam) as fallback.")

                await asyncio.sleep(1)

            if not joined and not shutdown_requested.is_set():
                logger.error("Failed to join meeting within 30s.")
                await page.screenshot(path="backend/automation/debug_join_failure.png")
                return

            if joined:
                print("SUCCESS: JOINED")
                
                # Safety check: Ensure muted after joining
                try:
                    await asyncio.sleep(2) # Wait for UI to settle inside
                    modifier = "Control" if sys.platform != "darwin" else "Meta"
                    
                    # If we still see "Turn off" buttons, it means we are NOT muted
                    mic_off_btn = page.get_by_role("button", name=re.compile(r"Turn off microphone", re.IGNORECASE))
                    if await mic_off_btn.is_visible(timeout=500):
                        await page.keyboard.press(f"{modifier}+d")
                        logger.info("Muted microphone inside meeting.")

                    cam_off_btn = page.get_by_role("button", name=re.compile(r"Turn off camera", re.IGNORECASE))
                    if await cam_off_btn.is_visible(timeout=500):
                        await page.keyboard.press(f"{modifier}+e")
                        logger.info("Muted camera inside meeting.")
                except:
                    pass
                
                # Instant Guest Sync: Get everyone's name right after joining
                try:
                    participants = []
                    
                    # 1. Base: Scrape names directly from the visible video tiles (always works)
                    tiles = await page.query_selector_all('[data-participant-id]')
                    for tile in tiles:
                        # Extract all text from the tile and take the most prominent line
                        name = await tile.evaluate('''el => {
                            // Try self-name first
                            const selfName = el.querySelector('[data-self-name]');
                            if (selfName) return selfName.innerText;
                            
                            // Google Meet ALWAYS wraps participant display names in a .notranslate span 
                            // to prevent Google Translate from corrupting people's actual names.
                            // However, they ALSO use .notranslate for Material Icons (e.g., 'frame_person', 'more_vert').
                            // We filter out any elements with 'icon' in their class, or strings containing underscores.
                            const noTranslates = Array.from(el.querySelectorAll('.notranslate')).filter(n => {
                                const text = n.innerText || '';
                                if (n.className.includes('icon') || text.includes('_') || text.includes('more_vert')) return false;
                                return text.length > 2;
                            });
                            if (noTranslates.length > 0) return noTranslates[0].innerText;
                            
                            // Fallback if absolutely necessary
                            const nameTags = Array.from(el.querySelectorAll('div, span')).filter(n => {
                                const text = n.innerText || '';
                                if (text.includes('more_vert') || text.includes('More options') || text.includes('Others might still see')) return false;
                                return text.length > 2 && text.length < 50 && !text.includes('\\n');
                            });
                            
                            // The longest valid string is usually the full name
                            nameTags.sort((a, b) => (b.innerText || '').length - (a.innerText || '').length);
                            return nameTags.length > 0 ? nameTags[0].innerText : '';
                        }''')
                        
                        if name:
                            participants.append(name.strip().replace(" (You)", ""))
                            
                    # 2. Try to open participants panel for completeness
                    panel_btn = page.locator('button[jsname="Szv8ic"], [aria-label="Show everyone"], button[aria-label*="everyone"]')
                    if await panel_btn.is_visible(timeout=3000):
                        await panel_btn.click()
                        await asyncio.sleep(1)
                        
                        items = await page.query_selector_all('[role="list"] [role="listitem"]')
                        if not items:
                            items = await page.query_selector_all('[role="listitem"]')
                            
                        for item in items:
                            name_el = await item.query_selector('[data-self-name], [aria-label]')
                            if name_el:
                                label = await name_el.get_attribute('aria-label')
                                if label:
                                    name = label.strip()
                                else:
                                    name = await name_el.inner_text()
                                
                                if name and '\n' in name:
                                    name = name.split('\n')[0]
                                    
                                if name and name.strip():
                                    participants.append(name.strip().replace(" (You)", ""))
                                    
                    # Deduplicate names
                    participants = list(set(participants))
                    
                    if participants:
                        logger.info(f"Initial guest sync: {participants}")
                        print(json.dumps({
                            "type": "participant_sync",
                            "timestamp": time.time(),
                            "participants": participants
                        }), flush=True)
                    else:
                        logger.info("Initial guest sync: found 0 participants")
                except Exception as e:
                    logger.debug(f"Initial sync failed: {e}")

                last_speakers = set()
                consecutive_missing_meeting = 0
                loop_count = 0
                consecutive_silent_loops = 0
                
                while not shutdown_requested.is_set():
                    await asyncio.sleep(1)
                    
                    left_meeting = await page.get_by_text("You left the meeting").is_visible(timeout=200)
                    home_btn = await page.get_by_role("button", name="Return to home screen").is_visible(timeout=200)
                    
                    if left_meeting or home_btn:
                        consecutive_missing_meeting += 1
                        if consecutive_missing_meeting >= 3:
                            logger.info("Meeting ended or assistant removed (detected end screen).")
                            break
                    else:
                        consecutive_missing_meeting = 0

                    try:
                        # 1. Enable Captions (Direct Click + Shortcut fallback)
                        if loop_count == 5:
                            try:
                                cc_btn = page.locator('button[jsname="r6nke"], button[aria-label*="captions"]')
                                if await cc_btn.is_visible(timeout=500):
                                    is_on = await cc_btn.get_attribute("aria-pressed")
                                    if is_on != "true":
                                        await cc_btn.click()
                                        logger.info("Clicked CC button to enable captions.")
                                    else:
                                        logger.info("Captions already enabled.")
                                else:
                                    await page.keyboard.press("c")
                                    logger.info("Sent 'c' to enable captions (button not found).")
                            except:
                                await page.keyboard.press("c")

                        # 2. Periodically ensure participants panel is open (Secondary)
                        if loop_count % 15 == 0:
                            try:
                                panel_btn = page.locator('button[jsname="Szv8ic"], [aria-label="Show everyone"]')
                                if await panel_btn.is_visible(timeout=200):
                                    if await panel_btn.get_attribute("aria-pressed") != "true":
                                        await panel_btn.click()
                            except:
                                pass

                        current_speakers = []
                        
                        # Strategy A: Aria-label parsing (most stable production method)
                        speakers = await page.query_selector_all('[aria-label*="is speaking"]')
                        for el in speakers:
                            label = await el.get_attribute('aria-label')
                            if label:
                                # Parse "Amit is speaking" -> "Amit"
                                name = label.split(' is speaking')[0].strip()
                                if name and "presenting" not in name.lower() and name != "Someone":
                                    current_speakers.append(name.replace(" (You)", ""))
                        
                        # Strategy B: Active tile highlight fallback (visual state)
                        if not current_speakers:
                            tiles = await page.query_selector_all('[data-participant-id]')
                            for tile in tiles:
                                is_active = await tile.evaluate('''el => {
                                    // Strategy 1: Check the Active Speaker Pulse Ring
                                    // Google Meet scales this ring using font-size mapping to audio volume.
                                    const ring = el.querySelector('[jsname="YQuObe"]');
                                    if (ring && ring.style.fontSize) {
                                        const volume = parseFloat(ring.style.fontSize);
                                        // > 1.0em indicates actual speaking volume. < 1.0em is background noise / muted baseline.
                                        if (volume > 1.0) return true;
                                    }
                                    
                                    // Strategy 2: Check the Equalizer Bars
                                    // The three vertical dots bounce when someone is speaking.
                                    const eq = el.querySelector('[jsname="QgSmzd"]');
                                    if (eq) {
                                        const bars = eq.querySelectorAll('div');
                                        if (bars.length === 3) {
                                            for (let bar of bars) {
                                                const h = window.getComputedStyle(bar).height;
                                                if (h && parseFloat(h) > 6) return true; // Animating taller than baseline dot
                                            }
                                        }
                                    }

                                    return false;
                                }''')
                                if is_active:
                                    name = await tile.evaluate('''el => {
                                        const selfName = el.querySelector('[data-self-name]');
                                        if (selfName) return selfName.innerText;
                                        
                                        const noTranslates = Array.from(el.querySelectorAll('.notranslate')).filter(n => {
                                            const text = n.innerText || '';
                                            if (n.className.includes('icon') || text.includes('_') || text.includes('more_vert')) return false;
                                            return text.length > 2;
                                        });
                                        if (noTranslates.length > 0) return noTranslates[0].innerText;
                                        
                                        const nameTags = Array.from(el.querySelectorAll('div, span')).filter(n => {
                                            const text = n.innerText || '';
                                            if (text.includes('more_vert') || text.includes('More options') || text.includes('Others might still see')) return false;
                                            return text.length > 2 && text.length < 50 && !text.includes('\\n');
                                        });
                                        nameTags.sort((a, b) => (b.innerText || '').length - (a.innerText || '').length);
                                        return nameTags.length > 0 ? nameTags[0].innerText : '';
                                    }''')
                                    if name and "presenting" not in name.lower():
                                        current_speakers.append(name.strip().replace(" (You)", ""))
                        
                        # Strategy C: Closed Captions
                        if not current_speakers:
                            caption_containers = await page.query_selector_all('div[aria-live="polite"]')
                            for container in caption_containers:
                                names = await container.query_selector_all("img[alt], [jsname='Z39Y8'], b, strong, .KTvD9, .jmS74c")
                                for n_el in names:
                                    alt = await n_el.get_attribute("alt")
                                    name = alt if alt else await n_el.inner_text()
                                    if name and 1 < len(name.strip()) < 50:
                                        current_speakers.append(name.strip().replace(" (You)", ""))


                        speaker_set = set(current_speakers)
                        if speaker_set != last_speakers:
                            logger.info(f"Speaking Activity: {list(speaker_set)}")
                            print(json.dumps({
                                "type": "speaking_event",
                                "timestamp": time.time(),
                                "active_speakers": list(speaker_set)
                            }), flush=True)
                            last_speakers = speaker_set
                            consecutive_silent_loops = 0
                        else:
                            consecutive_silent_loops += 1

                        if consecutive_silent_loops >= 40:
                            await page.screenshot(path="backend/automation/debug_meeting.png")
                            html_content = await page.content()
                            with open("backend/automation/debug_meeting.html", "w") as f:
                                f.write(html_content)
                            consecutive_silent_loops = 0

                    except Exception as e:
                        logger.debug(f"Scraper error: {e}")
                        continue
                    finally:
                        loop_count += 1

            if shutdown_requested.is_set() and joined:
                logger.info("Attempting to leave call gracefully...")
                try:
                    # Look for the leave call button
                    leave_btn = page.get_by_role("button", name=re.compile(r"Leave call", re.IGNORECASE))
                    if await leave_btn.is_visible(timeout=2000):
                        await leave_btn.click()
                        logger.info("Clicked 'Leave call' button.")
                        # Check for the secondary "Leave meeting" confirmation if it appears
                        confirm_btn = page.get_by_role("button", name=re.compile(r"Leave meeting", re.IGNORECASE))
                        if await confirm_btn.is_visible(timeout=1000):
                            await confirm_btn.click()
                            logger.info("Clicked secondary 'Leave meeting' confirmation.")
                        await asyncio.sleep(1) # Give it a moment to process
                except Exception as e:
                    logger.warning(f"Failed to leave call gracefully: {e}")

    except Exception as e:
        logger.error(f"Unexpected error in bot execution: {e}", exc_info=True)
    finally:
        if context:
            logger.info("Closing browser...")
            try:
                await context.close()
            except Exception as e:
                pass
        
        # Ensure stdin task is cancelled if still running
        if not stdin_task.done():
            stdin_task.cancel()



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
