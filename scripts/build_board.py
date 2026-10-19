"""Attach the reviewed championship quotes and the walk-forward note to the current snapshot."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nba2027.market import attach_quotes, quote_from_book, review_event  # noqa: E402
from nba2027.page import render_html  # noqa: E402
from nba2027.snapshot import write_csv  # noqa: E402

STORE_DOCS = Path("/cursor/stores/self/docs")


def _parse_z(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def load_quotes(registry: dict, books_path: Path) -> tuple[dict, list[str], str]:
    raw = json.loads(books_path.read_text(encoding="utf-8"))
    by_id = {item["market_id"]: item for item in raw}
    stamps = []
    failures = []
    quotes = {}
    for row in registry["markets"] + registry["unmapped"]:
        fetched = by_id.get(row["market_id"])
        if fetched is None:
            quotes[row["market_id"]] = quote_from_book(None, "没有这次订单簿响应", datetime.now(timezone.utc))
            failures.append(f"{row['question']}：没有订单簿响应")
            continue
        book = json.loads(fetched["body"]) if fetched.get("body") else None
        error = fetched.get("err")
        if error:
            failures.append(f"{row['question']}：{error}")
        stamp = None
        if book and book.get("timestamp"):
            raw_ts = int(book["timestamp"])
            if raw_ts > 10**12:
                raw_ts /= 1000.0
            stamp = datetime.fromtimestamp(raw_ts, timezone.utc)
            stamps.append(stamp)
        quotes[row["market_id"]] = {"book": book, "error": error, "stamp": stamp}
    comparison = max(stamps) if stamps else datetime.now(timezone.utc)
    parsed = {}
    for market_id, item in quotes.items():
        parsed[market_id] = quote_from_book(item["book"], item["error"], comparison)
    return parsed, failures, comparison.strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    document = json.loads((ROOT / "output" / "preseason-2026-27.json").read_text(encoding="utf-8"))
    event = json.loads((ROOT / "data" / "raw" / "gamma-nba-2027-champion.json").read_text(encoding="utf-8"))
    if isinstance(event, list):
        event = event[0]
    reviewed_at = "2026-10-19T13:11:09Z"
    registry = review_event(event, reviewed_at)
    (ROOT / "data" / "market_registry.json").write_text(
        json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    quotes, failures, comparison_at = load_quotes(registry, ROOT / "data" / "raw" / "clob-books.json")
    (ROOT / "data" / "clob_quotes.json").write_text(
        json.dumps(quotes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    attach_quotes(document, registry, quotes, comparison_at)
    document["market_comparison"]["clob_failures"] = failures
    report_path = ROOT / "data" / "walk_forward_report.json"
    if report_path.exists():
        document["walk_forward"] = json.loads(report_path.read_text(encoding="utf-8"))
    else:
        document["walk_forward"] = {
            "attempted": True,
            "data_fetched": False,
            "replaced_parameters": False,
            "summary": "三个赛季的 walk-forward 没有跑完，当前快照仍是参数写死的那一次模拟。",
            "failures": [],
        }
    report = document["walk_forward"]
    if report.get("replaced_parameters") and report.get("best_k") is not None:
        same_sd = float(report["best_series_shock_sd"]) == float(document["parameters"]["series_shock_sd"])
        if same_sd:
            document["parameter_status"] = "w 已由 walk-forward 替换；系列赛标准差仍是 3.0"
        else:
            document["parameter_status"] = (
                f"w 与系列赛标准差已由 walk-forward 替换（标准差 {report['best_series_shock_sd']}）"
            )
        document["parameters"]["status"] = document["parameter_status"]
        document["parameters"]["w_k"] = report["best_k"]
        document["parameters"]["w"] = report["best_w"]
        document["probability_note"] = (
            "赛前还没有 2026—27 的比赛，w 为 0。30 队频率仍是随机种子 "
            f"{document['random_seed']} 的那次模拟，没有因为拟合而重跑。"
        )
    html = render_html(document)
    json_text = json.dumps(document, ensure_ascii=False, indent=2)
    targets = [
        ROOT / "output" / "preseason-2026-27.json",
        ROOT / "output" / "preseason-2026-27.html",
        STORE_DOCS / "preseason-2026-27.json",
        STORE_DOCS / "preseason-2026-27.html",
    ]
    for path in targets:
        if path.suffix == ".json":
            path.write_text(json_text, encoding="utf-8")
        else:
            path.write_text(html, encoding="utf-8")
        print(path, path.stat().st_size)
    write_csv(document, ROOT / "output" / "preseason-2026-27.csv")


if __name__ == "__main__":
    main()
