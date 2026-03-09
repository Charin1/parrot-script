from __future__ import annotations

import re
import subprocess
import sys
from typing import Optional


def _ffmpeg_device_output(fmt: str) -> str:
    cmd = ["ffmpeg", "-f", fmt, "-list_devices", "true", "-i", "dummy"]
    if fmt == "avfoundation":
        cmd[-1] = ""
        
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    return "\n".join([result.stdout, result.stderr])


def list_audio_devices() -> list[dict]:
    """
    Run ffmpeg device listing and parse available audio input devices for the current OS.
    Returns list of {"index": int | str, "name": str}.
    """
    devices: list[dict] = []
    
    if sys.platform == "darwin":
        output = _ffmpeg_device_output("avfoundation")
        seen_indexes: set[int] = set()
        in_audio_section = False

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if "AVFoundation audio devices" in line:
                in_audio_section = True
                continue
            if "AVFoundation video devices" in line:
                in_audio_section = False

            if not in_audio_section:
                continue

            match = re.search(r"\[(\d+)\]\s+(.+)$", line)
            if match:
                index = int(match.group(1))
                if index not in seen_indexes:
                    seen_indexes.add(index)
                    devices.append({"index": index, "name": match.group(2).strip()})

    elif sys.platform == "win32":
        output = _ffmpeg_device_output("dshow")
        # Windows dshow output: [dshow @ 00000]  "Microphone Array (Realtek Audio)"
        # Sometimes followed by alternative names.
        for raw_line in output.splitlines():
            if "dshow @" in raw_line and '"' in raw_line:
                # Basic extraction of the string name (dshow uses string queries)
                match = re.search(r'\"([^\"]+)\"', raw_line)
                if match:
                    name = match.group(1)
                    if name not in [d["name"] for d in devices] and "video" not in raw_line.lower():
                        devices.append({"index": f'"{name}"', "name": name})
                        
    else:
        # Linux / PulseAudio - FFmpeg doesn't easily list pulse devices the same way natively.
        # Advise the user to use standard tools.
        print("Linux detected: Please use 'pactl list sources short' or 'arecord -l' to find your audio devices.")
        devices.append({"index": "default", "name": "Default PulseAudio/ALSA input"})

    return devices


def find_blackhole_device() -> Optional[int]:
    """Return the index of the first BlackHole audio device, if present (macOS only)."""
    if sys.platform != "darwin":
        return None
        
    for device in list_audio_devices():
        if "blackhole" in device["name"].lower():
            return int(device["index"])
    return None
