"""Build the preseason JSON document and the Chinese static page from one result."""

from __future__ import annotations

import csv
import html
import json
from datetime import datetime, timezone

import numpy as np

from .cup import CUP_APPROXIMATION
from .parameters import (
    BACK_TO_BACK_POINTS,
    HOME_COURT_POINTS,
    INFORMATION_AS_OF,
    LOGISTIC_SCALE,
    MARGIN_SD,
    MODEL_VERSION,
    PARAMETER_STATUS,
    SERIES_SHOCK_SD,
    THETA_SD,
)
from .rules import APPROXIMATIONS
from .teams import TEAMS

DISCLAIMER = "这不是投注建议。本页是对未来比赛结果的概率估计，不保证准确，不自动交易。"
ATTRIBUTION = "统计仅用于私人研究，页面署名 NBA.com。不转售，也不公开一份持续更新的比赛统计库。"


def rank_quantile(hist_row, q: float, n: int) -> int:
    need = max(1, int(np.ceil(q * n)))
    total = 0
    for rank in range(1, 16):
        total += int(hist_row[rank])
        if total >= need:
            return rank
    return 15


def _percent(count: int, n: int) -> float:
    return 100.0 * count / n


def build_document(result, inputs, generated_at: str | None = None) -> dict:
    generated_at = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    failed = inputs["priors_doc"]["failed_preferred_source"]
    base = {
        "title": "2026—27 NBA 总冠军概率（赛前）",
        "target": "2027 年 NBA 总决赛胜者",
        "parameter_status": PARAMETER_STATUS,
        "model_version": MODEL_VERSION,
        "model_as_of": INFORMATION_AS_OF,
        "generated_at": generated_at,
        "includes_2026_27_results": False,
        "previous_snapshot": None,
        "disclaimer": DISCLAIMER,
        "attribution": ATTRIBUTION,
        "scenarios": [],
        "adjustments_applied": inputs["adjustments_applied"],
        "adjustment_note": inputs["adjustments_doc"]["description"],
        "failed_prior_source": failed,
        "prior_source": {
            "url": inputs["priors_doc"]["source_url"],
            "fetched_on": inputs["priors_doc"]["fetched_on"],
            "fields": inputs["priors_doc"]["fields"],
        },
        "schedule_source": {
            "url": inputs["schedule_doc"]["source_url"],
            "page": inputs["schedule_doc"]["source_page"],
            "as_of": inputs["schedule_doc"]["as_of"],
            "note": inputs["schedule_doc"]["note"],
        },
        "cup_source": {
            "url": inputs["cup_doc"]["source_url"],
            "note": inputs["cup_doc"]["source_note"],
        },
        "parameters": {
            "status": PARAMETER_STATUS,
            "logistic_scale": LOGISTIC_SCALE,
            "home_court_points": HOME_COURT_POINTS,
            "back_to_back_points": BACK_TO_BACK_POINTS,
            "series_shock_sd": SERIES_SHOCK_SD,
            "theta_sd": THETA_SD,
            "margin_sd": MARGIN_SD,
        },
        "approximations": APPROXIMATIONS + [CUP_APPROXIMATION, _REST_NOTE, _SERIES_NOTE, _INTERVAL_NOTE],
    }
    if result is None:
        base.update(
            {
                "probabilities_published": False,
                "withheld_reason": "至少一支球队缺少 2025—26 攻防效率，整表不填概率。",
                "teams": [_blank_team(index, inputs) for index in range(len(TEAMS))],
            }
        )
        return base

    n = int(result["n_total"])
    if int(result["champions"].sum()) != n:
        raise RuntimeError("each simulation must have one champion")
    shown = [round(_percent(int(result["champions"][i]), n), 2) for i in range(len(TEAMS))]
    if abs(sum(shown) - 100.0) > 0.1:
        raise RuntimeError(f"rounded probabilities sum to {sum(shown)}")

    teams = []
    for index, team in enumerate(TEAMS):
        count = int(result["champions"][index])
        outer_counts = [int(value) for value in result["outer"][:, index]]
        outer_rates = np.array(outer_counts, dtype=float) / int(result["n_inner"])
        med = rank_quantile(result["rank_hist"][index], 0.50, n)
        q1 = rank_quantile(result["rank_hist"][index], 0.25, n)
        q3 = rank_quantile(result["rank_hist"][index], 0.75, n)
        reached = result["reached"][index]
        opponents = result["r1"][index]
        opponent_total = int(opponents.sum())
        if opponent_total == 0:
            modal_opponent = None
            modal_share = None
        else:
            opp = int(opponents.argmax())
            modal_opponent = {
                "team_id": TEAMS[opp].team_id,
                "zh": TEAMS[opp].zh,
                "share_of_round1": float(opponents[opp] / opponent_total),
            }
            modal_share = modal_opponent["share_of_round1"]
        path = _path_sentence(team.conference, med, q1, q3, reached, n, modal_opponent, modal_share)
        teams.append(
            {
                "team_id": team.team_id,
                "abbrev": team.abbrev,
                "zh": team.zh,
                "en": team.en,
                "conference": "东部" if team.conference == "East" else "西部",
                "prior_status": inputs["prior_status"][index],
                "ortg": float(inputs["ortg"][index]),
                "drtg": float(inputs["drtg"][index]),
                "theta": float(inputs["theta"][index]),
                "championships": count,
                "n": n,
                "p_champion": count / n,
                "p_champion_percent_rounded": shown[index],
                "exact_zero": False,
                "eliminated": False,
                "elimination_basis": None,
                "uncertainty": {
                    "method": "外层样本频率的 10% 与 90% 分位",
                    "p10": float(np.quantile(outer_rates, 0.10)),
                    "p90": float(np.quantile(outer_rates, 0.90)),
                    "outer_championships": outer_counts,
                },
                "delta_pp": None,
                "change_reason": "首份快照，没有上一份可比。",
                "seed_median": med,
                "seed_q1": q1,
                "seed_q3": q3,
                "p_top10": int(reached[0]) / n,
                "p_round1": int(reached[1]) / n,
                "p_round2": int(reached[2]) / n,
                "p_conference_finals": int(reached[3]) / n,
                "p_finals": int(reached[4]) / n,
                "modal_round1_opponent": modal_opponent,
                "path": path,
            }
        )
    teams.sort(key=lambda row: (-row["championships"], row["team_id"]))
    base.update(
        {
            "probabilities_published": True,
            "n_simulations": n,
            "n_outer": int(result["n_outer"]),
            "n_inner": int(result["n_inner"]),
            "random_seed": int(result["seed"]),
            "probability_sum": 1.0,
            "rounded_percent_sum": round(sum(shown), 2),
            "teams": teams,
        }
    )
    return base


