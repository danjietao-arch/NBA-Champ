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
    from .page import render_html as render_page

    return render_page(document)


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
