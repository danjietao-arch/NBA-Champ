"""Pure playoff rules: seeding, play-in, series home order, elimination.

Two-team ties are simplified. Ties of three or more teams are an explicit
approximation of the official multi-team procedure.
"""

from __future__ import annotations

from collections import defaultdict
from fractions import Fraction

HIGHER_SEED_HOME_GAMES = frozenset({1, 2, 5, 7})

APPROXIMATIONS = [
    "两队胜率相同的简化顺序：相互胜负，然后净胜分，然后 team_id。没有使用分区冠军身份、分区战绩、联盟战绩，也没有使用对季后赛球队的战绩。",
    "三队及以上同时平分时做了近似：不走官方的多队连锁流程，也不在平分小组里先两两拆开再重排。这组球队按净胜分、组内相互胜场、team_id 排序。",
    "总决赛主场：常规赛胜率，然后净胜分，然后较小的 team_id。这代替官方那串更长的平分条款。",
    "无缘附加赛的数学淘汰只在「已经有 10 支同部球队的胜场多于本队理论上限」时成立。胜场刚好等于上限时仍可能靠平分晋级，v1 不把这种情况判成淘汰。",
    "系列赛 0—3 落后不是淘汰。对手没拿到 4 胜之前继续比赛，概率不得提前写成精确的 0。",
]


def higher_seed_is_home(game_number: int) -> bool:
    if game_number not in range(1, 8):
        raise ValueError(f"series game number must be 1..7, got {game_number}")
    return game_number in HIGHER_SEED_HOME_GAMES


def series_home_team(game_number: int, higher, lower):
    return higher if higher_seed_is_home(game_number) else lower


def series_is_over(wins_a: int, wins_b: int) -> bool:
    return wins_a >= 4 or wins_b >= 4


def is_series_eliminated(wins_for: int, wins_against: int) -> bool:
    """True only when the opponent has already won 4 games."""
    return wins_against >= 4


def replay_series(higher, lower, games: list[dict]) -> list[dict]:
    """Walk a finished or partial series. Home teams must follow 2-2-1-1-1."""
    wins_hi = 0
    wins_lo = 0
    states = []
    for game in games:
        number = int(game["game"])
        expected = series_home_team(number, higher, lower)
        if game["home"] != expected:
            raise AssertionError(
                f"game {number} home is {game['home']}, pattern expects {expected}"
            )
        if game["away"] not in (higher, lower) or game["home"] not in (higher, lower):
            raise AssertionError("game teams do not match the series")
        if int(game["home_score"]) == int(game["away_score"]):
            raise ValueError("series games cannot end tied")
        home_won = int(game["home_score"]) > int(game["away_score"])
        if game["home"] == higher:
            if home_won:
                wins_hi += 1
            else:
                wins_lo += 1
        else:
            if home_won:
                wins_lo += 1
            else:
                wins_hi += 1
        states.append(
            {
                "game": number,
                "wins_higher": wins_hi,
                "wins_lower": wins_lo,
                "over": series_is_over(wins_hi, wins_lo),
                "higher_eliminated": is_series_eliminated(wins_hi, wins_lo),
                "lower_eliminated": is_series_eliminated(wins_lo, wins_hi),
            }
        )
        if series_is_over(wins_hi, wins_lo) and number != games[-1]["game"]:
            raise AssertionError("series continued after a team reached 4 wins")
    return states


def break_record_tie(tied: list[int], point_diff, h2h) -> list[int]:
    """Order one win-percentage tie group, best first."""
    tied = list(tied)
    if len(tied) <= 1:
        return tied
    if len(tied) == 2:
        a, b = tied
        ahead = int(h2h[a, b]) - int(h2h[b, a])
        if ahead != 0:
            return [a, b] if ahead > 0 else [b, a]
        if int(point_diff[a]) != int(point_diff[b]):
            return [a, b] if int(point_diff[a]) > int(point_diff[b]) else [b, a]
        return sorted((a, b))

    def key(team: int):
        head = sum(int(h2h[team, other]) for other in tied if other != team)
        return (-int(point_diff[team]), -head, team)

    return sorted(tied, key=key)


