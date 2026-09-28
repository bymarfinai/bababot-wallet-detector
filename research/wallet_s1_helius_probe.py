from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

from wallet_s1_data_foundation import build_helius_gtfa_payload


def fetch_page(api_key: str, wallet: str, limit: int = 10) -> dict:
    endpoint = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
    payload = build_helius_gtfa_payload(wallet, limit=limit)
    req = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only BabaBot Wallet Detector Stage-1 Helius probe."
    )
    parser.add_argument("--wallet", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    api_key = os.environ.get("HELIUS_API_KEY")
    if not api_key:
        raise SystemExit("HELIUS_API_KEY is required in the environment")

    payload = fetch_page(api_key, args.wallet, args.limit)
    if payload.get("error"):
        print(json.dumps(payload["error"], indent=2))
        return 2

    result = payload.get("result") or {}
    data = result.get("data") or []
    summary = {
        "wallet": args.wallet,
        "count": len(data),
        "pagination_token_present": bool(result.get("paginationToken")),
        "first_slot": data[0].get("slot") if data else None,
        "last_slot": data[-1].get("slot") if data else None,
    }
    print(json.dumps(summary, indent=2))

    if args.out:
        path = Path(args.out)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"saved raw response: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
