# ARC deployment baseline

ARC defaults to local mode at `127.0.0.1:3132`. These files do not deploy it.

## Local Windows

Set `OPENAI_API_KEY` in the Windows user environment if AI tasks are needed, then double-click `START-ARC.bat`. Local tools work without it. Discord is optional.

## Authenticated single-customer container

1. Copy `.env.example` to `.env`, replace placeholders, and use a long random `ARC_AUTH_TOKEN`.
2. Keep Privacy Mode on and restrict the host/network firewall to the customer.
3. Validate with `docker compose config`. Run `docker compose up --build` only after deployment approval.
4. Authenticate with username `arc` and the configured ARC auth token.

The compose port is loopback-only. Production mode refuses to start without authentication. Add TLS and customer network controls before any non-local exposure. `/health` returns safe state booleans only.

## Discord

Set `DISCORD_BOT_TOKEN` and `ARC_DISCORD_CHANNEL_ID`. ARC registers `/arc`, `/study`, and `/arc_status`; it rejects DMs and other channels. Do not grant message-content intent.

Never commit `.env`, credentials, databases, or private keys. File tools are workspace-confined; writes always require dashboard approval.
