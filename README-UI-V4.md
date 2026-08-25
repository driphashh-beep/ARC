# ARC UI V4 — Neon Tool Board

V4 replaces the generic V3 dashboard with the command-center layout approved from the UI reference.

## What is real and active
- Workspace Browser, File Reader, File Search, and Calculator
- Python Code Check, which compiles but never executes
- ARC Database Summary
- Text → Asset and File Writer, both approval-gated
- Web Search only when explicitly checked for a task, with an API-cost warning
- Optional Discord testing bridge, shown as off when unconfigured

## Dashboard
- Neon bordered tool board
- Task composer
- Real capability status
- Recent files
- ARC result
- Approval queue
- Activity log
- Task history
- Runtime/system health
- API/token controls
- Animated ARC workflow graph

## Cost controls
- Model: gpt-5.6-luna
- Max output tokens: 800
- Max tool loops: 3
- Daily API-call hard limit: 20
- Daily token hard limit: 100000
- Privacy Mode on by default

Default local address: http://127.0.0.1:3132
