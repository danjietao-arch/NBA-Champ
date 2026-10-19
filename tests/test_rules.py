import json
from pathlib import Path

import numpy as np

from nba2027.rules import (
    eliminated_from_play_in,
    higher_seed_is_home,
    is_series_eliminated,
    play_in_home_teams,
    rank_by_group_record,
    rank_teams,
    replay_series,
    resolve_play_in,
    series_home_team,
    series_is_over,
)

ROOT = Path(__file__).resolve().parents[1]


def _fixture(name):
    return json.loads((ROOT / "data" / "fixtures" / name).read_text(encoding="utf-8"))


def _winner(game):
    if game["home_score"] == game["away_score"]:
        raise AssertionError("tied game")
    return game["home"] if game["home_score"] > game["away_score"] else game["away"]


def test_2023_ecf_home_order_and_0_3_is_not_elimination():
    fixture = _fixture("2023_ecf.json")
    assert [higher_seed_is_home(game) for game in range(1, 8)] == [
        True, True, False, False, True, False, True
    ]
    states = replay_series(fixture["higher_seed"], fixture["lower_seed"], fixture["games"])
    assert len(states) == 7
    assert states[2]["wins_higher"] == 0
    assert states[2]["wins_lower"] == 3
    assert states[2]["over"] is False
    assert states[2]["higher_eliminated"] is False
    assert states[-1]["wins_higher"] == 3
    assert states[-1]["wins_lower"] == 4
    assert states[-1]["over"] is True
    assert states[-1]["higher_eliminated"] is True
    assert states[-1]["lower_eliminated"] is False


def test_2024_finals_home_order():
    fixture = _fixture("2024_finals.json")
    states = replay_series(fixture["higher_seed"], fixture["lower_seed"], fixture["games"])
    assert [(state["wins_higher"], state["wins_lower"]) for state in states][-1] == (4, 1)
    assert series_home_team(6, "BOS", "DAL") == "DAL"
    assert series_home_team(7, "BOS", "DAL") == "BOS"
    assert series_is_over(4, 1) is True
    assert is_series_eliminated(1, 4) is True


def test_2024_east_play_in_advancement():
    fixture = _fixture("2024_playin_east.json")
    games = {game["role"]: game for game in fixture["games"]}
    assert games["7v8"]["home"] == fixture["seventh"]
    assert games["9v10"]["home"] == fixture["ninth"]
    winner_78 = _winner(games["7v8"])
    winner_910 = _winner(games["9v10"])
    winner_last = _winner(games["8seed"])
    homes = play_in_home_teams(
        fixture["seventh"], fixture["eighth"], fixture["ninth"], fixture["tenth"], winner_78
    )
    assert homes[2] == games["8seed"]["home"]
    assert resolve_play_in(
        fixture["seventh"],
        fixture["eighth"],
        fixture["ninth"],
        fixture["tenth"],
        winner_78,
        winner_910,
        winner_last,
    ) == (fixture["seed7"], fixture["seed8"])


def test_two_team_tie_uses_head_to_head_before_point_differential():
    wins = np.array([41, 41])
    losses = np.array([41, 41])
    point_diff = np.array([10, 80])
    h2h = np.zeros((2, 2), dtype=int)
    h2h[0, 1] = 3
    h2h[1, 0] = 1
    assert rank_teams([0, 1], wins, losses, point_diff, h2h) == [0, 1]


def test_three_team_tie_sorts_by_point_differential():
    wins = np.array([40, 40, 40])
    losses = np.array([42, 42, 42])
    point_diff = np.array([5, 0, 20])
    h2h = np.zeros((3, 3), dtype=int)
    h2h[0, 2] = 4
    assert rank_teams([0, 1, 2], wins, losses, point_diff, h2h)[0] == 2


def test_play_in_elimination_needs_ten_teams_strictly_ahead():
    wins = np.zeros(15, dtype=int)
    remaining = np.zeros(15, dtype=int)
    wins[0] = 20
    remaining[0] = 5
    conference = list(range(15))
    wins[1:11] = 26
    assert eliminated_from_play_in(0, wins, remaining, conference) is True
    wins[1:11] = 25
    assert eliminated_from_play_in(0, wins, remaining, conference) is False
    wins[1:10] = 40
    assert eliminated_from_play_in(0, wins, remaining, conference) is False


def test_wildcard_tie_skips_head_to_head():
    group_wins = np.array([3, 3, 3])
    point_diff = np.array([1, 9, 0])
    h2h = np.zeros((3, 3), dtype=int)
    h2h[0, 1] = 2
    prior = np.array([50, 50, 50])
    assert rank_by_group_record([0, 1, 2], group_wins, point_diff, h2h, prior, True)[0] == 1
    assert rank_by_group_record([0, 1, 2], group_wins, point_diff, h2h, prior, False)[0] == 0


def test_zero_three_is_not_a_finished_series():
    assert series_is_over(0, 3) is False
    assert is_series_eliminated(0, 3) is False
    assert is_series_eliminated(3, 0) is False
    assert is_series_eliminated(0, 4) is True
