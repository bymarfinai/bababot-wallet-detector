from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from research.wallet_s1_data_foundation import validate_solana_address

STAGE7_VERSION = "wallet-s7-v1"
STAGE4_VERSION = "wallet-s4-v1"
STAGE5_VERSION = "wallet-s5-v1"
STAGE6_VERSION = "wallet-s6-v1"
CHAIN = "solana"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _validate_source_version(
    source: dict[str, Any] | None,
    expected_version: str,
    source_name: str,
) -> None:
    if source is None:
        return
    actual = str(source.get("version") or "")
    if actual != expected_version:
        raise ValueError(
            f"unsupported {source_name} version: {actual!r}; "
            f"expected {expected_version!r}"
        )


def _verify_record_fingerprint(row: dict[str, Any]) -> None:
    actual = str(row.get("record_fingerprint") or "")
    if not actual:
        raise ValueError(
            f"registry record missing fingerprint for {row.get('wallet')}"
        )
    core = {
        key: value
        for key, value in row.items()
        if key != "record_fingerprint"
    }
    expected = _fingerprint(core)
    if actual != expected:
        raise ValueError(
            f"registry record fingerprint mismatch for {row.get('wallet')}"
        )


def _wallet_of(value: dict[str, Any] | None) -> str | None:
    if not value:
        return None
    wallet = str(value.get("wallet") or "").strip()
    return wallet or None


def _validate_same_wallet(
    wallet: str,
    *,
    performance: dict[str, Any] | None,
    classification: dict[str, Any],
    meme_profile: dict[str, Any] | None,
    explosion_profile: dict[str, Any] | None,
) -> None:
    sources = {
        "performance": _wallet_of(performance),
        "classification": _wallet_of(classification),
        "meme_profile": _wallet_of(meme_profile),
        "explosion_profile": _wallet_of(explosion_profile),
    }
    mismatches = {
        source: source_wallet
        for source, source_wallet in sources.items()
        if source_wallet is not None and source_wallet != wallet
    }
    if mismatches:
        raise ValueError(
            f"wallet identity mismatch for {wallet}: {mismatches}"
        )


