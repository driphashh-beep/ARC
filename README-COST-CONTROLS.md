# ARC Cost-Control Fix

This update modifies the existing ARC only. It does not create a second agent/project.

Defaults:
- Model: `gpt-5.6-luna`
- Max output tokens per API response: `800`
- Max tool-loop rounds per task: `3`
- Daily API-call ceiling: `20`
- Daily token ceiling: `100000`
- API request/token usage is logged locally in `data/arc.db`
- File writes remain approval-gated

The launcher inherits optional configuration from the Windows environment. ARC still starts without an API key so local tools remain usable.
