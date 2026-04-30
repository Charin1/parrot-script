import asyncio
import logging
from backend.assistants import AutomatedMeetingLinkLauncher
import subprocess
import time

logging.basicConfig(level=logging.INFO)

def test():
    meeting_id = "fee6e2fc-24bf-4307-a22b-2e171b399a42"
    launcher = AutomatedMeetingLinkLauncher()
    main_loop = asyncio.new_event_loop()
    
    # Mock subprocess
    import sys
    proc = subprocess.Popen([sys.executable, "-c", "import time; print('{\"type\": \"speaking_event\", \"timestamp\": 1777514697.0510578, \"active_speakers\": [\"Charin Patel\"]}'); time.sleep(1)"], stdout=subprocess.PIPE)
    
    # Run _read_bot_output
    launcher._read_bot_output(meeting_id, proc, "backend/automation/bot.log", main_loop)

if __name__ == "__main__":
    test()
