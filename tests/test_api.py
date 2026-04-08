import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.api.routes import meetings as meetings_routes
from backend.assistants import AssistantSession
from backend.api.server import app
from backend.config import settings
from backend.core.events import TranscriptSegmentEvent
from backend.storage.db import init_db
from backend.storage.repositories.segments import SegmentsRepository
from backend.storage.repositories.speakers import SpeakersRepository
from backend.storage.repositories.summaries import SummariesRepository


def setup_test_db(tmp_path, api_token: str = 'test-token') -> TestClient:
    db_file = tmp_path / 'test_api.db'
    settings.db_path = db_file.as_posix()
    settings.api_token = api_token
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(init_db())
    return TestClient(app)


def auth_headers() -> dict[str, str]:
    return {'Authorization': f'Bearer {settings.api_token}'}


def test_create_and_list_meetings(tmp_path) -> None:
    client = setup_test_db(tmp_path)

    unauthorized = client.get('/api/meetings/')
    assert unauthorized.status_code == 401

    response = client.get('/api/meetings/', headers=auth_headers())
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    created = client.post('/api/meetings/', json={'title': 'Test Meeting'}, headers=auth_headers())
    assert created.status_code == 200
    body = created.json()
    assert 'id' in body
    assert body['title'] == 'Test Meeting'
    assert body['capture_mode'] == 'private'
    assert body['ghost_mode'] is True
    assert body['assistant_join_status'] == 'not_requested'
    assert body['consent_status'] == 'not_needed'

    security = client.get('/health')
    assert security.status_code == 200
    assert security.headers['x-content-type-options'] == 'nosniff'
    assert security.headers['x-frame-options'] == 'DENY'

    bad_update = client.patch(
        f"/api/meetings/{body['id']}",
        json={'status': 'hacked'},
        headers=auth_headers(),
    )
    assert bad_update.status_code == 422


def test_assistant_mode_start_launches_recording_flow(tmp_path, monkeypatch) -> None:
    client = setup_test_db(tmp_path)

    created = client.post(
        '/api/meetings/',
        json={'title': 'Assistant Mode'},
        headers=auth_headers(),
    )
    assert created.status_code == 200
    meeting_id = created.json()['id']

    async def fake_start_pipeline(meeting_id: str, pipeline) -> None:
        return None

    class FakeAssistantProvider:
        async def request_join(self, request) -> AssistantSession:
            return AssistantSession(
                join_status='pending',
                source_platform='google_meet',
                consent_status='required',
                provider_session_id='provider-session-1',
                provider_metadata={'launch_strategy': 'test'},
                message='Google Meet was opened on this device and live capture has started.',
            )

    monkeypatch.setattr(meetings_routes, '_start_pipeline', fake_start_pipeline)
    monkeypatch.setattr(meetings_routes, 'assistant_provider', FakeAssistantProvider())

    started = client.post(
        f'/api/meetings/{meeting_id}/start',
        json={
            'capture_mode': 'assistant',
            'ghost_mode': False,
            'meeting_url': 'https://meet.google.com/abc-defg-hij',
            'assistant_visible_name': 'Parrot Script Assistant',
        },
        headers=auth_headers(),
    )
    assert started.status_code == 200
    payload = started.json()
    assert payload['status'] == 'recording'
    assert 'opened' in payload['message'].lower()

    meeting = client.get(f'/api/meetings/{meeting_id}', headers=auth_headers())
    assert meeting.status_code == 200
    body = meeting.json()
    assert body['status'] == 'recording'
    assert body['capture_mode'] == 'assistant'
    assert body['ghost_mode'] is False
    assert body['source_platform'] == 'google_meet'
    assert body['meeting_url'] == 'https://meet.google.com/abc-defg-hij'
    assert body['assistant_join_status'] == 'pending'
    assert body['consent_status'] == 'required'
    assert body['provider_session_id'] == 'provider-session-1'


def test_assistant_mode_normalizes_google_meet_code(tmp_path, monkeypatch) -> None:
    client = setup_test_db(tmp_path)

    created = client.post(
        '/api/meetings/',
        json={'title': 'Assistant URL Normalize'},
        headers=auth_headers(),
    )
    assert created.status_code == 200
    meeting_id = created.json()['id']

    captured_request = {}

    async def fake_start_pipeline(meeting_id: str, pipeline) -> None:
        return None

    class FakeAssistantProvider:
        async def request_join(self, request) -> AssistantSession:
            captured_request["meeting_url"] = request.meeting_url
            captured_request["source_platform"] = request.source_platform
            return AssistantSession(
                join_status='pending',
                source_platform=request.source_platform,
                consent_status='required',
                provider_session_id='provider-session-2',
                provider_metadata={'launch_strategy': 'test'},
                message='Google Meet was opened on this device and live capture has started.',
            )

    monkeypatch.setattr(meetings_routes, '_start_pipeline', fake_start_pipeline)
    monkeypatch.setattr(meetings_routes, 'assistant_provider', FakeAssistantProvider())

    started = client.post(
        f'/api/meetings/{meeting_id}/start',
        json={
            'capture_mode': 'assistant',
            'ghost_mode': False,
            'meeting_url': 'abc-defg-hij',
            'assistant_visible_name': 'Parrot Script Assistant',
        },
        headers=auth_headers(),
    )
    assert started.status_code == 200
    assert captured_request["meeting_url"] == 'https://meet.google.com/abc-defg-hij'
    assert captured_request["source_platform"] == 'google_meet'

    meeting = client.get(f'/api/meetings/{meeting_id}', headers=auth_headers())
    assert meeting.status_code == 200
    body = meeting.json()
    assert body['meeting_url'] == 'https://meet.google.com/abc-defg-hij'
    assert body['source_platform'] == 'google_meet'


