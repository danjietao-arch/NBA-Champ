import json
from pathlib import Path

import numpy as np

from nba2027.cup import count_games, filler_games
from nba2027.data_load import load_inputs
from nba2027.parameters import PARAMETER_STATUS
from nba2027.snapshot import DISCLAIMER, ATTRIBUTION, build_document, probability_cell, render_html
from nba2027.teams import TEAMS

ROOT = Path(__file__).resolve().parents[1]


def test_filler_games_give_every_non_qualifier_two_dates():
    meetings = np.zeros((30, 30), dtype=np.int16)
    meetings[0, 1] = meetings[1, 0] = 3
    east = list(range(11))
    west = list(range(11, 22))
    games = filler_games(east, west, meetings, np.zeros(30, dtype=np.int16))
    counts = count_games(games)
    assert all(counts[team] == 2 for team in range(22))
    cross = [game for game in games if (game.home < 11) != (game.away < 11)]
    assert len(cross) == 2
    seen = set()
    for game in games:
        for team in (game.home, game.away):
            key = (game.date, team)
            assert key not in seen
            seen.add(key)


def test_published_inputs_cover_thirty_teams():
    inputs = load_inputs(ROOT / "data")
    assert inputs["missing_priors"] == []
    assert inputs["prior_status"] == ["已采集"] * 30
    assert inputs["n_games"] == 1200
    assert inputs["adjustments_applied"] == []
    okc = next(index for index, team in enumerate(TEAMS) if team.abbrev == "OKC")
    assert inputs["theta"][okc] == 11.05
    assert len({team.team_id for team in TEAMS}) == 30


def test_low_confidence_adjustment_does_not_change_theta(tmp_path):
    for name in ("priors_2025_26.json", "schedule_2026_27.json", "adjustments.json", "cup_groups_2026.json"):
        (tmp_path / name).write_text((ROOT / "data" / name).read_text(encoding="utf-8"), encoding="utf-8")
    adjustments = json.loads((tmp_path / "adjustments.json").read_text(encoding="utf-8"))
    adjustments["entries"] = [
        {
            "team_id": 1610612760,
            "target": "未证实传言",
            "direction": "down",
            "magnitude": 5,
            "effective_date": "2026-10-01",
            "source": "none",
            "confidence": "low",
            "recorded_by": "test",
        }
    ]
    (tmp_path / "adjustments.json").write_text(json.dumps(adjustments), encoding="utf-8")
    inputs = load_inputs(tmp_path)
    okc = next(index for index, team in enumerate(TEAMS) if team.abbrev == "OKC")
    assert inputs["theta"][okc] == 11.05
    assert inputs["adjustments_applied"] == []


def test_page_labels_probability_zero_as_a_frequency_not_elimination():
    inputs = load_inputs(ROOT / "data")
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
    assert document["parameter_status"] == PARAMETER_STATUS
    assert document["rounded_percent_sum"] == 100.0
    assert document["includes_2026_27_results"] is False
    zeros = [team for team in document["teams"] if team["championships"] == 0]
    assert zeros
    assert all(team["exact_zero"] is False and team["eliminated"] is False for team in zeros)
    assert "不是官方淘汰" in probability_cell(zeros[0])
    page = render_html(document)
    assert PARAMETER_STATUS in page
    assert "NBA.com" in page
    assert DISCLAIMER in page
    assert ATTRIBUTION in page
    assert inputs["priors_doc"]["failed_preferred_source"]["url"] in page
    assert "不是投注建议" in page


def test_missing_prior_publishes_no_probability(tmp_path):
    for name in ("priors_2025_26.json", "schedule_2026_27.json", "adjustments.json", "cup_groups_2026.json"):
        (tmp_path / name).write_text((ROOT / "data" / name).read_text(encoding="utf-8"), encoding="utf-8")
    priors = json.loads((tmp_path / "priors_2025_26.json").read_text(encoding="utf-8"))
    priors["teams"] = [row for row in priors["teams"] if row["abbrev"] != "WAS"]
    (tmp_path / "priors_2025_26.json").write_text(json.dumps(priors), encoding="utf-8")
    inputs = load_inputs(tmp_path)
    assert "WAS" in inputs["missing_priors"]
    document = build_document(None, inputs, generated_at="2026-10-19T12:00:00Z")
    assert document["probabilities_published"] is False
    assert all(team["p_champion"] is None for team in document["teams"])
    was = next(team for team in document["teams"] if team["abbrev"] == "WAS")
    assert was["prior_status"] == "待采集"
    assert probability_cell(was) == "待采集"
