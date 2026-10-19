# 2026—27 NBA 总冠军概率（赛前）

私人研究页面。30 队的夺冠频率来自种子 `20261019` 的那次蒙特卡洛。赛前还没有 2026—27 的比赛，所以 walk-forward 选出的 `w` 在这份快照里是 0，频率没有重跑。系列赛标准差仍是 3.0。

页面标明：**w 已由 walk-forward 替换；系列赛标准差仍是 3.0**

对照只读 [NBA: 2027 Champion](https://polymarket.com/event/nba-2027-champion) 的总冠军 YES。订单簿报价不进入模型。

这不是投注建议。统计只用于私人研究，页面署名 NBA.com。

## 运行

```bash
python3 -m pytest -q
python3 scripts/build_preseason_snapshot.py
python3 scripts/run_walk_forward.py
python3 scripts/build_board.py
python3 scripts/hourly_quotes.py
python3 scripts/recompute_after_games.py
```

`build_preseason_snapshot.py` 重跑模拟。`build_board.py` 把已经审过的冠军市场和 walk-forward 说明贴上当前快照。没有 2026—27 逐场结果时，`recompute_after_games.py` 不改概率。
