"""Public EVM wallet configuration and local ARC transaction metadata."""
from __future__ import annotations

import os
import re
from typing import Any

import arc_core as core

NETWORKS = {
    8453: {
        "key": "base", "name": "Base", "chainId": 8453, "chainHex": "0x2105",
        "rpc": os.getenv("ARC_WALLET_BASE_RPC", "https://mainnet.base.org"),
        "explorer": "https://basescan.org", "native": {"symbol": "ETH", "decimals": 18},
        "usdc": {"symbol": "USDC", "decimals": 6, "address": os.getenv(
            "ARC_WALLET_BASE_USDC", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")},
    },
    84532: {
        "key": "base-sepolia", "name": "Base Sepolia", "chainId": 84532, "chainHex": "0x14a34",
        "rpc": os.getenv("ARC_WALLET_BASE_SEPOLIA_RPC", "https://sepolia.base.org"),
        "explorer": "https://sepolia.basescan.org", "native": {"symbol": "ETH", "decimals": 18},
        "usdc": {"symbol": "USDC", "decimals": 6, "address": os.getenv(
            "ARC_WALLET_BASE_SEPOLIA_USDC", "0x036CbD53842c5426634e7929541eC2318f3dCF7e")},
    },
}

def selected_chain_id() -> int:
    return 8453 if os.getenv("ARC_WALLET_NETWORK", "base-sepolia").strip().lower() == "base" else 84532

def public_config() -> dict[str, Any]:
    return {
        "selectedChainId": selected_chain_id(), "networks": NETWORKS,
        "walletConnectConfigured": bool(os.getenv("ARC_WALLETCONNECT_PROJECT_ID", "").strip()),
    }

def init_db() -> None:
    con = core.db()
    con.execute("""CREATE TABLE IF NOT EXISTS wallet_transactions(
        hash TEXT PRIMARY KEY, created TEXT NOT NULL, wallet_address TEXT NOT NULL,
        chain_id INTEGER NOT NULL, asset TEXT NOT NULL, amount TEXT NOT NULL,
        recipient TEXT NOT NULL, status TEXT NOT NULL, explorer_url TEXT NOT NULL)""")
    con.commit(); con.close()

def record_transaction(item: dict[str, Any]) -> dict[str, Any]:
    tx_hash = str(item.get("hash", ""))
    address = str(item.get("walletAddress", ""))
    recipient = str(item.get("recipient", ""))
    chain_id = int(item.get("chainId", 0) or 0)
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", tx_hash): raise ValueError("Invalid transaction hash.")
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", recipient):
        raise ValueError("Invalid wallet address.")
    if chain_id not in NETWORKS: raise ValueError("Unsupported network.")
    asset = str(item.get("asset", "")).upper()
    if asset not in {"ETH", "USDC"}: raise ValueError("Unsupported asset.")
    amount = str(item.get("amount", "")).strip()
    if not re.fullmatch(r"(?:0|[1-9]\d*)(?:\.\d{1,18})?", amount) or len(amount) > 80:
        raise ValueError("Invalid transaction amount.")
    status = str(item.get("status", "pending")).lower()
    if status not in {"pending", "confirmed", "failed"}: raise ValueError("Invalid transaction status.")
    network = NETWORKS[chain_id]
    explorer = f'{network["explorer"]}/tx/{tx_hash}'
    con = core.db(); con.execute("""INSERT INTO wallet_transactions
        (hash,created,wallet_address,chain_id,asset,amount,recipient,status,explorer_url)
        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(hash) DO UPDATE SET status=excluded.status""",
        (tx_hash, core.now(), address, chain_id, asset, amount, recipient, status, explorer))
    con.commit(); con.close()
    return {"ok": True, "explorerUrl": explorer}

def transaction_history(address: str = "", limit: int = 20) -> list[dict[str, Any]]:
    init_db(); con = core.db()
    sql = "SELECT hash,created,wallet_address,chain_id,asset,amount,recipient,status,explorer_url FROM wallet_transactions"
    args: list[Any] = []
    if address:
        sql += " WHERE lower(wallet_address)=lower(?)"; args.append(address)
    sql += " ORDER BY created DESC LIMIT ?"; args.append(max(1, min(int(limit), 100)))
    rows = con.execute(sql, args).fetchall(); con.close()
    keys = ("hash","created","walletAddress","chainId","asset","amount","recipient","status","explorerUrl")
    return [dict(zip(keys, row)) for row in rows]

init_db()
