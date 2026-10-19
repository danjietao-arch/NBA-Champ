"""December games that the August 2026 schedule leaves unassigned.

NBA.com's Cup 101 says those opponents depend on group play. Quarterfinals and
semifinals count as regular-season games. The championship does not. The 22
teams that miss the knockout each play two games in that window, with two of
those games crossing conferences. Quarterfinal losers play each other once.

The exact travel formula is not published. This pairs teams with a deterministic
greedy matching that prefers opponents already scheduled to meet more often,
and gives the home court to the team with fewer designated home games so far.
"""

from __future__ import annotations

from dataclasses import dataclass

CUP_APPROXIMATION = (
    "12 月 4–10 日官方尚未指定对手。模拟按 Cup 101 的结构补上计入常规赛的场次："
    "分区四分之一决赛与半决赛、四分之一决赛负者的一场补赛，以及未晋级球队的两场。"
    "冠军战不计入。未晋级球队的具体对手是近似：每区小组赛排名最末的两队各打一场跨部比赛，"
    "其余用贪心配对，优先选择已经交手更多的对手，不包含联盟未公布的旅行约束。"
    "这些补赛的主场给到当时主场场次较少的一方；平手则 team 索引较小的一方主场。"
    "杯赛抽签这一条用稳定的 team 索引代替，以便同一随机种子可以复现。"
)


@dataclass(frozen=True)
class ExtraGame:
    date: str
    home: int
    away: int
    kind: str


def perfect_matching(teams: list[int], meetings) -> list[tuple[int, int]]:
    """Greedy perfect matching. `teams` must have even length."""
    remaining = set(int(team) for team in teams)
    if len(remaining) % 2 != 0:
        raise ValueError("matching needs an even number of teams")
    pairs = []
    while remaining:
        best = None
        ordered = sorted(remaining)
        for i, left in enumerate(ordered):
            for right in ordered[i + 1 :]:
                score = (int(meetings[left, right]), -left, -right)
                if best is None or score > best[0]:
                    best = (score, left, right)
        _, left, right = best
        pairs.append((left, right))
        remaining.remove(left)
        remaining.remove(right)
    return pairs


def _assign_home(left: int, right: int, home_count) -> tuple[int, int]:
    if home_count[left] < home_count[right] or (
        home_count[left] == home_count[right] and left < right
    ):
        host, visitor = left, right
    else:
        host, visitor = right, left
    home_count[host] += 1
    return host, visitor


def filler_games(ranked_east: list[int], ranked_west: list[int], meetings, home_count) -> list[ExtraGame]:
    """Two games for each of the 11 non-qualifiers in each conference.

    `ranked_*` is best group-play finish to worst.
    """
    if len(ranked_east) != 11 or len(ranked_west) != 11:
        raise ValueError("each conference must have 11 non-qualifiers")
    homes = list(home_count)
    # Copy so a second night can avoid rematches without touching the caller.
    weight = meetings.copy()
    games: list[ExtraGame] = []

    def add_night(date: str, east_cross_index: int, west_cross_index: int):
        east_cross = ranked_east[east_cross_index]
        west_cross = ranked_west[west_cross_index]
        host, visitor = _assign_home(east_cross, west_cross, homes)
        games.append(ExtraGame(date, host, visitor, "filler"))
        weight[east_cross, west_cross] -= 100
        weight[west_cross, east_cross] -= 100
        east_pool = [team for team in ranked_east if team != east_cross]
        west_pool = [team for team in ranked_west if team != west_cross]
        for pool in (east_pool, west_pool):
            for left, right in sorted(perfect_matching(pool, weight)):
                host, visitor = _assign_home(left, right, homes)
                games.append(ExtraGame(date, host, visitor, "filler"))
                weight[left, right] -= 100
                weight[right, left] -= 100

    # Worst team crosses on Dec 6; second-worst crosses on Dec 10.
    add_night("2026-12-06", -1, -1)
    add_night("2026-12-10", -2, -2)
    return games


def count_games(games: list[ExtraGame]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for game in games:
        counts[game.home] = counts.get(game.home, 0) + 1
        counts[game.away] = counts.get(game.away, 0) + 1
    return counts
