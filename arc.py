"""ARC local browser chat command center."""
import base64, html, io, json, os, secrets, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import arc_core as core
import arc_wallet

AUTH_TOKEN=os.getenv("ARC_AUTH_TOKEN","")
if core.ENV_MODE=="production" and not AUTH_TOKEN: raise RuntimeError("ARC_AUTH_TOKEN is required in production.")
def esc(x): return html.escape(core.redact(x))
def status(): return {**core.database_summary(),"openai":core.OPENAI_CONFIGURED,"discord":bool(os.getenv("DISCORD_BOT_TOKEN") and os.getenv("ARC_DISCORD_CHANNEL_ID")),"privacy":core.PRIVACY_MODE}

def approval_card(action_id):
    con=core.db(); row=con.execute("SELECT target,payload,reason,status FROM pending_actions WHERE id=?",(action_id,)).fetchone(); con.close()
    if not row: return ""
    target,payload,reason,state=row; asset=reason.startswith("Text → Asset:"); title=payload.splitlines()[0].lstrip("# ") if payload else target
    meta='<div class="proposal">'
    if asset: meta+=f'<b>Proposed title</b><span>{esc(title)}</span><b>Asset type</b><span>{esc(reason.split(":",1)[1].strip())}</span>'
    meta+=f'<b>Proposed filename</b><span>{esc(target)}</span><b>Preview</b><pre>{esc(payload[:2000])}</pre></div>'
    if state=="pending": meta+=f'<div class="actions"><form method="post" action="/approve"><input type="hidden" name="id" value="{action_id}"><button class="approve">Approve</button></form><form method="post" action="/reject"><input type="hidden" name="id" value="{action_id}"><button class="reject">Reject</button></form></div>'
    else: meta+=f'<small>Action {esc(state)}</small>'
    return f'<div class="approval"><strong>Approval required</strong>{meta}</div>'

