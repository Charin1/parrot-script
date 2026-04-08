from __future__ import annotations

from backend.config import settings
from backend.video.video_capture import ScreenCapture


def test_resolve_macos_screen_index_prefers_capture_screen(monkeypatch) -> None:
    capture = ScreenCapture("meeting-1")
    monkeypatch.setattr("backend.video.video_capture.sys.platform", "darwin")
    monkeypatch.setattr(settings, "video_screen_index", 0, raising=False)
    monkeypatch.setattr(
        capture,
        "_list_macos_video_devices",
        lambda: [(0, "FaceTime HD Camera"), (2, "Capture screen 0"), (3, "Capture screen 1")],
    )

    assert capture._resolve_macos_screen_index() == 2


def test_resolve_macos_screen_index_keeps_configured_screen(monkeypatch) -> None:
    capture = ScreenCapture("meeting-2")
    monkeypatch.setattr("backend.video.video_capture.sys.platform", "darwin")
    monkeypatch.setattr(settings, "video_screen_index", 3, raising=False)
    monkeypatch.setattr(
        capture,
        "_list_macos_video_devices",
        lambda: [(0, "FaceTime HD Camera"), (2, "Capture screen 0"), (3, "Capture screen 1")],
    )

    assert capture._resolve_macos_screen_index() == 3


def test_format_start_error_for_macos_permission(monkeypatch) -> None:
    capture = ScreenCapture("meeting-3")
    monkeypatch.setattr("backend.video.video_capture.sys.platform", "darwin")
    message = capture._format_start_error(
        1,
        "avfoundation: not authorized to capture screen. Open System Settings and allow Screen Recording.",
    )

    assert "Screen Recording" in message
    assert "macOS blocked screen capture" in message
