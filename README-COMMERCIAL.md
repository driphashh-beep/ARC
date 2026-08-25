# ARC Commercial Overview

ARC is a local, browser-operated AI command center for workspace tasks. Its primary interface is a persistent dashboard chat that automatically routes natural-language requests to restricted local tools.

## Product safeguards

- Privacy Mode redacts secrets, personal data, private network addresses, and local user paths from chat, tool, file, and Discord output.
- Workspace reads are restricted to the ARC project and credential files are blocked.
- File creation is approval-gated: ARC shows the proposed filename and content before writing.
- Web Search is disabled by default and must be enabled per chat message.
- Discord is optional and restricted to one configured server channel.

## Operation

On Windows, users start ARC by double-clicking `START-ARC.bat`, then work through the browser chat. PowerShell, Python commands, and VS Code are development tools rather than normal user controls.

Licensing, pricing, support commitments, and production deployment terms are not defined by this repository and must be established separately before commercial distribution.
