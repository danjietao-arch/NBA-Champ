"""Replay the last three seasons and keep the hardcoded parameters unless both scores improve."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nba2027.history import MONTHS, SEASONS, assemble_season, parse_games, parse_ratings  # noqa: E402
from nba2027.walkforward import run_walk_forward  # noqa: E402

STATS_NBA_FAILURE = (
    "https://stats.nba.com/stats/leaguegamelog 在 2026-10-19 请求 2025-26 常规赛时，"
    "25 秒后超时，返回 0 字节。逐场日志改用 Basketball-Reference 的月份赛程，没有补造比赛。"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def load_from_html(html_dir: Path) -> dict:
    seasons = []
    for spec in SEASONS:
        games = []
        for month in MONTHS:
            games.extend(parse_games(_read(html_dir / f"games-{spec['end_year']}-{month}.html")))
        prior_name = f"r{spec['prior_year'] % 100:02d}.html"
        ratings = parse_ratings(_read(html_dir / prior_name))
        seasons.append(assemble_season(games, ratings, spec["season"], spec["end_year"]))
    return {
        "fetched_on": "2026-10-19",
        "game_source": "https://www.basketball-reference.com/leagues/NBA_{year}_games-{month}.html",
        "rating_source": "https://www.basketball-reference.com/leagues/NBA_{year}_ratings.html",
        "stats_nba_failure": STATS_NBA_FAILURE,
        "seasons": seasons,
    }


def main() -> None:
    html_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp")
    n_sims = int(sys.argv[2]) if len(sys.argv) > 2 else 800
    history = load_from_html(html_dir)
    out = ROOT / "data" / "history"
    out.mkdir(parents=True, exist_ok=True)
    (out / "game_logs.json").write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    report = run_walk_forward(history, n_sims=n_sims)
    report["failures"] = [STATS_NBA_FAILURE]
    report["sources"] = [history["game_source"], history["rating_source"]]
    path = ROOT / "data" / "walk_forward_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report["summary"])
    print(path)


if __name__ == "__main__":
    main()
