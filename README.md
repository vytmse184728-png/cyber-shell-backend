# Cyber Shell Backend Starter

Starter repository for an API backend and web chatbot that support the `cyber-shell` / PTY wrapper.

## Current wrapper payload contract

The current `cyber-shell` repo sends JSON with these fields:

- `session_id`
- `hostname`
- `shell`
- `seq`
- `cwd`
- `cmd`
- `exit_code`
- `output`
- `output_truncated`
- `started_at`
- `finished_at`
- `is_interactive`
- `metadata`

This backend keeps that contract unchanged.

## Run with Docker Compose

1. Create `.env` from `.env.example`
2. Update the values:

```bash
cp .env.example .env
```

3. Run:

```bash
docker compose up --build
```

4. Open:

- Web UI: `http://127.0.0.1:60081/`
- Health: `http://127.0.0.1:60081/health`

## Point the wrapper to this backend

Because the current endpoint contract is `/api/terminal-events`, you only need to point the wrapper to the new backend:

```bash
cyber-shell   --endpoint-url http://127.0.0.1:60081/api/terminal-events   --api-key replace-me
```

## Test ingestion with curl

```bash
curl -i -X POST http://127.0.0.1:60081/api/terminal-events   -H "Content-Type: application/json"   -H "Authorization: Bearer replace-me"   -d '{
    "session_id":"s1",
    "seq":1,
    "cmd":"whoami",
    "cwd":"/home/kali",
    "exit_code":0,
    "output":"kali",
    "output_truncated":false,
    "started_at":"2026-03-21T10:00:00Z",
    "finished_at":"2026-03-21T10:00:01Z",
    "is_interactive":false,
    "hostname":"kali",
    "shell":"bash",
    "metadata":{}
  }'
```

## Main environment variables

- `API_KEY`: authentication key for telemetry from the wrapper
- `GEMINI_API_KEY`: API key for the Google Gen AI SDK
- `GEMINI_MODEL`: defaults to `gemini-2.5-flash`
- `GEMINI_API_VERSION`: defaults to `v1`
- `DATABASE_URL`: Postgres or SQLite connection DSN
- `HTTP_TOOL_ALLOWED_HOSTS`: host allowlist for the HTTP tool
- `HTTP_TOOL_ALLOWED_METHODS`: defaults to `GET,HEAD`
- `APP_PORT`: exposed port for the web/API container, defaults to `60081`

## Chat flow

The frontend sends `message + session_id + conversation_id` to `/api/chat`.
The server:

1. Builds a system prompt for a testing support role that only provides guidance
2. Calls Gemini through `google-genai`
3. If the model wants to call a tool, the server runs the allowlisted DB/HTTP tool
4. Sends the tool result back to the model
5. Returns the final answer to the frontend

## Included AI tools

- `get_session_overview`
- `get_recent_events`
- `search_events`
- `send_http_request`
