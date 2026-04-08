#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys


def list_macos_video_devices() -> list[tuple[int, str]]:
    result = subprocess.run(
        ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True,
        text=True,
        check=False,
    )
    output = "\n".join([result.stdout, result.stderr])

    devices: list[tuple[int, str]] = []
    in_video_section = False
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if "AVFoundation video devices" in line:
            in_video_section = True
            continue
        if "AVFoundation audio devices" in line:
            in_video_section = False
            continue
        if not in_video_section:
            continue

        match = re.search(r"\[(\d+)\]\s+(.+)$", line)
        if match:
            devices.append((int(match.group(1)), match.group(2).strip()))

    return devices


def main() -> int:
    if sys.platform != "darwin":
        print("Video device listing is currently only implemented for macOS (avfoundation).")
        return 0

    devices = list_macos_video_devices()
    if not devices:
        print("No AVFoundation video devices found. Verify ffmpeg is installed.")
        return 1

    print("Detected AVFoundation video devices:")
    for index, name in devices:
        marker = " (recommended)" if "capture screen" in name.lower() else ""
        print(f"  [{index}] {name}{marker}")

    print("\nSet VIDEO_SCREEN_INDEX in .env to one of the screen capture indexes above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