def test_private_mode_start_keeps_recording_flow(tmp_path, monkeypatch) -> None:
    client = setup_test_db(tmp_path)

    created = client.post(
        '/api/meetings/',
        json={'title': 'Private Mode'},
        headers=auth_headers(),
    )
    assert created.status_code == 200
    meeting_id = created.json()['id']

    async def fake_start_pipeline(meeting_id: str, pipeline) -> None:
        return None

    monkeypatch.setattr(meetings_routes, '_start_pipeline', fake_start_pipeline)

    started = client.post(
        f'/api/meetings/{meeting_id}/start',
        json={
            'capture_mode': 'private',
            'ghost_mode': True,
        },
        headers=auth_headers(),
    )
    assert started.status_code == 200
    payload = started.json()
    assert payload['status'] == 'recording'
    assert payload['message'] is None

    meeting = client.get(f'/api/meetings/{meeting_id}', headers=auth_headers())
    assert meeting.status_code == 200
    body = meeting.json()
    assert body['status'] == 'recording'
    assert body['capture_mode'] == 'private'
    assert body['ghost_mode'] is True
    assert body['source_platform'] == 'local'
    assert body['assistant_join_status'] == 'not_requested'


def test_delete_meeting_with_related_rows(tmp_path) -> None:
    client = setup_test_db(tmp_path)

    created = client.post(
        '/api/meetings/',
        json={'title': 'Delete with children'},
        headers=auth_headers(),
    )
    assert created.status_code == 200
    meeting_id = created.json()['id']

    async def seed_children() -> None:
        await SegmentsRepository().insert(
            TranscriptSegmentEvent(
                meeting_id=meeting_id,
                speaker='Speaker 1',
                text='Hello world',
                start_time=0.0,
                end_time=1.0,
                confidence=0.9,
                segment_id=str(uuid4()),
            )
        )
        await SpeakersRepository().upsert(meeting_id, 'Speaker 1')
        await SummariesRepository().insert(meeting_id, 'Summary content', 'test-model')

    asyncio.run(seed_children())

    deleted = client.delete(f'/api/meetings/{meeting_id}', headers=auth_headers())
    assert deleted.status_code == 200
    assert deleted.json()['deleted'] is True

    missing = client.get(f'/api/meetings/{meeting_id}', headers=auth_headers())
    assert missing.status_code == 404


def test_transcript_pagination(tmp_path) -> None:
    client = setup_test_db(tmp_path)

    created = client.post(
        '/api/meetings/',
        json={'title': 'Transcript pages'},
        headers=auth_headers(),
    )
    assert created.status_code == 200
    meeting_id = created.json()['id']

    async def seed_segments() -> None:
        repo = SegmentsRepository()
        for index in range(3):
            await repo.insert(
                TranscriptSegmentEvent(
                    meeting_id=meeting_id,
                    speaker='Speaker 1',
                    text=f'Segment {index + 1}',
                    start_time=float(index),
                    end_time=float(index) + 0.5,
                    confidence=0.9,
                    segment_id=str(uuid4()),
                )
            )

    asyncio.run(seed_segments())

    page1 = client.get(
        f'/api/meetings/{meeting_id}/transcript?page=1&limit=2',
        headers=auth_headers(),
    )
    assert page1.status_code == 200
    body1 = page1.json()
    assert body1['total'] == 3
    assert len(body1['items']) == 2

    page2 = client.get(
        f'/api/meetings/{meeting_id}/transcript?page=2&limit=2',
        headers=auth_headers(),
    )
    assert page2.status_code == 200
    body2 = page2.json()
    assert body2['total'] == 3
    assert len(body2['items']) == 1


def test_health_reports_optional_auth_and_allows_requests_without_token(tmp_path) -> None:
    client = setup_test_db(tmp_path, api_token='')

    health = client.get('/health')
    assert health.status_code == 200
    assert health.json() == {'status': 'ok', 'auth_required': False}

    meetings = client.get('/api/meetings/')
    assert meetings.status_code == 200
    assert isinstance(meetings.json(), list)


def test_websocket_rejects_unauthorized_clients(tmp_path) -> None:
    client = setup_test_db(tmp_path)

    with client.websocket_connect('/ws/meetings/test-meeting') as websocket:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()

    assert exc_info.value.code == 4401


def test_cors_allows_loopback_preview_origin(tmp_path) -> None:
    client = setup_test_db(tmp_path)

    response = client.options(
        '/api/meetings/',
        headers={
            'Origin': 'http://127.0.0.1:4173',
            'Access-Control-Request-Method': 'GET',
        },
    )

    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://127.0.0.1:4173'
