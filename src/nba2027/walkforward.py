"""Three-season walk-forward against the hardcoded simulator.

The control is the published simulator: series shock sd 3.0, and theta equal to
the preseason prior (there is no in-season weight yet). A candidate replaces
those two only when both log loss and Brier are lower. Market prices are not
an input.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from .history import checkpoint_dates
from .parameters import (
    HOME_COURT_POINTS,
    LOGISTIC_SCALE,
    MARGIN_SD,
    SERIES_SHOCK_SD,
    THETA_SD,
)
from .rules import rank_teams
from .teams import TEAMS

EAST = [index for index, team in enumerate(TEAMS) if team.conference == "East"]
WEST = [index for index, team in enumerate(TEAMS) if team.conference == "West"]
ABBREV_INDEX = {team.abbrev: index for index, team in enumerate(TEAMS)}
INDEX_ABBREV = {index: team.abbrev for index, team in enumerate(TEAMS)}

SERIES_GRID = (1.5, 3.0, 5.0)
K_GRID = (None, 40, 120, 400)
ROUND_NAMES = ("首轮结束", "分区半决赛结束", "分区决赛结束", "总决赛结束")


def sigmoid(diff: np.ndarray) -> np.ndarray:
    scaled = np.clip(diff / LOGISTIC_SCALE, -50.0, 50.0)
    return 1.0 / (1.0 + np.exp(-scaled))


def choose_replacement(rows: list[dict]) -> dict:
    """Replace w and series variance only when both scores beat the control."""
    control = next(row for row in rows if row["series_shock_sd"] == SERIES_SHOCK_SD and row["k"] is None)
    better = [
        row
        for row in rows
        if row is not control
        and row["log_loss"] < control["log_loss"]
        and row["brier"] < control["brier"]
    ]
    better.sort(key=lambda row: (row["log_loss"], row["brier"], row["series_shock_sd"], row["k"] or 0))
    if not better:
        return {"replaced": False, "control": control, "best": control}
    return {"replaced": True, "control": control, "best": better[0]}


def prepare_seasons(history: dict) -> tuple[list[dict], list[str]]:
    prepared = []
    problems = []
    for season in history["seasons"]:
        problems.extend(season.get("problems") or [])
        if season.get("champion") not in ABBREV_INDEX:
            problems.append(f"{season['season']} 没有从系列赛里读出冠军")
            continue
        prepared.append(_prepare(season))
    return prepared, problems


def _prepare(season: dict) -> dict:
    prior = np.zeros(30, dtype=float)
    for abbrev, value in season["prior_nrtg"].items():
        prior[ABBREV_INDEX[abbrev]] = value
    regular = [_game_tuple(game) for game in season["games_regular"]]
    dates = {}
    for game in season["games_regular"]:
        dates.setdefault(game["home"], set()).add(game["date"])
        dates.setdefault(game["away"], set()).add(game["date"])
    cup = season.get("uncounted_cup_final") or {}
    if cup.get("date"):
        for abbrev in (cup.get("home"), cup.get("away")):
            if abbrev in dates:
                dates[abbrev].add(cup["date"])
    for game in regular:
        game["home_b2b"] = _b2b(dates, INDEX_ABBREV[game["home"]], game["date"])
        game["away_b2b"] = _b2b(dates, INDEX_ABBREV[game["away"]], game["date"])
    standings = _standings(regular)
    seeds = _actual_seeds(standings, season["games_play_in"])
    rounds = _round_winners(season)
    bracket_ok = _bracket_matches(seeds, rounds[0] if rounds else [])
    return {
        "season": season["season"],
        "champion": ABBREV_INDEX[season["champion"]],
        "prior": prior,
        "regular": regular,
        "standings": standings,
        "seeds": seeds,
        "rounds": rounds,
        "bracket_ok": bracket_ok,
        "checkpoints": checkpoint_dates(season),
        "cup_final": cup,
    }


def _game_tuple(game: dict) -> dict:
    home = ABBREV_INDEX[game["home"]]
    away = ABBREV_INDEX[game["away"]]
    margin = int(game["home_pts"]) - int(game["away_pts"])
    edge = 0.0 if game["neutral"] else HOME_COURT_POINTS
    return {
        "date": game["date"],
        "home": home,
        "away": away,
        "margin": margin,
        "edge": edge,
        "home_b2b": False,
        "away_b2b": False,
    }


def _b2b(dates: dict, abbrev: str, iso: str) -> bool:
    previous = (datetime.fromisoformat(iso) - timedelta(days=1)).date().isoformat()
    return previous in dates.get(abbrev, ())


def _standings(games: list[dict]) -> dict:
    wins = np.zeros(30, dtype=np.int16)
    losses = np.zeros(30, dtype=np.int16)
    point_diff = np.zeros(30, dtype=np.int32)
    h2h = np.zeros((30, 30), dtype=np.int16)
    played = np.zeros(30, dtype=np.int16)
    for game in games:
        home, away, margin = game["home"], game["away"], game["margin"]
        if margin > 0:
            winner, loser, size = home, away, margin
        elif margin < 0:
            winner, loser, size = away, home, -margin
        else:
            raise RuntimeError("game log has a tie")
        wins[winner] += 1
        losses[loser] += 1
        point_diff[winner] += size
        point_diff[loser] -= size
        h2h[winner, loser] += 1
        played[home] += 1
        played[away] += 1
    return {"wins": wins, "losses": losses, "point_diff": point_diff, "h2h": h2h, "played": played}


def _actual_seeds(standings: dict, play_in: list[dict]) -> dict | None:
    seeds = {}
    for name, pool in (("East", EAST), ("West", WEST)):
        order = rank_teams(pool, standings["wins"], standings["losses"], standings["point_diff"], standings["h2h"])
        seventh, eighth, ninth, tenth = order[6:10]
        winner_78 = _play_in_winner(play_in, seventh, eighth)
        winner_910 = _play_in_winner(play_in, ninth, tenth)
        if winner_78 is None or winner_910 is None:
            return None
        loser = eighth if winner_78 == seventh else seventh
        winner_last = _play_in_winner(play_in, loser, winner_910)
        if winner_last is None:
            return None
        seeds[name] = order[:6] + [winner_78, winner_last]
    return seeds


def _play_in_winner(games: list[dict], a: int, b: int) -> int | None:
    pair = {INDEX_ABBREV[a], INDEX_ABBREV[b]}
    found = [game for game in games if {game["home"], game["away"]} == pair]
    if len(found) != 1:
        return None
    game = found[0]
    winner = game["home"] if game["home_pts"] > game["away_pts"] else game["away"]
    return ABBREV_INDEX[winner]


def _round_winners(season: dict) -> list[list[dict]]:
    series = sorted(season["series"], key=lambda item: (item["start"], item["end"], item["teams"]))
    finished = [item for item in series if item.get("winner")]
    if len(finished) < 15:
        return []
    chunks = [finished[0:8], finished[8:12], finished[12:14], finished[14:15]]
    rounds = []
    for chunk in chunks:
        rounds.append(
            [
                {
                    "teams": [ABBREV_INDEX[abbrev] for abbrev in item["teams"]],
                    "winner": ABBREV_INDEX[item["winner"]],
                }
                for item in chunk
            ]
        )
    return rounds


def _bracket_matches(seeds: dict | None, round1: list[dict]) -> bool:
    if not seeds or len(round1) != 8:
        return False
    expected = set()
    for pool in seeds.values():
        for higher, lower in ((0, 7), (3, 4), (1, 6), (2, 5)):
            expected.add(frozenset((pool[higher], pool[lower])))
    actual = {frozenset(item["teams"]) for item in round1}
    return expected == actual


def run_walk_forward(history: dict, n_sims: int = 800, seed: int = 20261019) -> dict:
    prepared, problems = prepare_seasons(history)
    base = {
        "attempted": True,
        "seasons": [season["season"] for season in history.get("seasons", [])],
        "n_sims": n_sims,
        "seed": seed,
        "series_grid": list(SERIES_GRID),
        "k_grid": ["先验" if value is None else value for value in K_GRID],
        "control": {"series_shock_sd": SERIES_SHOCK_SD, "w": "0，沿用赛前先验"},
        "market_prices_used": False,
        "form": "本赛季表现用逐场分差的场均，不是每百回合。日志里没有回合数，所以没有把分差换算成进攻防守效率。",
        "note": "对照的是参数写死的同一模拟器。一个赛季不能证明模型优于市场。市场报价没有进入拟合。",
    }
    if problems or len(prepared) != 3:
        base.update(
            {
                "data_fetched": False,
                "replaced_parameters": False,
                "problems": problems or ["没有凑齐三个可回放的赛季"],
                "summary": "三个赛季的逐场日志不完整，没有替换 w 或系列赛方差，仍用当前这份快照。",
            }
        )
        return base
    tasks = []
    for season_index, season in enumerate(prepared):
        for point_index, point in enumerate(season["checkpoints"]):
            if point["kind"] == "playoff_round" and not season["bracket_ok"]:
                continue
            if point["name"] == "总决赛结束":
                continue
            tasks.append((season_index, point_index, point))
    if not tasks:
        base.update(
            {
                "data_fetched": True,
                "replaced_parameters": False,
                "problems": ["没有可以评分的时点"],
                "summary": "日志能读，但没有可以评分的时点，没有替换参数。",
            }
        )
        return base
    rows = []
    for series_sd in SERIES_GRID:
        for k in K_GRID:
            total_log = 0.0
            total_brier = 0.0
            details = []
            for season_index, point_index, point in tasks:
                season = prepared[season_index]
                probabilities = _champion_probabilities(
                    season, point, k, series_sd, n_sims, seed + 1000 * season_index + point_index
                )
                log_loss, brier = _scores(probabilities, season["champion"], n_sims)
                total_log += log_loss
                total_brier += brier
                details.append(
                    {
                        "season": season["season"],
                        "checkpoint": point["name"],
                        "log_loss": round(log_loss, 6),
                        "brier": round(brier, 6),
                    }
                )
            count = len(tasks)
            rows.append(
                {
                    "series_shock_sd": series_sd,
                    "k": k,
                    "w": "0，沿用赛前先验" if k is None else f"已赛场次 / (已赛场次 + {k})",
                    "log_loss": total_log / count,
                    "brier": total_brier / count,
                    "checkpoints": details,
                }
            )
    decision = choose_replacement(rows)
    best = decision["best"]
    control = decision["control"]
    replaced = decision["replaced"]
    summary = _summary(replaced, best, control, prepared)
    base.update(
        {
            "data_fetched": True,
            "replaced_parameters": replaced,
            "problems": [] if all(item["bracket_ok"] for item in prepared) else [
                f"{item['season']} 的种子近似和真实首轮对阵不一致，季后赛时点没有拿来打分。"
                for item in prepared
                if not item["bracket_ok"]
            ],
            "bracket_ok": {item["season"]: item["bracket_ok"] for item in prepared},
            "champions_from_logs": {
                item["season"]: INDEX_ABBREV[item["champion"]] for item in prepared
            },
            "checkpoint_count": len(tasks),
            "candidates": [
                {
                    "series_shock_sd": row["series_shock_sd"],
                    "w": row["w"],
                    "k": row["k"],
                    "log_loss": round(row["log_loss"], 6),
                    "brier": round(row["brier"], 6),
                }
                for row in rows
            ],
            "control_log_loss": round(control["log_loss"], 6),
            "control_brier": round(control["brier"], 6),
            "best_log_loss": round(best["log_loss"], 6),
            "best_brier": round(best["brier"], 6),
            "best_series_shock_sd": best["series_shock_sd"],
            "best_w": best["w"],
            "best_k": best["k"],
            "summary": summary,
        }
    )
    return base


def _summary(replaced: bool, best: dict, control: dict, prepared: list[dict]) -> str:
    champions = "、".join(f"{item['season']} {INDEX_ABBREV[item['champion']]}" for item in prepared)
    scores = (
        f"写死参数的对数损失 {control['log_loss']:.4f}、Brier {control['brier']:.4f}。"
        f"网格里最好的是系列赛标准差 {best['series_shock_sd']}、w 为{best['w']}，"
        f"对数损失 {best['log_loss']:.4f}、Brier {best['brier']:.4f}。"
    )
    skipped = [item["season"] for item in prepared if not item["bracket_ok"]]
    skip_text = ""
    if skipped:
        skip_text = "这些赛季的季后赛时点没有打分，因为种子近似和真实首轮对阵不一致：" + "、".join(skipped) + "。"
    if not replaced:
        return (
            f"已用最近三个赛季的逐场日志做 walk-forward（冠军来自系列赛记录：{champions}）。"
            f"{scores}对数损失和 Brier 没有同时优于写死参数，所以不替换。"
            f"{skip_text}一个赛季不能证明模型优于市场。"
        )
    same_sd = best["series_shock_sd"] == control["series_shock_sd"]
    same_w = best["k"] is None
    if same_sd and not same_w:
        change = f"两项都更好。w 改为{best['w']}。系列赛标准差仍是 {best['series_shock_sd']}，没有改。"
    elif same_w and not same_sd:
        change = f"两项都更好。系列赛标准差改为 {best['series_shock_sd']}。w 仍是赛前先验。"
    else:
        change = f"两项都更好，因此采用系列赛标准差 {best['series_shock_sd']}，w 为{best['w']}。"
    return (
        f"已用最近三个赛季的逐场日志做 walk-forward（冠军来自系列赛记录：{champions}）。"
        f"{scores}{change}赛前一场未打，w 为 0，所以这份 30 队频率没有重跑。"
        f"{skip_text}一个赛季不能证明模型优于市场。"
    )


def _scores(probabilities: np.ndarray, champion: int, n_sims: int) -> tuple[float, float]:
    floor = 1.0 / (2.0 * n_sims)
    clipped = np.clip(probabilities, floor, 1.0)
    clipped = clipped / clipped.sum()
    log_loss = float(-np.log(clipped[champion]))
    target = np.zeros(30)
    target[champion] = 1.0
    brier = float(np.sum((probabilities - target) ** 2))
    return log_loss, brier


def _champion_probabilities(season: dict, point: dict, k, series_sd: float, n_sims: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    theta_shock = rng.normal(0.0, THETA_SD, size=(n_sims, 30))
    known, remaining, played, margin = _checkpoint_state(season, point)
    if k is None:
        weight = np.zeros(30)
    else:
        weight = played / (played + float(k))
    base = (1.0 - weight) * season["prior"] + weight * margin
    theta = base + theta_shock
    wins = np.tile(known["wins"], (n_sims, 1)).astype(np.int16)
    losses = np.tile(known["losses"], (n_sims, 1)).astype(np.int16)
    point_diff = np.tile(known["point_diff"], (n_sims, 1)).astype(np.int32)
    h2h = np.tile(known["h2h"], (n_sims, 1, 1)).astype(np.int16)
    if remaining:
        _simulate_games(theta, wins, losses, point_diff, h2h, remaining, rng)
    if point["kind"] == "playoff_round":
        counts = _simulate_from_actual(season, point, theta, wins, losses, point_diff, series_sd, rng)
    else:
        counts = _simulate_fresh_bracket(theta, wins, losses, point_diff, h2h, series_sd, rng)
    return counts / n_sims


def _checkpoint_state(season: dict, point: dict):
    after = point["after"]
    wins = np.zeros(30, dtype=np.int16)
    losses = np.zeros(30, dtype=np.int16)
    point_diff = np.zeros(30, dtype=np.int32)
    h2h = np.zeros((30, 30), dtype=np.int16)
    played = np.zeros(30, dtype=float)
    remaining = []
    games = season["regular"]
    if point["kind"] == "preseason":
        remaining = games
    else:
        for game in games:
            if game["date"] <= after:
                _apply_actual(wins, losses, point_diff, h2h, played, game)
            else:
                remaining.append(game)
    margin = np.divide(point_diff, played, out=np.zeros(30), where=played > 0)
    known = {"wins": wins, "losses": losses, "point_diff": point_diff, "h2h": h2h}
    return known, remaining, played, margin


def _apply_actual(wins, losses, point_diff, h2h, played, game) -> None:
    home, away, margin = game["home"], game["away"], game["margin"]
    if margin > 0:
        winner, loser, size = home, away, margin
    else:
        winner, loser, size = away, home, -margin
    wins[winner] += 1
    losses[loser] += 1
    point_diff[winner] += size
    point_diff[loser] -= size
    h2h[winner, loser] += 1
    played[home] += 1
    played[away] += 1


def _simulate_games(theta, wins, losses, point_diff, h2h, games, rng) -> None:
    n_sims = theta.shape[0]
    index = np.arange(n_sims)
    for game in games:
        home = game["home"]
        away = game["away"]
        diff = theta[:, home] - theta[:, away] + game["edge"]
        if game["home_b2b"]:
            diff = diff - 1.5
        if game["away_b2b"]:
            diff = diff + 1.5
        home_won = rng.random(n_sims) < sigmoid(diff)
        margin = np.maximum(1, np.rint(np.abs(diff + rng.normal(0.0, MARGIN_SD, size=n_sims)))).astype(np.int32)
        winners = np.where(home_won, home, away)
        losers = np.where(home_won, away, home)
        wins[index, winners] += 1
        losses[index, losers] += 1
        point_diff[index, winners] += margin
        point_diff[index, losers] -= margin
        h2h[index, winners, losers] += 1


def _simulate_fresh_bracket(theta, wins, losses, point_diff, h2h, series_sd, rng) -> np.ndarray:
    n_sims = theta.shape[0]
    east = np.empty((n_sims, 8), dtype=np.int16)
    west = np.empty((n_sims, 8), dtype=np.int16)
    for sample in range(n_sims):
        east_order = rank_teams(EAST, wins[sample], losses[sample], point_diff[sample], h2h[sample])
        west_order = rank_teams(WEST, wins[sample], losses[sample], point_diff[sample], h2h[sample])
        east[sample, :6] = east_order[:6]
        west[sample, :6] = west_order[:6]
        east[sample, 6], east[sample, 7] = _one_play_in(east_order[6:10], theta[sample], rng)
        west[sample, 6], west[sample, 7] = _one_play_in(west_order[6:10], theta[sample], rng)
    return _finish(east, west, theta, wins, losses, point_diff, series_sd, rng)


def _one_play_in(top, theta_row, rng) -> tuple[int, int]:
    seventh, eighth, ninth, tenth = [int(team) for team in top]
    winner_78 = seventh if rng.random() < _scalar_prob(theta_row, seventh, eighth) else eighth
    winner_910 = ninth if rng.random() < _scalar_prob(theta_row, ninth, tenth) else tenth
    loser = eighth if winner_78 == seventh else seventh
    winner_last = loser if rng.random() < _scalar_prob(theta_row, loser, winner_910) else winner_910
    return winner_78, winner_last


def _scalar_prob(theta_row, home: int, away: int) -> float:
    diff = float(theta_row[home] - theta_row[away] + HOME_COURT_POINTS)
    diff = min(50.0 * LOGISTIC_SCALE, max(-50.0 * LOGISTIC_SCALE, diff))
    return float(1.0 / (1.0 + np.exp(-diff / LOGISTIC_SCALE)))


def _simulate_from_actual(season, point, theta, wins, losses, point_diff, series_sd, rng) -> np.ndarray:
    """Hard-constrain series that have already finished. Do not redraw them."""
    n_sims = theta.shape[0]
    name = point["name"]
    done = ROUND_NAMES.index(name) + 1
    east = np.tile(np.array(season["seeds"]["East"], dtype=np.int16), (n_sims, 1))
    west = np.tile(np.array(season["seeds"]["West"], dtype=np.int16), (n_sims, 1))
    winners = []
    for pool in (east, west):
        round_winners = []
        for higher_i, lower_i in ((0, 7), (3, 4), (1, 6), (2, 5)):
            higher = pool[:, higher_i]
            lower = pool[:, lower_i]
            if done >= 1:
                actual = _lookup_winner(season["rounds"][0], int(higher[0]), int(lower[0]))
                round_winners.append(np.full(n_sims, actual, dtype=np.int16))
            else:
                round_winners.append(_series(higher, lower, theta, series_sd, rng))
        if done >= 2:
            semis = [
                np.full(n_sims, _lookup_winner(season["rounds"][1], int(round_winners[0][0]), int(round_winners[1][0])), dtype=np.int16),
                np.full(n_sims, _lookup_winner(season["rounds"][1], int(round_winners[2][0]), int(round_winners[3][0])), dtype=np.int16),
            ]
        else:
            semis = [
                _advance(round_winners[0], round_winners[1], pool, theta, series_sd, rng),
                _advance(round_winners[2], round_winners[3], pool, theta, series_sd, rng),
            ]
        if done >= 3:
            winners.append(np.full(n_sims, _lookup_winner(season["rounds"][2], int(semis[0][0]), int(semis[1][0])), dtype=np.int16))
        else:
            winners.append(_advance(semis[0], semis[1], pool, theta, series_sd, rng))
    if done >= 4:
        counts = np.zeros(30, dtype=float)
        counts[season["champion"]] = n_sims
        return counts
    champion = _finals(winners[0], winners[1], wins, losses, point_diff, theta, series_sd, rng)
    counts = np.zeros(30, dtype=float)
    for team in champion:
        counts[int(team)] += 1
    return counts


def _lookup_winner(round_rows: list[dict], a: int, b: int) -> int:
    pair = {a, b}
    for row in round_rows:
        if set(row["teams"]) == pair:
            return int(row["winner"])
    raise RuntimeError(f"no finished series for {INDEX_ABBREV[a]} vs {INDEX_ABBREV[b]}")


def _finish(east, west, theta, wins, losses, point_diff, series_sd, rng) -> np.ndarray:
    east_champ = _conference_winner(east, theta, series_sd, rng)
    west_champ = _conference_winner(west, theta, series_sd, rng)
    champion = _finals(east_champ, west_champ, wins, losses, point_diff, theta, series_sd, rng)
    counts = np.zeros(30, dtype=float)
    for team in champion:
        counts[int(team)] += 1
    return counts


def _conference_winner(seeds, theta, series_sd, rng) -> np.ndarray:
    winners = []
    for higher_i, lower_i in ((0, 7), (3, 4), (1, 6), (2, 5)):
        winners.append(_series(seeds[:, higher_i], seeds[:, lower_i], theta, series_sd, rng))
    semis = [
        _advance(winners[0], winners[1], seeds, theta, series_sd, rng),
        _advance(winners[2], winners[3], seeds, theta, series_sd, rng),
    ]
    return _advance(semis[0], semis[1], seeds, theta, series_sd, rng)


def _advance(left, right, seeds, theta, series_sd, rng) -> np.ndarray:
    index = np.arange(theta.shape[0])
    seed_no = np.full((theta.shape[0], 30), 99, dtype=np.int16)
    for slot in range(8):
        seed_no[index, seeds[:, slot]] = slot
    left_better = seed_no[index, left] < seed_no[index, right]
    higher = np.where(left_better, left, right)
    lower = np.where(left_better, right, left)
    return _series(higher, lower, theta, series_sd, rng)


def _finals(east, west, wins, losses, point_diff, theta, series_sd, rng) -> np.ndarray:
    index = np.arange(theta.shape[0])
    played_east = wins[index, east] + losses[index, east]
    played_west = wins[index, west] + losses[index, west]
    left = wins[index, east].astype(np.int32) * played_west.astype(np.int32)
    right = wins[index, west].astype(np.int32) * played_east.astype(np.int32)
    percent = np.sign(left - right)
    margin = np.sign(point_diff[index, east] - point_diff[index, west])
    east_home = np.where(percent != 0, percent > 0, np.where(margin != 0, margin > 0, east < west))
    higher = np.where(east_home, east, west)
    lower = np.where(east_home, west, east)
    return _series(higher, lower, theta, series_sd, rng)


def _series(higher, lower, theta, series_sd, rng) -> np.ndarray:
    n_sims = theta.shape[0]
    index = np.arange(n_sims)
    shock = rng.normal(0.0, series_sd, size=n_sims)
    wins_hi = np.zeros(n_sims, dtype=np.int8)
    wins_lo = np.zeros(n_sims, dtype=np.int8)
    uniforms = rng.random((7, n_sims))
    for game_number in range(7):
        live = (wins_hi < 4) & (wins_lo < 4)
        if not np.any(live):
            break
        higher_home = game_number in (0, 1, 4, 6)
        home = higher if higher_home else lower
        away = lower if higher_home else higher
        sign = 1.0 if higher_home else -1.0
        diff = theta[index, home] - theta[index, away] + HOME_COURT_POINTS + sign * shock
        home_won = uniforms[game_number] < sigmoid(diff)
        hi_won = home_won if higher_home else ~home_won
        wins_hi += (live & hi_won).astype(np.int8)
        wins_lo += (live & ~hi_won).astype(np.int8)
    return np.where(wins_hi >= 4, higher, lower)
