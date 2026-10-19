"""Hardcoded simulator parameters.

These constants are not estimated from historical game logs. Walk-forward
fitting is out of scope. Every published snapshot must use PARAMETER_STATUS
verbatim.
"""

PARAMETER_STATUS = "参数写死，尚未用历史拟合"

MODEL_VERSION = "preseason-hardcoded-1"

# Information cutoff for the preseason snapshot. The 2026-27 regular season
# starts the next day, so no 2026-27 result is an input.
INFORMATION_AS_OF = "2026-10-19"

# Logistic scale in net-rating points. A 10-point edge is logistic(1) ≈ 73%
# before home court. Round constant, not fit.
LOGISTIC_SCALE = 10.0

# Home-court edge in net-rating points. Round constant, not fit.
HOME_COURT_POINTS = 2.5

# Subtracted from a team that played the previous calendar day.
BACK_TO_BACK_POINTS = 1.5

# One draw per series, added to the higher seed for every game in that series.
SERIES_SHOCK_SD = 3.0

# Preseason uncertainty of net rating, applied once per outer sample.
THETA_SD = 2.5

# Noise on the margin used only for tiebreak point differential.
MARGIN_SD = 11.0

RANDOM_SEED = 20261019
N_OUTER = 40
N_INNER = 250
