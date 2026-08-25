"""ARC core: configuration, privacy, local tools, state, approvals, and AI loop."""
from __future__ import annotations

import ast
import datetime as dt
import fnmatch
import hashlib
import json
import math
import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "arc.db"
DATA_DIR.mkdir(exist_ok=True)


def _integer(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(value, high))


MODEL = os.getenv("ARC_MODEL", "gpt-5.6-luna")
PORT = _integer("ARC_PORT", 3132, 1, 65535)
ENV_MODE = os.getenv("ARC_ENV", "local").strip().lower()
PRIVACY_MODE = os.getenv("ARC_PRIVACY_MODE", "on").strip().lower() not in {"0", "false", "off"}
MAX_OUTPUT_TOKENS = _integer("ARC_MAX_OUTPUT_TOKENS", 800, 128, 4000)
MAX_TOOL_LOOPS = _integer("ARC_MAX_TOOL_LOOPS", 3, 1, 6)
DAILY_API_CALL_LIMIT = _integer("ARC_DAILY_API_CALL_LIMIT", 20, 1, 10000)
DAILY_TOKEN_LIMIT = _integer("ARC_DAILY_TOKEN_LIMIT", 100000, 1000, 10000000)
MAX_PROMPT_CHARS = _integer("ARC_MAX_PROMPT_CHARS", 20000, 100, 200000)
OPENAI_CONFIGURED = bool(os.getenv("OPENAI_API_KEY", "").strip())

