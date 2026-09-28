from __future__ import annotations

from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import Any
import re

STAGE1_VERSION = "wallet-s1-v1"
CHAIN = "solana"
LAMPORTS_PER_SOL = Decimal("1000000000")

_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


@dataclass(frozen=True)
class TokenDelta:
    wallet: str
    mint: str
    raw_delta: int
    decimals: int

    @property
    def ui_delta(self) -> Decimal:
        return Decimal(self.raw_delta) / (Decimal(10) ** self.decimals)

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["ui_delta"] = str(self.ui_delta)
        return row


@dataclass(frozen=True)
class NativeDelta:
    wallet: str
    lamport_delta: int

    @property
    def sol_delta(self) -> Decimal:
        return Decimal(self.lamport_delta) / LAMPORTS_PER_SOL

    def to_dict(self) -> dict[str, Any]:
        return {
            "wallet": self.wallet,
            "lamport_delta": self.lamport_delta,
            "sol_delta": str(self.sol_delta),
        }


def validate_solana_address(address: str) -> str:
    value = str(address or "").strip()
    if not _BASE58_RE.fullmatch(value):
        raise ValueError(f"invalid Solana address: {address!r}")
    return value


def build_helius_gtfa_payload(
    wallet: str,
    *,
    limit: int = 100,
    pagination_token: str | None = None,
    sort_order: str = "asc",
) -> dict[str, Any]:
    """Build the frozen Stage-1 historical backfill request.

    No token/symbol filter is accepted: Stage 1 is wallet-centric and must discover
    every token account balance change belonging to the target wallet.
    """
    wallet = validate_solana_address(wallet)
    if not 1 <= int(limit) <= 100:
        raise ValueError("full-transaction gTFA limit must be between 1 and 100")
    if sort_order not in {"asc", "desc"}:
        raise ValueError("sort_order must be 'asc' or 'desc'")

    options: dict[str, Any] = {
        "transactionDetails": "full",
        "sortOrder": sort_order,
        "limit": int(limit),
        "filters": {
            "status": "succeeded",
            "tokenAccounts": "balanceChanged",
        },
    }
    if pagination_token:
        options["paginationToken"] = pagination_token

    return {
        "jsonrpc": "2.0",
        "id": "wallet-detector-stage1",
        "method": "getTransactionsForAddress",
        "params": [wallet, options],
    }


def _account_keys(tx: dict[str, Any]) -> list[str]:
    transaction = tx.get("transaction") or {}
    message = transaction.get("message") or {}
    keys = message.get("accountKeys") or []
    out: list[str] = []
    for item in keys:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            out.append(str(item.get("pubkey") or ""))
        else:
            out.append("")
    return out


def extract_wallet_token_deltas(tx: dict[str, Any], wallet: str) -> list[TokenDelta]:
    """Aggregate owner-level token deltas from standard Solana transaction metadata.

    This is a Stage-1 data sufficiency check, not yet BUY/SELL normalization.
    """
    wallet = validate_solana_address(wallet)
    meta = tx.get("meta") or {}
    pre = meta.get("preTokenBalances") or []
    post = meta.get("postTokenBalances") or []

    before: dict[str, tuple[int, int]] = {}
    after: dict[str, tuple[int, int]] = {}

    def absorb(rows: list[dict[str, Any]], target: dict[str, tuple[int, int]]) -> None:
        for row in rows:
            if str(row.get("owner") or "") != wallet:
                continue
            mint = str(row.get("mint") or "")
            ui = row.get("uiTokenAmount") or {}
            amount = int(str(ui.get("amount") or "0"))
            decimals = int(ui.get("decimals") or 0)
            old_amount, old_decimals = target.get(mint, (0, decimals))
            if old_decimals != decimals:
                raise ValueError(f"inconsistent decimals for mint {mint}")
            target[mint] = (old_amount + amount, decimals)

    absorb(pre, before)
    absorb(post, after)

    result: list[TokenDelta] = []
    for mint in sorted(set(before) | set(after)):
        pre_amount, pre_decimals = before.get(mint, (0, after[mint][1]))
        post_amount, post_decimals = after.get(mint, (0, pre_decimals))
        if pre_decimals != post_decimals:
            raise ValueError(f"inconsistent decimals for mint {mint}")
        delta = post_amount - pre_amount
        if delta:
            result.append(TokenDelta(wallet, mint, delta, pre_decimals))
    return result


def extract_wallet_native_delta(tx: dict[str, Any], wallet: str) -> NativeDelta | None:
    """Return the wallet's raw lamport balance change when the wallet is an account key."""
    wallet = validate_solana_address(wallet)
    keys = _account_keys(tx)
    try:
        idx = keys.index(wallet)
    except ValueError:
        return None

    meta = tx.get("meta") or {}
    pre = meta.get("preBalances") or []
    post = meta.get("postBalances") or []
    if idx >= len(pre) or idx >= len(post):
        return None
    return NativeDelta(wallet=wallet, lamport_delta=int(post[idx]) - int(pre[idx]))


def stage1_sufficiency_report(tx: dict[str, Any], wallet: str) -> dict[str, Any]:
    """Small deterministic probe proving raw data can feed Stage 2."""
    transaction = tx.get("transaction") or {}
    sigs = transaction.get("signatures") or []
    signature = str(sigs[0]) if sigs else ""

    deltas = extract_wallet_token_deltas(tx, wallet)
    native = extract_wallet_native_delta(tx, wallet)

    return {
        "version": STAGE1_VERSION,
        "chain": CHAIN,
        "wallet": validate_solana_address(wallet),
        "signature": signature,
        "slot": tx.get("slot"),
        "block_time": tx.get("blockTime"),
        "token_delta_count": len(deltas),
        "token_deltas": [d.to_dict() for d in deltas],
        "native_delta": native.to_dict() if native else None,
        "sufficient_for_stage2": bool(
            signature
            and tx.get("slot") is not None
            and (deltas or native)
        ),
    }