def _blank_team(index: int, inputs) -> dict:
    team = TEAMS[index]
    status = inputs["prior_status"][index]
    return {
        "team_id": team.team_id,
        "abbrev": team.abbrev,
        "zh": team.zh,
        "en": team.en,
        "conference": "东部" if team.conference == "East" else "西部",
        "prior_status": status,
        "ortg": None if status != "已采集" else float(inputs["ortg"][index]),
        "drtg": None if status != "已采集" else float(inputs["drtg"][index]),
        "theta": None,
        "championships": None,
        "p_champion": None,
        "exact_zero": False,
        "eliminated": False,
        "elimination_basis": None,
        "delta_pp": None,
        "change_reason": "先验缺失，未模拟。",
        "path": "待采集",
    }


def _path_sentence(conference, med, q1, q3, reached, n, modal, share) -> str:
    side = "东部" if conference == "East" else "西部"
    text = (
        f"{side}排名中位 {med}（四分位 {q1}–{q3}）。"
        f"进入首轮 {int(reached[1]) / n:.1%}，"
        f"分区决赛 {int(reached[3]) / n:.1%}，"
        f"总决赛 {int(reached[4]) / n:.1%}。"
    )
    if modal is None:
        return text + "这些模拟里没有进入首轮。"
    return text + f"在进入首轮的模拟里，最常见对手是{modal['zh']}（{share:.0%}）。"


def probability_cell(team: dict) -> str:
    if team.get("eliminated"):
        basis = team.get("elimination_basis") or "见快照"
        return f"0%（官方淘汰：{basis}）"
    if team.get("p_champion") is None or team.get("prior_status") == "待采集":
        return "待采集"
    count = int(team["championships"])
    n = int(team["n"])
    if count == 0:
        return f"0.00%（0/{n}，模拟频率，不是官方淘汰）"
    return f"{team['p_champion_percent_rounded']:.2f}%（{count}/{n}）"


