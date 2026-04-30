from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from backend.storage.repositories.meetings import MeetingsRepository


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
        meeting_id: str,
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


class AutomatedMeetingLinkLauncher(MeetingLinkLauncher):
    def __init__(self, venv_python: str = "./.venv/bin/python"):
        self.venv_python = venv_python
        self.bot_script = os.path.join(os.path.dirname(__file__), "automation", "assistant_bot.py")
        self._active_bots: dict[str, subprocess.Popen] = {}
        self._bot_speaking_state: dict[str, dict[str, float]] = {} # meeting_id -> {name: last_start_time}
        self._bot_speaking_events: dict[str, list[dict]] = {} # meeting_id -> list of finalized events
        self._recompute_tasks: dict[str, asyncio.Task] = {} # meeting_id -> periodic recompute task
        self.meetings_repo = MeetingsRepository()

    def launch(
        self,
        meeting_id: str,
        meeting_url: str,
        source_platform: SourcePlatform = "other",
        assistant_visible_name: str = "Parrot Script Assistant",
        loop: asyncio.AbstractEventLoop | None = None
    ) -> str:
        if source_platform == "google_meet" and os.path.exists(self.bot_script):
            profile_dir = os.path.join(os.path.dirname(self.bot_script), ".bot_profile")
            if not os.path.exists(profile_dir):
                import logging
                logger = logging.getLogger(__name__)
                logger.warning("Bot profile missing. Please run backend/automation/setup_bot_profile.py. Falling back to OS browser.")
            else:
                try:
                    import logging
                    logger = logging.getLogger(__name__)
                    # Launch the bot script in the background using the venv
                    cmd = [
                        self.venv_python,
                        self.bot_script,
                        "--url", meeting_url,
                        "--name", assistant_visible_name,
                        "--headed"
                    ]
                    bot_log = os.path.join(os.path.dirname(self.bot_script), "bot.log")
                    logger.info("Launching automated assistant bot for meeting %s: %s", meeting_id, " ".join(cmd))
                    
                    # We use a subprocess and read its stdout in a separate thread
                    proc = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        start_new_session=True
                    )
                    self._active_bots[meeting_id] = proc
                    
                    # Start background thread to parse bot output
                    import threading
                    thread = threading.Thread(
                        target=self._read_bot_output,
                        args=(meeting_id, proc, bot_log, loop),
                        daemon=True
                    )
                    thread.start()

                    return "playwright_automated_join"
                except Exception as exc:
                    logger.warning("Automated join failed, falling back to browser open: %s", exc)
        
        return super().launch(meeting_id, meeting_url, source_platform, assistant_visible_name)

    def _read_bot_output(self, meeting_id: str, proc: subprocess.Popen, log_path: str, loop: asyncio.AbstractEventLoop | None = None):
        from backend.native.service import NativeAttributionService
        native_service = NativeAttributionService()
        
        with open(log_path, "a") as log_file:
            log_file.write(f"\n--- Bot Started for {meeting_id} ---\n")
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                
                log_file.write(line)
                log_file.flush()

                if line.startswith("{"):
                    try:
                        data = json.loads(line)
                        if data.get("type") == "participant_sync":
                            participants = [{"external_id": name, "display_name": name} for name in data.get("participants", [])]
                            if participants:
                                logger.info(f"Syncing initial guest list for {meeting_id}: {len(participants)} names")
                                if loop:
                                    asyncio.run_coroutine_threadsafe(native_service.sync_participants(meeting_id, participants), loop).result()
                                    asyncio.run_coroutine_threadsafe(native_service.recompute_attribution(meeting_id), loop).result()
                                else:
                                    asyncio.run(native_service.sync_participants(meeting_id, participants))
                                    asyncio.run(native_service.recompute_attribution(meeting_id))
                            continue

                        if data.get("type") == "speaking_event":
                            active_speakers = data.get("active_speakers", [])
                            abs_time = float(data.get("timestamp", time.time()))
                            
                            # Fetch meeting to get start time for relative offset
                            if loop:
                                future = asyncio.run_coroutine_threadsafe(self.meetings_repo.get(meeting_id), loop)
                                meeting = future.result()
                            else:
                                meeting = asyncio.run(self.meetings_repo.get(meeting_id))
                                
                            if not meeting:
                                continue
                            
                            # Calculate relative time (segments start at 0.0 relative to audio_start_timestamp)
                            meeting_start_ts = meeting.get("audio_start_timestamp") or meeting.get("created_at_ts") or time.time()
                            rel_time = max(0.0, abs_time - meeting_start_ts)

                            # Update state
                            current_state = self._bot_speaking_state.setdefault(meeting_id, {})
                            all_events = self._bot_speaking_events.setdefault(meeting_id, [])
                            
                            active_set = set(active_speakers)
                            prev_set = set(current_state.keys())

                            # People who just started talking
                            for name in active_set - prev_set:
                                current_state[name] = rel_time
                            
                            # People who just stopped talking
                            for name in prev_set - active_set:
                                start_t = current_state.pop(name)
                                all_events.append({
                                    "participant_external_id": name,
                                    "start_time": start_t,
                                    "end_time": rel_time,
                                    "confidence": 1.0
                                })

                            # Sync participants immediately so we have the IDs
                            participants = [{"external_id": name, "display_name": name} for name in active_speakers]
                            if participants:
                                if loop:
                                    asyncio.run_coroutine_threadsafe(native_service.sync_participants(meeting_id, participants), loop).result()
                                else:
                                    asyncio.run(native_service.sync_participants(meeting_id, participants))
                            
                            # Periodically sync all speaking events and recompute
                            # (We use all_events + currently active ones extended to rel_time)
                            # Sync if someone started/stopped talking, OR periodically for long continuous speakers
                            state_changed = bool(active_set != prev_set)
                            if state_changed or len(all_events) % 5 == 0:
                                live_events = list(all_events)
                                for name, start_t in current_state.items():
                                    live_events.append({
                                        "participant_external_id": name,
                                        "start_time": start_t,
                                        "end_time": rel_time + 1.0, # Pad slightly for live
                                        "confidence": 1.0
                                    })
                                
                                if live_events:
                                if live_events:
                                    if loop:
                                        asyncio.run_coroutine_threadsafe(native_service.sync_speaking_events(meeting_id, live_events, "bot_scraper"), loop).result()
                                        res = asyncio.run_coroutine_threadsafe(native_service.recompute_attribution(meeting_id), loop).result()
                                    else:
                                        asyncio.run(native_service.sync_speaking_events(meeting_id, live_events, "bot_scraper"))
                                        res = asyncio.run(native_service.recompute_attribution(meeting_id))
                                        


                                    # Start periodic recompute so new segments get attributed as Whisper produces them
                                    if loop and meeting_id not in self._recompute_tasks:
                                        async def _periodic_recompute(mid: str, svc):
                                            try:
                                                while mid in self._active_bots:
                                                    await asyncio.sleep(5)
                                                    r = await svc.recompute_attribution(mid)
                                                    if r["segments_mapped"] > 0:

                                            except asyncio.CancelledError:
                                                pass
                                            except Exception as exc:
                                                logger.error(f"Periodic recompute error for {mid}: {exc}")
                                        task = asyncio.run_coroutine_threadsafe(
                                            _periodic_recompute(meeting_id, native_service), loop
                                        )
                                        self._recompute_tasks[meeting_id] = task
                                    
                    except Exception as e:
                        import traceback
                        logger.error("Error parsing bot speaking event: %s\n%s", e, traceback.format_exc())
                        continue

        # Finalize any ongoing speaking state when the bot exits
        try:
            current_state = self._bot_speaking_state.get(meeting_id, {})
            all_events = self._bot_speaking_events.get(meeting_id, [])
            if current_state:
                # Get the meeting's end time for the final event boundary
                final_time = time.time()
                if loop:
                    meeting = asyncio.run_coroutine_threadsafe(self.meetings_repo.get(meeting_id), loop).result()
                else:
                    meeting = asyncio.run(self.meetings_repo.get(meeting_id))
                if meeting:
                    meeting_start_ts = meeting.get("created_at_ts") or final_time
                    rel_end = max(0.0, final_time - meeting_start_ts)
                    for name, start_t in current_state.items():
                        all_events.append({
                            "participant_external_id": name,
                            "start_time": start_t,
                            "end_time": rel_end,
                            "confidence": 1.0
                        })

            if all_events and loop:
                from backend.native.service import NativeAttributionService
                native_service = NativeAttributionService()
                participants = [{"external_id": ev["participant_external_id"], "display_name": ev["participant_external_id"]} for ev in all_events]
                asyncio.run_coroutine_threadsafe(native_service.sync_participants(meeting_id, participants), loop).result()
                asyncio.run_coroutine_threadsafe(native_service.sync_speaking_events(meeting_id, all_events, "bot_scraper"), loop).result()
                res = asyncio.run_coroutine_threadsafe(native_service.recompute_attribution(meeting_id), loop).result()

        except Exception as e:
            logger.error("Error finalizing speaking events for %s: %s", meeting_id, e)

        # Cleanup
        # Cancel periodic recompute first (it checks self._active_bots to stop)
        task = self._recompute_tasks.pop(meeting_id, None)
        if task:
            task.cancel()
        self._bot_speaking_state.pop(meeting_id, None)
        self._bot_speaking_events.pop(meeting_id, None)
        proc.wait()
        self._active_bots.pop(meeting_id, None)

    def stop(self, meeting_id: str):
        proc = self._active_bots.pop(meeting_id, None)
        if proc and proc.poll() is None:
            logger.info("Stopping automated assistant bot for meeting %s", meeting_id)
            try:
                # Try graceful shutdown first by sending QUIT to stdin
                if proc.stdin:
                    proc.stdin.write("QUIT\n")
                    proc.stdin.flush()
                
                # Wait a bit for it to process the leave
                proc.wait(timeout=3)
            except (subprocess.TimeoutExpired, BrokenPipeError, OSError):
                # Fall back to termination if it's stuck
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()

    def describe(self) -> str:
        return "playwright_automation"


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
        self.launcher = launcher or AutomatedMeetingLinkLauncher()

    async def request_stop(self, meeting_id: str):
        if hasattr(self.launcher, "stop"):
            await asyncio.to_thread(self.launcher.stop, meeting_id)

    async def request_join(self, request: AssistantJoinRequest) -> AssistantSession:
        loop = asyncio.get_running_loop()
        try:
            launch_strategy = await asyncio.to_thread(
                self.launcher.launch,
                request.meeting_id,
                request.meeting_url,
                request.source_platform,
                request.assistant_visible_name,
                loop
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
