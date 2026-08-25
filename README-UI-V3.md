# ARC UI V3

This update edits the existing ARC application. It does not create another agent.

## UI changes
- Command-center dashboard layout
- System/model/usage status cards
- Approval queue
- Recent task history
- Quick prompt buttons
- Bottom-center animated ARC flow: INPUT → REASON → TOOL → VERIFY → RESULT
- Responsive layout for smaller screens

## Runtime controls
- Default model: gpt-5.6-luna
- Max output tokens: 800
- Max tool-loop rounds: 3
- Daily API-call hard ceiling: 20
- Token/API usage stored locally in data/arc.db
- File writes remain approval-gated
- ARC remains a single primary agent

Open: http://localhost:3131
