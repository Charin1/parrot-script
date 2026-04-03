import asyncio

from backend.assistants import AssistantJoinRequest, LocalMeetingAssistantProvider


class FakeLauncher:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.launched_urls: list[str] = []

    def launch(self, meeting_url: str) -> None:
        if self.should_fail:
            raise OSError("launcher unavailable")
        self.launched_urls.append(meeting_url)

    def describe(self) -> str:
        return "fake-launcher"


def test_local_assistant_provider_launches_meeting_link() -> None:
    launcher = FakeLauncher()
    provider = LocalMeetingAssistantProvider(launcher=launcher)

    session = asyncio.run(
        provider.request_join(
            AssistantJoinRequest(
                meeting_id="meeting-1",
                title="Assistant Meeting",
                meeting_url="https://meet.google.com/abc-defg-hij",
                source_platform="google_meet",
                assistant_visible_name="Parrot Script Assistant",
            )
        )
    )

    assert launcher.launched_urls == ["https://meet.google.com/abc-defg-hij"]
    assert session.join_status == "pending"
    assert session.consent_status == "required"
    assert session.provider_session_id is not None
    assert session.provider_metadata is not None
    assert session.provider_metadata["launch_strategy"] == "local_link_launch"
    assert "live capture has started" in (session.message or "").lower()


def test_local_assistant_provider_surfaces_launch_failures() -> None:
    provider = LocalMeetingAssistantProvider(launcher=FakeLauncher(should_fail=True))

    session = asyncio.run(
        provider.request_join(
            AssistantJoinRequest(
                meeting_id="meeting-2",
                title="Broken Assistant Meeting",
                meeting_url="https://zoom.us/j/123456789",
                source_platform="zoom",
                assistant_visible_name="Parrot Script Assistant",
            )
        )
    )

    assert session.join_status == "failed"
    assert session.consent_status == "unknown"
    assert session.provider_metadata is not None
    assert session.provider_metadata["launched_via"] == "fake-launcher"
    assert "could not open the zoom link" in (session.message or "").lower()
