"""Hourly CLOB quote job. Reuses the model snapshot. Does not train on prices."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nba2027.hourly import connect, record_hour  # noqa: E402


def main() -> int:
    snapshot_path = ROOT / "output" / "preseason-2026-27.json"
    registry_path = ROOT / "data" / "market_registry.json"
    quotes_path = ROOT / "data" / "clob_quotes.json"
    if not snapshot_path.exists() or not registry_path.exists() or not quotes_path.exists():
        print("缺少快照、市场登记或订单簿文件，不写入报价。")
        return 2
    document = json.loads(snapshot_path.read_text(encoding="utf-8"))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    stored = json.loads(quotes_path.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    as_of_hour = now.strftime("%Y-%m-%dT%H")
    fetched_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    by_id = {row["market_id"]: row for row in registry["markets"]}
    quotes = []
    for market_id, quote in stored.items():
        row = by_id.get(market_id)
        if row is None:
            continue
        quotes.append(
            {
                "market_id": market_id,
                "team_id": row.get("team_id"),
                "bid": quote.get("bid") if quote.get("quote_status") == "valid" else None,
                "ask": quote.get("ask") if quote.get("quote_status") == "valid" else None,
                "mid": quote.get("mid") if quote.get("quote_status") == "valid" else None,
                "spread": quote.get("spread") if quote.get("quote_status") == "valid" else None,
                "quote_status": quote.get("quote_status") or "missing",
                "book_timestamp": quote.get("book_timestamp"),
            }
        )
    connection = connect(ROOT / "data" / "nba2027.sqlite")
    result = record_hour(connection, as_of_hour, document, quotes, fetched_at)
    print(f"{as_of_hour} {result} quotes={len(quotes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
