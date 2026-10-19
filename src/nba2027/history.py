"""Parse Basketball-Reference month pages into team game logs.

stats.nba.com is not used here: that endpoint timed out when this project
tried it. Ratings are previous-season net ratings, which are known before the
season being replayed. Game logs supply the score, home team, date, and opponent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .teams import TEAMS

BR_TO_ABBREV = {"BRK": "BKN", "CHO": "CHA", "PHO": "PHX"}
ABBREV_TO_INDEX = {team.abbrev: index for index, team in enumerate(TEAMS)}
MONTHS = (
    "october",
    "november",
    "december",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
)
SEASONS = (
    {"season": "2023-24", "end_year": 2024, "prior_year": 2023},
    {"season": "2024-25", "end_year": 2025, "prior_year": 2024},
    {"season": "2025-26", "end_year": 2026, "prior_year": 2025},
)

_ROW_RE = re.compile(r"<tr\b[^>]*>.*?</tr>", re.S)
_TEAM_RE = re.compile(r"/teams/([A-Z]{3})/")
_STAT_RE = re.compile(r'data-stat="([^"]+)"[^>]*>(.*?)</t[dh]>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def abbrev_from_br(code: str) -> str:
    return BR_TO_ABBREV.get(code, code)


def parse_games(html: str) -> list[dict]:
    games = []
    for row in _ROW_RE.findall(html):
        date_match = re.search(r'data-stat="date_game" csk="(\d{8})', row)
        if not date_match:
            continue
        fields = {name: _TAG_RE.sub("", body).strip() for name, body in _STAT_RE.findall(row)}
        visitor = _TEAM_RE.search(row[row.find('data-stat="visitor_team_name"'):] if 'visitor_team_name' in row else "")
        # Search each side separately so a visitor link cannot be reused as home.
        visitor_chunk = _chunk(row, "visitor_team_name")
        home_chunk = _chunk(row, "home_team_name")
        visitor_match = _TEAM_RE.search(visitor_chunk)
        home_match = _TEAM_RE.search(home_chunk)
        if not visitor_match or not home_match:
            continue
        if not fields.get("visitor_pts", "").isdigit() or not fields.get("home_pts", "").isdigit():
            continue
        remark = fields.get("game_remarks", "")
        games.append(
            {
                "date": f"{date_match.group(1)[0:4]}-{date_match.group(1)[4:6]}-{date_match.group(1)[6:8]}",
                "away": abbrev_from_br(visitor_match.group(1)),
                "home": abbrev_from_br(home_match.group(1)),
                "away_pts": int(fields["visitor_pts"]),
                "home_pts": int(fields["home_pts"]),
                "neutral": remark.lower().startswith("at "),
                "play_in": "play-in" in remark.lower(),
                "remark": remark,
            }
        )
    return games


def _chunk(row: str, stat: str) -> str:
    start = row.find(f'data-stat="{stat}"')
    if start < 0:
        return ""
    end = row.find('data-stat="', start + 10)
    return row[start:] if end < 0 else row[start:end]


def parse_ratings(html: str) -> dict[str, float]:
    ratings = {}
    for row in _ROW_RE.findall(html):
        if 'data-stat="team_name"' not in row or 'data-stat="net_rtg"' not in row:
            continue
        team_match = _TEAM_RE.search(_chunk(row, "team_name"))
        net_match = re.search(r'data-stat="net_rtg"[^>]*>\s*(-?\d+(?:\.\d+)?)', row)
        if not team_match or not net_match:
            continue
        abbrev = abbrev_from_br(team_match.group(1))
        if abbrev not in ABBREV_TO_INDEX:
            continue
        ratings[abbrev] = float(net_match.group(1))
    return ratings


def cup_final_key(games: list[dict]) -> dict | None:
    """The championship game is logged but does not count as a regular-season game.

    Month pages label both group games and the final as NBA Cup or In-Season
    Tournament. The final is the last such game. Excluding it is what leaves
    every team on 82 counted games; the earlier cup games stay in the log.
    """
    marked = [
        game for game in games
        if "cup" in game["remark"].lower() or "tournament" in game["remark"].lower()
    ]
    if not marked:
        return None
    final = max(marked, key=lambda game: (game["date"], game["home"], game["away"]))
    return dict(final)


def assemble_season(games: list[dict], ratings: dict[str, float], season: str, end_year: int) -> dict:
    deduped = []
    seen = set()
    for game in sorted(games, key=lambda item: (item["date"], item["home"], item["away"])):
        key = (game["date"], game["home"], game["away"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(game)
    final = cup_final_key(deduped)
    final_key = None if final is None else (final["date"], final["home"], final["away"])
    regular = []
    play_in = []
    playoff = []
    played = {team.abbrev: 0 for team in TEAMS}
    for game in deduped:
        key = (game["date"], game["home"], game["away"])
        if final_key is not None and key == final_key:
            continue
        if game["play_in"]:
            play_in.append(game)
            continue
        if played[game["home"]] >= 82 or played[game["away"]] >= 82:
            playoff.append(game)
            continue
        regular.append(game)
        played[game["home"]] += 1
        played[game["away"]] += 1
    series = _series(playoff)
    rounds = _rounds(series)
    problems = []
    short = [abbrev for abbrev, count in played.items() if count != 82]
    if short:
        problems.append(f"{season} 常规赛不是每队 82 场：{', '.join(sorted(short))}")
    if len(play_in) != 6:
        problems.append(f"{season} 附加赛场次是 {len(play_in)}，不是 6")
    if [len(bucket) for bucket in rounds] != [8, 4, 2, 1]:
        problems.append(f"{season} 系列赛轮次数量是 {[len(bucket) for bucket in rounds]}，不是 8/4/2/1")
    missing_prior = [team.abbrev for team in TEAMS if team.abbrev not in ratings]
    if missing_prior:
        problems.append(f"{season} 缺少上赛季净效率：{', '.join(missing_prior)}")
    champion = None
    if rounds and rounds[-1]:
        last_series = rounds[-1][0]
        champion = last_series["winner"]
        if last_series["wins"][last_series["winner"]] < 4:
            problems.append(f"{season} 最后一系列没有打到 4 胜")
            champion = None
    return {
        "season": season,
        "end_year": end_year,
        "games_regular": regular,
        "games_play_in": play_in,
        "games_playoff": playoff,
        "series": [_public_series(item) for item in series],
        "round_ends": [_round_end(bucket) for bucket in rounds],
        "prior_nrtg": {abbrev: ratings[abbrev] for abbrev in ratings},
        "champion": champion,
        "regular_season_counts": played,
        "uncounted_cup_final": final,
        "problems": problems,
    }


def _series(games: list[dict]) -> list[dict]:
    buckets: dict[tuple[str, str], list[dict]] = {}
    for game in games:
        key = tuple(sorted((game["home"], game["away"])))
        buckets.setdefault(key, []).append(game)
    series = []
    for pair, rows in buckets.items():
        wins = {pair[0]: 0, pair[1]: 0}
        used = []
        for game in rows:
            if wins[pair[0]] >= 4 or wins[pair[1]] >= 4:
                break
            winner = game["home"] if game["home_pts"] > game["away_pts"] else game["away"]
            wins[winner] += 1
            used.append(game)
        winner = max(wins, key=wins.get)
        series.append(
            {
                "teams": list(pair),
                "games": used,
                "wins": wins,
                "winner": winner if wins[winner] >= 4 else None,
                "start": used[0]["date"],
                "end": used[-1]["date"],
            }
        )
    series.sort(key=lambda item: (item["start"], item["end"], item["teams"]))
    return series


def _rounds(series: list[dict]) -> list[list[dict]]:
    """Split finished series into the four rounds by start date."""
    finished = [item for item in series if item["winner"]]
    finished.sort(key=lambda item: (item["start"], item["end"], item["teams"]))
    if len(finished) < 15:
        return [finished]
    return [finished[0:8], finished[8:12], finished[12:14], finished[14:15]]


def _round_end(bucket: list[dict]) -> str | None:
    if not bucket:
        return None
    return max(item["end"] for item in bucket)


def _public_series(item: dict) -> dict:
    return {
        "teams": item["teams"],
        "winner": item["winner"],
        "wins": item["wins"],
        "start": item["start"],
        "end": item["end"],
        "games": len(item["games"]),
    }


def load_history(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def checkpoint_dates(season: dict) -> list[dict]:
    """Preseason, about 20/40/60 games, end of the regular season, and each round."""
    counts = {team.abbrev: 0 for team in TEAMS}
    marks = {20: None, 40: None, 60: None}
    for game in season["games_regular"]:
        for abbrev in (game["home"], game["away"]):
            counts[abbrev] += 1
        ordered = sorted(counts.values())
        median = ordered[len(ordered) // 2]
        for target in marks:
            if marks[target] is None and median >= target:
                marks[target] = game["date"]
    points = [{"name": "赛前", "after": None, "kind": "preseason"}]
    for target, after in marks.items():
        points.append({"name": f"约{target}场", "after": after, "kind": "regular"})
    last_regular = season["games_regular"][-1]["date"] if season["games_regular"] else None
    points.append({"name": "常规赛结束", "after": last_regular, "kind": "regular_end"})
    labels = ("首轮结束", "分区半决赛结束", "分区决赛结束", "总决赛结束")
    for label, after in zip(labels, season["round_ends"]):
        points.append({"name": label, "after": after, "kind": "playoff_round"})
    return points
