from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.integration
def test_integration_pipeline_fixture_exists() -> None:
    fixture = Path("tests/fixtures/sample_meeting.wav")
    if not fixture.exists():
        pytest.skip("Integration fixture missing: tests/fixtures/sample_meeting.wav")

    # Placeholder test scaffold for end-to-end pipeline. Full run requires:
    # - ffmpeg + capture device
    # - Whisper model download
    # - Ollama running with configured model
    assert fixture.stat().st_size > 0
