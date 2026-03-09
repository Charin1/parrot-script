#!/usr/bin/env python3
from __future__ import annotations

from backend.audio.devices import find_blackhole_device, list_audio_devices


def main() -> None:
    devices = list_audio_devices()
    if not devices:
        print("No audio devices detected.")
        return

    print("Available audio devices:")
    for device in devices:
        print(f"  [{device['index']}] {device['name']}")

    blackhole = find_blackhole_device()
    if blackhole is None:
        print("\nBlackHole device not found.")
    else:
        print(f"\nBlackHole device index: {blackhole}")


if __name__ == "__main__":
    main()
