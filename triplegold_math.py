"""Triple Gold: a classic 3-reel, 3-row slot with ONE payline (the middle row).

Every reel is stopped by a uniform random position on the same 20-symbol strip; the visible column is the strip symbol
above / on / below that position. So the top and bottom rows shown to the player are the real neighbours on the reel.
The payline pays for three of a kind, and for exactly two cherries anywhere on the middle row.

The NOMINAL pay table below has an exact base RTP of 1.0 (checked by `base_rtp()` over all 20^3 stops). The server
applies the disclosed house edge by scaling every payout with (1 - edge) (the same scale every cabinet game uses),
so the player is shown and paid `effective_table(edge)`.
"""
from itertools import product

STRIP = ["C", "B", "C", "R", "C", "B", "S", "C", "B", "C", "R", "C", "B", "C", "S", "B", "R", "C", "B", "R"]
N = len(STRIP)
NAMES = {"C": "cherry", "B": "bell", "R": "bar", "S": "seven"}
# nominal multipliers (stake x m) on the middle row
PAY3 = {"C": 4.0, "B": 8.0, "R": 20.0, "S": 80.0}
PAY_TWO_CHERRIES = 1.0
BASE_RTP = 1.0


def grid(pos):
    """3 rows x 3 reels of symbol letters for stop positions pos=(p0,p1,p2)."""
    cols = [[STRIP[(p - 1) % N], STRIP[p % N], STRIP[(p + 1) % N]] for p in pos]
    return [[cols[c][r] for c in range(3)] for r in range(3)]


def line_multiplier(line):
    if line[0] == line[1] == line[2]:
        return PAY3[line[0]]
    if line.count("C") == 2:
        return PAY_TWO_CHERRIES
    return 0.0


def multiplier(pos):
    return line_multiplier(grid(pos)[1])


def base_rtp():
    return sum(multiplier(p) for p in product(range(N), repeat=3)) / N ** 3


def hit_frequency():
    return sum(1 for p in product(range(N), repeat=3) if multiplier(p) > 0) / N ** 3


def effective_table(edge):
    s = max(0.0, min(1.0, 1.0 - float(edge))) / BASE_RTP
    rows = [{"symbol": NAMES[k], "kind": "three", "multiplier": round(v * s, 2)} for k, v in PAY3.items()]
    rows.insert(0, {"symbol": "cherry", "kind": "two", "multiplier": round(PAY_TWO_CHERRIES * s, 2)})
    return rows


assert len(STRIP) == 20 and abs(base_rtp() - BASE_RTP) < 1e-12, base_rtp()
