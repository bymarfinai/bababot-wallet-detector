from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from statistics import median
from typing import Any, Iterable

STAGE6_VERSION = "wallet-s6-v1"

HORIZONS_SECONDS = {
    "6h": 6 * 60 * 60,
    "24h": 24 * 60 * 60,
    "72h": 72 * 60 * 60,
}
MULTIPLES = {
    "2x": Decimal("2"),
    "5x": Decimal("5"),
    "10x": Decimal("10"),
}
DEFAULT_ENTRY_PRICE_MAX_DELAY_SECONDS = 5 * 60
ZERO = Decimal("0")


def _d(value: Any) -> Decimal:
    return Decimal(str(value))


def _s(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == ZERO:
        return "0"
    return format(value.normalize(), "f")


def _pct(numerator: int, denominator: int) -> str | None:
    if denominator <= 0:
        return None
    return _s(Decimal(numerator) / Decimal(denominator) * Decimal("100"))


def _median_int(values: list[int]) -> int | None:
    if not values:
        return None
    return int(median(values))


def _valid_buys(buys: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_signatures: set[tuple[str, str]] = set()

    for row in buys:
        if str(row.get("event_type") or "") != "SWAP":
            continue
        if str(row.get("side") or "") != "BUY":
            continue
        if not row.get("wallet") or not row.get("base_asset"):
            continue
        if row.get("block_time") is None:
            continue

        signature = str(row.get("signature") or "")
        wallet = str(row.get("wallet") or "")
        if signature:
            dedupe_key = (wallet, signature)
            if dedupe_key in seen_signatures:
                continue
            seen_signatures.add(dedupe_key)
        rows.append(dict(row))

    return sorted(
        rows,
        key=lambda row: (
            int(row["block_time"]),
            int(row.get("slot") or 0),
            str(row.get("signature") or ""),
        ),
    )


def _prepare_prices(
    price_series: dict[str, Iterable[dict[str, Any]]],
) -> dict[str, list[tuple[int, Decimal]]]:
    result: dict[str, list[tuple[int, Decimal]]] = {}

    for token, points in price_series.items():
        by_time: dict[int, Decimal] = {}
        for point in points:
            ts = int(point["timestamp"])
            price = _d(point["price"])
            if price <= ZERO:
                raise ValueError(f"non-positive price for {token} at {ts}")
            by_time[ts] = price
        result[str(token)] = sorted(by_time.items())

    return result


def _entry_reference_price(
    buy: dict[str, Any],
    prices: list[tuple[int, Decimal]],
    *,
    max_delay_seconds: int,
) -> tuple[Decimal | None, str | None, int | None]:
    if bool(buy.get("quote_is_usd")) and buy.get("execution_price_quote") is not None:
        execution_price = _d(buy["execution_price_quote"])
        if execution_price > ZERO:
            return (
                execution_price,
                "WALLET_EXECUTION_USD_STABLE",
                int(buy["block_time"]),
            )

    entry_time = int(buy["block_time"])
    for ts, price in prices:
        if ts < entry_time:
            continue
        if ts - entry_time <= max_delay_seconds:
            return price, "MARKET_SERIES_AT_OR_AFTER_ENTRY", ts
        break

    return None, None, None


def evaluate_buy_outcomes(
    buys: Iterable[dict[str, Any]],
    price_series: dict[str, Iterable[dict[str, Any]]],
    *,
    horizons_seconds: dict[str, int] = HORIZONS_SECONDS,
    multiples: dict[str, Decimal] = MULTIPLES,
    entry_price_max_delay_seconds: int = DEFAULT_ENTRY_PRICE_MAX_DELAY_SECONDS,
) -> list[dict[str, Any]]:
    """Label every valid BUY with forward 2x/5x/10x outcomes.

    A threshold is:
    - HIT when it is observed within the horizon;
    - MISS only when full horizon coverage exists and no hit occurs;
    - INCOMPLETE when no hit is seen but the price series ends too early.

    This prevents truncated data from becoming a false negative.
    """
    if entry_price_max_delay_seconds < 0:
        raise ValueError("entry_price_max_delay_seconds must be >= 0")

    prepared = _prepare_prices(price_series)
    outcomes: list[dict[str, Any]] = []

    for buy in _valid_buys(buys):
        token = str(buy["base_asset"])
        entry_time = int(buy["block_time"])
        points = prepared.get(token, [])
        entry_price, price_source, price_time = _entry_reference_price(
            buy,
            points,
            max_delay_seconds=entry_price_max_delay_seconds,
        )

        common = {
            "version": STAGE6_VERSION,
            "wallet": str(buy["wallet"]),
            "signature": str(buy.get("signature") or ""),
            "token": token,
            "entry_time": entry_time,
            "entry_price": _s(entry_price),
            "entry_price_source": price_source,
            "entry_price_time": price_time,
        }

        if entry_price is None:
            outcomes.append(
                {
                    **common,
                    "status": "NO_ENTRY_PRICE",
                    "horizons": {},
                }
            )
            continue

        future = [(ts, price) for ts, price in points if ts >= entry_time]
        coverage_end = future[-1][0] if future else None
        horizon_output: dict[str, Any] = {}

        for horizon_name, horizon_seconds in horizons_seconds.items():
            horizon_end = entry_time + int(horizon_seconds)
            window = [
                (ts, price)
                for ts, price in future
                if ts <= horizon_end
            ]
            peak_price = max((price for _, price in window), default=entry_price)
            peak_multiple = peak_price / entry_price
            threshold_output: dict[str, Any] = {}

            for multiple_name, multiple in multiples.items():
                target = entry_price * Decimal(multiple)
                hit_point = next(
                    (
                        (ts, price)
                        for ts, price in window
                        if price >= target
                    ),
                    None,
                )
                if hit_point is not None:
                    hit_time, hit_price = hit_point
                    threshold_output[multiple_name] = {
                        "status": "HIT",
                        "hit_time": hit_time,
                        "lead_seconds": hit_time - entry_time,
                        "hit_price": _s(hit_price),
                    }
                elif coverage_end is not None and coverage_end >= horizon_end:
                    threshold_output[multiple_name] = {
                        "status": "MISS",
                        "hit_time": None,
                        "lead_seconds": None,
                        "hit_price": None,
                    }
                else:
                    threshold_output[multiple_name] = {
                        "status": "INCOMPLETE",
                        "hit_time": None,
                        "lead_seconds": None,
                        "hit_price": None,
                    }

            horizon_output[horizon_name] = {
                "horizon_seconds": int(horizon_seconds),
                "coverage_end": coverage_end,
                "full_coverage": (
                    coverage_end is not None and coverage_end >= horizon_end
                ),
                "peak_price_observed": _s(peak_price),
                "peak_multiple_observed": _s(peak_multiple),
                "thresholds": threshold_output,
            }

        outcomes.append(
            {
                **common,
                "status": "EVALUATED",
                "horizons": horizon_output,
            }
        )

    return outcomes


def build_meme_hunter_profile(
    outcomes: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    rows = list(outcomes)
    wallets = sorted({str(row.get("wallet") or "") for row in rows if row.get("wallet")})
    if len(wallets) > 1:
        raise ValueError("meme hunter profile input contains multiple wallets")

    wallet = wallets[0] if wallets else ""
    evaluated = [row for row in rows if row.get("status") == "EVALUATED"]
    no_entry_price = sum(1 for row in rows if row.get("status") == "NO_ENTRY_PRICE")
    bucket_names = [
        (horizon_name, multiple_name)
        for horizon_name in HORIZONS_SECONDS
        for multiple_name in MULTIPLES
    ]
    buckets: dict[str, Any] = {}

    for horizon_name, multiple_name in bucket_names:
        eligible_rows: list[dict[str, Any]] = []
        hit_rows: list[dict[str, Any]] = []
        incomplete_rows: list[dict[str, Any]] = []

        for row in evaluated:
            horizon = (row.get("horizons") or {}).get(horizon_name)
            if not horizon:
                continue
            threshold = (horizon.get("thresholds") or {}).get(multiple_name)
            if not threshold:
                continue

            status = threshold.get("status")
            if status in {"HIT", "MISS"}:
                eligible_rows.append(row)
            elif status == "INCOMPLETE":
                incomplete_rows.append(row)

            if status == "HIT":
                hit_rows.append(
                    {
                        "row": row,
                        "lead_seconds": int(threshold["lead_seconds"]),
                    }
                )

        eligible_tokens = sorted({str(row["token"]) for row in eligible_rows})
        hit_tokens = sorted({str(item["row"]["token"]) for item in hit_rows})
        lead_seconds = [item["lead_seconds"] for item in hit_rows]

        key = f"{multiple_name}@{horizon_name}"
        buckets[key] = {
            "multiple": multiple_name,
            "horizon": horizon_name,
            "eligible_buys": len(eligible_rows),
            "hit_buys": len(hit_rows),
            "miss_buys": len(eligible_rows) - len(hit_rows),
            "incomplete_buys": len(incomplete_rows),
            "hit_rate_buy_pct": _pct(len(hit_rows), len(eligible_rows)),
            "eligible_distinct_tokens": len(eligible_tokens),
            "hit_distinct_tokens": len(hit_tokens),
            "hit_rate_token_pct": _pct(len(hit_tokens), len(eligible_tokens)),
            "median_hit_lead_seconds": _median_int(lead_seconds),
            "min_hit_lead_seconds": min(lead_seconds) if lead_seconds else None,
            "max_hit_lead_seconds": max(lead_seconds) if lead_seconds else None,
            "hit_tokens": hit_tokens,
        }

    return {
        "version": STAGE6_VERSION,
        "wallet": wallet,
        "profile_available": bool(rows),
        "input_buy_count": len(rows),
        "evaluated_buy_count": len(evaluated),
        "no_entry_price_count": no_entry_price,
        "distinct_tokens_bought": len({str(row.get("token") or "") for row in rows if row.get("token")}),
        "buckets": buckets,
        "label_status": "EVIDENCE_PROFILE_ONLY",
        "label_note": (
            "Stage 6 measures repeatable explosion capture; final Meme Hunter "
            "qualification threshold is deferred until population calibration."
        ),
    }


def match_buys_to_explosion_events(
    buys: Iterable[dict[str, Any]],
    explosion_events: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse all buys by the same wallet in one explosion event into one match."""
    valid_buys = _valid_buys(buys)
    events_by_token: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_event_ids: set[str] = set()

    for raw in explosion_events:
        event = dict(raw)
        event_id = str(event.get("event_id") or "")
        token = str(event.get("token") or "")
        if not event_id or not token:
            raise ValueError("explosion event requires event_id and token")
        if event_id in seen_event_ids:
            raise ValueError(f"duplicate explosion event_id: {event_id}")
        seen_event_ids.add(event_id)

        start_time = int(event["start_time"])
        trigger_time = int(event["trigger_time"])
        if trigger_time <= start_time:
            raise ValueError(f"invalid explosion event time range: {event_id}")
        event["start_time"] = start_time
        event["trigger_time"] = trigger_time
        events_by_token[token].append(event)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    event_lookup: dict[str, dict[str, Any]] = {}

    for token, events in events_by_token.items():
        for event in events:
            event_lookup[str(event["event_id"])] = event

        token_buys = [row for row in valid_buys if str(row["base_asset"]) == token]
        for buy in token_buys:
            buy_time = int(buy["block_time"])
            wallet = str(buy["wallet"])
            for event in events:
                if event["start_time"] <= buy_time < event["trigger_time"]:
                    grouped[(wallet, str(event["event_id"]))].append(buy)

    matches: list[dict[str, Any]] = []
    for (wallet, event_id), rows in grouped.items():
        event = event_lookup[event_id]
        times = [int(row["block_time"]) for row in rows]
        earliest = min(times)
        latest = max(times)
        matches.append(
            {
                "version": STAGE6_VERSION,
                "wallet": wallet,
                "event_id": event_id,
                "token": str(event["token"]),
                "threshold_multiple": str(event.get("threshold_multiple") or ""),
                "horizon": str(event.get("horizon") or ""),
                "start_time": int(event["start_time"]),
                "trigger_time": int(event["trigger_time"]),
                "buy_count_before_trigger": len(rows),
                "earliest_entry_time": earliest,
                "latest_entry_time": latest,
                "first_entry_lead_seconds": int(event["trigger_time"]) - earliest,
                "last_entry_lead_seconds": int(event["trigger_time"]) - latest,
                "signatures": [
                    str(row.get("signature") or "")
                    for row in rows
                    if row.get("signature")
                ],
            }
        )

    return sorted(
        matches,
        key=lambda row: (
            str(row["wallet"]),
            int(row["trigger_time"]),
            str(row["event_id"]),
        ),
    )


def build_explosion_match_profile(
    matches: Iterable[dict[str, Any]],
    *,
    wallet: str,
) -> dict[str, Any]:
    rows = [row for row in matches if str(row.get("wallet") or "") == wallet]
    first_leads = [int(row["first_entry_lead_seconds"]) for row in rows]
    last_leads = [int(row["last_entry_lead_seconds"]) for row in rows]

    by_threshold: dict[str, int] = defaultdict(int)
    by_horizon: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.get("threshold_multiple"):
            by_threshold[str(row["threshold_multiple"])] += 1
        if row.get("horizon"):
            by_horizon[str(row["horizon"])] += 1

    return {
        "version": STAGE6_VERSION,
        "wallet": wallet,
        "matched_explosion_events": len(rows),
        "matched_distinct_tokens": len({str(row["token"]) for row in rows}),
        "matched_event_ids": [str(row["event_id"]) for row in rows],
        "events_by_threshold": dict(sorted(by_threshold.items())),
        "events_by_horizon": dict(sorted(by_horizon.items())),
        "median_first_entry_lead_seconds": _median_int(first_leads),
        "median_last_entry_lead_seconds": _median_int(last_leads),
        "matches": rows,
    }
