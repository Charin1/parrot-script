from __future__ import annotations

import sys

import pytest

from backend.audio.capture import AudioCapture
from backend.core.exceptions import AudioCaptureError


def test_resolve_device_index_uses_blackhole_fallback(monkeypatch) -> None:
    capture = AudioCapture(device_index=9)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        "backend.audio.devices.list_audio_devices",
        lambda: [
            {"index": 0, "name": "MacBook Pro Microphone"},
            {"index": 2, "name": "BlackHole 2ch"},
        ],
    )
    monkeypatch.setattr("backend.audio.devices.find_blackhole_device", lambda: 2)

    assert capture._resolve_device_index() == 2


def test_resolve_device_index_errors_when_no_macos_devices(monkeypatch) -> None:
    capture = AudioCapture(device_index=0)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr("backend.audio.devices.list_audio_devices", lambda: [])
    monkeypatch.setattr("backend.audio.devices.find_blackhole_device", lambda: None)

    with pytest.raises(AudioCaptureError) as exc_info:
        capture._resolve_device_index()

    assert "no macos avfoundation audio devices" in str(exc_info.value).lower()


def test_format_start_error_for_invalid_macos_device(monkeypatch) -> None:
    capture = AudioCapture(device_index=5)
    capture._resolved_device_index = 2
    monkeypatch.setattr(sys, "platform", "darwin")

    message = capture._format_start_error(1, "Invalid audio device index")

    assert "AUDIO_DEVICE_INDEX" in message
    assert "Resolved index was 2" in message
