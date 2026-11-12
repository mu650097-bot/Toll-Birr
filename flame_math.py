"""Flame Classics: 3-reel, ONE-row slot with a memoryless "Hot Respin".

Each reel stops on a uniform random position of the same 20-symbol strip; the single payline pays
  three of a kind: cherry x5, bell x20, flame x50, seven x200   (nominal)   and exactly two cherries x1.5.
After the first spin the server draws, independently on EVERY paid spin, a Hot Respin with probability 1/8:
a free second spin at the same stake whose win is added. Because the trigger is memoryless (no hidden or visible
counter), no bet-sizing pattern can raise the player's expected return above the disclosed RTP.

Nominal base RTP = R0 * (1 + 1/8), R0 = exact single-spin RTP over all 20^3 stops. The server scales every payout by
(1 - edge) / BASE_RTP so the long-run RTP is exactly 1 - edge, and the player is shown `effective_table(edge)`.
"""
from itertools import product

STRIP = ["C", "K", "B", "C", "F", "K", "C", "S", "C", "K", "B", "C", "K", "F", "C", "K", "B", "C", "C", "K"]
# C cherry 8, K coal 6, B bell 3, F flame 2, S seven 1  (K = blank "coal": never pays)
N = len(STRIP)
NAMES = {"C": "cherry", "K": "coal", "B": "bell", "F": "flame", "S": "seven"}
PAY3 = {"C": 5.0, "B": 20.0, "F": 50.0, "S": 200.0}
PAY_TWO_CHERRIES = 1.5
HOT_ONE_IN = 8


def line_multiplier(line):
    if line[0] == line[1] == line[2] and line[0] in PAY3:
        return PAY3[line[0]]
    if line.count("C") == 2:
        return PAY_TWO_CHERRIES
    return 0.0


def spin_line(pos):
    return [STRIP[p % N] for p in pos]


def single_spin_rtp():
    return sum(line_multiplier(spin_line(p)) for p in product(range(N), repeat=3)) / N ** 3


def hit_frequency():
    return sum(1 for p in product(range(N), repeat=3) if line_multiplier(spin_line(p)) > 0) / N ** 3


R0 = single_spin_rtp()
BASE_RTP = R0 * (1.0 + 1.0 / HOT_ONE_IN)


def effective_table(edge):
    s = max(0.0, min(1.0, 1.0 - float(edge))) / BASE_RTP
    rows = [{"symbol": "cherry", "kind": "two", "multiplier": round(PAY_TWO_CHERRIES * s, 2)}]
    rows += [{"symbol": NAMES[k], "kind": "three", "multiplier": round(v * s, 2)} for k, v in PAY3.items()]
    return rows


assert len(STRIP) == 20 and STRIP.count("C") == 8 and STRIP.count("K") == 6 and STRIP.count("B") == 3 and STRIP.count("F") == 2 and STRIP.count("S") == 1
