# ARC V2

This update adds the first real agentic tool layer to the existing ARC build.

## Added
- Read-only workspace file listing
- Read-only text-file inspection
- Tool loop through the OpenAI Responses API
- Approval-gated file-write proposals
- Approve / Reject controls in the ARC web UI
- Pending-action persistence in SQLite
- Existing ARC folder is backed up before update

## Safety
ARC can inspect the local ARC workspace without approval.
Any file write is converted into a pending action and must be approved in the UI.
Secrets are not exposed by tools.

## Suggested first test
Ask:

`Inspect this ARC workspace and tell me what files currently define the system. Do not modify anything.`

Then test approval gating:

`Create a file named TEST-ARC-V2.txt containing "ARC V2 tool approval works".`

ARC should create a pending approval instead of writing immediately.