def page(notice=""):
    s=status(); chat=[]; wallet_intent=None
    for m in core.chat_history(100):
        if m["role"]=="tool":
            chat.append(f'<details class="toolmsg"><summary>{esc(m["content"])}</summary><pre>{esc(m["tool_status"])}</pre></details>')
            if m["tool_name"]=="arc_wallet":
                try: wallet_intent=json.loads(m["tool_status"]).get("wallet_action")
                except (ValueError, TypeError): pass
        else:
            label="You" if m["role"]=="user" else "ARC"; extra=approval_card(m["pending_action_id"]) if m["pending_action_id"] else ""
            chat.append(f'<article class="msg {m["role"]}"><b>{label}</b><div>{esc(m["content"])}</div>{extra}</article>')
    if not chat: chat.append('<div class="empty">Ask ARC naturally. It will choose and run the right tool.</div>')
    tools=[("list_workspace","Workspace listing"),("read_text_file","File reader"),("search_workspace","Workspace search"),("calculator","Calculator"),("check_python_file","Code check"),("arc_database_summary","ARC database"),("propose_text_asset","Text → Asset"),("propose_file_write","File writer")]
    palette=''.join(f'<div><i></i><b>{n}</b><small>{d}</small></div>' for n,d in tools)
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ARC Chat</title><link rel="stylesheet" href="/assets/wallet.css"><style>
:root{{--bg:#030812;--line:#184b70;--cyan:#24dbea;--text:#d9efff;--muted:#7893aa;--green:#28d6a0;--red:#ff6f86}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px Segoe UI,Arial}}.app{{max-width:1300px;margin:auto;padding:18px}}header{{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #258fe2;padding:10px 0 16px}}h1{{margin:0;letter-spacing:.12em}}.badge{{border:1px solid var(--green);color:var(--green);padding:5px 9px;border-radius:20px}}.layout{{display:grid;grid-template-columns:minmax(0,3fr) minmax(260px,1fr);gap:14px;margin-top:14px}}.panel{{background:linear-gradient(160deg,#081728,#030a13);border:1px solid var(--line);border-radius:9px;padding:14px}}.chat{{height:62vh;overflow:auto;padding:8px;display:flex;flex-direction:column;gap:10px}}.msg{{max-width:84%;padding:12px 14px;border-radius:12px;line-height:1.5;white-space:pre-wrap}}.msg.user{{align-self:flex-end;background:#123c61}}.msg.assistant{{align-self:flex-start;background:#0b2535;border:1px solid #18728b}}.msg b{{display:block;color:var(--cyan);font-size:11px;margin-bottom:5px}}.toolmsg{{background:#06101c;border-left:3px solid var(--cyan);padding:8px 12px;color:var(--muted)}}summary{{cursor:pointer;color:#9cc5da}}pre{{white-space:pre-wrap;max-height:220px;overflow:auto;color:#a9c6d7}}.composer{{border-top:1px solid var(--line);padding-top:12px}}textarea{{width:100%;min-height:72px;resize:vertical;background:#020a14;color:var(--text);border:1px solid #23628d;border-radius:8px;padding:11px}}.controls{{display:flex;align-items:center;justify-content:space-between;margin-top:8px}}label{{color:var(--muted)}}input[type=checkbox]{{accent-color:var(--cyan)}}button{{cursor:pointer;border:1px solid #278ee0;background:#0b3152;color:white;border-radius:6px;padding:9px 15px;font-weight:700}}.palette>div{{padding:10px 3px;border-bottom:1px solid #153954}}.palette b,.palette small{{display:block;margin-left:17px}}.palette small{{color:var(--muted);margin-top:3px}}.palette i{{float:left;width:8px;height:8px;background:var(--green);border-radius:50%;margin-top:4px}}.statusgrid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:15px}}.stat{{background:#05101c;padding:10px;border:1px solid #123b59}}.stat small{{display:block;color:var(--muted)}}.stat b{{color:var(--cyan)}}.approval{{border:1px solid #835cff;margin-top:10px;padding:10px;background:#130c29}}.proposal{{display:grid;grid-template-columns:130px 1fr;gap:7px;margin-top:9px}}.proposal b{{color:#aa8aff}}.proposal pre{{grid-column:1/3;background:#050a12;padding:8px}}.actions{{display:flex;gap:8px;margin-top:8px}}.actions form{{margin:0}}.approve{{border-color:var(--green);color:var(--green)}}.reject{{border-color:var(--red);color:var(--red)}}.notice{{padding:9px;background:#163a32;margin-top:10px}}.empty{{color:var(--muted);margin:auto}}@media(max-width:800px){{.layout{{grid-template-columns:1fr}}.chat{{height:55vh}}}}
</style></head><body><main class="app"><header><div><h1>ARC // CHAT</h1><small>Local reasoning · automatic tools · approval-gated actions</small></div><span class="badge">PRIVACY {'ON' if s['privacy'] else 'OFF'}</span></header>{f'<div class="notice">{esc(notice)}</div>' if notice else ''}<div class="layout"><section class="panel"><div id="chat" class="chat">{''.join(chat)}</div><form class="composer" method="post" action="/chat"><textarea name="message" maxlength="{core.MAX_PROMPT_CHARS}" placeholder="Message ARC…" required autofocus></textarea><div class="controls"><label><input type="checkbox" name="web_enabled" value="1"> Enable web access for this message</label><button>Send →</button></div></form></section><aside class="panel"><h3>TOOL PALETTE · STATUS</h3><div class="statusgrid"><div class="stat"><small>Local tools</small><b>READY</b></div><div class="stat"><small>Web search</small><b>OPT-IN</b></div><div class="stat"><small>Completed tasks</small><b>{s['tasks_complete']}</b></div><div class="stat"><small>Approvals</small><b>{s['approvals_pending']}</b></div></div><div class="palette">{palette}</div><p><small>Tools are selected automatically. File writes always require approval.</small></p></aside></div><section id="arc-wallet" class="panel wallet-panel"><div class="wallet-head"><div><h2>ARC WALLET</h2><small>Injected EVM wallet · Base Sepolia by default</small></div><div><button id="wallet-refresh">Refresh</button> <button id="wallet-history-btn">History</button></div></div><div id="wallet-state"></div><div class="wallet-grid"><div class="wallet-value"><small>Connection</small><b id="wallet-connection">Not connected</b></div><div class="wallet-value"><small>Wallet address</small><b id="wallet-address">—</b></div><div class="wallet-value"><small>Network</small><b id="wallet-network">—</b></div><div class="wallet-value"><small>Balances</small><b><span id="wallet-eth">—</span><br><span id="wallet-usdc">—</span></b></div></div><div class="wallet-actions"><button id="wallet-connect">Connect Wallet</button><button data-action="pay">Pay</button><button data-action="receive">Receive</button><button data-action="transfer">Transfer</button><button id="wallet-switch-sepolia">Base Sepolia</button><button id="wallet-switch-base">Base</button><button id="wallet-disconnect" hidden>Disconnect</button></div></section></main><div id="wallet-modal" class="wallet-modal" role="dialog" aria-modal="true"><section class="wallet-card"><div class="wallet-modal-head"><h2 id="wallet-modal-title">ARC Wallet</h2><button id="wallet-modal-close" class="wallet-close" aria-label="Close">×</button></div><div id="wallet-modal-body"></div></section></div><script>window.ARC_WALLET_INTENT={json.dumps(wallet_intent)};const c=document.getElementById('chat');c.scrollTop=c.scrollHeight;</script><script src="/assets/wallet.js"></script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    server_version="ARC/2.0"; sys_version=""
    def log_message(self,*_): pass
    def authorized(self):
        if core.ENV_MODE!="production": return True
        try:
            scheme,value=self.headers.get("Authorization","").split(" ",1); user,password=base64.b64decode(value).decode().split(":",1)
            return scheme.lower()=="basic" and secrets.compare_digest(user,"arc") and secrets.compare_digest(password,AUTH_TOKEN)
        except Exception: return False
    def send_bytes(self,data,ctype,code=200):
        self.send_response(code); self.send_header("Content-Type",ctype); self.send_header("Content-Length",str(len(data))); self.send_header("Cache-Control","no-store"); self.send_header("X-Content-Type-Options","nosniff"); self.send_header("X-Frame-Options","DENY"); self.send_header("Content-Security-Policy","default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'"); self.end_headers(); self.wfile.write(data)
    def send_html(self,x,code=200): self.send_bytes(x.encode(),"text/html; charset=utf-8",code)
    def require_auth(self):
        if self.authorized(): return True
        self.send_response(401); self.send_header("WWW-Authenticate",'Basic realm="ARC"'); self.end_headers(); return False
    def redirect(self): self.send_response(303); self.send_header("Location","/"); self.end_headers()
    def do_GET(self):
        parsed=urlparse(self.path); route=parsed.path
        if route=="/health": self.send_bytes(json.dumps({"status":"healthy","privacy_mode":core.PRIVACY_MODE}).encode(),"application/json"); return
        if not self.require_auth(): return
        if route=="/api/status": self.send_bytes(json.dumps(status()).encode(),"application/json"); return
        if route=="/api/wallet/config": self.send_bytes(json.dumps(arc_wallet.public_config()).encode(),"application/json"); return
        if route=="/api/wallet/transactions":
            address=parse_qs(parsed.query).get("address",[""])[0]
            self.send_bytes(json.dumps(arc_wallet.transaction_history(address)).encode(),"application/json"); return
        if route=="/api/wallet/qr":
            address=parse_qs(parsed.query).get("address",[""])[0]
            if not __import__("re").fullmatch(r"0x[0-9a-fA-F]{40}",address): self.send_bytes(b"Invalid address","text/plain",400); return
            try:
                import qrcode
                image=qrcode.make(address); output=io.BytesIO(); image.save(output,format="PNG")
                self.send_bytes(output.getvalue(),"image/png"); return
            except ImportError: self.send_bytes(b"QR support is not installed.","text/plain",503); return
        if route in {"/assets/wallet.css","/assets/wallet.js"}:
            path=core.safe_path(route.lstrip("/")); ctype="text/css" if route.endswith(".css") else "text/javascript"
            self.send_bytes(path.read_bytes(),ctype+"; charset=utf-8"); return
        if route!="/": self.send_error(404); return
        self.send_html(page())
    def do_POST(self):
        if not self.require_auth(): return
        route=urlparse(self.path).path; raw=self.rfile.read(min(int(self.headers.get("Content-Length","0")),1100000))
        if route=="/api/wallet/transactions":
            try:
                result=arc_wallet.record_transaction(json.loads(raw.decode("utf-8")))
                self.send_bytes(json.dumps(result).encode(),"application/json"); return
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_bytes(json.dumps({"error":str(exc)}).encode(),"application/json",400); return
        form=parse_qs(raw.decode("utf-8","replace"))
        if route=="/chat":
            prompt=form.get("message",[""])[0].strip(); web=form.get("web_enabled",[""])[0]=="1"
            if not prompt: self.send_html(page("Enter a message first."),400); return
            core.add_chat_message("user",prompt); con=core.db(); cur=con.execute("INSERT INTO tasks(created,prompt,result,status) VALUES(?,?,?,?)",(core.now(),core.redact(prompt),"","running")); task_id=cur.lastrowid; con.commit(); con.close()
            try:
                routed=core.route_chat(prompt,web); tool=routed["tool"] or "ARC reasoning"
                core.add_chat_message("tool",f"ARC used {tool} · completed",tool,json.dumps(routed["tool_result"],ensure_ascii=False,indent=2)); core.add_chat_message("assistant",routed["reply"],pending_action_id=routed["pending_action_id"]); state="complete"; result=routed["reply"]
            except Exception as exc: state="failed"; result=f"ARC error: {core.redact(exc)}"; core.add_chat_message("assistant",result)
            con=core.db(); con.execute("UPDATE tasks SET result=?,status=? WHERE id=?",(result,state,task_id)); con.commit(); con.close(); core.log_event("chat_"+state,"web enabled" if web else "web disabled"); self.redirect(); return
        if route in {"/approve","/reject"}:
            try: action_id=int(form.get("id",["0"])[0])
            except ValueError: action_id=0
            result=core.apply_pending(action_id) if route=="/approve" else core.reject_pending(action_id); core.add_chat_message("assistant",result); self.redirect(); return
        self.send_error(404)

def start_discord():
    if not(os.getenv("DISCORD_BOT_TOKEN") and os.getenv("ARC_DISCORD_CHANNEL_ID")): return "not configured"
    try:
        from discord_bridge import run_discord
        threading.Thread(target=run_discord,daemon=True).start(); return "starting"
    except Exception as exc: core.log_event("discord_start_failed",str(exc)); return "failed"
def main():
    ds=start_discord(); bind=os.getenv("ARC_BIND","0.0.0.0" if core.ENV_MODE=="production" else "127.0.0.1")
    print(f"ARC running at http://localhost:{core.PORT}"); print(f"Privacy Mode: {'ON' if core.PRIVACY_MODE else 'OFF'} | Discord: {ds}"); ThreadingHTTPServer((bind,core.PORT),Handler).serve_forever()
if __name__=="__main__": main()
