from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4


CaptureMode = Literal["private", "assistant"]
SourcePlatform = Literal["local", "google_meet", "zoom", "teams", "other"]
AssistantJoinStatus = Literal["not_requested", "pending", "joined", "unsupported", "failed"]
ConsentStatus = Literal["not_needed", "required", "pending", "granted", "denied", "unknown"]


@dataclass(frozen=True)
class AssistantJoinRequest:
    meeting_id: str
    title: str
    meeting_url: str
    source_platform: SourcePlatform
    assistant_visible_name: str


@dataclass(frozen=True)
class AssistantSession:
    join_status: AssistantJoinStatus
    source_platform: SourcePlatform
    consent_status: ConsentStatus
    provider_session_id: str | None = None
    provider_metadata: dict[str, object] | None = None
    message: str | None = None


class MeetingLinkLauncher:
    def launch(
        self,
        meeting_url: str,
        source_platform: SourcePlatform = "other",
        assistant_visible_name: str = "Parrot Script Assistant",
    ) -> str:
        """Launch meeting URL and return the launch strategy label."""
        if source_platform == "google_meet":
            strategy = self._launch_google_meet_guest_window(meeting_url)
            if strategy is not None:
                return strategy

        if sys.platform == "darwin":
            subprocess.run(["open", meeting_url], check=True, timeout=10)
            return "default_browser_open"

        if sys.platform == "win32":
            os.startfile(meeting_url)  # type: ignore[attr-defined]
            return "default_browser_open"

        subprocess.run(["xdg-open", meeting_url], check=True, timeout=10)
        return "default_browser_open"

    def _launch_google_meet_guest_window(self, meeting_url: str) -> str | None:
        candidates: list[tuple[str, list[str]]]
        if sys.platform == "darwin":
            candidates = [
                (
                    "chrome_guest_window",
                    ["open", "-na", "Google Chrome", "--args", "--new-window", "--guest", meeting_url],
                ),
                (
                    "chrome_incognito_window",
                    ["open", "-na", "Google Chrome", "--args", "--new-window", "--incognito", meeting_url],
                ),
                (
                    "chromium_incognito_window",
                    ["open", "-na", "Chromium", "--args", "--new-window", "--incognito", meeting_url],
                ),
                (
                    "edge_inprivate_window",
                    ["open", "-na", "Microsoft Edge", "--args", "--new-window", "--inprivate", meeting_url],
                ),
            ]
        elif sys.platform == "win32":
            candidates = [
                ("chrome_guest_window", ["chrome", "--new-window", "--guest", meeting_url]),
                ("chrome_incognito_window", ["chrome", "--new-window", "--incognito", meeting_url]),
                ("edge_inprivate_window", ["msedge", "--new-window", "--inprivate", meeting_url]),
            ]
        else:
            candidates = [
                ("chrome_guest_window", ["google-chrome", "--new-window", "--guest", meeting_url]),
                ("chrome_incognito_window", ["google-chrome", "--new-window", "--incognito", meeting_url]),
                ("chromium_incognito_window", ["chromium", "--new-window", "--incognito", meeting_url]),
                ("edge_inprivate_window", ["microsoft-edge", "--new-window", "--inprivate", meeting_url]),
            ]

        for strategy, cmd in candidates:
            try:
                subprocess.run(cmd, check=True, timeout=10)
                return strategy
            except (FileNotFoundError, OSError, subprocess.SubprocessError):
                continue
        return None

    def describe(self) -> str:
        if sys.platform == "darwin":
            return "open"
        if sys.platform == "win32":
            return "os.startfile"
        return "xdg-open"


class StubMeetingAssistantProvider:
    async def request_join(self, request: AssistantJoinRequest) -> AssistantSession:
        return AssistantSession(
            join_status="unsupported",
            source_platform=request.source_platform,
            consent_status="required",
            provider_metadata={
                "meeting_url": request.meeting_url,
                "assistant_visible_name": request.assistant_visible_name,
                "reason": "No meeting assistant provider is configured yet.",
            },
            message=(
                "Assistant mode settings were saved, but no meeting provider is configured yet. "
                "Private mode remains fully functional on-device."
            ),
        )


