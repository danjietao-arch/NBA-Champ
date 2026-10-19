"""Review the 2026-27 championship event and attach CLOB quotes.

Gamma finds the markets. The order book, not Gamma's displayed price, supplies
bid, ask, and mid. Quotes never change theta or the simulation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .teams import TEAMS

FINAL_WORDS = ("conference", "regular season", "nba cup", "in-season tournament")
NAME_ALIASES = {
    "los angeles clippers": "la clippers",
}


def review_event(event: dict, reviewed_at: str) -> dict:
    """Build the registry from questions that were actually read."""
    if event.get("slug") != "nba-2027-champion":
        raise RuntimeError(f"refusing to review event {event.get('slug')}")
    by_name = {}
    for team in TEAMS:
        by_name[_canonical(team.en)] = team
    mapped = []
    unmapped = []
    for market in event["markets"]:
        question = str(market.get("question") or "")
        group = str(market.get("groupItemTitle") or "")
        outcomes = _json_list(market.get("outcomes"))
        tokens = _json_list(market.get("clobTokenIds"))
        yes_index = outcomes.index("Yes") if "Yes" in outcomes else None
        yes_token = tokens[yes_index] if yes_index is not None and yes_index < len(tokens) else None
        team = by_name.get(_canonical(group))
        rejected = _rejected_question(question)
        record = {
            "event_id": str(event["id"]),
            "market_id": str(market["id"]),
            "yes_token_id": yes_token,
            "team_id": None if team is None or rejected else team.team_id,
            "team_abbr": None if team is None or rejected else team.abbrev,
            "question": question,
            "resolution_text": str(market.get("description") or ""),
            "group": group,
            "active": bool(market.get("active")),
            "closed": bool(market.get("closed")),
            "reviewed_at": reviewed_at,
        }
        if team is None or rejected or yes_token is None:
            record["status"] = "unmapped"
            record["unmapped_reason"] = _unmapped_reason(question, group, team, rejected, yes_token)
            unmapped.append(record)
        else:
            record["status"] = "active" if record["active"] and not record["closed"] else "inactive"
            mapped.append(record)
    other_present = any(item["group"] == "Other" or "another team" in item["question"].lower() for item in unmapped)
    return {
        "event_id": str(event["id"]),
        "event_slug": event.get("slug"),
        "event_title": event.get("title"),
        "event_url": "https://polymarket.com/event/nba-2027-champion",
        "reviewed_at": reviewed_at,
        "review_note": (
            "只读了这个 2026—27 总冠军事件。问题原文要是 2027 NBA Finals 的冠军，"
            "并且队名对得上 30 支球队，才进入差值。分区冠军、常规赛冠军、NBA Cup、Other 和占位队不进入。"
        ),
        "markets": mapped,
        "unmapped": unmapped,
        "mapped_team_count": len(mapped),
        "coverage_incomplete": True if other_present or len(mapped) != 30 else False,
        "coverage_incomplete_reason": (
            "事件里还有 Other 或占位市场，或者没有为每一支球队找到同一条总冠军规则。"
            "原始 YES 中间价不归一化。"
            if other_present or len(mapped) != 30
            else ""
        ),
    }


def quote_from_book(book: dict | None, error: str | None, comparison_at: datetime) -> dict:
    """Blank prices unless both sides of the book are present and fresh."""
    blank = {
        "quote_status": "missing",
        "bid": None,
        "ask": None,
        "mid": None,
        "spread": None,
        "book_timestamp": None,
        "error": error,
    }
    if not book:
        return blank
    bids = [float(level["price"]) for level in book.get("bids") or []]
    asks = [float(level["price"]) for level in book.get("asks") or []]
    stamp = _timestamp(book.get("timestamp"))
    blank["book_timestamp"] = None if stamp is None else stamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not bids or not asks:
        blank["quote_status"] = "one_sided"
        return blank
    bid = round(max(bids), 4)
    ask = round(min(asks), 4)
    if bid <= 0 or ask <= bid:
        blank["quote_status"] = "one_sided"
        return blank
    if stamp is None or abs((comparison_at - stamp).total_seconds()) > 90 * 60:
        blank["quote_status"] = "stale"
        return blank
    return {
        "quote_status": "valid",
        "bid": bid,
        "ask": ask,
        "mid": round((bid + ask) / 2.0, 4),
        "spread": round(ask - bid, 4),
        "book_timestamp": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "error": None,
    }


def attach_quotes(document: dict, registry: dict, quotes_by_market: dict, comparison_at: str) -> dict:
    """Join quotes onto a finished model snapshot. Does not touch probabilities."""
    by_team = {row["team_id"]: row for row in registry["markets"]}
    valid = 0
    for team in document["teams"]:
        row = by_team.get(team["team_id"])
        if row is None:
            team["market"] = {
                "quote_status": "unlisted",
                "bid": None,
                "ask": None,
                "mid": None,
                "spread": None,
                "delta_pp": None,
                "market_as_of": None,
            }
            continue
        quote = quotes_by_market.get(row["market_id"]) or quote_from_book(None, "no book", _parse_z(comparison_at))
        market = {
            "market_id": row["market_id"],
            "yes_token_id": row["yes_token_id"],
            "question": row["question"],
            "quote_status": quote["quote_status"],
            "bid": quote["bid"] if quote["quote_status"] == "valid" else None,
            "ask": quote["ask"] if quote["quote_status"] == "valid" else None,
            "mid": quote["mid"] if quote["quote_status"] == "valid" else None,
            "spread": quote["spread"] if quote["quote_status"] == "valid" else None,
            "market_as_of": quote["book_timestamp"] if quote["quote_status"] == "valid" else None,
            "error": quote.get("error"),
        }
        if quote["quote_status"] == "valid" and team.get("p_champion") is not None:
            market["delta_pp"] = round(100.0 * (float(team["p_champion"]) - float(quote["mid"])), 2)
            valid += 1
        else:
            market["delta_pp"] = None
        team["market"] = market
    mids = [team["market"]["mid"] for team in document["teams"] if team["market"].get("mid") is not None]
    document["market_comparison"] = {
        "event_id": registry["event_id"],
        "event_slug": registry["event_slug"],
        "event_url": registry["event_url"],
        "comparison_as_of": comparison_at,
        "valid_quotes": valid,
        "mapped_teams": registry["mapped_team_count"],
        "coverage_incomplete": True,
        "coverage_incomplete_reason": registry["coverage_incomplete_reason"],
        "raw_mid_sum": None if not mids else sum(mids),
        "normalized": False,
        "unmapped": [
            {"question": item["question"], "reason": item["unmapped_reason"], "market_id": item["market_id"]}
            for item in registry["unmapped"]
        ],
        "prices_entered_model": False,
    }
    return document


def _canonical(name: str) -> str:
    lowered = " ".join(name.lower().split())
    return NAME_ALIASES.get(lowered, lowered)


def _rejected_question(question: str) -> bool:
    lowered = question.lower()
    if "2027 nba finals" not in lowered:
        return True
    return any(word in lowered for word in FINAL_WORDS)


def _unmapped_reason(question: str, group: str, team, rejected: bool, yes_token) -> str:
    if rejected:
        return "问题不是 2027 总决赛冠军，不进入差值。"
    if yes_token is None:
        return "没有读到 YES token。"
    if group == "Other" or "another team" in question.lower():
        return "Other 结局，不进入差值。"
    if team is None:
        return "不是 30 支 NBA 球队之一（占位市场），不进入差值。"
    return "未匹配。"


def _json_list(value):
    if isinstance(value, str):
        return json.loads(value)
    return list(value or [])


def _timestamp(value) -> datetime | None:
    if value is None or value == "":
        return None
    raw = int(value)
    if raw > 10**12:
        raw = raw / 1000.0
    return datetime.fromtimestamp(raw, timezone.utc)


def _parse_z(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