def render_html(document: dict) -> str:
    rows = []
    if document["probabilities_published"]:
        for team in document["teams"]:
            low = team["uncertainty"]["p10"] * 100
            high = team["uncertainty"]["p90"] * 100
            rows.append(
                "<tr>"
                f"<td>{_esc(team['conference'])} · {_esc(team['zh'])}<span>{_esc(team['en'])}</span></td>"
                f"<td class='num'>{team['theta']:.2f}<span>{team['ortg']:.2f} / {team['drtg']:.2f}</span></td>"
                f"<td class='num'>{_esc(probability_cell(team))}</td>"
                f"<td class='num'>{low:.2f}% – {high:.2f}%</td>"
                "<td>—</td>"
                f"<td>{_esc(team['change_reason'])}</td>"
                f"<td class='num'>{team['seed_median']}<span>{team['seed_q1']}–{team['seed_q3']}</span></td>"
                f"<td>{_esc(team['path'])}</td>"
                "</tr>"
            )
        sum_line = (
            f"30 队四舍五入后的百分比之和为 {document['rounded_percent_sum']:.2f}%。"
            f"未四舍五入的频率之和为 100%：{document['n_simulations']} 次模拟各产生一个冠军。"
        )
    else:
        for team in document["teams"]:
            theta = "待采集" if team["theta"] is None else f"{team['theta']:.2f}"
            rows.append(
                "<tr>"
                f"<td>{_esc(team['conference'])} · {_esc(team['zh'])}<span>{_esc(team['en'])}</span></td>"
                f"<td class='num'>{_esc(theta)}</td>"
                f"<td>{_esc(probability_cell(team))}</td>"
                "<td>待采集</td><td>—</td>"
                f"<td>{_esc(team['change_reason'])}</td>"
                "<td>—</td><td>待采集</td>"
                "</tr>"
            )
        sum_line = document["withheld_reason"]

    failed = document["failed_prior_source"]
    approximations = "".join(f"<li>{_esc(item)}</li>" for item in document["approximations"])
    meta = _meta_block(document)
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>2026—27 NBA 总冠军概率（赛前）</title>
<style>
:root {{
  --ink: #1c1915;
  --muted: #5f584e;
  --paper: #f3efe6;
  --card: #fffaf3;
  --line: #ddd4c6;
  --mark: #8d2d1f;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font: 16px/1.55 "Source Han Sans SC", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
}}
main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 64px; }}
h1 {{ font-family: "Source Han Serif SC", "Noto Serif SC", "Songti SC", Palatino, serif; font-weight: 600; font-size: 2rem; margin: 0 0 12px; }}
h2 {{ font-size: 1.05rem; margin: 28px 0 8px; }}
p {{ margin: 0 0 10px; }}
.status {{
  display: inline-block;
  margin: 0 0 16px;
  padding: 6px 10px;
  background: var(--mark);
  color: #fffaf3;
  font-weight: 700;
  letter-spacing: 0.02em;
}}
.warn, .note {{
  background: var(--card);
  border-left: 4px solid var(--mark);
  padding: 12px 14px;
  margin: 0 0 16px;
}}
.note {{ border-left-color: #8a8175; }}
.meta {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px 16px; margin: 8px 0 18px; }}
.meta div {{ background: var(--card); border: 1px solid var(--line); padding: 8px 10px; }}
.meta span {{ display: block; color: var(--muted); font-size: 0.78rem; }}
table {{ width: 100%; border-collapse: collapse; background: var(--card); font-size: 0.92rem; }}
th, td {{ border-bottom: 1px solid var(--line); padding: 8px 8px; vertical-align: top; text-align: left; }}
th {{ font-size: 0.78rem; color: var(--muted); font-weight: 600; }}
td span, th span {{ display: block; color: var(--muted); font-size: 0.75rem; }}
.num {{ font-variant-numeric: tabular-nums; white-space: nowrap; }}
footer {{ margin-top: 28px; color: var(--muted); font-size: 0.92rem; }}
code {{ word-break: break-all; }}
</style>
</head>
<body>
<main>
<p>私人研究 · 赛前快照 · 不是公开网站</p>
<h1>2026—27 NBA 总冠军概率</h1>
<p class="status">{PARAMETER_STATUS}</p>
<div class="warn"><p>{DISCLAIMER}</p></div>
<p>目标只是 2027 年 6 月总决赛的胜者。这里的数字是模拟频率，不是实力排名，也没有用 2026—27 已经打完的比赛——赛季尚未开始。</p>
{meta}
<p>{sum_line}</p>
<table>
<thead>
<tr>
<th>球队</th>
<th>先验净效率<span>进攻 / 防守，每百回合</span></th>
<th>模拟夺冠频率</th>
<th>不确定性<span>外层 10%–90%，单独列出</span></th>
<th>相对上一份</th>
<th>变化原因</th>
<th>种子中位<span>四分位</span></th>
<th>预期路径</th>
</tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
<h2>规则近似</h2>
<ul>{approximations}</ul>
<h2>来源</h2>
<div class="note">
<p>优先想用的 NBA 统计接口没有返回，所以 2025—26 攻防效率改用下面这份已打开的表，而不是编一个数。失败的地址：</p>
<p><code>{_esc(failed['url'])}</code></p>
<p>{_esc(failed['error'])}</p>
<p>实际使用：<a href="{_esc(document['prior_source']['url'])}">{_esc(document['prior_source']['url'])}</a>，抓取日 { _esc(document['prior_source']['fetched_on']) }。</p>
<p>赛程：<a href="{_esc(document['schedule_source']['url'])}">NBA.com 2026—27 赛程 PDF</a>（文件内日期 { _esc(document['schedule_source']['as_of']) }）。杯赛规则：<a href="{_esc(document['cup_source']['url'])}">NBA.com Cup 101</a>。</p>
<p>人工调整：没有已核实且写明幅度的条目，主预测不加休赛期修正。假设情景：没有。</p>
</div>
<footer>
<p>{ATTRIBUTION}</p>
<p>{DISCLAIMER}</p>
<p>NBA.com 的使用条款限制把统计做成综合、定期更新的数据库，并限制用于博彩。本页不提供赔率、不下单、也不把市场报价写进模型。</p>
</footer>
</main>
<script type="application/json" id="snapshot">{payload}</script>
</body>
</html>
"""


def _meta_block(document: dict) -> str:
    items = [
        ("信息截止", document["model_as_of"]),
        ("模型版本", document["model_version"]),
        ("参数状态", document["parameter_status"]),
        ("生成时间（UTC）", document["generated_at"]),
    ]
    if document["probabilities_published"]:
        items.extend(
            [
                ("模拟次数 N", str(document["n_simulations"])),
                ("外层 × 内层", f"{document['n_outer']} × {document['n_inner']}"),
                ("随机种子", str(document["random_seed"])),
            ]
        )
    return "<div class='meta'>" + "".join(
        f"<div><span>{_esc(label)}</span>{_esc(value)}</div>" for label, value in items
    ) + "</div>"


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def write_csv(document: dict, path) -> None:
    fields = [
        "球队", "conference", "team_id", "先验净效率", "先验状态",
        "夺冠次数", "N", "模拟频率", "不确定性10", "不确定性90",
        "相对上一份", "变化原因", "种子中位", "种子四分位低", "种子四分位高", "预期路径",
    ]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for team in document["teams"]:
            uncertainty = team.get("uncertainty") or {}
            writer.writerow(
                {
                    "球队": team["zh"],
                    "conference": team["conference"],
                    "team_id": team["team_id"],
                    "先验净效率": team["theta"] if team["theta"] is not None else "待采集",
                    "先验状态": team["prior_status"],
                    "夺冠次数": team["championships"] if team["championships"] is not None else "",
                    "N": team.get("n", ""),
                    "模拟频率": probability_cell(team),
                    "不确定性10": uncertainty.get("p10", ""),
                    "不确定性90": uncertainty.get("p90", ""),
                    "相对上一份": "",
                    "变化原因": team["change_reason"],
                    "种子中位": team.get("seed_median", ""),
                    "种子四分位低": team.get("seed_q1", ""),
                    "种子四分位高": team.get("seed_q3", ""),
                    "预期路径": team.get("path", ""),
                }
            )


_REST_NOTE = (
    "休息只计背靠背：上一自然日打过就扣掉写死的分数，多休息不加分。"
    "中立场（赛程 PDF 里用 vs 标出的场次）主场优势为 0。"
    "季后赛按隔日处理，不再另扣背靠背。"
)
_SERIES_NOTE = (
    "系列赛开始时抽一次正态冲击，七场共用，所以各场胜负不是互相独立的，"
    "也不能把系列赛写成七场独立概率的连乘。附加赛和杯赛单场没有这层冲击。"
)
_INTERVAL_NOTE = (
    "点估计是全部模拟的夺冠频率。不确定性是各外层样本自己的频率的 10% 与 90% 分位，"
    "单独给出，不和点估计加成一个数。官方淘汰才是精确的 0；模拟次数里的 0 只是这 N 次没出现。"
)