class LocalMeetingAssistantProvider:
    def __init__(self, launcher: MeetingLinkLauncher | None = None):
        self.launcher = launcher or MeetingLinkLauncher()

    async def request_join(self, request: AssistantJoinRequest) -> AssistantSession:
        try:
            launch_strategy = await asyncio.to_thread(
                self.launcher.launch,
                request.meeting_url,
                request.source_platform,
                request.assistant_visible_name,
            )
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            return AssistantSession(
                join_status="failed",
                source_platform=request.source_platform,
                consent_status="unknown",
                provider_metadata={
                    "meeting_url": request.meeting_url,
                    "assistant_visible_name": request.assistant_visible_name,
                    "launch_strategy": "local_link_launch_failed",
                    "launched_via": self.launcher.describe(),
                    "reason": str(exc),
                },
                message=(
                    f"Could not open the {platform_label(request.source_platform)} link on this device. "
                    "Check that the meeting app or a default browser is available."
                ),
            )

        manual_steps = launch_manual_steps(
            request.source_platform,
            request.assistant_visible_name,
            launch_strategy,
        )
        display_name_note = display_name_note_for(request.source_platform, request.assistant_visible_name)
        return AssistantSession(
            join_status="pending",
            source_platform=request.source_platform,
            consent_status="required",
            provider_session_id=str(uuid4()),
            provider_metadata={
                "meeting_url": request.meeting_url,
                "assistant_visible_name": request.assistant_visible_name,
                "launch_strategy": launch_strategy,
                "launched_via": self.launcher.describe(),
                "manual_steps": manual_steps,
                "speaker_identity_level": "heuristic",
                "speaker_identity_reason": (
                    "Assistant mode currently transcribes one mixed local audio stream. "
                    "Participant-aware/stream-aware provider mapping is not connected yet."
                ),
                "capture_topology": "local_mixed_audio",
                "display_name_note": display_name_note,
            },
            message=build_launch_message(
                source_platform=request.source_platform,
                manual_steps=manual_steps,
                display_name_note=display_name_note,
            ),
        )


def resolve_capture_mode(
    capture_mode: str | None,
    ghost_mode: bool | None,
) -> tuple[CaptureMode, bool]:
    if capture_mode == "assistant":
        return "assistant", False
    if capture_mode == "private":
        return "private", True
    if ghost_mode is False:
        return "assistant", False
    return "private", True


def infer_source_platform(meeting_url: str | None) -> SourcePlatform | None:
    if not meeting_url:
        return None

    hostname = (urlparse(meeting_url).hostname or "").lower()
    if not hostname:
        return None
    if "meet.google." in hostname:
        return "google_meet"
    if "zoom." in hostname:
        return "zoom"
    if "teams." in hostname or "teams.microsoft." in hostname:
        return "teams"
    return "other"


def serialize_provider_metadata(value: dict[str, object] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def platform_label(source_platform: SourcePlatform) -> str:
    if source_platform == "google_meet":
        return "Google Meet"
    if source_platform == "zoom":
        return "Zoom"
    if source_platform == "teams":
        return "Microsoft Teams"
    return "meeting"


def launch_manual_steps(
    source_platform: SourcePlatform,
    assistant_visible_name: str | None = None,
    launch_strategy: str | None = None,
) -> list[str]:
    if source_platform == "google_meet":
        guest_hint = (
            "A guest/private browser window was opened for Meet."
            if launch_strategy and ("guest" in launch_strategy or "incognito" in launch_strategy or "inprivate" in launch_strategy)
            else "The meeting link was opened in your browser."
        )
        name = assistant_visible_name or "Parrot Script Assistant"
        return [
            guest_hint,
            f'If prompted for a guest name, enter "{name}" and click "Ask to join".',
            'If you are already signed in, click "Join now" to enter as that account.',
            "Ensure meeting output is routed to your configured capture device so transcript audio is recorded.",
        ]
    if source_platform == "zoom":
        return [
            "The invite link was opened on this device.",
            "Allow Zoom Workplace to open, or choose Join from browser if the host allows it.",
            "Complete the Zoom join prompt to enter the meeting.",
        ]
    if source_platform == "teams":
        return [
            "The meeting link was opened on this device.",
            "Choose Teams desktop or web when prompted.",
            "Complete the Teams join prompt to enter the meeting.",
        ]
    return [
        "The meeting link was opened on this device.",
        "Finish the provider join prompt in the opened app or browser window.",
    ]


def display_name_note_for(source_platform: SourcePlatform, assistant_visible_name: str) -> str:
    if source_platform == "google_meet":
        return (
            f'Google Meet may use your signed-in Google account or a guest join prompt instead of "{assistant_visible_name}".'
        )
    if source_platform == "zoom":
        return (
            f'Zoom may ask you to confirm or edit the visible name before joining. Requested name: "{assistant_visible_name}".'
        )
    if source_platform == "teams":
        return (
            f'Teams may let you edit the display name during join. Requested name: "{assistant_visible_name}".'
        )
    return f'The provider controls the visible display name. Requested name: "{assistant_visible_name}".'


def build_launch_message(
    *,
    source_platform: SourcePlatform,
    manual_steps: list[str],
    display_name_note: str,
) -> str:
    joined_platform = platform_label(source_platform)
    steps = " ".join(manual_steps)
    return (
        f"{joined_platform} was opened on this device and live capture has started. "
        f"{steps} {display_name_note} "
        "Parrot Script will keep transcribing local system audio while the meeting is live."
    )
