"""One preseason Monte Carlo. Parameters stay hardcoded.

Draw order for a seeded Generator, so the same seed repeats:

1. For each outer sample: 30 net-rating shocks, then the regular-season
   uniforms and margins for every inner season.
2. For each inner season, in order: December games by date, East play-in,
   West play-in, East series, West series, Finals. A series draws its shock
   before its game uniforms.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from .cup import ExtraGame, filler_games
from .parameters import (
    LOGISTIC_SCALE,
    MARGIN_SD,
    N_INNER,
    N_OUTER,
    RANDOM_SEED,
    SERIES_SHOCK_SD,
    THETA_SD,
)
from .rules import (
    finals_home_is_a,
    higher_seed_is_home,
    is_series_eliminated,
    play_in_home_teams,
    rank_by_group_record,
    rank_teams,
    resolve_play_in,
    series_is_over,
)

N_TEAMS = 30
EAST_GROUPS = ("EA", "EB", "EC")
WEST_GROUPS = ("WA", "WB", "WC")
DECEMBER_ORDINAL = {
    iso: date.fromisoformat(iso).toordinal()
    for iso in ("2026-12-04", "2026-12-05", "2026-12-06", "2026-12-08", "2026-12-09", "2026-12-10")
}


def game_probability(theta_home, theta_away, home_b2b, away_b2b, neutral, shock_for_home) -> float:
    from .parameters import BACK_TO_BACK_POINTS, HOME_COURT_POINTS

    diff = float(theta_home) - float(theta_away) + float(shock_for_home)
    if not neutral:
        diff += HOME_COURT_POINTS
    if home_b2b:
        diff -= BACK_TO_BACK_POINTS
    if away_b2b:
        diff += BACK_TO_BACK_POINTS
    scaled = diff / LOGISTIC_SCALE
    if scaled >= 50.0:
        return 1.0
    if scaled <= -50.0:
        return 0.0
    return float(1.0 / (1.0 + np.exp(-scaled)))


def simulate_series(higher: int, lower: int, theta, rng, wins_hi: int = 0, wins_lo: int = 0) -> int:
    """Best of seven. A 0-3 deficit is still live; only 4 wins ends it."""
    if series_is_over(wins_hi, wins_lo):
        raise RuntimeError("series is already over")
    if is_series_eliminated(wins_hi, wins_lo) or is_series_eliminated(wins_lo, wins_hi):
        raise RuntimeError("eliminated team cannot keep playing")
    shock = float(rng.normal(0.0, SERIES_SHOCK_SD))
    game_number = wins_hi + wins_lo + 1
    while wins_hi < 4 and wins_lo < 4:
        if higher_seed_is_home(game_number):
            probability = game_probability(theta[higher], theta[lower], False, False, False, shock)
            if rng.random() < probability:
                wins_hi += 1
            else:
                wins_lo += 1
        else:
            probability = game_probability(theta[lower], theta[higher], False, False, False, -shock)
            if rng.random() < probability:
                wins_lo += 1
            else:
                wins_hi += 1
        game_number += 1
        if game_number > 8:
            raise RuntimeError("series exceeded 7 games")
    return higher if wins_hi >= 4 else lower


def _sigmoid_array(diff: np.ndarray) -> np.ndarray:
    scaled = np.clip(diff / LOGISTIC_SCALE, -50.0, 50.0)
    return 1.0 / (1.0 + np.exp(-scaled))


def draw_regular_season(theta, inputs, rng, n_inner: int):
    diff = theta[inputs["home"]] - theta[inputs["away"]] + inputs["edge"]
    probability = _sigmoid_array(diff)
    home_win = rng.random((n_inner, inputs["n_games"])) < probability
    noise = rng.normal(0.0, MARGIN_SD, size=home_win.shape)
    margin = np.maximum(1, np.rint(np.abs(diff + noise))).astype(np.int16)
    return home_win, margin


def accumulate_regular_season(home_win, margin, inputs):
    n_inner, _n_games = home_win.shape
    home = inputs["home"]
    away = inputs["away"]
    cup = inputs["cup"]
    winner = np.where(home_win, home, away)
    loser = np.where(home_win, away, home)
    wins = np.zeros((n_inner, N_TEAMS), dtype=np.int16)
    point_diff = np.zeros((n_inner, N_TEAMS), dtype=np.int32)
    h2h = np.zeros((n_inner, N_TEAMS, N_TEAMS), dtype=np.int16)
    group_wins = np.zeros((n_inner, N_TEAMS), dtype=np.int16)
    group_diff = np.zeros((n_inner, N_TEAMS), dtype=np.int32)
    group_h2h = np.zeros((n_inner, N_TEAMS, N_TEAMS), dtype=np.int16)
    for sample in range(n_inner):
        won = winner[sample]
        lost = loser[sample]
        np.add.at(wins[sample], won, 1)
        np.add.at(point_diff[sample], won, margin[sample])
        np.add.at(point_diff[sample], lost, -margin[sample])
        np.add.at(h2h[sample], (won, lost), 1)
        cup_winner = won[cup]
        cup_loser = lost[cup]
        np.add.at(group_wins[sample], cup_winner, 1)
        np.add.at(group_diff[sample], cup_winner, margin[sample][cup])
        np.add.at(group_diff[sample], cup_loser, -margin[sample][cup])
        np.add.at(group_h2h[sample], (cup_winner, cup_loser), 1)
    losses = np.full((n_inner, N_TEAMS), 80, dtype=np.int16) - wins
    return wins, losses, point_diff, h2h, group_wins, group_diff, group_h2h


@dataclass
class SeasonTrace:
    champion: int
    ranks: np.ndarray
    reached: np.ndarray
    r1_opponent: np.ndarray


def _apply(wins, losses, point_diff, h2h, home, away, home_won, margin) -> int:
    if home_won:
        wins[home] += 1
        losses[away] += 1
        point_diff[home] += margin
        point_diff[away] -= margin
        h2h[home, away] += 1
        return home
    wins[away] += 1
    losses[home] += 1
    point_diff[away] += margin
    point_diff[home] -= margin
    h2h[away, home] += 1
    return away


def _play_counted(game: ExtraGame, theta, rng, wins, losses, point_diff, h2h, team_dates, extra_dates) -> int:
    ordinal = DECEMBER_ORDINAL[game.date]
    for team in (game.home, game.away):
        if ordinal in team_dates[team] or ordinal in extra_dates[team]:
            raise RuntimeError(f"team {team} already plays on {game.date}")
    home_b2b = (ordinal - 1) in team_dates[game.home] or (ordinal - 1) in extra_dates[game.home]
    away_b2b = (ordinal - 1) in team_dates[game.away] or (ordinal - 1) in extra_dates[game.away]
    probability = game_probability(theta[game.home], theta[game.away], home_b2b, away_b2b, False, 0.0)
    home_won = bool(rng.random() < probability)
    margin = max(1, int(np.rint(abs(float(rng.normal(float(theta[game.home]) - float(theta[game.away]), MARGIN_SD))))))
    winner = _apply(wins, losses, point_diff, h2h, game.home, game.away, home_won, margin)
    extra_dates[game.home].add(ordinal)
    extra_dates[game.away].add(ordinal)
    return winner


def _single_game(home, away, theta, rng) -> int:
    probability = game_probability(theta[home], theta[away], False, False, False, 0.0)
    return home if rng.random() < probability else away


def _knockout_seeds(group_members, group_wins, group_diff, group_h2h, prior_wins, conference):
    ranked_groups = [
        rank_by_group_record(members, group_wins, group_diff, group_h2h, prior_wins, False)
        for members in group_members
    ]
    winners = [ranked[0] for ranked in ranked_groups]
    seconds = [ranked[1] for ranked in ranked_groups]
    ordered_winners = rank_by_group_record(winners, group_wins, group_diff, group_h2h, prior_wins, True)
    wildcard = rank_by_group_record(seconds, group_wins, group_diff, group_h2h, prior_wins, True)[0]
    seed_map = {
        ordered_winners[0]: 1,
        ordered_winners[1]: 2,
        ordered_winners[2]: 3,
        wildcard: 4,
    }
    outsiders = [team for team in conference if team not in seed_map]
    ranked_outsiders = rank_by_group_record(
        outsiders, group_wins, group_diff, group_h2h, prior_wins, False
    )
    return ordered_winners[0], ordered_winners[1], ordered_winners[2], wildcard, seed_map, ranked_outsiders


def _play_in(seventh, eighth, ninth, tenth, theta, rng):
    winner_78 = _single_game(seventh, eighth, theta, rng)
    winner_910 = _single_game(ninth, tenth, theta, rng)
    last_home = play_in_home_teams(seventh, eighth, ninth, tenth, winner_78)[2]
    winner_last = _single_game(last_home, winner_910, theta, rng)
    return resolve_play_in(seventh, eighth, ninth, tenth, winner_78, winner_910, winner_last)


def _conference_bracket(seeds, theta, rng, reached, r1_opponent) -> int:
    seed_number = {team: index for index, team in enumerate(seeds)}
    winners = []
    for higher_i, lower_i in ((0, 7), (3, 4), (1, 6), (2, 5)):
        higher = seeds[higher_i]
        lower = seeds[lower_i]
        r1_opponent[higher] = lower
        r1_opponent[lower] = higher
        reached[higher, 1] = True
        reached[lower, 1] = True
        winner = simulate_series(higher, lower, theta, rng)
        winners.append(winner)
        reached[winner, 2] = True
    finalists = []
    for left, right in ((winners[0], winners[1]), (winners[2], winners[3])):
        higher, lower = (left, right) if seed_number[left] < seed_number[right] else (right, left)
        winner = simulate_series(higher, lower, theta, rng)
        finalists.append(winner)
        reached[winner, 3] = True
    left, right = finalists
    higher, lower = (left, right) if seed_number[left] < seed_number[right] else (right, left)
    champion = simulate_series(higher, lower, theta, rng)
    reached[champion, 4] = True
    return champion


def _play_many(games, theta, rng, wins, losses, point_diff, h2h, team_dates, extra_dates) -> dict:
    winners = {}
    for game in sorted(games, key=lambda item: (item.date, item.home, item.away)):
        winners[(game.home, game.away)] = _play_counted(
            game, theta, rng, wins, losses, point_diff, h2h, team_dates, extra_dates
        )
    return winners


def _other(game: ExtraGame, winner: int) -> int:
    return game.away if winner == game.home else game.home


def play_one_season(theta, reg, sample: int, inputs, rng) -> SeasonTrace:
    wins = reg[0][sample].copy()
    losses = reg[1][sample].copy()
    point_diff = reg[2][sample].copy()
    h2h = reg[3][sample].copy()
    group_wins = reg[4][sample]
    group_diff = reg[5][sample]
    group_h2h = reg[6][sample]
    prior_wins = inputs["prior_wins"]
    east_seed = _knockout_seeds(
        [inputs["groups"][name] for name in EAST_GROUPS],
        group_wins, group_diff, group_h2h, prior_wins, inputs["east"],
    )
    west_seed = _knockout_seeds(
        [inputs["groups"][name] for name in WEST_GROUPS],
        group_wins, group_diff, group_h2h, prior_wins, inputs["west"],
    )
    fillers = filler_games(east_seed[5], west_seed[5], inputs["meetings"], inputs["base_home"])
    extra_dates = [set() for _ in range(N_TEAMS)]
    quarterfinals = []
    seed_maps = []
    for seed1, seed2, seed3, wildcard, seed_map, _outsiders in (east_seed, west_seed):
        quarterfinals.append(ExtraGame("2026-12-04", seed1, wildcard, "qf"))
        quarterfinals.append(ExtraGame("2026-12-05", seed2, seed3, "qf"))
        seed_maps.append(seed_map)

    qf_winners = _play_many(
        quarterfinals + [game for game in fillers if game.date == "2026-12-06"],
        theta, rng, wins, losses, point_diff, h2h, inputs["team_dates"], extra_dates,
    )
    followups = []
    for index, game_pair in enumerate((quarterfinals[0:2], quarterfinals[2:4])):
        winners = []
        losers = []
        for game in game_pair:
            winner = qf_winners[(game.home, game.away)]
            winners.append(winner)
            losers.append(_other(game, winner))
        seed_map = seed_maps[index]
        left, right = winners
        higher, lower = (left, right) if seed_map[left] < seed_map[right] else (right, left)
        followups.append(ExtraGame("2026-12-08", higher, lower, "sf"))
        left, right = losers
        higher, lower = (left, right) if seed_map[left] < seed_map[right] else (right, left)
        followups.append(ExtraGame("2026-12-09", higher, lower, "qf_loser"))
    followups.extend(game for game in fillers if game.date == "2026-12-10")
    _play_many(followups, theta, rng, wins, losses, point_diff, h2h, inputs["team_dates"], extra_dates)

    played = wins + losses
    if not np.all(played == 82):
        bad = [int(index) for index in np.where(played != 82)[0]]
        raise RuntimeError(f"teams {bad} did not play 82 games: {played[bad].tolist()}")

    reached = np.zeros((N_TEAMS, 6), dtype=bool)
    ranks = np.zeros(N_TEAMS, dtype=np.int16)
    r1_opponent = np.full(N_TEAMS, -1, dtype=np.int16)
    seeds = []
    for conference in (inputs["east"], inputs["west"]):
        order = rank_teams(conference, wins, losses, point_diff, h2h)
        for place, team in enumerate(order, start=1):
            ranks[team] = place
            if place <= 10:
                reached[team, 0] = True
        if sorted(int(ranks[team]) for team in conference) != list(range(1, 16)):
            raise RuntimeError("conference ranks are not 1 through 15")
        seventh, eighth = _play_in(order[6], order[7], order[8], order[9], theta, rng)
        seeds.append(order[:6] + [seventh, eighth])

    east_champ = _conference_bracket(seeds[0], theta, rng, reached, r1_opponent)
    west_champ = _conference_bracket(seeds[1], theta, rng, reached, r1_opponent)
    if finals_home_is_a(east_champ, west_champ, wins, losses, point_diff):
        higher, lower = east_champ, west_champ
    else:
        higher, lower = west_champ, east_champ
    champion = simulate_series(higher, lower, theta, rng)
    reached[champion, 5] = True
    return SeasonTrace(champion, ranks, reached, r1_opponent)


def run_monte_carlo(inputs, n_outer: int = N_OUTER, n_inner: int = N_INNER, seed: int = RANDOM_SEED, progress=None):
    if any(status != "已采集" for status in inputs["prior_status"]):
        raise RuntimeError("refusing to simulate with a missing prior")
    rng = np.random.default_rng(seed)
    n_total = n_outer * n_inner
    champions = np.zeros(N_TEAMS, dtype=np.int32)
    outer = np.zeros((n_outer, N_TEAMS), dtype=np.int32)
    rank_hist = np.zeros((N_TEAMS, 16), dtype=np.int32)
    reached = np.zeros((N_TEAMS, 6), dtype=np.int32)
    r1 = np.zeros((N_TEAMS, N_TEAMS), dtype=np.int32)
    for outer_index in range(n_outer):
        theta = inputs["theta"] + rng.normal(0.0, THETA_SD, size=N_TEAMS)
        home_win, margin = draw_regular_season(theta, inputs, rng, n_inner)
        regular = accumulate_regular_season(home_win, margin, inputs)
        for sample in range(n_inner):
            trace = play_one_season(theta, regular, sample, inputs, rng)
            champions[trace.champion] += 1
            outer[outer_index, trace.champion] += 1
            for team in range(N_TEAMS):
                rank_hist[team, int(trace.ranks[team])] += 1
                reached[team] += trace.reached[team]
                opponent = int(trace.r1_opponent[team])
                if opponent >= 0:
                    r1[team, opponent] += 1
        if progress:
            progress(outer_index + 1, n_outer)
    return {
        "champions": champions,
        "outer": outer,
        "rank_hist": rank_hist,
        "reached": reached,
        "r1": r1,
        "n_outer": n_outer,
        "n_inner": n_inner,
        "n_total": n_total,
        "seed": seed,
    }
