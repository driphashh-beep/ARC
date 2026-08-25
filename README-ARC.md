# ARC Command Center

ARC is a local AI command center at `http://localhost:3132` with eight workspace-restricted local tools, SQLite history, approval-gated writes, Privacy Mode, optional task-enabled Web Search, and an optional channel-restricted Discord bridge.

## What it does
- Runs locally at `http://localhost:3132`
- Uses the OpenAI Responses API
- Stores task history locally in `data/arc.db`
- Keeps destructive/external actions approval-gated by policy
- Leaves existing ARC identity/protocol files intact

## Requirements
- Windows
- Python 3.10+
- Python 3.10+; `OPENAI_API_KEY` is optional for local tools and required only for AI tasks

## Start
Double-click `START-ARC.bat`.

Or from PowerShell:

```powershell
python -m pip install -r requirements.txt
python arc.py
```

Then open `http://localhost:3132`.

## Model
Default: `gpt-5.6`

Optional override:

```powershell
$env:ARC_MODEL="gpt-5.6-terra"
python arc.py
```
