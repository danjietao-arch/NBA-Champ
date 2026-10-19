"""Chinese static page for one championship snapshot.

The bars, seeds, paths, and market quotes are read from that snapshot.
A missing quote is left blank. It is not drawn as zero.
"""

from __future__ import annotations

import json

from .snapshot import probability_cell


def render_html(document: dict) -> str:
    cards = [_team_card(team) for team in document["teams"]]
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    status = document["parameter_status"]
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>2026—27 NBA 总冠军概率</title>
<style>
:root {{
  --ink: #1c1915;
  --muted: #5c564c;
  --paper: #f4efe6;
  --card: #fffaf3;
  --line: #e4dacb;
  --mark: #8d2d1f;
  --bar: #8d2d1f;
  --band: rgba(141, 45, 31, 0.18);
  --tick: #1f4e79;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font: 16px/1.5 "Source Han Sans SC", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
}}
a {{ color: var(--mark); }}
.site-header {{
  background: #241c16;
  color: #fffaf3;
  padding: 22px 16px 18px;
}}
.site-header .kicker {{ margin: 0 0 6px; letter-spacing: 0.08em; font-size: 0.78rem; color: #eadfce; }}
.site-header h1 {{
  margin: 0 0 12px;
  font-family: "Source Han Serif SC", "Noto Serif SC", "Songti SC", Palatino, serif;
  font-size: clamp(1.6rem, 4vw, 2.4rem);
  font-weight: 600;
  line-height: 1.2;
}}
.banner {{
  display: inline-block;
  margin: 0;
  padding: 6px 10px;
  background: var(--mark);
  color: #fffaf3;
  font-weight: 700;
}}
.wrap {{ max-width: 980px; margin: 0 auto; padding: 20px 16px 56px; }}
.notice, .note {{
  background: var(--card);
  border-left: 4px solid var(--mark);
  padding: 12px 14px;
  margin: 0 0 14px;
}}
.note {{ border-left-color: #8a8175; }}
.meta {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
  margin: 0 0 18px;
}}
.meta div {{ background: var(--card); border: 1px solid var(--line); padding: 8px 10px; }}
.meta span {{ display: block; color: var(--muted); font-size: 0.75rem; }}
.toolbar {{
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  align-items: center;
  margin: 8px 0 12px;
}}
.legend {{ color: var(--muted); font-size: 0.88rem; margin: 0 0 12px; }}
.swatch {{
  display: inline-block;
  width: 1.1em;
  height: 0.7em;
  margin-right: 4px;
  vertical-align: -1px;
  background: var(--bar);
}}
.swatch.band {{ background: var(--band); border: 1px solid var(--bar); }}
.swatch.tick {{ width: 0; border-left: 2px solid var(--tick); background: transparent; }}
.team {{
  background: var(--card);
  border: 1px solid var(--line);
  padding: 12px 12px 10px;
  margin: 0 0 10px;
}}
.team-top {{
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
}}
.team h2 {{ font-size: 1.05rem; margin: 0; font-weight: 650; }}
.team h2 span, .sub {{ display: block; color: var(--muted); font-size: 0.78rem; font-weight: 450; }}
.pct {{ margin: 0; font-variant-numeric: tabular-nums; font-size: 1.25rem; font-weight: 700; white-space: nowrap; }}
.track {{
  position: relative;
  height: 16px;
  margin: 8px 0 6px;
  background: #f0e7da;
  border-radius: 99px;
  overflow: hidden;
}}
.fill {{
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  background: var(--bar);
  border-radius: 99px;
}}
.band {{
  position: absolute;
  top: 0;
  bottom: 0;
  background: var(--band);
}}
.tick {{
  position: absolute;
  top: -2px;
  bottom: -2px;
  width: 2px;
  background: var(--tick);
}}
.path, .why {{ margin: 4px 0; }}
.quote {{
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  margin: 8px 0 0;
}}
.quote div {{ background: #f7f1e7; padding: 6px 8px; min-height: 44px; }}
.quote dt {{ color: var(--muted); font-size: 0.72rem; }}
.quote dd {{ margin: 0; font-variant-numeric: tabular-nums; min-height: 1.2em; }}
.na {{ margin: 6px 0 0; color: var(--muted); font-weight: 700; }}
h2.section {{ font-size: 1.15rem; margin: 28px 0 8px; }}
ul {{ margin: 0 0 12px; padding-left: 1.2em; }}
footer {{ color: var(--muted); margin-top: 28px; }}
code {{ word-break: break-all; }}
@media (max-width: 640px) {{
  .quote {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .pct {{ font-size: 1.1rem; }}
  .team-top {{ align-items: flex-start; }}
}}
@media (min-width: 900px) {{
  .site-header {{ padding-left: max(16px, calc(50vw - 490px)); padding-right: max(16px, calc(50vw - 490px)); }}
}}
</style>
</head>
<body>
<header class="site-header">
<p class="kicker">私人研究 · 赛前快照 · 不是公开网站</p>
<h1>2026—27 NBA 总冠军概率</h1>
<p class="banner">{_esc(status)}</p>
</header>
<main class="wrap">
<div class="notice"><p>{_esc(document["disclaimer"])}</p></div>
<p>目标只是 2027 年 6 月总决赛的胜者。条形是模拟频率，不是实力排名。市场报价只放在旁边对照，不写进模型。</p>
{_note(document.get("probability_note"))}
{_meta(document)}
<p>{_esc(_sum_line(document))}</p>
<div class="toolbar">
<label><input id="valid-only" type="checkbox"> 只看有效报价</label>
</div>
<p class="legend"><span class="swatch"></span>模型概率 <span class="swatch band"></span>不确定性，外层 10%–90% <span class="swatch tick"></span>Polymarket YES 中间价。没有有效报价时不画这根线。</p>
<section id="teams" aria-label="三十队夺冠概率">
{''.join(cards)}
</section>
{_walk_forward(document)}
{_market_intro(document)}
{_unmapped(document)}
<h2 class="section">规则近似</h2>
<ul>{''.join(f'<li>{_esc(item)}</li>' for item in document['approximations'])}</ul>
<h2 class="section">来源</h2>
{_sources(document)}
<footer>
<p>{_esc(document["attribution"])}</p>
<p>{_esc(document["disclaimer"])}</p>
<p>统计署名 <a href="https://www.nba.com/">NBA.com</a>。NBA.com 的使用条款限制把统计做成综合、定期更新的数据库，并限制用于博彩。本页不提供赔率、不下单、也不把市场报价写进模型。</p>
</footer>
</main>
<script>
document.getElementById("valid-only").addEventListener("change", function (event) {{
  document.querySelectorAll(".team").forEach(function (card) {{
    card.hidden = event.target.checked && card.dataset.quote !== "valid";
  }});
}});
</script>
<script type="application/json" id="snapshot">{payload}</script>
</body>
</html>
"""


def _team_card(team: dict) -> str:
    market = team.get("market") or {}
    status = market.get("quote_status") or ""
    quote_flag = "valid" if status == "valid" else "na"
    title = f"{team['conference']} · {team['zh']}"
    if team.get("p_champion") is None:
        body = "<p>待采集</p><div class='track' aria-hidden='true'></div>"
    else:
        width = max(0.0, min(100.0, float(team["p_champion"]) * 100))
        low = float(team["uncertainty"]["p10"]) * 100
        high = float(team["uncertainty"]["p90"]) * 100
        band = ""
        if high > low:
            band = f"<span class='band' style='left:{low:.4f}%;width:{high - low:.4f}%'></span>"
        tick = ""
        if status == "valid" and market.get("mid") is not None:
            left = max(0.0, min(100.0, float(market["mid"]) * 100))
            tick = f"<span class='tick' style='left:{left:.4f}%'></span>"
        label = probability_cell(team)
        seed = ""
        if team.get("seed_median") is not None:
            seed = (
                f"<p class='path'>种子中位 {int(team['seed_median'])}，"
                f"四分位 {int(team['seed_q1'])}–{int(team['seed_q3'])}。</p>"
                f"<p class='path'>{_esc(team.get('path') or '')}</p>"
            )
        uncertainty = f"不确定性 {low:.2f}% – {high:.2f}%"
        body = (
            f"<p class='pct'>{_esc(label)}</p></div>"
            f"<div class='track' role='img' aria-label='{_esc(title)} {_esc(label)}，{_esc(uncertainty)}'>"
            f"{band}<span class='fill' style='width:{width:.4f}%'></span>{tick}</div>"
            f"<p class='why'>{_esc(uncertainty)}。相对上一份：—。{_esc(team.get('change_reason') or '')}</p>"
            f"{seed}"
        )
        # The opening flex row is closed inside body when a probability exists.
        return (
            f"<article class='team' data-quote='{quote_flag}'>"
            f"<div class='team-top'><h2>{_esc(title)}<span>{_esc(team['en'])}</span></h2>"
            f"{body}{_quote_block(market)}</article>"
        )
    return (
        f"<article class='team' data-quote='{quote_flag}'>"
        f"<div class='team-top'><h2>{_esc(title)}<span>{_esc(team['en'])}</span></h2></div>"
        f"{body}{_quote_block(market)}</article>"
    )


def _quote_block(market: dict) -> str:
    valid = market.get("quote_status") == "valid"
    values = {
        "YES 中间价": _market_pct(market.get("mid")) if valid else "",
        "买价": _market_pct(market.get("bid")) if valid else "",
        "卖价": _market_pct(market.get("ask")) if valid else "",
        "差（百分点）": _pp(market.get("delta_pp")) if valid else "",
    }
    cells = "".join(f"<div><dt>{_esc(label)}</dt><dd>{_esc(value)}</dd></div>" for label, value in values.items())
    note = "" if valid else "<p class='na'>N/A</p>"
    return f"<dl class='quote'>{cells}</dl>{note}"


def _market_pct(value) -> str:
    if value is None:
        return ""
    return f"{float(value) * 100:.2f}%"


def _pp(value) -> str:
    if value is None:
        return ""
    return f"{float(value):+.2f}"


def _meta(document: dict) -> str:
    items = [
        ("信息截止", document["model_as_of"]),
        ("模型版本", document["model_version"]),
        ("参数状态", document["parameter_status"]),
        ("生成时间（UTC）", document["generated_at"]),
    ]
    if document.get("probabilities_published"):
        items.extend(
            [
                ("模拟次数 N", str(document["n_simulations"])),
                ("外层 × 内层", f"{document['n_outer']} × {document['n_inner']}"),
                ("随机种子", str(document["random_seed"])),
            ]
        )
    market = document.get("market_comparison") or {}
    if market:
        items.append(("市场比较时间（UTC）", market.get("comparison_as_of") or ""))
        items.append(("有效双边报价", f"{market.get('valid_quotes', 0)} / {market.get('mapped_teams', 0)}"))
    return "<div class='meta'>" + "".join(
        f"<div><span>{_esc(label)}</span>{_esc(value)}</div>" for label, value in items
    ) + "</div>"


def _sum_line(document: dict) -> str:
    if not document.get("probabilities_published"):
        return document.get("withheld_reason") or "待采集"
    return (
        f"30 队四舍五入后的百分比之和为 {document['rounded_percent_sum']:.2f}%。"
        f"未四舍五入的频率之和为 100%：{document['n_simulations']} 次模拟各产生一个冠军。"
    )


def _note(text: str | None) -> str:
    if not text:
        return ""
    return f"<p>{_esc(text)}</p>"


def _walk_forward(document: dict) -> str:
    report = document.get("walk_forward")
    if not report:
        return ""
    lines = [f"<h2 class='section'>三个赛季回看</h2><p>{_esc(report.get('summary') or '')}</p>"]
    if report.get("form"):
        lines.append(f"<p>{_esc(report['form'])}</p>")
    if report.get("note"):
        lines.append(f"<p>{_esc(report['note'])}</p>")
    for problem in report.get("problems") or []:
        lines.append(f"<p>{_esc(problem)}</p>")
    for failure in report.get("failures") or []:
        lines.append(f"<p>没有用上的来源：{_esc(failure)}</p>")
    return "".join(lines)


def _market_intro(document: dict) -> str:
    market = document.get("market_comparison")
    if not market:
        return "<p>这份页面还没有并入订单簿报价。</p>"
    parts = [
        "<h2 class='section'>Polymarket 对照</h2>",
        "<p>只用 <a href='https://polymarket.com/event/nba-2027-champion'>NBA: 2027 Champion</a> 里已经读过问题原文的总冠军 YES。"
        "中间价是订单簿最优买价和卖价的平均，不是 Gamma 上的展示价。单边、过期或没有订单簿时留空，并标 N/A。</p>",
    ]
    if market.get("coverage_incomplete"):
        parts.append(f"<p>{_esc(market.get('coverage_incomplete_reason') or '')} 因此记 coverage_incomplete，不把报价归一化。</p>")
    if market.get("raw_mid_sum") is not None:
        parts.append(f"<p>有效 YES 中间价直接相加是 {float(market['raw_mid_sum']) * 100:.1f}%。这个和不必是 100%。</p>")
    for failure in market.get("clob_failures") or []:
        parts.append(f"<p>订单簿：{_esc(failure)}</p>")
    return "".join(parts)


def _unmapped(document: dict) -> str:
    market = document.get("market_comparison") or {}
    rows = market.get("unmapped") or []
    if not rows:
        return ""
    items = "".join(f"<li>{_esc(row['question'])}：{_esc(row['reason'])}</li>" for row in rows)
    return f"<h2 class='section'>未进入差值的市场</h2><ul>{items}</ul>"


def _sources(document: dict) -> str:
    failed = document["failed_prior_source"]
    return f"""
<div class="note">
<p>优先想用的 NBA 统计接口没有返回，所以 2025—26 攻防效率改用下面这份已打开的表，而不是编一个数。失败的地址：</p>
<p><code>{_esc(failed["url"])}</code></p>
<p>{_esc(failed["error"])}</p>
<p>实际使用：<a href="{_esc(document["prior_source"]["url"])}">{_esc(document["prior_source"]["url"])}</a>，抓取日 {_esc(document["prior_source"]["fetched_on"])}。</p>
<p>赛程：<a href="{_esc(document["schedule_source"]["url"])}">NBA.com 2026—27 赛程 PDF</a>（文件内日期 {_esc(document["schedule_source"]["as_of"])}）。杯赛规则：<a href="{_esc(document["cup_source"]["url"])}">NBA.com Cup 101</a>。</p>
<p>人工调整：没有已核实且写明幅度的条目，主预测不加休赛期修正。假设情景：没有。</p>
</div>
"""


def _esc(value) -> str:
    import html

    return html.escape(str(value), quote=True)
