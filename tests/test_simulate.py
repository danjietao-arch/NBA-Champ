import numpy as np

from nba2027.data_load import load_inputs
from nba2027.rules import is_series_eliminated, series_is_over
from nba2027.simulate import run_monte_carlo, simulate_series


def test_team_down_0_3_can_still_win_the_series():
    theta = np.array([40.0, -40.0])
    rng = np.random.default_rng(0)
    winners = [simulate_series(0, 1, theta, rng, wins_hi=0, wins_lo=3) for _ in range(20)]
    assert 0 in winners
    assert series_is_over(0, 3) is False
    assert is_series_eliminated(0, 3) is False


def test_two_seeded_seasons_repeat_and_sum_to_one():
    inputs = load_inputs()
    first = run_monte_carlo(inputs, n_outer=1, n_inner=2, seed=11)
    second = run_monte_carlo(inputs, n_outer=1, n_inner=2, seed=11)
    assert int(first["champions"].sum()) == 2
    assert np.array_equal(first["champions"], second["champions"])
    assert np.array_equal(first["rank_hist"], second["rank_hist"])
    assert int(first["reached"][:, 5].sum()) == 2
    assert int(first["reached"][:, 4].sum()) == 4
