"""Recompute after a 2026-27 game only when that game is already on disk.

There is no 2026-27 result file in this repo. The script does not invent scores
and does not replace the current snapshot with zeros.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "results_2026_27.json"


def main() -> int:
    if not RESULTS.exists():
        print("没有 2026—27 逐场结果，不重算。当前快照保持不变。")
        return 0
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    games = payload.get("games") or []
    if not games:
        print("结果文件里没有比赛，不重算，也不把缺失比分写成 0。")
        return 0
    required = {"date", "home", "away", "home_pts", "away_pts"}
    for game in games:
        if not required <= set(game):
            print("结果文件缺字段，拒绝重算。")
            return 2
    print(
        f"读到 {len(games)} 场 2026—27 比赛。赛季中的重算要沿用已赛事实再模拟剩余赛程；"
        "这场运行不改当前赛前快照，避免在没有完整剩余赛程约束时另写一套概率。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
