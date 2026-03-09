# Frontend

## Stack

- React 18
- TypeScript
- Vite
- Axios
- React Markdown
- Plain CSS in `src/index.css`

## Frontend Entry Points

### `src/main.tsx`

Responsibilities:

- boot the React app
- read persisted theme selection before first render
- apply `data-theme` to the root document element

### `src/App.tsx`

This is the orchestration component for the UI.

State owned here:

- `meetings`
- `selectedMeetingId`
- `newTitle`
- `summary`
- `busy`
- `appError`
- `apiTokenInput`
- `activeApiToken`
- `viewMode`

Cross-cutting hooks used here:

- `useTheme()`
- `useLocalRuntime()`
- `useWebSocket()`

Primary responsibilities:

- load meetings after auth is available
- load transcript and summary when the selected meeting changes
- refresh state after create/start/stop/generate actions
- render the left navigation/security/sidebar panels
- switch between live workspace and past dashboard views

## API Client

File: `src/api/client.ts`

Responsibilities:

- configure the axios client used across the UI
- persist the local API token in `localStorage`
- attach the bearer token to all API requests
- normalize API/network errors into user-facing messages

Key functions:

- `getApiToken()`
- `setApiToken()`
- `clearApiToken()`
- `formatApiError()`

Current client behavior:

- request base path is `/api`
- timeout is 30s
- requests identify themselves with `X-Requested-With: ParrotScriptClient`
- timeout and unreachable-backend cases get custom local-runtime error messages

## Hooks

### `src/hooks/useTheme.ts`

Responsibilities:

- support `light`, `dark`, and `system` theme modes
- listen to system theme changes
- persist the selected mode in `localStorage`
- set `data-theme` on the document root

### `src/hooks/useLocalRuntime.ts`

Responsibilities:

- watch browser online/offline events
- poll `/health` every 15 seconds
- expose backend reachability state

Return shape:

- `browserOnline`
- `backendReachability`

### `src/hooks/useWebSocket.ts`

Responsibilities:

- open the meeting-specific live stream socket
- append transcript segments without duplication
- cap transcript buffer growth
- track live meeting status messages
- reconnect after failures with backoff and jitter
- retry when the browser comes back online or becomes visible again

Return shape:

- `segments`
- `status`
- `setSegments`
- `connectionState`

Connection states:

- `idle`
- `connecting`
- `connected`
- `reconnecting`
- `unauthorized`
- `disconnected`

## Components

### Workspace and navigation

- `MeetingControls.tsx`: start/stop controls and live elapsed timer.
- `MeetingList.tsx`: selectable list of all meetings.
- `PastMeetingsDashboard.tsx`: completed/failed meeting dashboard with summary stats.
- `RuntimeStatusPanel.tsx`: browser connectivity, backend reachability, and socket state.

### Content views

- `LiveTranscript.tsx`: auto-scrolling transcript list with color-coded speaker pills.
- `SummaryPanel.tsx`: markdown rendering of the generated summary and regeneration action.
- `SearchBar.tsx`: semantic search UI with request cancellation and disabled/auth handling.

### Theme and visuals

- `ThemeSelector.tsx`: segmented control for system/light/dark mode.
- `icons.tsx`: inline SVG icon primitives used throughout the app.
- `index.css`: design tokens, grid layout, panels, buttons, dashboard cards, and responsive rules.

## Data Types

File: `src/types/models.ts`

Defines the shared frontend types used across API calls and rendering:

- `MeetingLifecycleStatus`
- `Meeting`
- `Segment`
- `Summary`
- `MeetingStatus`
- `SearchResult`

## UX and Runtime Behavior

### Auth flow

- The user enters `API_TOKEN` into the security panel.
- The token is saved in browser `localStorage`.
- API and WebSocket calls remain disabled until a token is present.
- Clearing the token resets local meeting, summary, and transcript state.

### Connectivity flow

- If the backend goes down, health state changes to unreachable.
- API failures show local-runtime-specific messages.
- WebSocket reconnects in the background and reports connection state in the runtime panel.
- When backend reachability recovers, the app refreshes the meeting list again.

### Theme flow

- The app applies a resolved theme before React mounts to avoid flashing.
- Theme mode persists across reloads.
- `system` mode tracks `prefers-color-scheme` changes live.

## Frontend Extension Points

- Add new data calls by extending `src/api/client.ts` first.
- Add shared state to `App.tsx` only if the state truly crosses panels.
- If a panel can manage its own async lifecycle, keep that logic in the component or a dedicated hook.
- Keep network retry logic in hooks/clients rather than scattered in presentational components.
