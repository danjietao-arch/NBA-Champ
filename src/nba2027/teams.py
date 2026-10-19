"""NBA stable team ids and the 2026 Emirates NBA Cup groups.

team_id values are the NBA stats TEAM_ID numbers. They were read from the
nba_api static table, which mirrors those ids:

https://raw.githubusercontent.com/swar/nba_api/master/src/nba_api/stats/library/data.py

The live stats.nba.com league dashboard timed out in this run, so the ids were
not re-downloaded from that endpoint. Cup groups are from NBA.com's Cup 101
explainer (the page writes "Washington Wizard"; the team is the Wizards).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Team:
    team_id: int
    abbrev: str
    zh: str
    en: str
    conference: str  # East or West
    division: str
    cup_group: str


# Sorted by team_id. Simulation index is this order.
TEAMS: tuple[Team, ...] = (
    Team(1610612737, "ATL", "亚特兰大老鹰", "Atlanta Hawks", "East", "Southeast", "EC"),
    Team(1610612738, "BOS", "波士顿凯尔特人", "Boston Celtics", "East", "Atlantic", "EC"),
    Team(1610612739, "CLE", "克利夫兰骑士", "Cleveland Cavaliers", "East", "Central", "EB"),
    Team(1610612740, "NOP", "新奥尔良鹈鹕", "New Orleans Pelicans", "West", "Southwest", "WB"),
    Team(1610612741, "CHI", "芝加哥公牛", "Chicago Bulls", "East", "Central", "EC"),
    Team(1610612742, "DAL", "达拉斯独行侠", "Dallas Mavericks", "West", "Southwest", "WA"),
    Team(1610612743, "DEN", "丹佛掘金", "Denver Nuggets", "West", "Northwest", "WA"),
    Team(1610612744, "GSW", "金州勇士", "Golden State Warriors", "West", "Pacific", "WC"),
    Team(1610612745, "HOU", "休斯顿火箭", "Houston Rockets", "West", "Southwest", "WA"),
    Team(1610612746, "LAC", "洛杉矶快船", "LA Clippers", "West", "Pacific", "WB"),
    Team(1610612747, "LAL", "洛杉矶湖人", "Los Angeles Lakers", "West", "Pacific", "WC"),
    Team(1610612748, "MIA", "迈阿密热火", "Miami Heat", "East", "Southeast", "EB"),
    Team(1610612749, "MIL", "密尔沃基雄鹿", "Milwaukee Bucks", "East", "Central", "EA"),
    Team(1610612750, "MIN", "明尼苏达森林狼", "Minnesota Timberwolves", "West", "Northwest", "WB"),
    Team(1610612751, "BKN", "布鲁克林篮网", "Brooklyn Nets", "East", "Atlantic", "EA"),
    Team(1610612752, "NYK", "纽约尼克斯", "New York Knicks", "East", "Atlantic", "EB"),
    Team(1610612753, "ORL", "奥兰多魔术", "Orlando Magic", "East", "Southeast", "EA"),
    Team(1610612754, "IND", "印第安纳步行者", "Indiana Pacers", "East", "Central", "EB"),
    Team(1610612755, "PHI", "费城76人", "Philadelphia 76ers", "East", "Atlantic", "EB"),
    Team(1610612756, "PHX", "菲尼克斯太阳", "Phoenix Suns", "West", "Pacific", "WA"),
    Team(1610612757, "POR", "波特兰开拓者", "Portland Trail Blazers", "West", "Northwest", "WC"),
    Team(1610612758, "SAC", "萨克拉门托国王", "Sacramento Kings", "West", "Pacific", "WC"),
    Team(1610612759, "SAS", "圣安东尼奥马刺", "San Antonio Spurs", "West", "Southwest", "WC"),
    Team(1610612760, "OKC", "俄克拉荷马城雷霆", "Oklahoma City Thunder", "West", "Northwest", "WB"),
    Team(1610612761, "TOR", "多伦多猛龙", "Toronto Raptors", "East", "Atlantic", "EA"),
    Team(1610612762, "UTA", "犹他爵士", "Utah Jazz", "West", "Northwest", "WA"),
    Team(1610612763, "MEM", "孟菲斯灰熊", "Memphis Grizzlies", "West", "Southwest", "WB"),
    Team(1610612764, "WAS", "华盛顿奇才", "Washington Wizards", "East", "Southeast", "EC"),
    Team(1610612765, "DET", "底特律活塞", "Detroit Pistons", "East", "Central", "EA"),
    Team(1610612766, "CHA", "夏洛特黄蜂", "Charlotte Hornets", "East", "Southeast", "EC"),
)

ABBREV_INDEX = {team.abbrev: i for i, team in enumerate(TEAMS)}


def conference_indices(conference: str) -> list[int]:
    return [i for i, team in enumerate(TEAMS) if team.conference == conference]


def cup_groups() -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {}
    for i, team in enumerate(TEAMS):
        groups.setdefault(team.cup_group, []).append(i)
    return groups
