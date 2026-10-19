"""Load the fetched prior, the published schedule, and the adjustment file."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np

from .parameters import BACK_TO_BACK_POINTS, HOME_COURT_POINTS
from .teams import ABBREV_INDEX, TEAMS, conference_indices, cup_groups

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def _read(name: str) -> dict:
    with (DATA / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_inputs(data_dir: Path | None = None):
    base = data_dir or DATA
    priors = json.loads((base / "priors_2025_26.json").read_text(encoding="utf-8"))
    schedule = json.loads((base / "schedule_2026_27.json").read_text(encoding="utf-8"))
    adjustments = json.loads((base / "adjustments.json").read_text(encoding="utf-8"))
    cup = json.loads((base / "cup_groups_2026.json").read_text(encoding="utf-8"))

    by_abbrev = {row["abbrev"]: row for row in priors["teams"]}
    missing = [team.abbrev for team in TEAMS if team.abbrev not in by_abbrev]
    theta = np.full(len(TEAMS), np.nan)
    ortg = np.full(len(TEAMS), np.nan)
    drtg = np.full(len(TEAMS), np.nan)
    prior_wins = np.zeros(len(TEAMS), dtype=np.int16)
    prior_losses = np.zeros(len(TEAMS), dtype=np.int16)
    status = []
    for index, team in enumerate(TEAMS):
        row = by_abbrev.get(team.abbrev)
        if row is None or row.get("ortg") is None or row.get("drtg") is None or row.get("nrtg") is None:
            status.append("待采集")
            continue
        theta[index] = float(row["nrtg"])
        ortg[index] = float(row["ortg"])
        drtg[index] = float(row["drtg"])
        prior_wins[index] = int(row["wins"])
        prior_losses[index] = int(row["losses"])
        status.append("已采集")

    applied = []
    for entry in adjustments.get("entries", []):
        required = ["team_id", "target", "direction", "magnitude", "effective_date", "source", "confidence", "recorded_by"]
        if any(field not in entry or entry[field] in (None, "") for field in required):
            raise ValueError("adjustment entry is missing a required field")
        if str(entry["confidence"]).lower() in {"low", "rumor", "unverified"}:
            continue
        index = next(i for i, team in enumerate(TEAMS) if team.team_id == int(entry["team_id"]))
        if status[index] != "已采集":
            continue
        magnitude = float(entry["magnitude"])
        if magnitude < 0:
            raise ValueError("adjustment magnitude must be non-negative; use direction")
        signed = magnitude if entry["direction"] == "up" else -magnitude
        if entry["direction"] not in {"up", "down"}:
            raise ValueError("adjustment direction must be up or down")
        theta[index] += signed
        applied.append(entry)

    games = schedule["games"]
    home = np.array([ABBREV_INDEX[game["home"]] for game in games], dtype=np.int16)
    away = np.array([ABBREV_INDEX[game["away"]] for game in games], dtype=np.int16)
    neutral = np.array([bool(game["neutral"]) for game in games])
    cup_flag = np.array([bool(game["cup"]) for game in games])
    date_ord = np.array([date.fromisoformat(game["date"]).toordinal() for game in games], dtype=np.int32)

    team_dates = [set() for _ in TEAMS]
    for game, ordinal in zip(games, date_ord):
        team_dates[ABBREV_INDEX[game["home"]]].add(int(ordinal))
        team_dates[ABBREV_INDEX[game["away"]]].add(int(ordinal))

    home_b2b = np.array([(int(ordinal) - 1) in team_dates[int(team)] for ordinal, team in zip(date_ord, home)])
    away_b2b = np.array([(int(ordinal) - 1) in team_dates[int(team)] for ordinal, team in zip(date_ord, away)])
    edge = np.where(neutral, 0.0, HOME_COURT_POINTS).astype(np.float64)
    edge = edge - home_b2b.astype(np.float64) * BACK_TO_BACK_POINTS
    edge = edge + away_b2b.astype(np.float64) * BACK_TO_BACK_POINTS

    meetings = np.zeros((len(TEAMS), len(TEAMS)), dtype=np.int16)
    base_home = np.zeros(len(TEAMS), dtype=np.int16)
    for game in games:
        h = ABBREV_INDEX[game["home"]]
        a = ABBREV_INDEX[game["away"]]
        meetings[h, a] += 1
        meetings[a, h] += 1
        if not game["neutral"]:
            base_home[h] += 1

    _validate(games, cup, missing)

    return {
        "theta": theta,
        "ortg": ortg,
        "drtg": drtg,
        "prior_wins": prior_wins,
        "prior_losses": prior_losses,
        "prior_status": status,
        "missing_priors": missing,
        "adjustments_applied": applied,
        "home": home,
        "away": away,
        "neutral": neutral,
        "cup": cup_flag,
        "edge": edge,
        "date_ord": date_ord,
        "team_dates": team_dates,
        "meetings": meetings,
        "base_home": base_home,
        "groups": cup_groups(),
        "east": conference_indices("East"),
        "west": conference_indices("West"),
        "priors_doc": priors,
        "schedule_doc": schedule,
        "adjustments_doc": adjustments,
        "cup_doc": cup,
        "n_games": len(games),
    }


def _validate(games, cup_doc, missing_priors) -> None:
    if len(games) != 1200:
        raise ValueError(f"expected 1200 published games, found {len(games)}")
    counts = {team.abbrev: 0 for team in TEAMS}
    cup_opponents: dict[str, set[str]] = {team.abbrev: set() for team in TEAMS}
    seen = {team.abbrev: set() for team in TEAMS}
    group_of = {team.abbrev: team.cup_group for team in TEAMS}
    for game in games:
        if game["date"] >= "2026-12-04" and game["date"] <= "2026-12-10":
            raise ValueError(f"published schedule unexpectedly includes {game['date']}")
        for side in ("home", "away"):
            abbrev = game[side]
            if game["date"] in seen[abbrev]:
                raise ValueError(f"{abbrev} plays twice on {game['date']}")
            seen[abbrev].add(game["date"])
            counts[abbrev] += 1
        if game["cup"]:
            cup_opponents[game["home"]].add(game["away"])
            cup_opponents[game["away"]].add(game["home"])
            if group_of[game["home"]] != group_of[game["away"]]:
                raise ValueError("cup game crosses groups")
    if any(value != 80 for value in counts.values()):
        raise ValueError(f"expected 80 published games per team, got {counts}")
    for abbrev, opponents in cup_opponents.items():
        if len(opponents) != 4:
            raise ValueError(f"{abbrev} has {len(opponents)} cup opponents")
        expected = set(cup_doc["groups"][group_of[abbrev]]) - {abbrev}
        if opponents != expected:
            raise ValueError(f"{abbrev} cup opponents {opponents} != {expected}")
    if missing_priors:
        return
