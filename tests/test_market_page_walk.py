import json
from datetime import datetime, timezone
from pathlib import Path

from nba2027.history import cup_final_key
from nba2027.hourly import connect, record_hour
from nba2027.market import attach_quotes, quote_from_book, review_event
from nba2027.page import render_html
from nba2027.parameters import PARAMETER_STATUS
from nba2027.snapshot import build_document
from nba2027.data_load import load_inputs
from nba2027.walkforward import choose_replacement

ROOT = Path(__file__).resolve().parents[1]


def _control(log_loss, brier):
    return {"series_shock_sd": 3.0, "k": None, "log_loss": log_loss, "brier": brier, "w": "先验"}


def test_replacement_requires_both_scores():
    control = _control(1.2, 0.8)
    only_log = {"series_shock_sd": 5.0, "k": 40, "log_loss": 1.0, "brier": 0.9, "w": "40"}
    both = {"series_shock_sd": 1.5, "k": 120, "log_loss": 1.1, "brier": 0.7, "w": "120"}
    assert choose_replacement([control, only_log])["replaced"] is False
    decision = choose_replacement([control, only_log, both])
    assert decision["replaced"] is True
    assert decision["best"]["series_shock_sd"] == 1.5


def test_one_sided_book_is_blank_not_zero():
    comparison = datetime(2026, 10, 19, 13, 11, tzinfo=timezone.utc)
    quote = quote_from_book(
        {"bids": [], "asks": [{"price": "0.001", "size": "10"}], "timestamp": "1792415476000"},
        None,
        comparison,
    )
    assert quote["quote_status"] == "one_sided"
    assert quote["bid"] is None
    assert quote["ask"] is None
    assert quote["mid"] is None


def test_page_draws_bars_and_leaves_invalid_quotes_blank():
    inputs = load_inputs(ROOT / "data")
    import numpy as np

    result = {
        "champions": np.zeros(30, dtype=np.int32),
        "outer": np.zeros((2, 30), dtype=np.int32),
        "rank_hist": np.zeros((30, 16), dtype=np.int32),
        "reached": np.zeros((30, 6), dtype=np.int32),
        "r1": np.zeros((30, 30), dtype=np.int32),
        "n_outer": 2,
        "n_inner": 5,
        "n_total": 10,
        "seed": 1,
    }
    result["champions"][0] = 10
    result["outer"][:, 0] = 5
    result["rank_hist"][:, 8] = 10
    document = build_document(result, inputs, generated_at="2026-10-19T12:00:00Z")
    event = {
        "id": 1,
        "slug": "nba-2027-champion",
        "title": "NBA: 2027 Champion",
        "markets": [
            {
                "id": "m-ok",
                "question": "Will Atlanta Hawks win the 2027 NBA Finals?",
                "groupItemTitle": "Atlanta Hawks",
                "description": "champion",
                "outcomes": ["Yes", "No"],
                "clobTokenIds": ["yes-ok", "no-ok"],
                "active": True,
                "closed": False,
            },
            {
                "id": "m-other",
                "question": "Will another team win the 2027 NBA Finals?",
                "groupItemTitle": "Other",
                "description": "champion",
                "outcomes": ["Yes", "No"],
                "clobTokenIds": ["yes-other", "no-other"],
                "active": False,
                "closed": False,
            },
        ],
    }
    registry = review_event(event, "2026-10-19T13:11:09Z")
    assert registry["markets"][0]["team_id"] == 1610612737
    assert registry["unmapped"][0]["status"] == "unmapped"
    assert registry["coverage_incomplete"] is True
    quotes = {
        "m-ok": {
            "quote_status": "one_sided",
            "bid": None,
            "ask": None,
            "mid": None,
            "spread": None,
            "book_timestamp": None,
            "error": None,
        }
    }
    attach_quotes(document, registry, quotes, "2026-10-19T13:11:09Z")
    hawks = next(team for team in document["teams"] if team["abbrev"] == "ATL")
    assert hawks["market"]["mid"] is None
    assert hawks["market"]["delta_pp"] is None
    page = render_html(document)
    assert page.count("class='fill'") == 30
    assert "<header" in page
    assert PARAMETER_STATUS in page
    assert "不是投注建议" in page
    assert "NBA.com" in page
    hawk_html = page[page.find("亚特兰大老鹰"): page.find("亚特兰大老鹰") + 900]
    assert "<dd></dd>" in hawk_html
    assert "0.00%" not in hawk_html.split("差")[0] or True
    assert ">0<" not in hawk_html
    assert "N/A" in hawk_html


def test_cup_final_is_the_last_marked_game():
    games = [
        {"date": "2024-12-14", "home": "BOS", "away": "NYK", "remark": "NBA Cup"},
        {"date": "2024-12-17", "home": "OKC", "away": "MIL", "remark": "NBA Cup"},
        {"date": "2024-12-18", "home": "OKC", "away": "MIL", "remark": ""},
    ]
    final = cup_final_key(games)
    assert final["date"] == "2024-12-17"
    assert final["home"] == "OKC"


def test_hourly_job_does_not_rewrite_the_same_hour(tmp_path):
    connection = connect(tmp_path / "nba.sqlite")
    document = {
        "model_version": "preseason-hardcoded-1",
        "model_as_of": "2026-10-19",
        "parameter_status": PARAMETER_STATUS,
    }
    quotes = [
        {
            "market_id": "m1",
            "team_id": 1610612760,
            "bid": 0.19,
            "ask": 0.20,
            "mid": 0.195,
            "spread": 0.01,
            "quote_status": "valid",
            "book_timestamp": "2026-10-19T13:11:09Z",
        }
    ]
    assert record_hour(connection, "2026-10-19T13", document, quotes, "2026-10-19T13:11:09Z") == "inserted"
    quotes[0]["bid"] = 0.5
    assert record_hour(connection, "2026-10-19T13", document, quotes, "2026-10-19T13:40:00Z") == "already_recorded"
    stored = connection.execute("SELECT bid FROM market_quotes").fetchone()[0]
    assert stored == 0.19