def _performance_summary(
    performance: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not performance:
        return None

    usd = performance.get("usd_comparable") or {}
    activity = performance.get("activity") or {}
    readiness = performance.get("qualification_readiness") or {}

    return {
        "version": performance.get("version"),
        "performance_available": bool(performance.get("performance_available")),
        "closed_trade_count": int(performance.get("closed_trade_count") or 0),
        "win_rate_pct": performance.get("win_rate_pct"),
        "median_roi_pct": performance.get("median_roi_pct"),
        "median_holding_seconds": performance.get("median_holding_seconds"),
        "distinct_base_assets": int(performance.get("distinct_base_assets") or 0),
        "quote_assets": list(performance.get("quote_assets") or []),
        "usd_net_metrics_complete": bool(usd.get("net_metrics_complete")),
        "usd_net_median_roi_pct": usd.get("net_median_roi_pct"),
        "usd_net_win_rate_pct": usd.get("net_win_rate_pct"),
        "usd_net_total_realized_pnl": usd.get(
            "net_total_realized_pnl_usd_stable"
        ),
        "active_days": int(activity.get("active_days") or 0),
        "trades_per_active_day": activity.get("trades_per_active_day"),
        "net_classification_ready": bool(
            readiness.get("net_classification_ready")
        ),
    }


def _meme_summary(
    meme_profile: dict[str, Any] | None,
    explosion_profile: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not meme_profile and not explosion_profile:
        return None

    buckets: dict[str, Any] = {}
    if meme_profile:
        for key, raw in sorted((meme_profile.get("buckets") or {}).items()):
            buckets[str(key)] = {
                "eligible_buys": int(raw.get("eligible_buys") or 0),
                "hit_buys": int(raw.get("hit_buys") or 0),
                "miss_buys": int(raw.get("miss_buys") or 0),
                "incomplete_buys": int(raw.get("incomplete_buys") or 0),
                "hit_rate_buy_pct": raw.get("hit_rate_buy_pct"),
                "eligible_distinct_tokens": int(
                    raw.get("eligible_distinct_tokens") or 0
                ),
                "hit_distinct_tokens": int(raw.get("hit_distinct_tokens") or 0),
                "hit_rate_token_pct": raw.get("hit_rate_token_pct"),
                "median_hit_lead_seconds": raw.get(
                    "median_hit_lead_seconds"
                ),
            }

    return {
        "version": (
            meme_profile.get("version")
            if meme_profile
            else explosion_profile.get("version")
        ),
        "evidence_profile_available": bool(
            meme_profile and meme_profile.get("profile_available")
        ),
        "label_status": (
            meme_profile.get("label_status")
            if meme_profile
            else "EVIDENCE_PROFILE_ONLY"
        ),
        "input_buy_count": int(
            (meme_profile or {}).get("input_buy_count") or 0
        ),
        "evaluated_buy_count": int(
            (meme_profile or {}).get("evaluated_buy_count") or 0
        ),
        "distinct_tokens_bought": int(
            (meme_profile or {}).get("distinct_tokens_bought") or 0
        ),
        "buckets": buckets,
        "matched_explosion_events": int(
            (explosion_profile or {}).get("matched_explosion_events") or 0
        ),
        "matched_distinct_tokens": int(
            (explosion_profile or {}).get("matched_distinct_tokens") or 0
        ),
        "median_first_entry_lead_seconds": (
            (explosion_profile or {}).get(
                "median_first_entry_lead_seconds"
            )
        ),
        "median_last_entry_lead_seconds": (
            (explosion_profile or {}).get(
                "median_last_entry_lead_seconds"
            )
        ),
    }


def _derive_registry_status(
    classification: dict[str, Any],
) -> tuple[str, bool, str]:
    status = str(classification.get("status") or "")

    if status == "QUALIFIED":
        return (
            "ACTIVE",
            True,
            "STAGE5_QUALIFIED",
        )
    if status == "UNQUALIFIED":
        return (
            "UNQUALIFIED",
            False,
            "STAGE5_UNQUALIFIED",
        )
    if status == "NOT_READY":
        return (
            "NOT_READY",
            False,
            str(classification.get("reason") or "STAGE5_NOT_READY"),
        )

    raise ValueError(f"unsupported Stage 5 classification status: {status!r}")


def build_registry_record(
    *,
    wallet: str,
    classification: dict[str, Any],
    performance: dict[str, Any] | None = None,
    meme_profile: dict[str, Any] | None = None,
    explosion_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one deterministic wallet registry record.

    Stage 7 adds no qualification rule. Live eligibility is inherited strictly
    from Stage 5 classification.
    """
    wallet = validate_solana_address(wallet)
    _validate_source_version(
        performance,
        STAGE4_VERSION,
        "Stage 4 performance",
    )
    _validate_source_version(
        classification,
        STAGE5_VERSION,
        "Stage 5 classification",
    )
    _validate_source_version(
        meme_profile,
        STAGE6_VERSION,
        "Stage 6 meme profile",
    )
    _validate_source_version(
        explosion_profile,
        STAGE6_VERSION,
        "Stage 6 explosion profile",
    )
    _validate_same_wallet(
        wallet,
        performance=performance,
        classification=classification,
        meme_profile=meme_profile,
        explosion_profile=explosion_profile,
    )

    registry_status, live_eligible, eligibility_reason = (
        _derive_registry_status(classification)
    )

    qualifying_segments = list(
        classification.get("qualifying_segments") or []
    )
    primary_segment = classification.get("primary_segment")

    if live_eligible and (
        performance is None
        or not bool(performance.get("performance_available"))
    ):
        raise ValueError(
            "qualified wallet requires an available Stage 4 performance source"
        )
    if live_eligible and not qualifying_segments:
        raise ValueError(
            "qualified wallet has no qualifying Stage 5 segments"
        )
    if live_eligible and primary_segment not in qualifying_segments:
        raise ValueError(
            "primary Stage 5 segment is not present in qualifying segments"
        )

    record_core = {
        "version": STAGE7_VERSION,
        "chain": CHAIN,
        "wallet": wallet,
        "registry_status": registry_status,
        "live_monitor_eligible": live_eligible,
        "eligibility_reason": eligibility_reason,
        "primary_segment": primary_segment,
        "qualifying_segments": qualifying_segments,
        "classification": {
            "version": classification.get("version"),
            "status": classification.get("status"),
            "basis": classification.get("basis"),
            "segments": classification.get("segments"),
            "thresholds": classification.get("thresholds"),
            "risk_note": classification.get("risk_note"),
        },
        "performance_summary": _performance_summary(performance),
        "meme_hunter_evidence": _meme_summary(
            meme_profile,
            explosion_profile,
        ),
        "special_labels": {
            "meme_hunter": (
                (meme_profile or {}).get(
                    "label_status",
                    "NO_STAGE6_EVIDENCE",
                )
            ),
            "whale": "DEFERRED_UNTIL_RELIABLE_CAPITAL_DATA",
        },
        "source_versions": {
            "stage4": (
                performance.get("version") if performance else None
            ),
            "stage5": classification.get("version"),
            "stage6_meme": (
                meme_profile.get("version") if meme_profile else None
            ),
            "stage6_explosion": (
                explosion_profile.get("version")
                if explosion_profile
                else None
            ),
        },
    }

    return {
        **record_core,
        "record_fingerprint": _fingerprint(record_core),
    }


def build_registry_snapshot(
    records: Iterable[dict[str, Any]],
    *,
    snapshot_id: str,
) -> dict[str, Any]:
    """Build one immutable, deterministic registry snapshot."""
    snapshot_id = str(snapshot_id or "").strip()
    if not snapshot_id:
        raise ValueError("snapshot_id is required")

    by_wallet: dict[str, dict[str, Any]] = {}
    for raw in records:
        row = dict(raw)
        wallet = validate_solana_address(str(row.get("wallet") or ""))
        if wallet in by_wallet:
            raise ValueError(f"duplicate wallet in registry snapshot: {wallet}")
        if str(row.get("version") or "") != STAGE7_VERSION:
            raise ValueError(
                f"unsupported registry record version for {wallet}"
            )
        _verify_record_fingerprint(row)
        by_wallet[wallet] = row

    ordered = [by_wallet[wallet] for wallet in sorted(by_wallet)]
    active_wallets = [
        row["wallet"]
        for row in ordered
        if bool(row.get("live_monitor_eligible"))
        and row.get("registry_status") == "ACTIVE"
    ]

    status_counts: dict[str, int] = {}
    segment_counts: dict[str, int] = {}
    for row in ordered:
        status = str(row.get("registry_status") or "")
        status_counts[status] = status_counts.get(status, 0) + 1
        for segment in row.get("qualifying_segments") or []:
            key = str(segment)
            segment_counts[key] = segment_counts.get(key, 0) + 1

    snapshot_core = {
        "version": STAGE7_VERSION,
        "snapshot_id": snapshot_id,
        "chain": CHAIN,
        "record_count": len(ordered),
        "active_wallet_count": len(active_wallets),
        "active_wallets": active_wallets,
        "status_counts": dict(sorted(status_counts.items())),
        "segment_counts": dict(sorted(segment_counts.items())),
        "records": ordered,
    }

    return {
        **snapshot_core,
        "snapshot_fingerprint": _fingerprint(snapshot_core),
    }


def verify_registry_snapshot(snapshot: dict[str, Any]) -> bool:
    """Verify the complete Stage-7 snapshot, including every record fingerprint."""
    if str(snapshot.get("version") or "") != STAGE7_VERSION:
        raise ValueError("unsupported registry snapshot version")

    snapshot_id = str(snapshot.get("snapshot_id") or "").strip()
    if not snapshot_id:
        raise ValueError("registry snapshot_id is required")

    expected = build_registry_snapshot(
        snapshot.get("records") or [],
        snapshot_id=snapshot_id,
    )
    if snapshot != expected:
        raise ValueError("registry snapshot integrity mismatch")
    return True


def upsert_registry_records(
    existing_records: Iterable[dict[str, Any]],
    new_records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace records by wallet without creating duplicate registry identities."""
    merged: dict[str, dict[str, Any]] = {}

    for raw in list(existing_records) + list(new_records):
        row = dict(raw)
        wallet = validate_solana_address(str(row.get("wallet") or ""))
        if str(row.get("version") or "") != STAGE7_VERSION:
            raise ValueError(f"unsupported registry record version for {wallet}")
        _verify_record_fingerprint(row)
        merged[wallet] = row

    return [merged[wallet] for wallet in sorted(merged)]
