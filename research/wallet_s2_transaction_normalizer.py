from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from research.wallet_s1_data_foundation import (
    CHAIN,
    LAMPORTS_PER_SOL,
    _account_keys,
    extract_wallet_native_delta,
    extract_wallet_token_deltas,
    validate_solana_address,
)

STAGE2_VERSION = "wallet-s2-v1"
NATIVE_SOL = "SOL_NATIVE"
WSOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
DEFAULT_USD_STABLE_MINTS = frozenset({USDC_MINT, USDT_MINT})


@dataclass(frozen=True)
class AssetDelta:
    asset_id: str
    asset_type: str
    raw_delta: int
    decimals: int
    amount: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "raw_delta": self.raw_delta,
            "decimals": self.decimals,
            "amount": str(self.amount),
        }


def _decimal_or_none(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _signature(tx: dict[str, Any]) -> str:
    transaction = tx.get("transaction") or {}
    sigs = transaction.get("signatures") or []
    return str(sigs[0]) if sigs else ""


def _fee_payer_is_wallet(tx: dict[str, Any], wallet: str) -> bool:
    keys = _account_keys(tx)
    return bool(keys and keys[0] == wallet)


def extract_economic_deltas(tx: dict[str, Any], wallet: str) -> list[AssetDelta]:
    """Return wallet-level net asset changes with the network fee removed from SOL.

    This intentionally does not attempt to remove rent deposits/refunds. Those are
    surfaced as a lower confidence note when native SOL is used as a swap leg.
    """
    wallet = validate_solana_address(wallet)
    deltas: list[AssetDelta] = []

    for row in extract_wallet_token_deltas(tx, wallet):
        deltas.append(
            AssetDelta(
                asset_id=row.mint,
                asset_type="TOKEN",
                raw_delta=row.raw_delta,
                decimals=row.decimals,
                amount=row.ui_delta,
            )
        )

    native = extract_wallet_native_delta(tx, wallet)
    if native is not None:
        fee = int((tx.get("meta") or {}).get("fee") or 0)
        economic_lamports = native.lamport_delta
        if _fee_payer_is_wallet(tx, wallet):
            economic_lamports += fee
        if economic_lamports:
            deltas.append(
                AssetDelta(
                    asset_id=NATIVE_SOL,
                    asset_type="NATIVE",
                    raw_delta=economic_lamports,
                    decimals=9,
                    amount=Decimal(economic_lamports) / LAMPORTS_PER_SOL,
                )
            )

    return sorted(deltas, key=lambda row: (row.asset_type, row.asset_id))


def _is_sol(asset_id: str) -> bool:
    return asset_id in {NATIVE_SOL, WSOL_MINT}


def _is_wrap_pair(a: AssetDelta, b: AssetDelta) -> bool:
    if {a.asset_id, b.asset_id} != {NATIVE_SOL, WSOL_MINT}:
        return False
    if a.amount == 0 or b.amount == 0 or (a.amount > 0) == (b.amount > 0):
        return False
    mismatch = abs(abs(a.amount) - abs(b.amount))
    return mismatch <= Decimal("0.01")


def _quote_priority(asset_id: str, usd_stables: set[str]) -> int | None:
    if asset_id in usd_stables:
        return 0
    if _is_sol(asset_id):
        return 1
    return None


def _normalize_swap(
    negative: AssetDelta,
    positive: AssetDelta,
    usd_stables: set[str],
) -> dict[str, Any]:
    neg_rank = _quote_priority(negative.asset_id, usd_stables)
    pos_rank = _quote_priority(positive.asset_id, usd_stables)

    if neg_rank is not None and (pos_rank is None or neg_rank < pos_rank):
        quote, base, side = negative, positive, "BUY"
    elif pos_rank is not None and (neg_rank is None or pos_rank < neg_rank):
        quote, base, side = positive, negative, "SELL"
    elif neg_rank is not None and pos_rank is not None:
        quote, base, side = negative, positive, "SWAP"
    else:
        quote, base, side = negative, positive, "SWAP"

    base_amount = abs(base.amount)
    quote_amount = abs(quote.amount)
    execution_price = quote_amount / base_amount if base_amount else None
    quote_is_usd = quote.asset_id in usd_stables
    usd_notional = quote_amount if quote_is_usd else None

    pricing_quality = "TOKEN_TO_TOKEN"
    confidence = "MEDIUM"
    notes: list[str] = []
    if quote_is_usd:
        pricing_quality = "DIRECT_USD_EXECUTION"
        confidence = "HIGH"
    elif quote.asset_id == WSOL_MINT:
        pricing_quality = "DIRECT_WSOL_EXECUTION"
        confidence = "HIGH"
    elif quote.asset_id == NATIVE_SOL:
        pricing_quality = "NET_NATIVE_SOL_EXECUTION"
        confidence = "MEDIUM"
        notes.append("native SOL quote may include rent/account lifecycle effects")

    return {
        "side": side,
        "input_asset": negative.asset_id,
        "input_amount": str(abs(negative.amount)),
        "output_asset": positive.asset_id,
        "output_amount": str(abs(positive.amount)),
        "base_asset": base.asset_id,
        "base_amount": str(base_amount),
        "quote_asset": quote.asset_id,
        "quote_amount": str(quote_amount),
        "execution_price_quote": _decimal_or_none(execution_price),
        "quote_is_usd": quote_is_usd,
        "usd_notional": _decimal_or_none(usd_notional),
        "pricing_quality": pricing_quality,
        "confidence": confidence,
        "notes": notes,
    }


def normalize_transaction(
    tx: dict[str, Any],
    wallet: str,
    *,
    usd_stable_mints: Iterable[str] = DEFAULT_USD_STABLE_MINTS,
) -> dict[str, Any]:
    wallet = validate_solana_address(wallet)
    meta = tx.get("meta") or {}
    fee = int(meta.get("fee") or 0)
    common = {
        "version": STAGE2_VERSION,
        "chain": CHAIN,
        "wallet": wallet,
        "signature": _signature(tx),
        "slot": tx.get("slot"),
        "block_time": tx.get("blockTime"),
        "network_fee_lamports": fee,
        "fee_payer_is_wallet": _fee_payer_is_wallet(tx, wallet),
    }

    if meta.get("err") is not None:
        return {
            **common,
            "event_type": "FAILED",
            "side": "NONE",
            "asset_deltas": [],
            "confidence": "HIGH",
            "notes": ["failed transaction; ignored for economic reconstruction"],
        }

    deltas = extract_economic_deltas(tx, wallet)
    common["asset_deltas"] = [row.to_dict() for row in deltas]

    if not deltas:
        return {
            **common,
            "event_type": "OTHER",
            "side": "NONE",
            "confidence": "HIGH",
            "notes": ["no wallet-level economic asset delta after fee removal"],
        }

    negatives = [row for row in deltas if row.amount < 0]
    positives = [row for row in deltas if row.amount > 0]

    if len(deltas) == 1:
        row = deltas[0]
        event_type = "TRANSFER_IN" if row.amount > 0 else "TRANSFER_OUT"
        confidence = "HIGH" if row.asset_type == "TOKEN" else "MEDIUM"
        notes = [] if row.asset_type == "TOKEN" else [
            "native-only movement may contain rent/account lifecycle effects"
        ]
        return {
            **common,
            "event_type": event_type,
            "side": "NONE",
            "asset": row.asset_id,
            "amount": str(abs(row.amount)),
            "confidence": confidence,
            "notes": notes,
        }

    if len(deltas) == 2 and len(negatives) == 1 and len(positives) == 1:
        negative, positive = negatives[0], positives[0]
        if _is_wrap_pair(negative, positive):
            event_type = "WRAP" if negative.asset_id == NATIVE_SOL else "UNWRAP"
            return {
                **common,
                "event_type": event_type,
                "side": "NONE",
                "input_asset": negative.asset_id,
                "input_amount": str(abs(negative.amount)),
                "output_asset": positive.asset_id,
                "output_amount": str(abs(positive.amount)),
                "confidence": "HIGH",
                "notes": ["SOL/WSOL conversion; not a market trade"],
            }

        swap = _normalize_swap(negative, positive, set(usd_stable_mints))
        return {**common, "event_type": "SWAP", **swap}

    return {
        **common,
        "event_type": "AMBIGUOUS",
        "side": "NONE",
        "confidence": "LOW",
        "negative_assets": [row.asset_id for row in negatives],
        "positive_assets": [row.asset_id for row in positives],
        "notes": [
            "multiple economic legs; preserve raw deltas and defer protocol-aware resolution"
        ],
    }


def normalize_transactions(
    transactions: Iterable[dict[str, Any]],
    wallet: str,
    *,
    usd_stable_mints: Iterable[str] = DEFAULT_USD_STABLE_MINTS,
) -> list[dict[str, Any]]:
    return [
        normalize_transaction(tx, wallet, usd_stable_mints=usd_stable_mints)
        for tx in transactions
    ]
