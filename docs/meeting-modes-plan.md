# Meeting Modes Plan

## Goal

Evolve Parrot Script from a single local capture workflow into a dual-mode meeting assistant:

1. `Ghost mode ON` (default): fully on-device capture and processing.
2. `Ghost mode OFF`: a visible meeting assistant can be invited into Google Meet, Zoom, Teams, and similar platforms.

The product should make the privacy and visibility tradeoff explicit before every recording starts.

## Product Definition

### Mode 1: Ghost Mode ON

- Runs entirely on the user's machine.
- Captures local system audio or selected device audio.
- No assistant joins the meeting as a participant.
- Best for privacy-sensitive use cases and zero external dependencies.
- Speaker identification quality depends on mixed audio diarization only.

### Mode 2: Ghost Mode OFF

- A visible assistant joins the meeting as a participant or platform-connected media client.
- Other participants can see that the assistant is present.
- Real-time capture quality should improve because the app can use meeting metadata, participant events, and platform-aware streams when available.
- Requires platform-specific permissions, consent handling, and a stronger trust/compliance UX.

## Fireflies-Like Behaviors To Support

The target experience should match the core behaviors users expect from tools like Fireflies:

- Manual invite by email or meeting link.
- Auto-join from connected calendar events.
- "Add to live meeting" for an already running call.
- Post-meeting transcript, summary, and search.
- Real-time transcript while the meeting is happening.
- Better speaker attribution than mixed-device diarization.

## Recommended Product Model

### Capture Mode Selector

Add a capture mode selector at meeting start:

- `On-device only`
- `Visible meeting assistant`

This should be persisted per meeting and surfaced in the meeting detail UI.

### Ghost Mode UX

- `Ghost mode ON`: show "Private capture on this device only".
- `Ghost mode OFF`: show "Assistant will join visibly and participants may see recording/consent indicators".
- Require a confirmation step the first time `Ghost mode OFF` is enabled.

### Meeting Entry Options

For `Ghost mode OFF`, support:

- Paste meeting URL
- Invite assistant email
- Join live meeting now
- Auto-join future calendar meetings

## Technical Architecture

### 1. Introduce a Capture Source Abstraction

Replace the current single-source pipeline with a source interface:

- `LocalAudioSource`
- `MeetingBotSource`
- future: `BrowserTabSource`, `UploadedRecordingSource`

Each source should normalize into the same downstream event model:

- audio frames
- timestamps
- participant events
- source metadata

### 2. Split Speaker Identity Into Levels

Do not treat all speaker labeling as the same problem. Add three levels:

- `heuristic`: local diarization from mixed audio only
- `participant-aware`: transcript segments mapped to platform participant metadata
- `stream-aware`: one audio stream per participant or near-equivalent attribution

This keeps the UI honest about confidence and explains why bot mode is better.

### 3. Add a Meeting Assistant Service Layer

Create a provider layer such as:

- `GoogleMeetProvider`
- `ZoomProvider`
- `TeamsProvider`

Responsibilities:

- validate link format
- schedule join
- create/join assistant session
- track join state and consent state
- map participant ids to transcript speakers
- stop and clean up sessions

### 4. Extend Storage

Add meeting-level fields for:

- `capture_mode`
- `ghost_mode`
- `source_platform`
- `meeting_url`
- `assistant_join_status`
- `assistant_visible_name`
- `consent_status`
- `provider_session_id`
- `provider_metadata`

Add participant/session tables for:

- platform participant id
- display name
- join/leave timestamps
- source confidence
- mapped local speaker label

## Real-Time Accuracy Strategy

### For Ghost Mode ON

Keep everything local and improve quality through:

- segment-level diarization
- better VAD/turn detection
- optional stronger local diarization backend
- speaker profile persistence across meetings

### For Ghost Mode OFF

Prefer participant-aware attribution over heuristic diarization whenever possible:

- use provider participant rosters
- use speaking events if available
- use separate participant audio when available
- fall back to embedding-based clustering only when platform metadata is insufficient

## Recommended Rollout

### Phase 1: Product Plumbing

- add `capture_mode` and `ghost_mode`
- add UI for mode selection
- add schema for provider metadata
- refactor pipeline around `CaptureSource`

### Phase 2: Local-Only Quality Pass

- improve fully on-device diarization
- add speaker profiles / voice memory
- expose confidence in UI
- add "private mode" badges and onboarding

### Phase 3: Hosted Assistant MVP

Start with one `ghost mode OFF` path:

- manual meeting URL input
- visible assistant join state
- live transcript in app
- clear consent/warning UI

Implementation recommendation:

- use a managed meeting-bot layer first for speed and platform coverage
- keep provider calls behind our own abstraction so we can replace it later

### Phase 4: Calendar + Auto-Join

- Google Calendar / Outlook connection
- auto-join rules
- "only when invited"
- "join all meetings with a web link"
- "join live now"

### Phase 5: Multi-Platform Hardening

- Google Meet
- Zoom
- Microsoft Teams
- retry/lobby/waiting room handling
- clearer failure reasons in UI

## Important Constraints

### Constraint 1: Visible assistant mode is not the same as fully on-device

This mode should be described as `connected mode` or `assistant mode`, not private mode. It requires platform integration and is visible by design.

### Constraint 2: Compliance is part of the feature, not an afterthought

The app must surface:

- who can see the assistant
- whether recording indicators appear
- whether host approval is required
- whether participants can block or remove the assistant

### Constraint 3: Provider support differs by platform

Platform behavior is not uniform, so the UI must show provider-specific requirements and limitations.

## External Findings That Affect The Plan

The following findings were reviewed on 2026-03-30 and should guide implementation:

- Fireflies supports manual invite, auto-join from connected calendars, and adding the assistant to a live meeting.
- Fireflies documents a visible bot participant for Google Meet and Zoom.
- Google Meet Media API is in Developer Preview and requires participant/admin consent for real-time media access.
- Google notes that participants are informed when Meet Media API is active and can turn it off.
- Zoom documents that participants are notified when a meeting is being recorded and external recording visibility is expected.
- Microsoft Teams supports calling/meeting bots, but bot access requires explicit app permissions and meeting bot registration.

## Recommended Naming

Avoid using only `ghost mode`, because it can sound stealthy in a way that may create trust/compliance confusion. Prefer:

- `Private Mode` for local-only capture
- `Assistant Mode` for visible join

If you still want the theme:

- `Ghost mode ON` = Private Mode
- `Ghost mode OFF` = Assistant Mode

## Suggested Next Build Step

Build the product scaffolding first:

1. add capture mode fields to the meeting model
2. add mode selector UI
3. create `CaptureSource` abstraction
4. add provider interface with a stub implementation
5. wire transcript pipeline to accept participant metadata when present
