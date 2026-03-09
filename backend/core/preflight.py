"""Startup preflight checks.

Validates that all required external dependencies and models are available
before the server accepts traffic. Every check logs its result with a clear
pass/fail indicator so issues are surfaced immediately at boot time.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import time

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

_PASS = "✅"
_FAIL = "❌"
_WARN = "⚠️"


class PreflightResult:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.warnings: list[str] = []
        self.failures: list[str] = []

    @property
    def ok(self) -> bool:
        return len(self.failures) == 0

    def summary_lines(self) -> list[str]:
        lines = [f"  {_PASS} {msg}" for msg in self.passed]
        lines += [f"  {_WARN} {msg}" for msg in self.warnings]
        lines += [f"  {_FAIL} {msg}" for msg in self.failures]
        return lines


def _check_ffmpeg(result: PreflightResult) -> None:
    """Verify FFmpeg is installed and list available audio devices."""
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        result.failures.append("FFmpeg not found on PATH – audio capture will fail")
        return
    result.passed.append(f"FFmpeg found at {ffmpeg_path}")

    try:
        proc = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Device list is printed to stderr by FFmpeg
        device_lines = [
            line
            for line in proc.stderr.splitlines()
            if "AVFoundation" in line and ("audio" in line.lower() or "input" in line.lower())
        ]
        if device_lines:
            result.passed.append(
                f"Audio devices detected ({len(device_lines)} entries). "
                f"Using device index {settings.audio_device_index}"
            )
        else:
            result.warnings.append(
                "No AVFoundation audio devices listed – "
                "check AUDIO_DEVICE_INDEX in .env or grant microphone permission"
            )
    except (subprocess.TimeoutExpired, OSError) as exc:
        result.warnings.append(f"Could not list audio devices: {exc}")


def _check_whisper(result: PreflightResult) -> None:
    """Load the Whisper model to surface download / compatibility errors early."""
    try:
        from faster_whisper import WhisperModel
        import logging

        # Ensure faster_whisper and huggingface_hub print download progress
        logging.getLogger("faster_whisper").setLevel(logging.INFO)

        started = time.perf_counter()
        WhisperModel(
            model_size_or_path=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            local_files_only=False,
        )
        elapsed = time.perf_counter() - started
        result.passed.append(
            f"Whisper model '{settings.whisper_model}' loaded in {elapsed:.1f}s "
            f"(device={settings.whisper_device}, compute={settings.whisper_compute_type})"
        )
    except Exception as exc:
        result.failures.append(f"Whisper model failed to load: {exc}")


def _check_voice_embedder(result: PreflightResult) -> None:
    """Load the resemblyzer VoiceEncoder."""
    try:
        from backend.core.pkg_resources_shim import ensure_pkg_resources
        ensure_pkg_resources()

        from resemblyzer import VoiceEncoder

        started = time.perf_counter()
        VoiceEncoder()
        elapsed = time.perf_counter() - started
        result.passed.append(f"Voice embedder (resemblyzer) loaded in {elapsed:.1f}s")
    except Exception as exc:
        result.failures.append(f"Voice embedder failed to load: {exc}")


async def _check_ollama(result: PreflightResult) -> None:
    """Ping the Ollama API to verify connectivity."""
    base = settings.ollama_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base}/api/tags")
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            model_names = [m.get("name", "?") for m in models]
            if settings.ollama_model in model_names:
                result.passed.append(
                    f"Ollama reachable – model '{settings.ollama_model}' available"
                )
            else:
                result.warnings.append(
                    f"Ollama reachable but model '{settings.ollama_model}' not found. "
                    f"Available: {', '.join(model_names) or 'none'}. "
                    f"Summaries will fail until the model is pulled."
                )
        else:
            result.warnings.append(
                f"Ollama returned HTTP {resp.status_code} – summaries may not work"
            )
    except (httpx.HTTPError, OSError):
        result.warnings.append(
            f"Ollama not reachable at {base} – "
            "live transcription still works but summaries will fail"
        )


async def run_preflight() -> PreflightResult:
    """Execute all preflight checks and return the combined result.

    Heavy model loads (Whisper, resemblyzer) are run in a thread pool so they
    don't block the event loop.
    """
    result = PreflightResult()
    loop = asyncio.get_running_loop()

    logger.info("Running startup preflight checks …")

    # Run sync checks in thread pool
    await loop.run_in_executor(None, _check_ffmpeg, result)
    await loop.run_in_executor(None, _check_whisper, result)
    await loop.run_in_executor(None, _check_voice_embedder, result)

    # Async checks
    await _check_ollama(result)

    # Print summary
    banner = "\n".join(result.summary_lines())
    if result.ok:
        logger.info("Preflight complete – all critical checks passed:\n%s", banner)
    else:
        logger.error("Preflight FAILED – critical issues found:\n%s", banner)

    return result