_DB_LOCK = threading.RLock()
_SECRET_NAMES = {
    ".env", ".env.local", ".env.production", "credentials", "credentials.json",
    "secrets.json", "id_rsa", "id_ed25519", "wallet.dat", "keystore",
}
_SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".kdbx"}
_IGNORE_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache"}
_SECRET_VALUE = re.compile(
    r"(?i)(api[_-]?key|token|password|passwd|secret|private[_-]?key|seed[_-]?phrase|wallet[_-]?seed)"
    r"\s*[:=]\s*([^\s,;]+)"
)
_OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")
_DISCORD_TOKEN = re.compile(r"\b(?:M|N|O)[A-Za-z\d_-]{20,}\.[A-Za-z\d_-]{5,}\.[A-Za-z\d_-]{20,}\b")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s])\d{3}[-.\s]\d{4}(?!\d)")
_PRIVATE_IP = re.compile(r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b")
_WINDOWS_USER = re.compile(r"(?i)\bC:\\Users\\[^\\\s<>:\"|?*]+")


def redact(value: Any) -> str:
    text = str(value)
    if not PRIVACY_MODE:
        return text
    text = _SECRET_VALUE.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    text = _OPENAI_KEY.sub("[REDACTED API KEY]", text)
    text = _DISCORD_TOKEN.sub("[REDACTED BOT TOKEN]", text)
    text = _EMAIL.sub("[REDACTED EMAIL]", text)
    text = _PHONE.sub("[REDACTED PHONE]", text)
    text = _PRIVATE_IP.sub("[REDACTED LOCAL NETWORK]", text)
    text = _WINDOWS_USER.sub("<USER>", text)
    return text


def is_sensitive_path(path: Path) -> bool:
    names = {part.lower() for part in path.parts}
    name = path.name.lower()
    return (
        name in _SECRET_NAMES
        or name.startswith(".env.")
        or path.suffix.lower() in _SECRET_SUFFIXES
        or bool(names & {".ssh", ".aws", ".gnupg", "credentials", "secrets", "wallets"})
    )


def safe_path(relative_path: str) -> Path:
    rel = str(relative_path or "").replace("\\", "/").lstrip("/")
    target = (ROOT / rel).resolve()
    if target != ROOT and ROOT not in target.parents:
        raise ValueError("Path escapes ARC workspace.")
    return target


def display_path(path: Path | str) -> str:
    p = safe_path(str(path)) if not isinstance(path, Path) else path.resolve()
    try:
        rel = p.relative_to(ROOT).as_posix()
    except ValueError:
        return "<BLOCKED PATH>"
    return "<WORKSPACE>" + (f"/{rel}" if rel != "." else "")


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, prompt TEXT NOT NULL,
        result TEXT NOT NULL, status TEXT NOT NULL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS pending_actions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, action_type TEXT NOT NULL,
        target TEXT NOT NULL, payload TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS api_usage(
        id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, model TEXT NOT NULL,
        input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
        total_tokens INTEGER NOT NULL DEFAULT 0)""")
    con.execute("""CREATE TABLE IF NOT EXISTS activity(
        id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, event TEXT NOT NULL,
        detail TEXT NOT NULL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS chat_messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, role TEXT NOT NULL,
        content TEXT NOT NULL, tool_name TEXT NOT NULL DEFAULT '', tool_status TEXT NOT NULL DEFAULT '',
        pending_action_id INTEGER)""")
    con.commit()
    return con


def log_event(event: str, detail: str = "") -> None:
    with _DB_LOCK:
        con = db()
        con.execute("INSERT INTO activity(created,event,detail) VALUES(?,?,?)", (now(), event, redact(detail)[:1000]))
        con.commit()
        con.close()


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def usage_today() -> tuple[int, int, int, int]:
    with _DB_LOCK:
        con = db()
        row = con.execute(
            "SELECT COUNT(*),COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),"
            "COALESCE(SUM(total_tokens),0) FROM api_usage WHERE created LIKE ?",
            (dt.date.today().isoformat() + "%",),
        ).fetchone()
        con.close()
    return tuple(int(x or 0) for x in row)


def workspace_browser(relative_path: str = "", max_depth: int = 3) -> dict[str, Any]:
    base = safe_path(relative_path)
    if not base.is_dir():
        return {"error": "Directory not found."}
    depth_limit = max(1, min(int(max_depth), 5))
    base_depth = len(base.parts)
    items = []
    for path in sorted(base.rglob("*")):
        if len(path.parts) - base_depth > depth_limit or any(part in _IGNORE_DIRS for part in path.parts):
            continue
        if is_sensitive_path(path):
            continue
        items.append({"path": path.relative_to(ROOT).as_posix(), "type": "dir" if path.is_dir() else "file"})
        if len(items) == 300:
            return {"items": items, "truncated": True}
    return {"items": items, "truncated": False}


def file_reader(relative_path: str) -> dict[str, Any]:
    path = safe_path(relative_path)
    if is_sensitive_path(path):
        return {"error": "Privacy Mode blocks credential and secret files."}
    if not path.is_file():
        return {"error": "File not found."}
    if path.stat().st_size > 500_000:
        return {"error": "File exceeds the 500 KB read limit."}
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"error": "Only UTF-8 text files can be read."}
    content = redact(raw[:120_000])
    return {"path": path.relative_to(ROOT).as_posix(), "content": content, "truncated": len(raw) > 120_000}


def file_search(query: str, glob: str = "*") -> dict[str, Any]:
    query = str(query or "").strip()
    if not query or len(query) > 200:
        return {"error": "Search query must contain 1-200 characters."}
    matches = []
    needle = query.casefold()
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in _IGNORE_DIRS for part in path.parts) or is_sensitive_path(path):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if not fnmatch.fnmatch(rel, glob) or path.stat().st_size > 500_000:
            continue
        if needle in rel.casefold():
            matches.append({"path": rel, "line": 0, "text": "Filename match"})
            if len(matches) >= 100:
                return {"matches": matches, "truncated": True}
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line in enumerate(lines, 1):
            if needle in line.casefold():
                matches.append({"path": rel, "line": line_no, "text": redact(line[:300])})
                if len(matches) >= 100:
                    return {"matches": matches, "truncated": True}
    return {"matches": matches, "truncated": False}


_BINOPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
           ast.Div: lambda a, b: a / b, ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b,
           ast.Pow: lambda a, b: a ** b}
_UNARY = {ast.UAdd: lambda a: +a, ast.USub: lambda a: -a}


def _eval(node: ast.AST, depth: int = 0) -> float | int:
    if depth > 25:
        raise ValueError("Expression is too complex.")
    if isinstance(node, ast.Expression):
        return _eval(node.body, depth + 1)
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left, right = _eval(node.left, depth + 1), _eval(node.right, depth + 1)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("Exponent is too large.")
        return _BINOPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand, depth + 1))
    raise ValueError("Only basic arithmetic is supported.")


def calculator(expression: str) -> dict[str, Any]:
    try:
        if len(expression) > 500:
            raise ValueError("Expression is too long.")
        value = _eval(ast.parse(expression, mode="eval"))
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Result is not finite.")
        return {"expression": expression, "result": value}
    except Exception as exc:
        return {"error": str(exc)}


def python_code_check(code: str = "", relative_path: str = "") -> dict[str, Any]:
    if relative_path:
        read = file_reader(relative_path)
        if "error" in read:
            return read
        code = read["content"]
    if len(code) > 200_000:
        return {"error": "Code exceeds the 200 KB check limit."}
    try:
        tree = ast.parse(code)
        compile(tree, relative_path or "<pasted-code>", "exec")
        return {"valid": True, "message": "Python syntax and compilation check passed. Code was not executed."}
    except (SyntaxError, ValueError) as exc:
        return {"valid": False, "line": getattr(exc, "lineno", None), "column": getattr(exc, "offset", None), "error": str(exc)}


def database_summary() -> dict[str, Any]:
    with _DB_LOCK:
        con = db()
        result = {
            "tasks_total": con.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
            "tasks_complete": con.execute("SELECT COUNT(*) FROM tasks WHERE status='complete'").fetchone()[0],
            "tasks_failed": con.execute("SELECT COUNT(*) FROM tasks WHERE status='failed'").fetchone()[0],
            "approvals_pending": con.execute("SELECT COUNT(*) FROM pending_actions WHERE status='pending'").fetchone()[0],
        }
        con.close()
    calls, inp, out, total = usage_today()
    result.update(api_calls_today=calls, input_tokens_today=inp, output_tokens_today=out, total_tokens_today=total)
    return result


def propose_file_write(relative_path: str, content: str, reason: str) -> dict[str, Any]:
    path = safe_path(relative_path)
    if path == ROOT or is_sensitive_path(path):
        return {"error": "That target is blocked by workspace/privacy policy."}
    if len(content.encode("utf-8")) > 1_000_000:
        return {"error": "Proposed file exceeds the 1 MB write limit."}
    rel = path.relative_to(ROOT).as_posix()
    with _DB_LOCK:
        con = db()
        cur = con.execute(
            "INSERT INTO pending_actions(created,action_type,target,payload,reason,status) VALUES(?,?,?,?,?,?)",
            (now(), "write_text_file", rel, content, redact(reason)[:1000], "pending"),
        )
        action_id = cur.lastrowid
        con.commit()
        con.close()
    log_event("approval_created", rel)
    return {"pending_action_id": action_id, "status": "pending_approval", "target": rel,
            "sha256": hashlib.sha256(content.encode()).hexdigest()}


def _slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]
    return value or "arc-asset"


ASSET_TYPES = {"study guide", "checklist", "sop", "prompt", "workflow", "template", "markdown", "json", "plain text"}


def text_to_asset(raw_text: str, asset_type: str, title: str = "") -> dict[str, Any]:
    raw_text, asset_type = str(raw_text).strip(), str(asset_type).strip().lower()
    if not raw_text or len(raw_text) > 200_000:
        return {"error": "Source text must contain 1-200,000 characters."}
    if asset_type not in ASSET_TYPES:
        return {"error": "Unsupported asset type.", "supported": sorted(ASSET_TYPES)}
    clean = redact(raw_text)
    heading = title.strip() or next((x.strip("# ") for x in clean.splitlines() if x.strip()), "ARC Asset")[:80]
    lines = [x.strip(" \t-*•") for x in clean.splitlines() if x.strip()]
    ext = "json" if asset_type == "json" else "txt" if asset_type == "plain text" else "md"
    filename = f"assets/{_slug(heading)}-{_slug(asset_type)}.{ext}"
    if asset_type == "json":
        content = json.dumps({"title": heading, "type": asset_type, "items": lines}, indent=2, ensure_ascii=False)
    elif asset_type == "plain text":
        content = clean + "\n"
    elif asset_type == "checklist":
        content = f"# {heading}\n\n" + "\n".join(f"- [ ] {x}" for x in lines) + "\n"
    elif asset_type == "study guide":
        content = f"# {heading}\n\n## Key material\n\n" + "\n".join(f"- {x}" for x in lines) + "\n\n## Review questions\n\n- What are the central ideas?\n- How would you explain them in your own words?\n"
    elif asset_type == "sop":
        content = f"# {heading}\n\n## Purpose\n\n{lines[0] if lines else clean}\n\n## Procedure\n\n" + "\n".join(f"{i}. {x}" for i, x in enumerate(lines, 1)) + "\n\n## Verification\n\n- [ ] Confirm each step completed.\n"
    elif asset_type == "workflow":
        content = f"# {heading}\n\n## Flow\n\n" + " → ".join(lines) + "\n\n## Steps\n\n" + "\n".join(f"{i}. {x}" for i, x in enumerate(lines, 1)) + "\n"
    elif asset_type == "prompt":
        content = f"# {heading}\n\n## Objective\n{clean}\n\n## Constraints\n- Use only verified information.\n- State assumptions clearly.\n\n## Output\nProvide a concise, structured result.\n"
    elif asset_type == "template":
        content = f"# {heading}\n\n## Objective\n[Describe the objective]\n\n## Inputs\n{clean}\n\n## Steps\n1. [Step]\n\n## Verification\n- [ ] [Success criterion]\n"
    else:
        content = f"# {heading}\n\n{clean}\n"
    proposal = propose_file_write(filename, content, f"Text → Asset: {asset_type}")
    proposal.update(asset_type=asset_type, proposed_filename=filename, preview=content[:2000])
    return proposal


def apply_pending(action_id: int) -> str:
    with _DB_LOCK:
        con = db()
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT action_type,target,payload,status FROM pending_actions WHERE id=?", (action_id,)).fetchone()
        if not row:
            con.rollback(); con.close(); return "Pending action not found."
        action_type, target, payload, status = row
        if status != "pending":
            con.rollback(); con.close(); return f"Action is already {status}."
        if action_type != "write_text_file":
            con.rollback(); con.close(); return "Unsupported pending action."
        path = safe_path(target)
        if is_sensitive_path(path):
            con.rollback(); con.close(); return "Target blocked by Privacy Mode."
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        con.execute("UPDATE pending_actions SET status='approved' WHERE id=?", (action_id,))
        con.commit(); con.close()
    log_event("approval_applied", target)
    return f"Approved and wrote {target}"


def reject_pending(action_id: int) -> str:
    with _DB_LOCK:
        con = db()
        cur = con.execute("UPDATE pending_actions SET status='rejected' WHERE id=? AND status='pending'", (action_id,))
        con.commit(); con.close()
    log_event("approval_rejected", str(action_id))
    return f"Rejected action {action_id}" if cur.rowcount else "Pending action not found or already resolved."


TOOL_FUNCTIONS = {
    "workspace_browser": workspace_browser, "file_reader": file_reader, "file_search": file_search,
    "calculator": calculator, "python_code_check": python_code_check, "arc_database_summary": database_summary,
    "text_to_asset": text_to_asset, "propose_file_write": propose_file_write,
}

# Public chat tool names. The older function names remain callable for compatibility.
TOOL_FUNCTIONS.update({
    "list_workspace": workspace_browser, "read_text_file": file_reader,
    "search_workspace": file_search, "check_python_file": python_code_check,
    "propose_text_asset": text_to_asset,
})

def add_chat_message(role: str, content: str, tool_name: str = "", tool_status: str = "",
                     pending_action_id: int | None = None) -> int:
    with _DB_LOCK:
        con = db()
        cur = con.execute("INSERT INTO chat_messages(created,role,content,tool_name,tool_status,pending_action_id) VALUES(?,?,?,?,?,?)",
                          (now(), role, redact(content), tool_name, tool_status, pending_action_id))
        con.commit(); con.close()
    return int(cur.lastrowid)

def chat_history(limit: int = 100) -> list[dict[str, Any]]:
    with _DB_LOCK:
        con = db()
        rows = con.execute("SELECT id,created,role,content,tool_name,tool_status,pending_action_id FROM chat_messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        con.close()
    return [dict(zip(("id","created","role","content","tool_name","tool_status","pending_action_id"), row)) for row in reversed(rows)]

def _extract_filename(prompt: str, suffix: str | None = None) -> str:
    names = re.findall(r"(?i)([\w./-]+\.(?:md|txt|py|json|csv|html|css|js))", prompt)
    if suffix:
        names = [n for n in names if n.lower().endswith(suffix)]
    return names[0] if names else ""

def route_chat(prompt: str, web_enabled: bool = False) -> dict[str, Any]:
    """Shared dashboard/Discord routing engine with safe local routing first."""
    clean = redact(str(prompt).strip()[:MAX_PROMPT_CHARS])
    low = clean.casefold()
    tool = ""
    result: dict[str, Any]
    wallet_address = re.search(r"0x[0-9a-fA-F]{40}", clean)
    wallet_amount = re.search(r"\b(\d+(?:\.\d+)?)\s*(USDC|ETH)\b", clean, re.I)
    if re.search(r"\bopen\b.*\b(?:arc )?wallet\b", low) or (re.search(r"\bshow\b.*\barc wallet\b", low) and "balance" not in low):
        tool = "arc_wallet"; result = {"wallet_action": {"action": "open"}}
        reply = "Opening ARC Wallet. Connect your wallet to view live balances or prepare a transaction."
    elif re.search(r"\bconnect\b.*\bwallet\b", low):
        tool = "arc_wallet"; result = {"wallet_action": {"action": "connect"}}
        reply = "Opening the wallet connection chooser. Your wallet must approve the connection."
    elif re.search(r"\b(?:show|what(?:'s| is))\b.*\bwallet balance\b", low):
        tool = "arc_wallet"; result = {"wallet_action": {"action": "balance"}}
        reply = "Opening ARC Wallet to show the connected account's live ETH and USDC balances."
    elif re.search(r"\b(?:receiv|receiving address)\w*\b", low):
        tool = "arc_wallet"; result = {"wallet_action": {"action": "receive"}}
        reply = "Opening the receive panel. Connect a wallet first if ARC is not connected."
    elif re.search(r"\b(?:recent|arc)\b.*\btransactions?\b", low):
        tool = "arc_wallet"; result = {"wallet_action": {"action": "history"}}
        reply = "Opening the local ARC transaction record. It includes ARC-initiated transactions only."
    elif re.search(r"\bswitch\b.*\bbase sepolia\b", low):
        tool = "arc_wallet"; result = {"wallet_action": {"action": "switch", "chainId": 84532}}
        reply = "Opening the wallet request to switch to Base Sepolia. Your wallet must confirm it."
    elif re.search(r"\bswitch\b.*\bbase\b", low):
        tool = "arc_wallet"; result = {"wallet_action": {"action": "switch", "chainId": 8453}}
        reply = "Opening the wallet request to switch to Base. Your wallet must confirm it."
    elif re.search(r"\b(pay|transfer|send)\b", low) and (wallet_amount or wallet_address):
        verb = re.search(r"\b(pay|transfer|send)\b", low).group(1)
        intent: dict[str, Any] = {"action": "send", "kind": "pay" if verb == "pay" else "transfer"}
        if wallet_amount: intent.update(amount=wallet_amount.group(1), asset=wallet_amount.group(2).upper())
        if wallet_address: intent["recipient"] = wallet_address.group(0)
        tool = "arc_wallet"; result = {"wallet_action": intent}
        reply = "I prefilled the ARC Wallet transaction form. Review the recipient, amount, network, and estimated fee; ARC will not submit until you explicitly approve in your wallet."
    elif re.search(r"\b(calculate|compute|what is)\b", low) and re.search(r"\d\s*[+*/%-]", low):
        tool = "calculator"
        expression = re.sub(r"(?i)^.*?\b(?:calculate|compute|what is)\b\s*", "", clean).strip(" ?.=")
        result = calculator(expression)
        reply = f"The result is {result['result']}." if "result" in result else f"Calculator error: {result['error']}"
    elif ("compile" in low or "syntax" in low or "python" in low and "check" in low) and ".py" in low:
        tool = "check_python_file"; filename = _extract_filename(clean, ".py")
        result = python_code_check(relative_path=filename)
        reply = result.get("message") or f"Python check failed: {result.get('error', 'unknown error')}"
    elif re.search(r"\b(how many|count|summary)\b", low) and re.search(r"\b(tasks?|approvals?|arc)\b", low):
        tool = "arc_database_summary"; result = database_summary()
        reply = f"ARC has completed {result['tasks_complete']} of {result['tasks_total']} recorded tasks. {result['tasks_failed']} failed and {result['approvals_pending']} approval(s) are pending."
    elif ("read" in low or "summar" in low) and _extract_filename(clean):
        tool = "read_text_file"; filename = _extract_filename(clean); result = file_reader(filename)
        if "error" in result: reply = f"File Reader error: {result['error']}"
        else:
            body = result["content"].strip(); lines = [x.strip("# ") for x in body.splitlines() if x.strip()]
            reply = f"{filename}: " + (" ".join(lines[:8])[:1200] or "The file is empty.")
    elif re.search(r"\b(find|search|locate)\b", low):
        tool = "search_workspace"
        query = "README" if "readme" in low else re.sub(r"(?i)^.*?\b(?:find|search|locate)(?: for)?\b", "", clean).strip(" ?.\"")
        result = file_search(query)
        paths = list(dict.fromkeys(x["path"] for x in result.get("matches", [])))
        reply = ("Found: " + ", ".join(paths[:30])) if paths else f"No workspace matches found for “{query}”."
    elif _extract_filename(clean) and re.search(r"\b(?:create|write|save)\b", low) and re.search(r"\b(?:file|with|containing|as)\b", low):
        tool = "propose_file_write"; filename = _extract_filename(clean)
        parts = re.split(r"(?i)\b(?:with|containing|content:)\b", clean, maxsplit=1)
        content = parts[1].strip() if len(parts) > 1 else clean
        result = propose_file_write(filename, content + ("" if content.endswith("\n") else "\n"), "Requested through ARC chat")
        reply = result.get("error") or f"I prepared a write to {filename}. Nothing will be written until you approve it below."
    elif re.search(r"(?i)turn (?:this|the following) text into", clean) or ("checklist" in low and "save" in low):
        tool = "propose_text_asset"
        kind = next((x for x in ASSET_TYPES if x in low), "checklist")
        source = clean.split(":", 1)[1].strip() if ":" in clean else re.split(r"(?i)\band save(?: it)?\b", clean, maxsplit=1)[0]
        source = re.sub(r"(?i)^.*?turn (?:this|the following) text into (?:a |an )?\w+[:\s-]*", "", source).strip() or clean
        result = text_to_asset(source, kind, "ARC Checklist" if kind == "checklist" else "ARC Asset")
        reply = result.get("error") or f"I prepared a {kind}. Review the proposal below; nothing will be written until you approve it."
    elif re.search(r"\b(list|show)\b.*\b(files?|workspace)\b", low):
        tool = "list_workspace"; result = workspace_browser("", 2)
        reply = "Workspace contains: " + ", ".join(x["path"] for x in result.get("items", [])[:40])
    elif web_enabled and re.search(r"\b(web|online|internet|latest|current)\b", low):
        if not OPENAI_CONFIGURED:
            tool = "web_search"; result = {"error": "OpenAI is not configured for web search."}; reply = result["error"]
        else:
            tool = "web_search"; result = {"response": run_arc(clean, True)}; reply = result["response"]
    elif OPENAI_CONFIGURED:
        tool = "arc_reasoning"; result = {"response": run_arc(clean, web_enabled)}; reply = result["response"]
    else:
        result = {"error": "No local route matched."}
        reply = "I can calculate, list or search workspace files, read text files, check Python files, report ARC database totals, and create approval-gated text assets."
    pending_id = result.get("pending_action_id") if isinstance(result, dict) else None
    return {"reply": redact(reply), "tool": tool, "tool_result": result, "pending_action_id": pending_id}

TOOLS = [
    {"type": "function", "name": "workspace_browser", "description": "List files within the ARC workspace.", "parameters": {"type": "object", "properties": {"relative_path": {"type": "string"}, "max_depth": {"type": "integer"}}, "required": []}},
    {"type": "function", "name": "file_reader", "description": "Read a privacy-filtered UTF-8 workspace file.", "parameters": {"type": "object", "properties": {"relative_path": {"type": "string"}}, "required": ["relative_path"]}},
    {"type": "function", "name": "file_search", "description": "Search text in workspace files.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "glob": {"type": "string"}}, "required": ["query"]}},
    {"type": "function", "name": "calculator", "description": "Safely evaluate basic arithmetic.", "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}},
    {"type": "function", "name": "python_code_check", "description": "Parse and compile-check Python without executing it.", "parameters": {"type": "object", "properties": {"code": {"type": "string"}, "relative_path": {"type": "string"}}, "required": []}},
    {"type": "function", "name": "arc_database_summary", "description": "Return aggregate local ARC database counts.", "parameters": {"type": "object", "properties": {}, "required": []}},
    {"type": "function", "name": "text_to_asset", "description": "Transform text to an asset and create a save approval.", "parameters": {"type": "object", "properties": {"raw_text": {"type": "string"}, "asset_type": {"type": "string"}, "title": {"type": "string"}}, "required": ["raw_text", "asset_type"]}},
    {"type": "function", "name": "propose_file_write", "description": "Propose a workspace text write; never writes until approved.", "parameters": {"type": "object", "properties": {"relative_path": {"type": "string"}, "content": {"type": "string"}, "reason": {"type": "string"}}, "required": ["relative_path", "content", "reason"]}},
]

SYSTEM_PROMPT = """You are ARC, one local AI command center. Use real tools and never invent status.
All file access is workspace-restricted. Never reveal credentials or secrets. File writes must use the approval tool.
Web Search is available only when the current request explicitly enables it. Be concise and distinguish facts from inference."""


def run_arc(prompt: str, web_enabled: bool = False) -> str:
    if not OPENAI_CONFIGURED:
        raise RuntimeError("OpenAI is not configured. Local tools and Text → Asset remain available.")
    prompt = redact(prompt[:MAX_PROMPT_CHARS])
    calls, _, _, tokens = usage_today()
    if calls >= DAILY_API_CALL_LIMIT:
        raise RuntimeError(f"Daily API request limit reached ({DAILY_API_CALL_LIMIT}).")
    if tokens >= DAILY_TOKEN_LIMIT:
        raise RuntimeError(f"Daily API token limit reached ({DAILY_TOKEN_LIMIT}).")
    from openai import OpenAI
    client = OpenAI()
    tools = list(TOOLS)
    if web_enabled:
        tools.append({"type": "web_search_preview"})

    def create(**kwargs: Any):
        if usage_today()[0] >= DAILY_API_CALL_LIMIT:
            raise RuntimeError("Daily API request limit reached during tool loop.")
        response = client.responses.create(**kwargs)
        usage = getattr(response, "usage", None)
        inp = int(getattr(usage, "input_tokens", 0) or 0)
        out = int(getattr(usage, "output_tokens", 0) or 0)
        total = int(getattr(usage, "total_tokens", inp + out) or 0)
        with _DB_LOCK:
            con = db(); con.execute("INSERT INTO api_usage(created,model,input_tokens,output_tokens,total_tokens) VALUES(?,?,?,?,?)", (now(), MODEL, inp, out, total)); con.commit(); con.close()
        return response

    response = create(model=MODEL, input=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}], tools=tools, max_output_tokens=MAX_OUTPUT_TOKENS)
    for _ in range(MAX_TOOL_LOOPS):
        function_calls = [x for x in response.output if getattr(x, "type", None) == "function_call"]
        if not function_calls:
            return redact(response.output_text or "ARC returned no text result.")
        outputs = []
        for call in function_calls:
            try:
                args = json.loads(call.arguments or "{}")
                result = TOOL_FUNCTIONS.get(call.name, lambda **_: {"error": "Unknown tool."})(**args)
            except Exception as exc:
                result = {"error": redact(exc)}
            outputs.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result, ensure_ascii=False)})
        response = create(model=MODEL, previous_response_id=response.id, input=outputs, tools=tools, max_output_tokens=MAX_OUTPUT_TOKENS)
    return "ARC stopped at the configured tool-loop limit."


db().close()