def rank_teams(team_ids, wins, losses, point_diff, h2h) -> list[int]:
    """Best conference (or any pool) record first."""
    buckets: dict[Fraction, list[int]] = defaultdict(list)
    for team in team_ids:
        played = int(wins[team]) + int(losses[team])
        pct = Fraction(int(wins[team]), played) if played else Fraction(0)
        buckets[pct].append(int(team))
    ordered: list[int] = []
    for pct in sorted(buckets, reverse=True):
        ordered.extend(break_record_tie(buckets[pct], point_diff, h2h))
    return ordered


def finals_home_is_a(a: int, b: int, wins, losses, point_diff) -> bool:
    """True when team a should be the Finals home team under the simplified rule."""
    played_a = int(wins[a]) + int(losses[a])
    played_b = int(wins[b]) + int(losses[b])
    pct_a = Fraction(int(wins[a]), played_a) if played_a else Fraction(0)
    pct_b = Fraction(int(wins[b]), played_b) if played_b else Fraction(0)
    if pct_a != pct_b:
        return pct_a > pct_b
    if int(point_diff[a]) != int(point_diff[b]):
        return int(point_diff[a]) > int(point_diff[b])
    return a < b


def play_in_home_teams(seventh, eighth, ninth, tenth, winner_7v8):
    """Homes: 7 hosts 8, 9 hosts 10, the 7/8 loser hosts the last game."""
    if winner_7v8 not in (seventh, eighth):
        raise ValueError("7/8 winner is not one of those two teams")
    loser = eighth if winner_7v8 == seventh else seventh
    return seventh, ninth, loser


def resolve_play_in(seventh, eighth, ninth, tenth, winner_7v8, winner_9v10, winner_last):
    """Return (7-seed, 8-seed). The 7/8 winner is the 7-seed."""
    if winner_7v8 not in (seventh, eighth):
        raise ValueError("7/8 winner is not one of those two teams")
    if winner_9v10 not in (ninth, tenth):
        raise ValueError("9/10 winner is not one of those two teams")
    loser = eighth if winner_7v8 == seventh else seventh
    if winner_last not in (loser, winner_9v10):
        raise ValueError("last-game winner was not in that game")
    return winner_7v8, winner_last


def eliminated_from_play_in(team: int, wins, remaining, conference_ids) -> bool:
    """Conservative win-total elimination from a top-10 play-in spot.

    Ten conference rivals already have more wins than this team can reach.
    Equal to the maximum is not elimination, because a tiebreak could still
    go this team's way.
    """
    ceiling = int(wins[team]) + int(remaining[team])
    ahead = 0
    for other in conference_ids:
        if int(other) == int(team):
            continue
        if int(wins[other]) > ceiling:
            ahead += 1
    return ahead >= 10


def break_cup_tie(tied, h2h, point_diff, prior_wins, skip_head_to_head: bool) -> list[int]:
    """Cup tie order: head-to-head (unless skipped), point differential, 2025-26 wins, team index.

    Total points are not a separate key. Every group-play team has four games,
    and the simulator only draws margins, so a constant points-per-game base
    would rank total points the same way as point differential.
    """
    tied = list(tied)
    if len(tied) <= 1:
        return tied
    if len(tied) == 2 and not skip_head_to_head:
        a, b = tied
        ahead = int(h2h[a, b]) - int(h2h[b, a])
        if ahead != 0:
            return [a, b] if ahead > 0 else [b, a]
    def key(team: int):
        if skip_head_to_head:
            head = 0
        else:
            head = sum(int(h2h[team, other]) for other in tied if other != team)
        return (-head, -int(point_diff[team]), -int(prior_wins[team]), team)

    if len(tied) == 2 and not skip_head_to_head:
        a, b = tied
        # head-to-head already applied; finish with the remaining keys
        if int(point_diff[a]) != int(point_diff[b]):
            return [a, b] if int(point_diff[a]) > int(point_diff[b]) else [b, a]
        if int(prior_wins[a]) != int(prior_wins[b]):
            return [a, b] if int(prior_wins[a]) > int(prior_wins[b]) else [b, a]
        return sorted((a, b))
    return sorted(tied, key=key)


def rank_by_group_record(team_ids, group_wins, point_diff, h2h, prior_wins, skip_head_to_head=False):
    buckets: dict[int, list[int]] = defaultdict(list)
    for team in team_ids:
        buckets[int(group_wins[team])].append(int(team))
    ordered: list[int] = []
    for wins in sorted(buckets, reverse=True):
        ordered.extend(
            break_cup_tie(buckets[wins], h2h, point_diff, prior_wins, skip_head_to_head)
        )
    return ordered
