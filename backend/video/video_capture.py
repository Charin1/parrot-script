from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

from backend.config import settings

logger = logging.getLogger(__name__)


class ScreenCapture:
    """FFmpeg-based screen recorder that writes to an MP4 file.

    Runs as a standalone subprocess alongside (not replacing) the existing
    AudioCapture pipeline.  The audio pipeline is completely unaffected —
    this class only writes video to disk.
    """

    def __init__(
        self,
        meeting_id: str,
        resolution: str | None = None,
        framerate: int | None = None,
        ghost_mode: bool = True,
        target_window_title: str | None = None,
    ):
        self.meeting_id = meeting_id
        self.resolution = resolution or settings.video_default_resolution
        self.framerate = framerate or settings.video_framerate
        self.ghost_mode = ghost_mode
        self.target_window_title = target_window_title

        self._output_path = Path(settings.db_path).parent / f"{meeting_id}.mp4"
        self._process: Optional[subprocess.Popen] = None
        self._stderr_thread_handle: Optional[threading.Thread] = None
        self._running = False
        self._selected_screen_index: Optional[int] = None

    @property
    def output_path(self) -> Path:
        return self._output_path

    async def start(self) -> None:
        if self._running:
            return

        self._output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = self._build_ffmpeg_cmd()
        logger.info("Starting screen capture: %s", " ".join(cmd))

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        # Fast-fail if ffmpeg exits immediately (common on macOS permission/device errors).
        await asyncio.sleep(0.6)
        if self._process.poll() is not None:
            stderr_output = ""
            if self._process.stderr is not None:
                try:
                    stderr_output = self._process.stderr.read().decode(errors="replace")
                except Exception:
                    stderr_output = ""
            exit_code = self._process.returncode
            self._process = None
            self._running = False
            raise RuntimeError(self._format_start_error(exit_code, stderr_output))

        self._running = True

        if self._process.stderr is not None:
            self._stderr_thread_handle = threading.Thread(
                target=self._stderr_thread, daemon=True
            )
            self._stderr_thread_handle.start()

    async def stop(self) -> None:
        self._running = False

        if self._process is not None:
            try:
                # Send 'q' to FFmpeg stdin for graceful shutdown so
                # the MP4 container is finalised properly.
                if self._process.stdin is not None:
                    try:
                        self._process.stdin.write(b"q")
                        self._process.stdin.flush()
                    except (BrokenPipeError, OSError):
                        pass

                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.terminate()
                try:
                    self._process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._process.kill()
            finally:
                self._process = None

        if self._stderr_thread_handle is not None and self._stderr_thread_handle.is_alive():
            self._stderr_thread_handle.join(timeout=1.0)

        if self._output_path.exists():
            size = self._output_path.stat().st_size
            logger.info(
                "Screen capture stopped. File: %s (%d bytes, %.1f MB)",
                self._output_path,
                size,
                size / (1024 * 1024),
            )
        else:
            logger.warning("Screen capture file not found after stop: %s", self._output_path)

    def _build_ffmpeg_cmd(self) -> list[str]:
        width, height = self._parse_resolution()

        if sys.platform == "darwin":
            return self._cmd_macos(width, height)
        elif sys.platform == "win32":
            return self._cmd_windows(width, height)
        else:
            return self._cmd_linux(width, height)

    def _parse_resolution(self) -> tuple[int, int]:
        try:
            w, h = self.resolution.split("x")
            return int(w), int(h)
        except (ValueError, AttributeError):
            return 1280, 720

    # ------------------------------------------------------------------
    # macOS — avfoundation
    # ------------------------------------------------------------------
    def _cmd_macos(self, width: int, height: int) -> list[str]:
        screen_idx = self._resolve_macos_screen_index()
        self._selected_screen_index = screen_idx
        logger.info("Using macOS AVFoundation screen device index: %s", screen_idx)
        return [
            "ffmpeg",
            "-y",
            "-f", "avfoundation",
            "-framerate", str(self.framerate),
            "-i", f"{screen_idx}:none",
            "-vf", f"scale={width}:{height}",
            "-c:v", settings.video_codec,
            "-preset", "ultrafast",
            "-crf", str(settings.video_crf),
            "-pix_fmt", "yuv420p",
            "-an",
            str(self._output_path),
        ]

    def _list_macos_video_devices(self) -> list[tuple[int, str]]:
        try:
            result = subprocess.run(
                ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:  # pragma: no cover - defensive; ffmpeg may be missing at runtime
            logger.warning("Unable to list macOS AVFoundation devices: %s", exc)
            return []

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
            if not match:
                continue
            devices.append((int(match.group(1)), match.group(2).strip()))

        return devices

    def _resolve_macos_screen_index(self) -> int:
        configured_index = settings.video_screen_index
        devices = self._list_macos_video_devices()
        if not devices:
            logger.warning(
                "Could not enumerate macOS AVFoundation video devices; falling back to VIDEO_SCREEN_INDEX=%s",
                configured_index,
            )
            return configured_index

        screen_devices = [
            (idx, name) for idx, name in devices if "capture screen" in name.lower()
        ]
        if screen_devices:
            if any(idx == configured_index for idx, _ in screen_devices):
                return configured_index
            resolved_idx, resolved_name = screen_devices[0]
            logger.warning(
                "VIDEO_SCREEN_INDEX=%s is not a screen device. Auto-selecting %s (%s).",
                configured_index,
                resolved_idx,
                resolved_name,
            )
            return resolved_idx

        if any(idx == configured_index for idx, _ in devices):
            logger.warning(
                "No explicit 'Capture screen' AVFoundation entry found. Using configured VIDEO_SCREEN_INDEX=%s.",
                configured_index,
            )
            return configured_index

        first_idx, first_name = devices[0]
        logger.warning(
            "VIDEO_SCREEN_INDEX=%s not found. Falling back to first AVFoundation video device %s (%s).",
            configured_index,
            first_idx,
            first_name,
        )
        return first_idx

    # ------------------------------------------------------------------
    # Linux — x11grab (stub: captures full screen)
    # ------------------------------------------------------------------
    def _cmd_linux(self, width: int, height: int) -> list[str]:
        return [
            "ffmpeg",
            "-y",
            "-f", "x11grab",
            "-framerate", str(self.framerate),
            "-video_size", f"{width}x{height}",
            "-i", ":0.0",
            "-c:v", settings.video_codec,
            "-preset", "ultrafast",
            "-crf", str(settings.video_crf),
            "-pix_fmt", "yuv420p",
            "-an",
            str(self._output_path),
        ]

    # ------------------------------------------------------------------
    # Windows — gdigrab (stub: captures full desktop)
    # ------------------------------------------------------------------
    def _cmd_windows(self, width: int, height: int) -> list[str]:
        return [
            "ffmpeg",
            "-y",
            "-f", "gdigrab",
            "-framerate", str(self.framerate),
            "-i", "desktop",
            "-vf", f"scale={width}:{height}",
            "-c:v", settings.video_codec,
            "-preset", "ultrafast",
            "-crf", str(settings.video_crf),
            "-pix_fmt", "yuv420p",
            "-an",
            str(self._output_path),
        ]

    def _stderr_thread(self) -> None:
        assert self._process is not None
        assert self._process.stderr is not None

        while self._running:
            line = self._process.stderr.readline()
            if not line:
                break
            logger.debug("ffmpeg-video: %s", line.decode(errors="replace").strip())

    def _format_start_error(self, exit_code: int | None, stderr_output: str) -> str:
        stderr_lower = stderr_output.lower()
        tail_lines = [line.strip() for line in stderr_output.strip().splitlines() if line.strip()]
        tail = " | ".join(tail_lines[-6:]) if tail_lines else "No ffmpeg stderr output."

        if sys.platform == "darwin":
            if (
                "not authorized to capture screen" in stderr_lower
                or "screen recording" in stderr_lower
                or "not permitted" in stderr_lower
            ):
                return (
                    "macOS blocked screen capture. Enable Screen Recording for the app that runs this backend "
                    "(Terminal/iTerm/Python) in System Settings > Privacy & Security > Screen Recording, then restart it. "
                    f"ffmpeg exit={exit_code}. Details: {tail}"
                )
            if (
                "no such file or directory" in stderr_lower
                or "input/output error" in stderr_lower
                or "cannot open input device" in stderr_lower
                or "device not found" in stderr_lower
            ):
                selected = self._selected_screen_index
                selected_hint = (
                    f"Resolved screen index was {selected}. " if selected is not None else ""
                )
                return (
                    "Unable to open the macOS AVFoundation screen input. "
                    f"{selected_hint}Try setting VIDEO_SCREEN_INDEX to the correct screen device index. "
                    f"ffmpeg exit={exit_code}. Details: {tail}"
                )

        return f"Screen capture failed to start (ffmpeg exit={exit_code}). Details: {tail}"
